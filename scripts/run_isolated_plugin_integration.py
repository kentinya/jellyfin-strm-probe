#!/usr/bin/env python3
"""Exercise the built plugin against the repository's isolated Jellyfin instance."""

from __future__ import annotations

import collections
import hashlib
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = ROOT / "scripts" / "development_environment.py"
PLUGIN_BUILD = ROOT / "src" / "Jellyfin.Plugin.StrmProbeOptimizer" / "bin" / "Release" / "net10.0"
PLUGIN_SOURCE = PLUGIN_BUILD / "Jellyfin.Plugin.StrmProbeOptimizer.dll"
PLUGIN_META = ROOT / "src" / "Jellyfin.Plugin.StrmProbeOptimizer" / "Packaging" / "meta.json"
PLUGIN_METADATA = json.loads(PLUGIN_META.read_text(encoding="utf-8"))
PLUGIN_ID = PLUGIN_METADATA["guid"]
PLUGIN_VERSION = PLUGIN_METADATA["version"]
PLUGIN_FOLDER_NAME = f"Jellyfin.Plugin.StrmProbeOptimizer_{PLUGIN_VERSION}"
FIXTURE = ROOT / "artifacts" / "dev-env" / "strm" / "Environment Fixture.strm"
PLUGIN_LOGGER = "Jellyfin.Plugin.StrmProbeOptimizer.Services.StrmPlaybackOptimizer"
MAX_WAIT_SECONDS = 90


def run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def deploy_plugin() -> None:
    require(PLUGIN_SOURCE.is_file(), "Release plugin assembly is missing; build the pinned solution first.")
    require(PLUGIN_META.is_file(), "Jellyfin plugin meta.json is missing.")
    plugin_root = ROOT / "artifacts" / "dev-env" / "config" / "plugins"
    destination = plugin_root / PLUGIN_FOLDER_NAME
    if destination.exists():
        existing_meta = destination / "meta.json"
        if existing_meta.exists():
            parsed = json.loads(existing_meta.read_text(encoding="utf-8"))
            require(parsed.get("guid") == "b061643e-d17d-4c6e-8ba2-6b57e286bd20", "Refusing to replace an unrelated plugin folder.")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PLUGIN_SOURCE, destination / PLUGIN_SOURCE.name)
    shutil.copy2(PLUGIN_META, destination / "meta.json")


def isolated_container_name() -> str:
    result = run([sys.executable, str(ENVIRONMENT), "status"], timeout=30)
    require(result.returncode == 0, "Could not inspect the repository's isolated Jellyfin environment.")
    matches: list[str] = []
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) >= 4 and columns[3] == "jellyfin":
            matches.append(columns[0])
    require(len(matches) == 1, "Expected exactly one Jellyfin container in the isolated environment.")
    return matches[0]


def isolated_media_container_name() -> str:
    project = "jf-strm-probe-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:10]
    result = run([
        "docker", "ps", "--filter", "label=com.docker.compose.project=" + project,
        "--format", "{{.Names}} {{.Label \"com.docker.compose.service\"}}",
    ], timeout=30)
    require(result.returncode == 0, "Could not inspect the isolated media service.")
    matches = [line.split()[0] for line in result.stdout.splitlines() if line.split()[-1:] == ["media"]]
    require(len(matches) == 1, "Expected exactly one media service in the repository's isolated environment.")
    return matches[0]


def restart_isolated_server() -> str:
    stop = run([sys.executable, str(ENVIRONMENT), "stop"], timeout=120)
    require(stop.returncode == 0, "The isolated Jellyfin stop command failed.")
    start = run([sys.executable, str(ENVIRONMENT), "up"], timeout=120)
    require(start.returncode == 0, "The isolated Jellyfin start command failed.")
    container = isolated_container_name()
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    while time.monotonic() < deadline:
        health = run(["docker", "inspect", "--format", "{{.State.Health.Status}}", container], timeout=15)
        if health.returncode == 0 and health.stdout.strip() == "healthy":
            public_info = request_json("http://127.0.0.1:18096/System/Info/Public", timeout=10)
            require(public_info.get("Version") == "12.2.0", "The isolated server version changed from the pinned 12.2.0 target.")
            return container
        time.sleep(1)
    raise RuntimeError("The isolated Jellyfin container did not become healthy.")


def request_json(url: str, *, headers: dict[str, str] | None = None, data: bytes | None = None, timeout: int = 15) -> dict:
    request = Request(url, headers=headers or {}, data=data, method="POST" if data is not None else "GET")
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


