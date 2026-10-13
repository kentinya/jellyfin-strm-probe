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
PLUGIN_FOLDER_NAME = "Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0"
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

    def plugin_status(self) -> str:
        plugins = request_json(self.base_url + "/Plugins", headers=self.headers, timeout=20)
        matches = [plugin for plugin in plugins if plugin.get("Name") == "STRM Probe Optimizer"]
        require(len(matches) == 1, "The STRM Probe Optimizer plugin was not found exactly once.")
        status = str(matches[0].get("Status"))
        require(status.lower() in {"active", "0"}, "The STRM Probe Optimizer plugin is not active.")
        return status

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

    def playback_info(self, item_id: str) -> tuple[int, dict]:
        query = urlencode({"UserId": self.user_id})
        request = Request(self.base_url + f"/Items/{item_id}/PlaybackInfo?{query}", headers=self.headers)
        try:
            with urlopen(request, timeout=75) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, {}


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
        "plugin_event": safe_event(event),
    }


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
    summary: dict[str, object] = {"fixture_restoration": "not needed"}
    try:
        deploy_plugin()
        container = restart_isolated_server()
        api = JellyfinApi()
        require(api.public_info().get("Version") == "12.2.0", "The active isolated Jellyfin version is not 12.2.0.")
        summary["plugin_status"] = api.plugin_status()
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

        retried_failure = call_playback(api, container, item_id, failed_url)
        require(retried_failure["http_status"] >= 400, "The failed URL unexpectedly became playable without recovery.")
        require(retried_failure["probe_calls"] == 1, "The failed URL retry did not execute exactly one matching native probe.")
        summary["failed_url_retry"] = retried_failure

        summary["status"] = "PASS"
        return 0
    finally:
        summary["fixture_restoration"] = restore_fixture_and_sync(api, item_id, container, original)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, URLError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