class JellyfinApi:
    def __init__(self) -> None:
        self.credentials_path = ROOT / "artifacts" / "dev-env" / "credentials.local.json"
        require(self.credentials_path.is_file(), "Isolated Jellyfin credentials are unavailable.")
        require(self.credentials_path.stat().st_mode & 0o777 == 0o600, "Isolated Jellyfin credentials must remain mode 0600.")
        self.credentials = json.loads(self.credentials_path.read_text(encoding="utf-8"))
        self.base_url = self.credentials["base_url"].rstrip("/")
        self.identity = 'MediaBrowser Client="STRM Probe Optimizer local validation", Device="local-test", DeviceId="strm-probe-tests", Version="0.1.0"'
        self.user_id = ""
        self.headers: dict[str, str] = {}
        self.login()

    def login(self) -> None:
        request = Request(
            self.base_url + "/Users/AuthenticateByName",
            data=json.dumps({"Username": self.credentials["username"], "Pw": self.credentials["password"]}).encode(),
            headers={"Content-Type": "application/json", "Authorization": self.identity},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:
            auth = json.load(response)
        self.user_id = auth["User"]["Id"]
        self.headers = {"Authorization": f'{self.identity}, Token="{auth["AccessToken"]}"'}

    def public_info(self) -> dict:
        return request_json(self.base_url + "/System/Info/Public", timeout=15)

    def plugin_state(self) -> str:
        plugins = request_json(self.base_url + "/Plugins", headers=self.headers, timeout=20)
        matches = [
            plugin for plugin in plugins
            if str(plugin.get("Id", "")).lower() == PLUGIN_ID.lower()
            or plugin.get("Name") == "STRM Probe Optimizer"
        ]
        require(len(matches) == 1, "The STRM Probe Optimizer plugin was not found exactly once.")
        return str(matches[0].get("Status"))

    def plugin_status(self) -> str:
        status = self.plugin_state()
        require(status.lower() in {"active", "0"}, "The STRM Probe Optimizer plugin is not active.")
        return status

    def plugin_action(self, enabled: bool) -> int:
        action = "Enable" if enabled else "Disable"
        status, _ = self.request_response(
            f"/Plugins/{PLUGIN_ID}/{PLUGIN_VERSION}/{action}",
            method="POST",
        )
        return status

    def request_response(self, path: str, *, method: str = "GET", data: bytes | None = None) -> tuple[int, bytes]:
        request = Request(
            self.base_url + path,
            headers={**self.headers, "Content-Type": "application/json"},
            data=data,
            method=method,
        )
        try:
            with urlopen(request, timeout=30) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    def fixture_item(self) -> dict:
        query = urlencode({"UserId": self.user_id, "Recursive": "true", "Limit": "1000"})
        result = request_json(self.base_url + "/Items?" + query, headers=self.headers, timeout=20)
        matches = [item for item in result.get("Items", []) if item.get("Name") == "Environment Fixture"]
        if not matches:
            request = Request(self.base_url + "/Library/Refresh", headers=self.headers, method="POST")
            with urlopen(request, timeout=20):
                pass
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                time.sleep(2)
                result = request_json(self.base_url + "/Items?" + query, headers=self.headers, timeout=20)
                matches = [item for item in result.get("Items", []) if item.get("Name") == "Environment Fixture"]
                if matches:
                    break
        require(len(matches) == 1, "Expected exactly one scanned Environment Fixture in the isolated libraries.")
        return matches[0]

    def named_library_item(self, name: str) -> dict:
        query = urlencode({"UserId": self.user_id, "Recursive": "true", "Limit": "1000", "Fields": "Path"})
        result = request_json(self.base_url + "/Items?" + query, headers=self.headers, timeout=20)
        matches = [item for item in result.get("Items", []) if item.get("Name") == name]
        require(len(matches) == 1, f"Expected exactly one isolated library item named {name!r}.")
        return matches[0]

    def item_details(self, item_id: str) -> dict:
        query = urlencode({"UserId": self.user_id, "Fields": "MediaStreams,Path"})
        return request_json(self.base_url + f"/Items/{item_id}?" + query, headers=self.headers, timeout=20)

    def force_full_refresh(self, item_id: str) -> tuple[int, bytes]:
        query = urlencode({
            "metadataRefreshMode": "FullRefresh",
            "imageRefreshMode": "None",
            "replaceAllMetadata": "false",
        })
        return self.request_response(f"/Items/{item_id}/Refresh?{query}", method="POST")

    def wait_for_item_refresh(self, item_id: str, previous_etag: str | None, timeout: int = 90) -> tuple[dict, int]:
        started = time.monotonic()
        deadline = started + timeout
        while time.monotonic() < deadline:
            details = self.item_details(item_id)
            refreshed = details.get("Etag")
            if refreshed and refreshed != previous_etag:
                return details, int((time.monotonic() - started) * 1000)
            time.sleep(0.25)
        raise RuntimeError("The isolated Jellyfin item did not persist its queued FullRefresh before the timeout.")

    def playback_info(self, item_id: str) -> tuple[int, dict]:
        query = urlencode({"UserId": self.user_id})
        request = Request(self.base_url + f"/Items/{item_id}/PlaybackInfo?{query}", headers=self.headers)
        try:
            with urlopen(request, timeout=75) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, {}

    def get_video_stream(self, item_id: str) -> tuple[int, bytes]:
        query = urlencode({"static": "true"})
        request = Request(self.base_url + f"/Videos/{item_id}/stream?" + query, headers=self.headers)
        try:
            with urlopen(request, timeout=75) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    def post_playback_info(self, item_id: str, payload: dict) -> tuple[int, dict]:
        query = urlencode({"UserId": self.user_id})
        request = Request(
            self.base_url + f"/Items/{item_id}/PlaybackInfo?{query}",
            data=json.dumps(payload).encode("utf-8"),
            headers={**self.headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=75) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, {}

    def saved_stream_snapshot(self, item_id: str) -> dict:
        query = urlencode({"UserId": self.user_id, "Fields": "MediaStreams"})
        item = request_json(self.base_url + f"/Items/{item_id}?{query}", headers=self.headers, timeout=20)
        streams = item.get("MediaStreams", [])
        serialized = json.dumps(streams, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {
            "stream_types": sorted({stream.get("Type") for stream in streams}),
            "streams_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        }


def parse_manifest(data: bytes) -> tuple[str, str | None, str | None]:
    text = data.decode("utf-8-sig")
    url: str | None = None
    sha1_value: str | None = None
    size_value: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# strm-probe-sha1:"):
            sha1_value = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("# strm-probe-size:"):
            size_value = stripped.split(":", 1)[1].strip()
        elif stripped and not stripped.startswith("#") and url is None:
            url = stripped
    require(url is not None, "The isolated STRM fixture has no URL.")
    return url, sha1_value, size_value


def replace_manifest_url(data: bytes, new_url: str) -> bytes:
    had_bom = data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    lines = text.splitlines(keepends=True)
    replaced = False
    updated: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not replaced and stripped and not stripped.startswith("#"):
            newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            updated.append(new_url + newline)
            replaced = True
        else:
            updated.append(line)
    require(replaced, "The isolated STRM fixture URL could not be replaced.")
    prefix = b"\xef\xbb\xbf" if had_bom else b""
    return prefix + "".join(updated).encode("utf-8")


def write_versioned_fixture(data: bytes, url: str, sha1_value: str, size_value: int) -> bytes:
    had_bom = data.startswith(b"\xef\xbb\xbf")
    lines = data.decode("utf-8-sig").splitlines()
    result: list[str] = []
    has_version = False
    has_sha1 = False
    has_size = False
    replaced_url = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# strm-probe-version:"):
            has_version = True
            result.append("# strm-probe-version:1")
        elif stripped.startswith("# strm-probe-sha1:"):
            if not has_sha1:
                result.append("# strm-probe-sha1:" + sha1_value)
                has_sha1 = True
        elif stripped.startswith("# strm-probe-size:"):
            if not has_size:
                result.append("# strm-probe-size:" + str(size_value))
                has_size = True
        elif stripped and not stripped.startswith("#") and not replaced_url:
            result.append(url)
            replaced_url = True
        else:
            result.append(line)
    require(replaced_url, "The isolated STRM fixture URL could not be replaced.")
    if not has_version:
        result.insert(0, "# strm-probe-version:1")
    if not has_sha1:
        result.insert(1, "# strm-probe-sha1:" + sha1_value)
    if not has_size:
        result.insert(2, "# strm-probe-size:" + str(size_value))
    prefix = b"\xef\xbb\xbf" if had_bom else b""
    return prefix + ("\n".join(result) + "\n").encode("utf-8")


def alternate_fixture_url(url: str) -> str:
    parts = urlsplit(url)
    leaf = parts.path.rsplit("/", 1)[-1]
    if leaf == "fixture.mp4":
        new_leaf = "fixture-alt.mp4"
    elif leaf == "fixture-alt.mp4":
        new_leaf = "fixture.mp4"
    else:
        raise RuntimeError("The isolated media endpoint does not reference a recognized fixture.")
    new_path = parts.path[: len(parts.path) - len(leaf)] + new_leaf
    return urlunsplit((parts.scheme, parts.netloc, new_path, parts.query, parts.fragment))


def missing_fixture_url(url: str) -> str:
    parts = urlsplit(url)
    parent = parts.path.rsplit("/", 1)[0]
    return urlunsplit((parts.scheme, parts.netloc, parent + "/missing-" + uuid.uuid4().hex + ".mp4", "", ""))


def source_result(response: dict, expected_url: str) -> dict:
    expected_hash = hashlib.sha256(expected_url.encode()).hexdigest()
    for source in response.get("MediaSources", []):
        path = source.get("Path") or ""
        if hashlib.sha256(path.encode()).hexdigest() == expected_hash:
            types = {stream.get("Type") for stream in source.get("MediaStreams", [])}
            return {
                "path_matches_manifest": True,
                "path_sha256": expected_hash,
                "has_video": "Video" in types,
                "has_audio": "Audio" in types,
            }
    return {"path_matches_manifest": False, "path_sha256": None, "has_video": False, "has_audio": False}


def plugin_events(container: str, item_id: str) -> list[str]:
    canonical_id = str(uuid.UUID(item_id))
    logs = run(["docker", "logs", "--tail", "1000", container], timeout=20)
    require(logs.returncode == 0, "Could not read isolated Jellyfin container logs.")
    output = logs.stdout + logs.stderr
    return [line for line in output.splitlines() if PLUGIN_LOGGER in line and canonical_id in line]


def event_delta(before: list[str], after: list[str]) -> list[str]:
    remaining = collections.Counter(before)
    delta: list[str] = []
    for line in after:
        if remaining[line] > 0:
            remaining[line] -= 1
        else:
            delta.append(line)
    return delta


def safe_event(line: str | None) -> str | None:
    if line is None:
        return None
    marker = PLUGIN_LOGGER + ": "
    return line.split(marker, 1)[-1]


def probe_calls(event: str | None) -> int | None:
    if event is None:
        return None
    match = re.search(r"(?:plugin probe calls|calls)\s+(\d+)", event)
    return int(match.group(1)) if match else None


def encoder_calls_total(event: str | None) -> int | None:
    if event is None:
        return None
    match = re.search(r"Jellyfin GetMediaInfo calls observed\s+(\d+)", event)
    return int(match.group(1)) if match else None


def media_request_counts(container: str) -> dict[str, int]:
    logs = run(["docker", "logs", "--tail", "5000", container], timeout=20)
    require(logs.returncode == 0, "Could not read the isolated synthetic media service counters.")
    lines = (logs.stdout + logs.stderr).splitlines()
    return {
        "fixture": sum("MEDIA_REQUEST GET fixture.mp4" in line for line in lines),
        "fixture_alt": sum("MEDIA_REQUEST GET fixture-alt.mp4" in line for line in lines),
        "slow_requests_started": sum("SLOW_MEDIA_REQUEST_STARTED " in line for line in lines),
    }


def counter_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {key: after.get(key, 0) - before.get(key, 0) for key in after}


def wait_for_slow_media_request(container: str, request_id: str, timeout: int = 30) -> None:
    marker = "SLOW_MEDIA_REQUEST_STARTED " + request_id
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        logs = run(["docker", "logs", "--tail", "200", container], timeout=15)
        require(logs.returncode == 0, "Could not observe the isolated delayed media request.")
        if marker in logs.stdout + logs.stderr:
            return
        time.sleep(0.1)
    raise RuntimeError("The isolated media service did not reach the delayed probe request.")


def live_tv_delegation_check(api: JellyfinApi, container: str) -> dict[str, object]:
    media_directory = ROOT / "artifacts" / "dev-env" / "media"
    playlist_name = "strm-probe-live-" + uuid.uuid4().hex[:10] + ".m3u"
    playlist_path = media_directory / playlist_name
    channel_name = "STRM Probe Live " + playlist_name.split("-")[-1].split(".")[0]
    tuner_id: str | None = None
    live_stream_id: str | None = None
    result: dict[str, object] = {"status": "FAIL"}
    try:
        with playlist_path.open("xb") as playlist:
            playlist.write(
                (
                    "#EXTM3U\n"
                    f'#EXTINF:-1 tvg-id="{channel_name}" tvg-name="{channel_name}",{channel_name}\n'
                    "http://media:8080/fixture.mp4\n"
                ).encode("utf-8")
            )

        add_status, add_body = api.request_response(
            "/LiveTv/TunerHosts",
            method="POST",
            data=json.dumps({
                "Type": "m3u",
                "Url": "http://media:8080/" + playlist_name,
                "FriendlyName": "Isolated STRM Probe Live TV",
                "TunerCount": 1,
                "AllowStreamSharing": False,
            }).encode("utf-8"),
        )
        require(add_status == 200, "Could not register the temporary isolated M3U tuner.")
        tuner_id = json.loads(add_body).get("Id")
        require(bool(tuner_id), "The isolated M3U tuner response did not contain an identifier.")

        tasks = request_json(api.base_url + "/ScheduledTasks", headers=api.headers, timeout=20)
        refresh_task = next((task for task in tasks if task.get("Name") == "Refresh Guide"), None)
        require(refresh_task is not None, "The isolated Jellyfin instance has no Refresh Guide task.")
        start_status, _ = api.request_response("/ScheduledTasks/Running/" + refresh_task["Id"], method="POST")
        require(start_status == 204, "The isolated Refresh Guide task did not start.")

        query = urlencode({"UserId": api.user_id, "Limit": "100"})
        channel: dict | None = None
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            channel_result = request_json(api.base_url + "/LiveTv/Channels?" + query, headers=api.headers, timeout=20)
            channel = next((item for item in channel_result.get("Items", []) if item.get("Name") == channel_name), None)
            if channel is not None:
                break
            time.sleep(0.5)
        require(channel is not None, "The isolated M3U tuner did not expose its synthetic channel.")

        before_open = plugin_events(container, channel["Id"])
        open_status, open_info = api.post_playback_info(channel["Id"], {
            "UserId": api.user_id,
            "AutoOpenLiveStream": True,
        })
        after_open = plugin_events(container, channel["Id"])
        open_events = [safe_event(line) for line in event_delta(before_open, after_open)]
        require(open_status == 200, "The isolated Live TV PlaybackInfo auto-open request failed.")
        sources = open_info.get("MediaSources", [])
        require(bool(sources), "The isolated Live TV PlaybackInfo response had no media source.")
        live_stream_id = sources[0].get("LiveStreamId")
        require(bool(live_stream_id), "The isolated Live TV PlaybackInfo response did not open a live stream.")

        before_live_info = plugin_events(container, channel["Id"])
        live_status, live_info = api.post_playback_info(channel["Id"], {
            "UserId": api.user_id,
            "LiveStreamId": live_stream_id,
        })
        after_live_info = plugin_events(container, channel["Id"])
        live_events = [safe_event(line) for line in event_delta(before_live_info, after_live_info)]
        live_result = source_result(live_info, "http://media:8080/fixture.mp4") if live_status == 200 else {}
        require(live_status == 200, "Jellyfin did not resolve the opened isolated live stream.")
        require(live_result.get("path_matches_manifest") and live_result.get("has_video"), "The isolated Live TV response did not retain its native media source.")
        require(not open_events and not live_events, "The plugin emitted STRM optimization events for Live TV.")
        result = {
            "status": "PASS",
            "auto_open_http_status": open_status,
            "live_stream_http_status": live_status,
            "returned_expected_source": True,
            "plugin_events": 0,
        }
        return result
    finally:
        if live_stream_id:
            api.request_response("/LiveStreams/Close?" + urlencode({"liveStreamId": live_stream_id}), method="POST")
        if tuner_id:
            api.request_response("/LiveTv/TunerHosts?" + urlencode({"id": tuner_id}), method="DELETE")
        playlist_path.unlink(missing_ok=True)


def call_playback(api: JellyfinApi, container: str, item_id: str, expected_url: str) -> dict:
    before = plugin_events(container, item_id)
    started = time.monotonic()
    status, response = api.playback_info(item_id)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    after = plugin_events(container, item_id)
    events = event_delta(before, after)
    matching = [line for line in events if str(uuid.UUID(item_id)) in line]
    event = matching[-1] if matching else None
    result = source_result(response, expected_url) if status == 200 else {
        "path_matches_manifest": False,
        "path_sha256": None,
        "has_video": False,
        "has_audio": False,
    }
    return {
        "http_status": status,
        "elapsed_ms": elapsed_ms,
        **result,
        "probe_calls": probe_calls(event),
        "encoder_calls_total": encoder_calls_total(event),
        "plugin_event": safe_event(event),
    }


def delegated_playback(api: JellyfinApi, container: str, item_id: str) -> dict[str, object]:
    before = plugin_events(container, item_id)
    status, response = api.playback_info(item_id)
    after = plugin_events(container, item_id)
    sources = response.get("MediaSources", []) if status == 200 else []
    source = sources[0] if sources else {}
    stream_types = {stream.get("Type") for stream in source.get("MediaStreams", [])}
    events = [safe_event(line) for line in event_delta(before, after)]
    return {
        "http_status": status,
        "has_media_source": bool(source),
        "has_video": "Video" in stream_types,
        "plugin_events": events,
        "source_path_is_local": str(source.get("Path", "")).startswith("/media/local/"),
    }


def ordinary_media_delegation_check(api: JellyfinApi, container: str) -> dict[str, object]:
    item = api.named_library_item("fixture")
    result = delegated_playback(api, container, item["Id"])
    require(result["http_status"] == 200 and result["has_media_source"] and result["has_video"], "Ordinary local media did not return its native playback source.")
    require(result["source_path_is_local"], "Ordinary local media did not retain its local path.")
    require(not result["plugin_events"], "The plugin intercepted ordinary local media.")
    return result


def legacy_strm_delegation_check(api: JellyfinApi, container: str) -> dict[str, object]:
    name = "Legacy Probe Control " + uuid.uuid4().hex[:10]
    path = ROOT / "artifacts" / "dev-env" / "strm" / (name + ".strm")
    try:
        with path.open("xb") as fixture:
            fixture.write(b"http://media:8080/fixture.mp4\n")
        status, _ = api.request_response("/Library/Refresh", method="POST")
        require(status == 204, "The isolated library scan for the legacy STRM control did not queue.")
        deadline = time.monotonic() + 60
        item: dict | None = None
        while time.monotonic() < deadline:
            try:
                item = api.named_library_item(name)
                break
            except RuntimeError:
                time.sleep(0.5)
        require(item is not None, "The unversioned STRM control was not scanned into the isolated library.")
        result = delegated_playback(api, container, item["Id"])
        require(result["http_status"] == 200 and result["has_media_source"] and result["has_video"], "The legacy STRM did not return its native playback source.")
        require(not result["plugin_events"], "The plugin intercepted an unversioned legacy STRM.")
        return result
    finally:
        path.unlink(missing_ok=True)


def manifest_race_check(api: JellyfinApi, container: str, item_id: str, current_url: str) -> dict[str, object]:
    request_id = uuid.uuid4().hex
    slow_url = urlunsplit((urlsplit(current_url).scheme, urlsplit(current_url).netloc, f"/slow/{request_id}/fixture.mp4", "", ""))
    FIXTURE.write_bytes(replace_manifest_url(FIXTURE.read_bytes(), slow_url))
    before = plugin_events(container, item_id)
    result_holder: dict[str, object] = {}

    def playback() -> None:
        try:
            status, response = api.playback_info(item_id)
            result_holder.update(status=status, response=response)
        except Exception as error:  # Retain thread failures for the owning assertion.
            result_holder["error"] = type(error).__name__

    worker = threading.Thread(target=playback, name="isolated-manifest-race", daemon=True)
    worker.start()
    wait_for_slow_media_request(isolated_media_container_name(), request_id)
    FIXTURE.write_bytes(replace_manifest_url(FIXTURE.read_bytes(), current_url))
    worker.join(timeout=90)
    require(not worker.is_alive(), "The manifest-race PlaybackInfo request did not finish.")
    after = plugin_events(container, item_id)
    events = [safe_event(line) for line in event_delta(before, after) if str(uuid.UUID(item_id)) in line]
    event = events[-1] if events else None
    status = int(result_holder.get("status", 0))
    require("error" not in result_holder, "The manifest-race PlaybackInfo request failed outside the HTTP response path.")
    require(status >= 400, "PlaybackInfo accepted a STRM manifest that changed during native probing.")
    require(event is not None and "manifest changed during native probe" in event, "The changed-manifest race did not retain the fingerprint with an explicit event.")
    require(probe_calls(event) == 1, "The changed-manifest race did not record exactly one matching native probe call.")
    require("fingerprint committed" not in event, "The changed-manifest race committed its fingerprint.")
    recovered = call_playback(api, container, item_id, current_url)
    ensure_success(recovered, current_url, 1)
    return {
        "http_status": status,
        "probe_calls": probe_calls(event),
        "fingerprint_retained": True,
        "recovery_http_status": recovered["http_status"],
        "recovery_probe_calls": recovered["probe_calls"],
        "recovery_encoder_calls_total": recovered["encoder_calls_total"],
        "event": event,
    }


def false_permission_stream_check(api: JellyfinApi, container: str, item_id: str, current_url: str) -> dict[str, object]:
    changed_url = alternate_fixture_url(current_url)
    FIXTURE.write_bytes(replace_manifest_url(FIXTURE.read_bytes(), changed_url))
    before = plugin_events(container, item_id)
    status, body = api.get_video_stream(item_id)
    after = plugin_events(container, item_id)
    events = [safe_event(line) for line in event_delta(before, after) if str(uuid.UUID(item_id)) in line]
    require(status == 200 and bool(body), "The real Jellyfin streaming request with allowMediaProbe=false did not delegate successfully.")
    require(not any("fingerprint committed" in event for event in events), "A false-permission stream request committed a changed STRM fingerprint.")
    next_playback = call_playback(api, container, item_id, changed_url)
    ensure_success(next_playback, changed_url, 1)
    return {
        "stream_http_status": status,
        "stream_bytes": len(body),
        "plugin_events": events,
        "next_playback_probe_calls": next_playback["probe_calls"],
        "next_playback_encoder_calls_total": next_playback["encoder_calls_total"],
    }


def manual_full_refresh_check(api: JellyfinApi, container: str, media_container: str, item_id: str, current_url: str, previous_total: int | None) -> tuple[dict[str, object], int | None, str]:
    candidate_url = alternate_fixture_url(current_url)
    FIXTURE.write_bytes(replace_manifest_url(FIXTURE.read_bytes(), candidate_url))
    details_before = api.item_details(item_id)
    manual_requests_before = media_request_counts(media_container)
    started = time.monotonic()
    status, _ = api.force_full_refresh(item_id)
    require(status == 204, "Jellyfin rejected the manual FullRefresh request.")
    details_after, refresh_elapsed = api.wait_for_item_refresh(item_id, details_before.get("Etag"), timeout=120)
    manual_requests_after = media_request_counts(media_container)
    manual_request_delta = counter_delta(manual_requests_before, manual_requests_after)

    # A queued manual FullRefresh may save metadata without probing remote STRM content.
    # The changed URL must still go through the plugin's normal native refresh on playback.
    playback = call_playback(api, container, item_id, candidate_url)
    ensure_success(playback, candidate_url, 1)
    observed_total = playback.get("encoder_calls_total")
    inferred_manual_calls = None
    if observed_total is not None and previous_total is not None:
        inferred_manual_calls = observed_total - previous_total - int(playback.get("probe_calls") or 0)
        require(inferred_manual_calls >= 0, "The observed GetMediaInfo counter moved backwards during manual FullRefresh measurement.")
    latest_total = observed_total if observed_total is not None else previous_total
    playback_requests_after = media_request_counts(media_container)
    playback_request_delta = counter_delta(manual_requests_after, playback_requests_after)
    observations: list[dict[str, object]] = [{
        "mode": "manual FullRefresh endpoint",
        "http_status": status,
        "elapsed_ms_until_item_etag_changed": int((time.monotonic() - started) * 1000),
        "etag_poll_ms": refresh_elapsed,
        "item_etag_changed": details_after.get("Etag") != details_before.get("Etag"),
        "synthetic_media_gets_during_manual_refresh": manual_request_delta,
        "inferred_get_media_info_calls_during_manual_refresh": inferred_manual_calls,
        "subsequent_playback_probe_calls": playback["probe_calls"],
        "subsequent_playback_elapsed_ms": playback["elapsed_ms"],
        "synthetic_media_gets_during_subsequent_probe": playback_request_delta,
    }]
    require(playback["probe_calls"] == 1, "The native manual FullRefresh event alone was incorrectly treated as plugin fingerprint confirmation.")

    # Measure repeated native FullRefresh work caused by same-SHA URL changes on PlaybackInfo.
    url = candidate_url
    for run_index in range(2):
        next_url = alternate_fixture_url(url)
        FIXTURE.write_bytes(replace_manifest_url(FIXTURE.read_bytes(), next_url))
        requests_before = media_request_counts(media_container)
        changed_playback = call_playback(api, container, item_id, next_url)
        ensure_success(changed_playback, next_url, 1)
        requests_after = media_request_counts(media_container)
        request_delta = counter_delta(requests_before, requests_after)
        total = changed_playback.get("encoder_calls_total")
        inferred_calls = None
        if total is not None and latest_total is not None:
            inferred_calls = total - latest_total
            require(inferred_calls >= 1, "The repeated native refresh did not increase the observed Jellyfin GetMediaInfo call count.")
        latest_total = total if total is not None else latest_total
        require(sum(request_delta.values()) > 0 or (inferred_calls is not None and inferred_calls > 0), "The repeated native refresh showed no synthetic-media or GetMediaInfo work.")
        observations.append({
            "mode": "PlaybackInfo URL-change native FullRefresh",
            "run": run_index + 1,
            "playback_http_status": changed_playback["http_status"],
            "playback_probe_calls": changed_playback["probe_calls"],
            "playback_elapsed_ms": changed_playback["elapsed_ms"],
            "inferred_get_media_info_calls": inferred_calls,
            "synthetic_media_gets": request_delta,
        })
        url = next_url

    return {"status": "PASS", "runs": observations}, latest_total, url


def ensure_success(result: dict, expected_url: str, expected_calls: int) -> None:
    require(result["http_status"] == 200, "Isolated PlaybackInfo did not return HTTP 200.")
    require(result["path_matches_manifest"], "PlaybackInfo did not return the current STRM address.")
    require(result["has_video"], "PlaybackInfo did not return a primary video stream.")
    require(result["probe_calls"] == expected_calls, f"Expected {expected_calls} matching native probe call(s), observed {result['probe_calls']}.")


def restore_fixture_and_sync(api: JellyfinApi | None, item_id: str | None, container: str | None, original: bytes) -> str | None:
    FIXTURE.write_bytes(original)
    if api is None or item_id is None or container is None:
        return "fixture restored; Jellyfin address sync not available"
    try:
        url, _, _ = parse_manifest(original)
        result = call_playback(api, container, item_id, url)
        require(result["http_status"] == 200 and result["path_matches_manifest"], "Restored fixture URL was not resaved by Jellyfin.")
        return "fixture restored and Jellyfin address synchronized"
    except Exception:
        return "fixture restored; Jellyfin address sync needs a later playback check"


def main() -> int:
    require(FIXTURE.is_file(), "The isolated STRM fixture is missing.")
    original = FIXTURE.read_bytes()
    api: JellyfinApi | None = None
    item_id: str | None = None
    container: str | None = None
    media_container: str | None = None
    plugin_disabled = False
    summary: dict[str, object] = {"fixture_restoration": "not needed"}
    exit_code = 1
    try:
        deploy_plugin()
        container = restart_isolated_server()
        api = JellyfinApi()
        require(api.public_info().get("Version") == "12.2.0", "The active isolated Jellyfin version is not 12.2.0.")
        summary["plugin_status"] = api.plugin_status()
        media_container = isolated_media_container_name()
        item = api.fixture_item()
        item_id = item["Id"]
        summary["fixture_item_id"] = item_id

        media_directory = ROOT / "artifacts" / "dev-env" / "media"
        media_a = (media_directory / "fixture.mp4").read_bytes()
        media_b = (media_directory / "fixture-alt.mp4").read_bytes()
        require(media_a == media_b, "The two local media fixtures must remain byte-identical for the same-SHA URL-change test.")
        current_url, _, _ = parse_manifest(FIXTURE.read_bytes())
        current_sha1 = hashlib.sha1(media_a).hexdigest()
        current_size = str(len(media_a))
        FIXTURE.write_bytes(write_versioned_fixture(FIXTURE.read_bytes(), current_url, current_sha1, int(current_size)))

        # A warm-up lets Jellyfin establish the current URL and stream in its native library.
        warmup = call_playback(api, container, item_id, current_url)
        require(warmup["http_status"] == 200 and warmup["path_matches_manifest"] and warmup["has_video"], "The isolated fixture could not be warmed through Jellyfin PlaybackInfo.")
        summary["warmup"] = warmup

        # Reset the prototype repository so the first measured request exercises first trust.
        container = restart_isolated_server()
        api = JellyfinApi()
        summary["plugin_status_after_restart"] = api.plugin_status()
        item = api.fixture_item()
        item_id = item["Id"]
        current_url, current_sha1, current_size = parse_manifest(FIXTURE.read_bytes())
        require(current_sha1 == hashlib.sha1(media_a).hexdigest() and current_size == str(len(media_a)), "The fixture content fingerprint changed during server restart.")

        first_trust = call_playback(api, container, item_id, current_url)
        ensure_success(first_trust, current_url, 0)
        require(first_trust["plugin_event"] is not None and "FirstTrust" in str(first_trust["plugin_event"]), "The first request did not record a trust handoff.")
        summary["first_trust"] = first_trust

        unchanged_repeat = call_playback(api, container, item_id, current_url)
        ensure_success(unchanged_repeat, current_url, 0)
        summary["unchanged_repeat"] = unchanged_repeat

        changed_url = alternate_fixture_url(current_url)
        FIXTURE.write_bytes(replace_manifest_url(FIXTURE.read_bytes(), changed_url))
        changed_sha1, changed_size = parse_manifest(FIXTURE.read_bytes())[1:]
        require(changed_sha1 == current_sha1 and changed_size == current_size, "The URL-change case did not keep SHA-1 and Size unchanged.")
        changed_address = call_playback(api, container, item_id, changed_url)
        ensure_success(changed_address, changed_url, 1)
        require(changed_address["plugin_event"] is not None and "fingerprint committed" in str(changed_address["plugin_event"]), "The changed URL result was not confirmed and committed.")
        summary["same_sha_url_change"] = changed_address

        unchanged_after_change = call_playback(api, container, item_id, changed_url)
        ensure_success(unchanged_after_change, changed_url, 0)
        summary["unchanged_after_change"] = unchanged_after_change

        # The saved URL and primary stream must survive a real server restart.
        container = restart_isolated_server()
        api = JellyfinApi()
        summary["plugin_status_after_address_restart"] = api.plugin_status()
        item = api.fixture_item()
        item_id = item["Id"]
        persisted_url, _, _ = parse_manifest(FIXTURE.read_bytes())
        restart_first = call_playback(api, container, item_id, persisted_url)
        ensure_success(restart_first, persisted_url, 0)
        summary["address_after_restart"] = restart_first
        streams_before_failure = api.saved_stream_snapshot(item_id)
        require("Video" in streams_before_failure["stream_types"], "The accepted Jellyfin item has no saved primary stream before failure injection.")

        # An unreachable replacement URL must fail closed and leave the accepted baseline retryable.
        failed_url = missing_fixture_url(persisted_url)
        FIXTURE.write_bytes(replace_manifest_url(FIXTURE.read_bytes(), failed_url))
        failed_probe = call_playback(api, container, item_id, failed_url)
        require(failed_probe["http_status"] >= 400, "An unprobeable changed URL did not fail closed in PlaybackInfo.")
        require(
            failed_probe["plugin_event"] is not None
            and ("fingerprint retained" in str(failed_probe["plugin_event"]) or "Native probe not accepted" in str(failed_probe["plugin_event"])),
            "The failed native refresh did not leave a retained-baseline event.",
        )
        require(failed_probe["probe_calls"] == 1, "The failed changed-URL case did not execute exactly one matching native probe.")
        summary["failed_changed_url"] = failed_probe
        streams_after_failure = api.saved_stream_snapshot(item_id)
        require(
            streams_after_failure["streams_sha256"] == streams_before_failure["streams_sha256"],
            "The failed native refresh changed the previously saved media streams.",
        )
        summary["failed_probe_retained_streams"] = {
            "same_as_before_failure": True,
            **streams_after_failure,
        }

        retried_failure = call_playback(api, container, item_id, failed_url)
        require(retried_failure["http_status"] >= 400, "The failed URL unexpectedly became playable without recovery.")
        require(retried_failure["probe_calls"] == 1, "The failed URL retry did not execute exactly one matching native probe.")
        summary["failed_url_retry"] = retried_failure
        streams_after_retry = api.saved_stream_snapshot(item_id)
        require(
            streams_after_retry["streams_sha256"] == streams_before_failure["streams_sha256"],
            "The failed URL retry changed the previously saved media streams.",
        )

        # Return to the last accepted fixture address before exercising independent native paths.
        FIXTURE.write_bytes(replace_manifest_url(FIXTURE.read_bytes(), persisted_url))
        recovered_after_failure = call_playback(api, container, item_id, persisted_url)
        ensure_success(recovered_after_failure, persisted_url, 1)
        summary["recovered_after_failure"] = recovered_after_failure

        summary["ordinary_media_delegation"] = ordinary_media_delegation_check(api, container)
        summary["legacy_strm_delegation"] = legacy_strm_delegation_check(api, container)
        summary["live_tv_delegation"] = live_tv_delegation_check(api, container)

        summary["false_permission_stream"] = false_permission_stream_check(api, container, item_id, persisted_url)
        race_url = alternate_fixture_url(persisted_url)
        summary["manifest_race"] = manifest_race_check(api, container, item_id, race_url)
        full_refresh, _, refreshed_url = manual_full_refresh_check(
            api,
            container,
            media_container,
            item_id,
            race_url,
            summary["manifest_race"].get("recovery_encoder_calls_total"),
        )
        summary["manual_full_refresh"] = full_refresh

        # Disable through Jellyfin, restart the isolated server to remove the proxy registrations,
        # and prove the versioned STRM remains playable through the native path.
        disable_status = api.plugin_action(False)
        require(disable_status == 204, "Jellyfin did not accept the isolated plugin-disable request.")
        plugin_disabled = True
        container = restart_isolated_server()
        api = JellyfinApi()
        disabled_state = api.plugin_state()
        require(disabled_state.lower() not in {"active", "0"}, "The plugin remained active after the isolated disable and restart.")
        disabled_playback = delegated_playback(api, container, item_id)
        require(
            disabled_playback["http_status"] == 200
            and disabled_playback["has_media_source"]
            and disabled_playback["has_video"]
            and not disabled_playback["plugin_events"],
            "The disabled plugin did not leave Jellyfin's native versioned-STRM playback operational.",
        )
        summary["disabled_plugin_delegation"] = {"state": disabled_state, **disabled_playback}
        enable_status = api.plugin_action(True)
        require(enable_status == 204, "Jellyfin did not accept the isolated plugin-enable request.")
        plugin_disabled = False
        container = restart_isolated_server()
        api = JellyfinApi()
        summary["plugin_status_after_enable"] = api.plugin_status()
        item = api.fixture_item()
        item_id = item["Id"]
        enabled_playback = call_playback(api, container, item_id, refreshed_url)
        ensure_success(enabled_playback, refreshed_url, 0)
        summary["enabled_plugin_after_restart"] = enabled_playback

        summary["status"] = "PASS"
        exit_code = 0
    finally:
        if plugin_disabled and api is not None:
            try:
                api.plugin_action(True)
                plugin_disabled = False
                container = restart_isolated_server()
                api = JellyfinApi()
                if item_id is not None:
                    item = api.fixture_item()
                    item_id = item["Id"]
            except Exception as error:
                summary["plugin_reenable_recovery"] = type(error).__name__
        summary["fixture_restoration"] = restore_fixture_and_sync(api, item_id, container, original)
        if exit_code == 0 and (
            plugin_disabled
            or summary["fixture_restoration"] != "fixture restored and Jellyfin address synchronized"
        ):
            summary["status"] = "FAIL"
            summary["error"] = "The plugin, isolated STRM fixture, or Jellyfin address could not be restored and verified."
            exit_code = 1
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, URLError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
