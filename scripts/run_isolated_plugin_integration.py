#!/usr/bin/env python3
"""Exercise the built plugin against the repository's isolated Jellyfin instance."""

from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import shutil
import sqlite3
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
PLUGIN_DATA_DIRECTORY = ROOT / "artifacts" / "dev-env" / "config" / "data" / "plugins" / uuid.UUID(PLUGIN_ID).hex
FINGERPRINT_DATABASE = PLUGIN_DATA_DIRECTORY / "strm-fingerprints.db"
FIXTURE = ROOT / "artifacts" / "dev-env" / "strm" / "Environment Fixture.strm"
CONFIGURATION_FILE = ROOT / "artifacts" / "dev-env" / "config" / "plugins" / "configurations" / "Jellyfin.Plugin.StrmProbeOptimizer.xml"
PLUGIN_LOGGER = "Jellyfin.Plugin.StrmProbeOptimizer.Services.StrmPlaybackOptimizer"
MAX_WAIT_SECONDS = 90

# Well-formed JSON bodies whose values are invalid for the core configuration. Each must be rejected
# without changing the effective configuration or the persisted file.
INVALID_CONFIGURATION_CASES: dict[str, dict[str, object]] = {
    "zero": {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 0, "DetailedLog": False},
    "nine": {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 9, "DetailedLog": False},
    "negative": {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": -1, "DetailedLog": False},
    "non_integer": {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": "two", "DetailedLog": False},
    "wrong_type": {"Enabled": "yes", "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False},
}


def run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def deploy_plugin() -> dict[str, object]:
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
    managed_files: list[str] = []
    for source in sorted(PLUGIN_BUILD.glob("*.dll")):
        shutil.copy2(source, destination / source.name)
        managed_files.append(source.name)
    deps_file = PLUGIN_BUILD / (PLUGIN_SOURCE.stem + ".deps.json")
    require(deps_file.is_file(), "The plugin dependency manifest is missing from the build output.")
    shutil.copy2(deps_file, destination / deps_file.name)
    managed_files.append(deps_file.name)
    deps_data = json.loads(deps_file.read_text(encoding="utf-8"))
    runtime_target = deps_data.get("runtimeTarget", {}).get("name")
    runtime_libraries = deps_data.get("targets", {}).get(runtime_target, {})
    runtime_asset_paths: list[str] = []
    dependency_libraries = deps_data.get("libraries", {})
    for library_name, library in runtime_libraries.items():
        library_metadata = dependency_libraries.get(library_name, {})
        package_path = Path(library_metadata.get("path", "")) if library_metadata.get("type") == "package" else Path()
        assets = list(library.get("runtime", {}))
        assets.extend(
            asset_path
            for asset_path, metadata in library.get("runtimeTargets", {}).items()
            if metadata.get("rid") == "linux-x64" and metadata.get("assetType") == "native"
        )
        for asset_path in assets:
            relative_asset = Path(asset_path)
            require(not relative_asset.is_absolute() and ".." not in relative_asset.parts, "The plugin dependency manifest contains an unsafe runtime asset path.")
            if relative_asset.suffix.lower() != ".dll" and not (relative_asset.suffix.lower() == ".so" and "linux-x64" in relative_asset.parts):
                continue
            source = PLUGIN_BUILD / relative_asset.name
            if not source.is_file():
                continue
            target = destination / package_path / relative_asset
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            runtime_asset_paths.append((package_path / relative_asset).as_posix())

    native_source = PLUGIN_BUILD / "runtimes" / "linux-x64" / "native"
    native_files: list[dict[str, str]] = []
    if native_source.is_dir():
        native_destination = destination / "runtimes" / "linux-x64" / "native"
        native_destination.mkdir(parents=True, exist_ok=True)
        for source in sorted(native_source.iterdir()):
            if source.is_file():
                target = native_destination / source.name
                shutil.copy2(source, target)
                native_files.append({
                    "file": source.name,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                })
    require(any(entry["file"] == "libe_sqlite3.so" for entry in native_files), "The pinned Linux SQLite runtime is missing from plugin output.")
    shutil.copy2(PLUGIN_META, destination / "meta.json")
    return {
        "managed_files": managed_files,
        "runtime_asset_paths": sorted(set(runtime_asset_paths)),
        "native_files": native_files,
    }


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
    observed_version: str | None = None
    last_public_info_error: OSError | json.JSONDecodeError | None = None
    while time.monotonic() < deadline:
        health = run(["docker", "inspect", "--format", "{{.State.Health.Status}}", container], timeout=15)
        if health.returncode == 0 and health.stdout.strip() == "healthy":
            try:
                public_info = request_json("http://127.0.0.1:18096/System/Info/Public", timeout=10)
                observed_version = public_info.get("Version")
                if observed_version == "12.2.0":
                    return container
            except (OSError, json.JSONDecodeError) as error:
                last_public_info_error = error
        time.sleep(1)
    if observed_version is not None:
        raise RuntimeError(f"The isolated server did not report pinned version 12.2.0 before timeout; last observed {observed_version!r}.")
    if last_public_info_error is not None:
        raise RuntimeError(f"The isolated Jellyfin container became healthy but its public API did not settle: {type(last_public_info_error).__name__}.")
    raise RuntimeError("The isolated Jellyfin container did not become healthy.")


def request_json(url: str, *, headers: dict[str, str] | None = None, data: bytes | None = None, timeout: int = 15) -> dict:
    request = Request(url, headers=headers or {}, data=data, method="POST" if data is not None else "GET")
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


class JellyfinApi:
    def __init__(self, credentials_path: Path | None = None) -> None:
        self.credentials_path = credentials_path or (ROOT / "artifacts" / "dev-env" / "credentials.local.json")
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

    def refresh_library(self) -> None:
        status, _ = self.request_response("/Library/Refresh", method="POST")
        require(status == 204, "The isolated library scan did not queue.")

    def wait_for_named_library_item(self, name: str, timeout: int = 60) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                return self.named_library_item(name)
            except RuntimeError:
                time.sleep(0.5)
        raise RuntimeError(f"The isolated library did not scan the temporary item named {name!r}.")

    def wait_for_named_library_item_absent(self, name: str, timeout: int = 60) -> None:
        query = urlencode({"UserId": self.user_id, "Recursive": "true", "Limit": "1000", "Fields": "Path"})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = request_json(self.base_url + "/Items?" + query, headers=self.headers, timeout=20)
            if not any(item.get("Name") == name for item in result.get("Items", [])):
                return
            time.sleep(0.5)
        raise RuntimeError(f"The isolated library still contains the removed temporary item {name!r}.")

    def merge_versions(self, item_ids: list[str]) -> int:
        query = urlencode({"ids": ",".join(item_ids)})
        status, _ = self.request_response("/Videos/MergeVersions?" + query, method="POST")
        return status

    def delete_alternate_sources(self, item_id: str) -> int:
        status, _ = self.request_response(f"/Videos/{item_id}/AlternateSources", method="DELETE")
        return status

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

    def playback_info(self, item_id: str, timeout: int = 75) -> tuple[int, dict]:
        query = urlencode({"UserId": self.user_id})
        request = Request(self.base_url + f"/Items/{item_id}/PlaybackInfo?{query}", headers=self.headers)
        try:
            with urlopen(request, timeout=timeout) as response:
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


def write_versioned_fixture(data: bytes, url: str, sha1_value: str | None, size_value: int) -> bytes:
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
            if not has_sha1 and sha1_value is not None:
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
    if not has_sha1 and sha1_value is not None:
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


def source_for_id(response: dict, item_id: str) -> dict | None:
    expected_id = uuid.UUID(item_id).hex
    return next(
        (source for source in response.get("MediaSources", [])
         if source.get("Id") and uuid.UUID(source["Id"]).hex == expected_id),
        None,
    )


def source_path_hash(source: dict | None) -> str | None:
    path = (source or {}).get("Path")
    return hashlib.sha256(path.encode("utf-8")).hexdigest() if path else None


def fingerprint_row(item_id: str, source_id: str) -> dict[str, object] | None:
    require(FINGERPRINT_DATABASE.is_file(), "The plugin fingerprint database is missing from the isolated Jellyfin DataPath.")
    database_uri = FINGERPRINT_DATABASE.as_posix() + "?mode=ro"
    with sqlite3.connect("file:" + database_uri, uri=True, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT item_id, source_key, url_hash, sha1, file_size FROM strm_fingerprint WHERE item_id = ? AND source_key = ?",
            (uuid.UUID(item_id).hex, uuid.UUID(source_id).hex),
        ).fetchone()
    return dict(row) if row is not None else None


def temporary_versioned_fixture(name: str, url: str, sha1_value: str, size_value: int) -> Path:
    path = ROOT / "artifacts" / "dev-env" / "strm" / (name + ".strm")
    source = FIXTURE.read_bytes()
    with path.open("xb") as fixture:
        fixture.write(write_versioned_fixture(source, url, sha1_value, size_value))
    return path


def expected_url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def unique_query_url(url: str, key: str) -> str:
    parts = urlsplit(url)
    query = urlencode({"strm_probe_case": key})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def local_media_path_for_url(url: str) -> Path | None:
    """Map an isolated synthetic-media URL back to the host file the media service serves."""
    parts = urlsplit(url)
    if parts.netloc != "media:8080":
        return None
    name = parts.path.rsplit("/", 1)[-1]
    if not name:
        return None
    return ROOT / "artifacts" / "dev-env" / "media" / name


def plugin_events_for_ids(container: str, item_ids: list[str]) -> list[str]:
    canonical_ids = [str(uuid.UUID(item_id)) for item_id in item_ids]
    logs = run(["docker", "logs", "--tail", "1000", container], timeout=20)
    require(logs.returncode == 0, "Could not read isolated Jellyfin container logs.")
    output = logs.stdout + logs.stderr
    return [line for line in output.splitlines() if PLUGIN_LOGGER in line and any(item_id in line for item_id in canonical_ids)]


def plugin_events(container: str, item_id: str) -> list[str]:
    return plugin_events_for_ids(container, [item_id])


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


def call_playback(
    api: JellyfinApi,
    container: str,
    item_id: str,
    expected_url: str,
    *,
    event_item_ids: list[str] | None = None,
    selected_media_source_id: str | None = None,
) -> dict:
    event_ids = event_item_ids or [item_id]
    before = plugin_events_for_ids(container, event_ids)
    started = time.monotonic()
    if selected_media_source_id is None:
        status, response = api.playback_info(item_id)
    else:
        status, response = api.post_playback_info(item_id, {
            "UserId": api.user_id,
            "MediaSourceId": selected_media_source_id,
        })
    elapsed_ms = int((time.monotonic() - started) * 1000)
    after = plugin_events_for_ids(container, event_ids)
    events = event_delta(before, after)
    matching = [line for line in events if any(str(uuid.UUID(value)) in line for value in event_ids)]
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
        "plugin_events": [safe_event(line) for line in matching],
        "media_source_ids": [uuid.UUID(source["Id"]).hex for source in response.get("MediaSources", []) if source.get("Id")],
        "media_sources": [
            {
                "id": uuid.UUID(source["Id"]).hex,
                "type": source.get("Type"),
                "path_sha256": source_path_hash(source),
                "stream_types": sorted({stream.get("Type") for stream in source.get("MediaStreams", [])}),
            }
            for source in response.get("MediaSources", [])
            if source.get("Id")
        ],
    }


def delegated_playback(api: JellyfinApi, container: str, item_id: str, expected_url: str | None = None) -> dict[str, object]:
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
        "path_matches_manifest": source_result(response, expected_url).get("path_matches_manifest") if expected_url is not None and status == 200 else None,
        "path_sha256": source_result(response, expected_url).get("path_sha256") if expected_url is not None and status == 200 else None,
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


def source_summary(result: dict, item_id: str) -> dict | None:
    expected_id = uuid.UUID(item_id).hex
    return next((source for source in result.get("media_sources", []) if source.get("id") == expected_id), None)


def source_event(result: dict, item_id: str) -> str | None:
    source_key = uuid.UUID(item_id).hex
    return next((event for event in result.get("plugin_events", []) if f"source {source_key}" in str(event)), None)


def multiversion_and_sqlite_failure_check(
    api: JellyfinApi,
    container: str,
    primary_item_id: str,
    primary_url: str,
    media_sha1: str,
    media_size: int,
    alternate_fixture_path: Path,
) -> tuple[dict[str, object], JellyfinApi, str, str]:
    alternate_name = alternate_fixture_path.stem
    alternate_url = alternate_fixture_url(primary_url)
    with alternate_fixture_path.open("xb") as alternate_fixture:
        alternate_fixture.write(write_versioned_fixture(FIXTURE.read_bytes(), alternate_url, media_sha1, media_size))
    api.refresh_library()
    alternate_item = api.wait_for_named_library_item(alternate_name)
    alternate_item_id = alternate_item["Id"]
    merge_status = api.merge_versions([primary_item_id, alternate_item_id])
    require(merge_status == 204, "Jellyfin did not merge the two isolated STRM videos into native alternate versions.")

    primary_id_hex = uuid.UUID(primary_item_id).hex
    alternate_id_hex = uuid.UUID(alternate_item_id).hex
    initial = call_playback(
        api,
        container,
        primary_item_id,
        primary_url,
        event_item_ids=[primary_item_id, alternate_item_id],
    )
    require(initial["http_status"] == 200 and initial["path_matches_manifest"] and initial["has_video"], "The primary entry did not return its own usable source after the native version merge.")
    require(set(initial["media_source_ids"]) == {primary_id_hex, alternate_id_hex}, "The primary entry did not expose exactly the two natively linked versions.")
    require(initial["media_source_ids"][0] == primary_id_hex, "The original fixture entry was not first in Jellyfin's ordered media-source response.")
    project_candidates = [
        candidate_id
        for candidate_id in (primary_item_id, alternate_item_id)
        if fingerprint_row(candidate_id, primary_item_id) is not None
        and fingerprint_row(candidate_id, alternate_item_id) is not None
    ]
    require(len(project_candidates) == 1, "The two native source keys did not resolve to one canonical project identity in SQLite.")
    canonical_project_id = project_candidates[0]
    canonical_project_hex = uuid.UUID(canonical_project_id).hex
    canonical_initial_url = alternate_url if canonical_project_id == alternate_item_id else primary_url
    secondary_version_id = alternate_item_id if canonical_project_id == primary_item_id else primary_item_id
    secondary_version_url = alternate_url if secondary_version_id == alternate_item_id else primary_url
    primary_source = source_summary(initial, primary_item_id)
    alternate_source = source_summary(initial, alternate_item_id)
    require(primary_source and "Video" in primary_source["stream_types"], "The primary version lost its saved video stream.")
    require(alternate_source and alternate_source["path_sha256"] == expected_url_hash(alternate_url) and "Video" in alternate_source["stream_types"], "The alternate version did not return its own probed address and primary stream.")
    primary_before = fingerprint_row(canonical_project_id, primary_item_id)
    alternate_before = fingerprint_row(canonical_project_id, alternate_item_id)
    require(primary_before and alternate_before, "The two natively linked versions did not receive independent SQLite rows.")
    require(primary_before["url_hash"] == expected_url_hash(primary_url), "The primary version row does not identify the primary STRM URL.")
    require(alternate_before["url_hash"] == expected_url_hash(alternate_url), "The alternate version row does not identify the alternate STRM URL.")
    require(primary_before["item_id"] == canonical_project_hex and alternate_before["item_id"] == canonical_project_hex, "The linked versions did not share the canonical project identity in SQLite.")
    require(primary_before["source_key"] == primary_id_hex and alternate_before["source_key"] == alternate_id_hex, "The linked versions did not retain their distinct native source keys.")
    streams_primary_before = api.saved_stream_snapshot(primary_item_id)
    streams_alternate_before = api.saved_stream_snapshot(alternate_item_id)

    selected = call_playback(
        api,
        container,
        canonical_project_id,
        secondary_version_url,
        event_item_ids=[primary_item_id, alternate_item_id],
        selected_media_source_id=secondary_version_id,
    )
    require(selected["http_status"] == 200 and source_summary(selected, secondary_version_id) is not None, "PlaybackInfo MediaSourceId selection did not retain the requested alternate source.")
    require(source_summary(selected, secondary_version_id)["path_sha256"] == expected_url_hash(secondary_version_url), "PlaybackInfo MediaSourceId selection returned a different source address.")

    direct = call_playback(
        api,
        container,
        secondary_version_id,
        secondary_version_url,
        event_item_ids=[primary_item_id, alternate_item_id],
    )
    require(direct["http_status"] == 200 and direct["path_matches_manifest"] and direct["has_video"], "The direct alternate-version entry did not return its own usable source.")
    require(direct["media_source_ids"] and direct["media_source_ids"][0] == uuid.UUID(secondary_version_id).hex, "The direct alternate entry did not exercise the native alternate-first response order.")

    changed_alternate_url = unique_query_url(alternate_url, "alternate-change-" + uuid.uuid4().hex[:10])
    alternate_fixture_path.write_bytes(write_versioned_fixture(alternate_fixture_path.read_bytes(), changed_alternate_url, media_sha1, media_size))
    changed_project_url = changed_alternate_url if canonical_project_id == alternate_item_id else primary_url
    changed = call_playback(
        api,
        container,
        canonical_project_id,
        changed_project_url,
        event_item_ids=[primary_item_id, alternate_item_id],
    )
    require(changed["http_status"] == 200 and changed["path_matches_manifest"], "Changing one linked STRM version prevented the primary entry from returning.")
    require(changed["media_source_ids"] and changed["media_source_ids"][0] == canonical_project_hex, "The canonical project entry did not place its primary version first.")
    changed_alternate_source = source_summary(changed, alternate_item_id)
    unchanged_primary_source = source_summary(changed, primary_item_id)
    require(changed_alternate_source and changed_alternate_source["path_sha256"] == expected_url_hash(changed_alternate_url), "The changed alternate URL was not returned for its source ID.")
    require(unchanged_primary_source and unchanged_primary_source["path_sha256"] == expected_url_hash(primary_url), "Changing the alternate version rewrote the primary address.")
    alternate_event = source_event(changed, alternate_item_id)
    primary_event = source_event(changed, primary_item_id)
    require(alternate_event is not None and probe_calls(alternate_event) == 1 and "fingerprint committed" in alternate_event, "The URL change did not probe and commit only the alternate source.")
    require(primary_event is not None and probe_calls(primary_event) == 0, "The unchanged primary source was probed while only the alternate URL changed.")
    primary_after = fingerprint_row(canonical_project_id, primary_item_id)
    alternate_after_url_only = fingerprint_row(canonical_project_id, alternate_item_id)
    require(primary_after == primary_before, "Changing the alternate version changed the primary fingerprint row.")
    require(alternate_after_url_only and alternate_after_url_only["url_hash"] == expected_url_hash(changed_alternate_url), "The changed alternate fingerprint was not committed under its stable source identity.")
    require(alternate_after_url_only["sha1"] == alternate_before["sha1"] and alternate_after_url_only["file_size"] == alternate_before["file_size"], "The alternate URL-only change changed its media content fingerprint.")

    no_sha_url = unique_query_url(changed_alternate_url, "alternate-no-sha-" + uuid.uuid4().hex[:10])
    alternate_fixture_path.write_bytes(write_versioned_fixture(alternate_fixture_path.read_bytes(), no_sha_url, None, media_size))
    require(parse_manifest(alternate_fixture_path.read_bytes())[1] is None, "The alternate-version missing-SHA case still contains a SHA-1 marker.")
    no_sha_playback = call_playback(
        api,
        container,
        canonical_project_id,
        no_sha_url if canonical_project_id == alternate_item_id else primary_url,
        event_item_ids=[primary_item_id, alternate_item_id],
    )
    no_sha_alternate_source = source_summary(no_sha_playback, alternate_item_id)
    require(no_sha_playback["http_status"] == 200 and no_sha_alternate_source and no_sha_alternate_source["path_sha256"] == expected_url_hash(no_sha_url), "The alternate version without SHA-1 did not return its current address and source.")
    no_sha_event = source_event(no_sha_playback, alternate_item_id)
    require(no_sha_event is not None and probe_calls(no_sha_event) == 1 and "fingerprint committed" in no_sha_event, "Changing an alternate URL without a comparable SHA-1 did not perform and commit a native probe.")
    alternate_after = fingerprint_row(canonical_project_id, alternate_item_id)
    require(alternate_after and alternate_after["url_hash"] == expected_url_hash(no_sha_url), "The no-SHA alternate URL was not committed under its stable source identity.")
    require(alternate_after["sha1"] is None and alternate_after["file_size"] == media_size, "The accepted alternate source inherited a SHA-1 from another version or lost its valid Size.")
    require(fingerprint_row(canonical_project_id, primary_item_id) == primary_before, "Accepting the no-SHA alternate changed the independent primary fingerprint.")

    streams_primary_after = api.saved_stream_snapshot(primary_item_id)
    streams_alternate_after = api.saved_stream_snapshot(alternate_item_id)
    require(streams_primary_after == streams_primary_before, "Updating the alternate source changed the primary item's saved streams.")
    require("Video" in streams_alternate_after["stream_types"], "The changed alternate source has no saved primary stream.")
    canonical_url_after_alternate_change = no_sha_url if canonical_project_id == alternate_item_id else primary_url

    direct_changed = call_playback(
        api,
        container,
        secondary_version_id,
        no_sha_url if secondary_version_id == alternate_item_id else primary_url,
        event_item_ids=[primary_item_id, alternate_item_id],
    )
    secondary_after_url = no_sha_url if secondary_version_id == alternate_item_id else primary_url
    require(direct_changed["http_status"] == 200 and direct_changed["path_matches_manifest"], "The direct alternate entry lost its updated address.")
    require(direct_changed["media_source_ids"] and direct_changed["media_source_ids"][0] == uuid.UUID(secondary_version_id).hex, "The direct alternate entry no longer places its own source first.")

    container = restart_isolated_server()
    api = JellyfinApi()
    restarted_root_url = canonical_url_after_alternate_change
    restarted = call_playback(
        api,
        container,
        canonical_project_id,
        restarted_root_url,
        event_item_ids=[primary_item_id, alternate_item_id],
    )
    require(restarted["http_status"] == 200 and set(restarted["media_source_ids"]) == {primary_id_hex, alternate_id_hex}, "The linked source set changed after Jellyfin restarted.")
    require(restarted["media_source_ids"][0] == canonical_project_hex, "The canonical project source order changed after Jellyfin restarted.")
    require(source_summary(restarted, canonical_project_id)["path_sha256"] == expected_url_hash(restarted_root_url), "The canonical project's saved address changed after restart.")
    require(source_summary(restarted, alternate_item_id)["path_sha256"] == expected_url_hash(no_sha_url), "The changed alternate address was not restored after restart.")
    for source_id in (primary_item_id, alternate_item_id):
        source_reuse = source_event(restarted, source_id)
        require(source_reuse is not None and probe_calls(source_reuse) == 0, "A persisted version source was re-probed after restart.")
    require(fingerprint_row(canonical_project_id, primary_item_id) == primary_after, "The primary source key changed after Jellyfin restarted.")
    require(fingerprint_row(canonical_project_id, alternate_item_id) == alternate_after, "The alternate source key or row changed after Jellyfin restarted.")
    direct_restarted = call_playback(
        api,
        container,
        secondary_version_id,
        secondary_after_url,
        event_item_ids=[primary_item_id, alternate_item_id],
    )
    require(direct_restarted["http_status"] == 200 and direct_restarted["path_matches_manifest"], "The direct version entry lost its address after restart.")
    require(direct_restarted["media_source_ids"] and direct_restarted["media_source_ids"][0] == uuid.UUID(secondary_version_id).hex, "The direct version ordering changed after restart.")
    direct_restarted_events = [source_event(direct_restarted, source_id) for source_id in (primary_item_id, alternate_item_id)]
    require(all(event is not None and probe_calls(event) == 0 for event in direct_restarted_events), "Direct-version playback re-probed a persisted source after restart.")
    selected_restarted = call_playback(
        api,
        container,
        canonical_project_id,
        secondary_version_url if secondary_version_id == primary_item_id else no_sha_url,
        event_item_ids=[primary_item_id, alternate_item_id],
        selected_media_source_id=secondary_version_id,
    )
    require(selected_restarted["http_status"] == 200 and source_summary(selected_restarted, secondary_version_id) is not None, "MediaSourceId selection failed after restart.")
    selected_restarted_events = [source_event(selected_restarted, source_id) for source_id in (primary_item_id, alternate_item_id)]
    require(all(event is not None and probe_calls(event) == 0 for event in selected_restarted_events), "MediaSourceId selection re-probed a persisted source after restart.")

    database_backup = FINGERPRINT_DATABASE.read_bytes()
    require(not Path(str(FINGERPRINT_DATABASE) + "-wal").exists(), "The isolated fingerprint database still has a WAL sidecar; refusing an unsafe database snapshot.")
    require(not Path(str(FINGERPRINT_DATABASE) + "-journal").exists(), "The isolated fingerprint database still has a journal sidecar; refusing an unsafe database snapshot.")
    trigger_name = "block_fingerprint_update_" + uuid.uuid4().hex[:10]
    failed_write_url = unique_query_url(changed_alternate_url, "sqlite-write-failure-" + uuid.uuid4().hex[:10])
    write_failed: dict[str, object] | None = None
    failure_summary: dict[str, object] = {}
    restored_api = api
    restored_container = container
    try:
        alternate_fixture_path.write_bytes(write_versioned_fixture(alternate_fixture_path.read_bytes(), failed_write_url, media_sha1, media_size))
        with sqlite3.connect(FINGERPRINT_DATABASE, timeout=10) as connection:
            connection.execute(
                f"CREATE TRIGGER {trigger_name} BEFORE UPDATE ON strm_fingerprint "
                f"WHEN OLD.item_id = '{canonical_project_hex}' AND OLD.source_key = '{alternate_id_hex}' "
                "BEGIN SELECT RAISE(ABORT, 'isolated write-failure validation'); END"
            )

        write_failed = call_playback(
            api,
            container,
            canonical_project_id,
            restarted_root_url,
            event_item_ids=[primary_item_id, alternate_item_id],
        )
        require(write_failed["http_status"] == 200 and write_failed["path_matches_manifest"], "A SQLite history write failure made the already persisted Jellyfin source unusable.")
        failure_events = [str(event) for event in write_failed["plugin_events"]]
        require(any("SqliteException" in event and "optimization disabled until restart" in event for event in failure_events), "The SQLite write failure did not disable optimization until restart with a redacted failure category.")
        require(not any("fingerprint committed" in event for event in failure_events), "A failed SQLite transaction was reported as a committed fingerprint.")
        unchanged_after_write_failure = fingerprint_row(canonical_project_id, alternate_item_id)
        require(unchanged_after_write_failure == alternate_after, "The rejected SQLite update changed the trusted alternate baseline.")
        followup_native = call_playback(
            api,
            container,
            canonical_project_id,
            restarted_root_url,
            event_item_ids=[primary_item_id, alternate_item_id],
        )
        require(followup_native["http_status"] == 200 and followup_native["path_matches_manifest"], "Jellyfin native playback did not recover after the plugin latched the SQLite failure.")
        require(not followup_native["plugin_events"], "The plugin continued making fingerprint decisions after the SQLite store was marked unavailable.")
        require(fingerprint_row(canonical_project_id, alternate_item_id) == alternate_after, "Native fallback after a SQLite write failure changed the trusted alternate baseline.")
        failure_summary = {
            "playback_http_status": write_failed["http_status"],
            "native_probe_calls": probe_calls(source_event(write_failed, alternate_item_id)),
            "fingerprint_unchanged": unchanged_after_write_failure,
            "plugin_events": failure_events,
            "native_followup": followup_native,
        }
    finally:
        stop = run([sys.executable, str(ENVIRONMENT), "stop"], timeout=120)
        require(stop.returncode == 0, "The isolated Jellyfin server did not stop before restoring the SQLite database snapshot.")
        FINGERPRINT_DATABASE.write_bytes(database_backup)
        restored_container = restart_isolated_server()
        restored_api = JellyfinApi()

    recovered_after_store_failure = call_playback(
        restored_api,
        restored_container,
        canonical_project_id,
        restarted_root_url,
        event_item_ids=[primary_item_id, alternate_item_id],
    )
    require(
        recovered_after_store_failure["http_status"] == 200
        and recovered_after_store_failure["path_matches_manifest"]
        and probe_calls(source_event(recovered_after_store_failure, alternate_item_id)) == 1,
        "After restoring the real SQLite file and restarting, the new alternate URL was not rechecked.",
    )
    recovered_alternate = fingerprint_row(canonical_project_id, alternate_item_id)
    require(recovered_alternate and recovered_alternate["url_hash"] == expected_url_hash(failed_write_url), "The recovered SQLite store did not commit the alternate URL after restart.")
    require(fingerprint_row(canonical_project_id, primary_item_id) == primary_before, "The SQLite recovery changed the independent primary fingerprint.")

    read_only_url = unique_query_url(failed_write_url, "sqlite-read-only-" + uuid.uuid4().hex[:10])
    read_only_project_url = read_only_url if canonical_project_id == alternate_item_id else primary_url
    alternate_fixture_path.write_bytes(write_versioned_fixture(alternate_fixture_path.read_bytes(), read_only_url, media_sha1, media_size))
    for suffix in ("-wal", "-shm", "-journal"):
        require(not Path(str(FINGERPRINT_DATABASE) + suffix).exists(), "The isolated fingerprint database has a sidecar; refusing read-only failure injection.")

    read_only_flag_set = False
    read_only_failure_summary: dict[str, object] = {}
    read_only_recovery_api = restored_api
    read_only_recovery_container = restored_container
    stop = run([sys.executable, str(ENVIRONMENT), "stop"], timeout=120)
    require(stop.returncode == 0, "The isolated Jellyfin server did not stop before read-only SQLite validation.")
    try:
        immutable = run(["chattr", "+i", str(FINGERPRINT_DATABASE)], timeout=20)
        require(immutable.returncode == 0, "The isolated filesystem could not make the fingerprint database read-only for failure validation.")
        read_only_flag_set = True
        read_only_container = restart_isolated_server()
        read_only_api = JellyfinApi()
        read_only_playback = call_playback(
            read_only_api,
            read_only_container,
            canonical_project_id,
            read_only_project_url,
            event_item_ids=[primary_item_id, alternate_item_id],
        )
        require(read_only_playback["http_status"] == 200 and read_only_playback["path_matches_manifest"], "Native playback did not preserve the changed source address after SQLite became read-only.")
        read_only_alternate = source_summary(read_only_playback, alternate_item_id)
        require(read_only_alternate and read_only_alternate["path_sha256"] == expected_url_hash(read_only_url), "Native fallback did not return the alternate source's current address while SQLite was read-only.")
        read_only_events = [str(event) for event in read_only_playback["plugin_events"]]
        require(
            any("SqliteException" in event and "optimization disabled until restart" in event for event in read_only_events),
            "An immutable SQLite fingerprint file did not disable optimization with a redacted failure category.",
        )
        require(not any("fingerprint committed" in event for event in read_only_events), "The immutable SQLite failure was reported as a committed fingerprint.")
        retained_read_only_row = fingerprint_row(canonical_project_id, alternate_item_id)
        require(retained_read_only_row == recovered_alternate, "Making the SQLite file read-only changed the trusted alternate baseline.")
        read_only_followup = call_playback(
            read_only_api,
            read_only_container,
            canonical_project_id,
            read_only_project_url,
            event_item_ids=[primary_item_id, alternate_item_id],
        )
        require(read_only_followup["http_status"] == 200 and read_only_followup["path_matches_manifest"], "Native playback did not continue after the SQLite failure latch.")
        require(not read_only_followup["plugin_events"], "The plugin continued making fingerprint decisions after the read-only failure latch.")
        require(fingerprint_row(canonical_project_id, alternate_item_id) == recovered_alternate, "Native fallback after the read-only failure changed the trusted baseline.")
        read_only_failure_summary = {
            "playback": read_only_playback,
            "trusted_fingerprint_retained": retained_read_only_row,
            "native_followup": read_only_followup,
        }
    finally:
        stop = run([sys.executable, str(ENVIRONMENT), "stop"], timeout=120)
        clear_status = 0
        if read_only_flag_set:
            clear_immutable = run(["chattr", "-i", str(FINGERPRINT_DATABASE)], timeout=20)
            clear_status = clear_immutable.returncode
        require(stop.returncode == 0, "The isolated Jellyfin server did not stop after read-only SQLite validation.")
        require(clear_status == 0, "The isolated SQLite read-only flag could not be cleared during recovery.")
        read_only_recovery_container = restart_isolated_server()
        read_only_recovery_api = JellyfinApi()

    recovered_after_read_only_failure = call_playback(
        read_only_recovery_api,
        read_only_recovery_container,
        canonical_project_id,
        read_only_project_url,
        event_item_ids=[primary_item_id, alternate_item_id],
    )
    recovered_read_only_alternate = source_summary(recovered_after_read_only_failure, alternate_item_id)
    require(
        recovered_after_read_only_failure["http_status"] == 200
        and recovered_after_read_only_failure["path_matches_manifest"]
        and recovered_read_only_alternate
        and recovered_read_only_alternate["path_sha256"] == expected_url_hash(read_only_url)
        and probe_calls(source_event(recovered_after_read_only_failure, alternate_item_id)) == 1,
        "After clearing the SQLite read-only flag and restarting, the alternate URL was not rechecked.",
    )
    read_only_recovered_row = fingerprint_row(canonical_project_id, alternate_item_id)
    require(read_only_recovered_row and read_only_recovered_row["url_hash"] == expected_url_hash(read_only_url), "The writable SQLite store did not commit the alternate URL after read-only recovery.")
    require(fingerprint_row(canonical_project_id, primary_item_id) == primary_before, "Read-only SQLite recovery changed the independent primary fingerprint.")

    return {
        "merge_http_status": merge_status,
        "canonical_project_item_id": canonical_project_id,
        "fixture_source_id": primary_item_id,
        "alternate_source_id": alternate_item_id,
        "primary_entry_before_change": initial,
        "selected_media_source_id": selected,
        "direct_alternate_entry_before_change": direct,
        "primary_fingerprint_before_change": primary_before,
        "alternate_fingerprint_before_change": alternate_before,
        "alternate_only_url_change": {
            "playback": changed,
            "primary_fingerprint_unchanged": primary_after,
            "alternate_fingerprint_updated": alternate_after_url_only,
            "primary_saved_streams_unchanged": streams_primary_after == streams_primary_before,
            "alternate_saved_video_stream": "Video" in streams_alternate_after["stream_types"],
        },
        "alternate_url_change_without_sha": {
            "playback": no_sha_playback,
            "fingerprint_before": alternate_after_url_only,
            "fingerprint_after": alternate_after,
        },
        "direct_alternate_entry_after_change": direct_changed,
        "primary_and_direct_version_after_restart": {
            "canonical_entry": restarted,
            "direct_secondary_entry": direct_restarted,
        },
        "sqlite_write_failure": failure_summary,
        "sqlite_recovery_after_restart": recovered_after_store_failure,
        "alternate_fingerprint_after_sqlite_recovery": recovered_alternate,
        "primary_identity_after_sqlite_recovery": fingerprint_row(canonical_project_id, primary_item_id),
        "sqlite_read_only_failure": read_only_failure_summary,
        "sqlite_recovery_after_read_only_restart": recovered_after_read_only_failure,
        "alternate_fingerprint_after_read_only_recovery": read_only_recovered_row,
    }, read_only_recovery_api, read_only_recovery_container, alternate_item_id


def same_url_content_and_size_change_check(
    api: JellyfinApi,
    container: str,
    media_container: str,
    item_id: str,
    current_url: str,
    current_sha1: str,
    current_size: int,
    media_bytes: bytes,
) -> dict[str, object]:
    """Exercise same-URL content replacement, non-comparable SHA-1 size changes and zero-probe replay."""
    media_path = local_media_path_for_url(current_url)
    require(media_path is not None and media_path.is_file(), "The same-URL change case does not reference a served local media file.")
    original_media = media_path.read_bytes()
    require(original_media == media_bytes, "The served media file changed before the same-URL content replacement test.")
    baseline_before = fingerprint_row(item_id, item_id)
    require(
        baseline_before is not None
        and baseline_before["url_hash"] == expected_url_hash(current_url)
        and baseline_before["sha1"] == current_sha1
        and baseline_before["file_size"] == current_size,
        "The same-URL change case did not start from the expected accepted baseline.",
    )
    summary: dict[str, object] = {}
    try:
        # 1) Same URL, real local media replacement with a changed effective SHA-1 and Size.
        changed_media = original_media + b"\n# strm-probe same-url content change\n"
        changed_sha1 = hashlib.sha1(changed_media).hexdigest()
        changed_size = len(changed_media)
        require(changed_sha1 != current_sha1 and changed_size != current_size, "The same-URL replacement did not change the content identity.")
        media_path.write_bytes(changed_media)
        FIXTURE.write_bytes(write_versioned_fixture(FIXTURE.read_bytes(), current_url, changed_sha1, changed_size))
        media_before = media_request_counts(media_container)
        streams_before = api.saved_stream_snapshot(item_id)
        content_change = call_playback(api, container, item_id, current_url)
        media_delta = counter_delta(media_before, media_request_counts(media_container))
        ensure_success(content_change, current_url, 1)
        require("fingerprint committed" in str(content_change["plugin_event"]), "The same-URL content change did not commit a fingerprint.")
        streams_after = api.saved_stream_snapshot(item_id)
        require("Video" in streams_after["stream_types"], "The same-URL content change did not leave a saved primary stream.")
        content_row = fingerprint_row(item_id, item_id)
        require(
            content_row is not None
            and content_row["url_hash"] == expected_url_hash(current_url)
            and content_row["sha1"] == changed_sha1
            and content_row["file_size"] == changed_size,
            "The same-URL content change did not persist the new SHA-1 and Size under the unchanged URL identity.",
        )
        require(media_delta.get("fixture", 0) + media_delta.get("fixture_alt", 0) >= 1, "The same-URL content change did not actually read the replaced local media.")
        summary["same_url_content_replacement"] = {
            "playback": content_change,
            "media_request_delta": media_delta,
            "saved_streams_before": streams_before,
            "saved_streams_after": streams_after,
            "fingerprint": content_row,
        }

        # 2) Same URL, no comparable SHA-1, valid Size change must probe. First commit a no-SHA baseline.
        media_path.write_bytes(original_media)
        no_sha_size = changed_size + 7
        FIXTURE.write_bytes(write_versioned_fixture(FIXTURE.read_bytes(), current_url, None, no_sha_size))
        no_sha_baseline = call_playback(api, container, item_id, current_url)
        ensure_success(no_sha_baseline, current_url, 1)
        require("fingerprint committed" in str(no_sha_baseline["plugin_event"]), "The no-SHA same-URL size change did not commit.")
        no_sha_row = fingerprint_row(item_id, item_id)
        require(no_sha_row is not None and no_sha_row["sha1"] is None and no_sha_row["file_size"] == no_sha_size, "The no-SHA baseline was not stored with an empty SHA-1 and the new Size.")

        noncomparable_size = no_sha_size + 5
        FIXTURE.write_bytes(write_versioned_fixture(FIXTURE.read_bytes(), current_url, None, noncomparable_size))
        noncomparable = call_playback(api, container, item_id, current_url)
        ensure_success(noncomparable, current_url, 1)
        require("fingerprint committed" in str(noncomparable["plugin_event"]), "A non-comparable SHA-1 with a different valid Size did not probe and commit.")
        noncomparable_row = fingerprint_row(item_id, item_id)
        require(noncomparable_row is not None and noncomparable_row["sha1"] is None and noncomparable_row["file_size"] == noncomparable_size, "The non-comparable size change did not persist its Size.")
        summary["same_url_noncomparable_size_change"] = {
            "baseline_commit": no_sha_baseline,
            "fingerprint": noncomparable_row,
            "playback": noncomparable,
        }

        # 3) Same URL, no comparable SHA-1, same valid Size must skip without a probe.
        same_size_repeat = call_playback(api, container, item_id, current_url)
        ensure_success(same_size_repeat, current_url, 0)
        summary["same_url_noncomparable_size_unchanged"] = same_size_repeat

        # 4) Re-establish the original accepted baseline at the same URL for the remaining flow.
        FIXTURE.write_bytes(write_versioned_fixture(FIXTURE.read_bytes(), current_url, current_sha1, current_size))
        media_path.write_bytes(original_media)
        reestablished = call_playback(api, container, item_id, current_url)
        ensure_success(reestablished, current_url, 1)
        require("fingerprint committed" in str(reestablished["plugin_event"]), "Re-establishing the original baseline did not commit.")
        require(fingerprint_row(item_id, item_id) == baseline_before, "Re-establishing the original baseline did not restore the accepted fingerprint.")
        summary["baseline_reestablished"] = reestablished
    finally:
        media_path.write_bytes(original_media)
    return summary


def replay_and_mtime_zero_probe_check(
    api: JellyfinApi,
    container: str,
    item_id: str,
    current_url: str,
    current_sha1: str,
    current_size: int,
) -> dict[str, object]:
    """Prove mtime-only changes, identical rewrites and delete/replay do not trigger a probe."""
    original = FIXTURE.read_bytes()
    baseline = fingerprint_row(item_id, item_id)
    require(baseline is not None, "The replay/mtime case has no accepted baseline.")
    try:
        os.utime(FIXTURE, (time.time() + 3600, time.time() + 3600))
        mtime_only = call_playback(api, container, item_id, current_url)
        ensure_success(mtime_only, current_url, 0)

        FIXTURE.write_bytes(original)
        identical_rewrite = call_playback(api, container, item_id, current_url)
        ensure_success(identical_rewrite, current_url, 0)

        FIXTURE.unlink()
        FIXTURE.write_bytes(original)
        replayed = call_playback(api, container, item_id, current_url)
        ensure_success(replayed, current_url, 0)

        require(fingerprint_row(item_id, item_id) == baseline, "A replay or mtime-only change altered the accepted fingerprint.")
        require(parse_manifest(FIXTURE.read_bytes())[1] == current_sha1, "The replay case changed the manifest SHA-1.")
        return {
            "mtime_only": mtime_only,
            "identical_rewrite": identical_rewrite,
            "delete_and_replay": replayed,
            "fingerprint_unchanged": baseline,
            "expected_sha1": current_sha1,
            "expected_size": current_size,
        }
    finally:
        FIXTURE.write_bytes(original)


def configuration_api_check(api: JellyfinApi, container: str, item_id: str, current_url: str) -> dict[str, object]:
    """Exercise the core configuration through Jellyfin's existing plugin configuration channel."""
    path = f"/Plugins/{PLUGIN_ID}/Configuration"
    defaults_status, defaults_body = api.request_response(path)
    require(defaults_status == 200, "Jellyfin did not return the plugin configuration.")
    defaults = json.loads(defaults_body)
    require(
        defaults.get("Enabled") is True
        and defaults.get("PlaybackAutoCheck") is True
        and defaults.get("MaxConcurrentProbes") == 2
        and defaults.get("DetailedLog") is False,
        f"The plugin configuration defaults are not Enabled=true, PlaybackAutoCheck=true, MaxConcurrentProbes=2, DetailedLog=false: {defaults}.",
    )

    rejected: dict[str, object] = {}
    for name, payload in INVALID_CONFIGURATION_CASES.items():
        file_before = CONFIGURATION_FILE.read_bytes()
        status, _ = api.request_response(path, method="POST", data=json.dumps(payload).encode("utf-8"))
        require(status >= 400, f"Jellyfin accepted the invalid configuration case {name!r}.")
        _, body = api.request_response(path)
        current = json.loads(body)
        require(
            current == defaults,
            f"The rejected configuration case {name!r} changed the effective configuration to {current}.",
        )
        require(
            CONFIGURATION_FILE.read_bytes() == file_before,
            f"The rejected configuration case {name!r} changed the persisted configuration file.",
        )
        rejected[name] = status

    # Baseline reuse event with DetailedLog=false: the concise line must not include the encoder-call detail.
    baseline_playback = call_playback(api, container, item_id, current_url)
    require(baseline_playback["http_status"] == 200, "A playback request before enabling DetailedLog failed.")
    baseline_events = [str(event) for event in baseline_playback["plugin_events"]]
    require(
        baseline_events and not any("Jellyfin GetMediaInfo calls observed" in event for event in baseline_events),
        f"DetailedLog=false unexpectedly emitted the detailed diagnostic: {baseline_events}.",
    )

    # A valid save with DetailedLog=true must take effect on the next check request and must not hot-apply
    # the concurrency change before restart.
    saved_status, _ = api.request_response(
        path,
        method="POST",
        data=b'{"Enabled":true,"PlaybackAutoCheck":true,"MaxConcurrentProbes":8,"DetailedLog":true}',
    )
    require(saved_status == 204, "Jellyfin did not accept a valid plugin configuration update.")
    _, saved_body = api.request_response(path)
    saved = json.loads(saved_body)
    require(
        saved.get("MaxConcurrentProbes") == 8 and saved.get("DetailedLog") is True,
        f"The saved plugin configuration was not read back: {saved}.",
    )

    # DetailedLog takes effect on the next check request without a restart.
    detailed_playback = call_playback(api, container, item_id, current_url)
    require(detailed_playback["http_status"] == 200, "A playback request after enabling DetailedLog failed.")
    require(
        any("Jellyfin GetMediaInfo calls observed" in str(event) for event in detailed_playback["plugin_events"]),
        f"DetailedLog=true did not produce the detailed next-request log: {detailed_playback['plugin_events']}.",
    )

    # Enabled=false must take effect on the next check request without a restart and delegate natively.
    disabled_status, _ = api.request_response(
        path,
        method="POST",
        data=b'{"Enabled":false,"PlaybackAutoCheck":true,"MaxConcurrentProbes":8,"DetailedLog":true}',
    )
    require(disabled_status == 204, "Jellyfin did not accept the Enabled=false configuration.")
    disabled_playback = delegated_playback(api, container, item_id, current_url)
    require(
        disabled_playback["http_status"] == 200 and disabled_playback["has_media_source"] and not disabled_playback["plugin_events"],
        f"Enabled=false did not delegate the next check request to Jellyfin: {disabled_playback}.",
    )

    # A concurrency change only applies after a restart; the saved file must retain the new value.
    container = restart_isolated_server()
    api = JellyfinApi()
    _, restarted_body = api.request_response(path)
    restarted = json.loads(restarted_body)
    require(
        restarted.get("MaxConcurrentProbes") == 8 and restarted.get("Enabled") is False,
        f"The plugin configuration did not survive restart: {restarted}.",
    )

    restore_status, _ = api.request_response(
        path,
        method="POST",
        data=b'{"Enabled":true,"PlaybackAutoCheck":true,"MaxConcurrentProbes":2,"DetailedLog":false}',
    )
    require(restore_status == 204, "Jellyfin did not accept the restored plugin configuration.")
    _, restored_body = api.request_response(path)
    require(json.loads(restored_body) == defaults, "The plugin configuration was not restored to its defaults.")

    return {
        "defaults": defaults,
        "rejected_cases": rejected,
        "saved": saved,
        "detailed_next_request": True,
        "disabled_next_request_delegated": True,
        "read_back_after_restart": restarted,
        "restored": json.loads(restored_body),
        "restart_container": container,
    }


def same_source_sharing_check(
    api: JellyfinApi,
    container: str,
    media_container: str,
    item_id: str,
    current_url: str,
) -> dict[str, object]:
    """Two concurrent playback requests for the same source must share one actually running probe."""
    request_id = uuid.uuid4().hex
    parts = urlsplit(current_url)
    slow_url = urlunsplit((parts.scheme, parts.netloc, f"/slow/{request_id}/fixture.mp4", "", ""))
    FIXTURE.write_bytes(replace_manifest_url(FIXTURE.read_bytes(), slow_url))
    before = plugin_events(container, item_id)
    results: dict[str, object] = {}

    def playback(key: str) -> None:
        try:
            status, response = api.playback_info(item_id)
            results[key] = (status, response)
        except Exception as error:  # Retain thread failures for the owning assertion.
            results[key] = ("error", type(error).__name__)

    leader = threading.Thread(target=playback, args=("leader",), name="isolated-share-leader", daemon=True)
    leader.start()
    wait_for_slow_media_request(media_container, request_id)
    follower = threading.Thread(target=playback, args=("follower",), name="isolated-share-follower", daemon=True)
    follower.start()
    leader.join(timeout=120)
    follower.join(timeout=120)
    require(not leader.is_alive() and not follower.is_alive(), "The concurrent same-source playback requests did not finish.")
    after = plugin_events(container, item_id)
    events = [safe_event(line) for line in event_delta(before, after) if str(uuid.UUID(item_id)) in line]
    started = [event for event in events if "probe started" in str(event)]
    committed = [event for event in events if "fingerprint committed" in str(event)]
    require("error" not in {results.get("leader", (None,))[0], results.get("follower", (None,))[0]}, "A concurrent same-source playback request failed outside the HTTP response path.")
    leader_status, leader_response = results["leader"]
    follower_status, follower_response = results["follower"]
    require(leader_status == 200 and follower_status == 200, f"Concurrent same-source PlaybackInfo did not return HTTP 200: {leader_status}, {follower_status}.")
    leader_source = source_result(leader_response, slow_url)
    follower_source = source_result(follower_response, slow_url)
    require(leader_source["path_matches_manifest"] and leader_source["has_video"], "The leading request did not return the current address and primary stream.")
    require(follower_source["path_matches_manifest"] and follower_source["has_video"], "The joining request did not return the current address and primary stream.")
    require(len(started) == 1, f"The concurrent same-source requests started {len(started)} native probes instead of exactly one.")
    require(len(committed) == 1, f"The concurrent same-source requests committed {len(committed)} fingerprints instead of exactly one.")

    followup = call_playback(api, container, item_id, slow_url)
    ensure_success(followup, slow_url, 0)

    # Restore the caller's manifest URL so the remaining checks keep operating on the same fixture version.
    FIXTURE.write_bytes(replace_manifest_url(FIXTURE.read_bytes(), current_url))
    restored = call_playback(api, container, item_id, current_url)
    ensure_success(restored, current_url, 1)
    return {
        "leader_http_status": leader_status,
        "follower_http_status": follower_status,
        "probes_started": len(started),
        "fingerprints_committed": len(committed),
        "followup_probe_calls": followup["probe_calls"],
        "restored_probe_calls": restored["probe_calls"],
        "events": events,
    }


def _concurrent_slow_probes(
    api: JellyfinApi,
    media_container: str,
    item_ids: list[str],
    slow_ids: list[str],
) -> tuple[list[float | None], dict[int, object]]:
    """Fire one playback request per item concurrently and record when each slow media request actually starts."""
    results: dict[int, object] = {}

    def playback(index: int, item_id: str) -> None:
        try:
            status, _ = api.playback_info(item_id)
            results[index] = status
        except Exception as error:  # Retain thread failures for the owning assertion.
            results[index] = f"error:{type(error).__name__}"

    threads = [
        threading.Thread(target=playback, args=(index, item_id), name=f"isolated-concurrency-{index}", daemon=True)
        for index, item_id in enumerate(item_ids)
    ]
    started = time.monotonic()
    for thread in threads:
        thread.start()
    marker_times: list[float | None] = [None] * len(slow_ids)
    deadline = started + 90
    while time.monotonic() < deadline and any(marker is None for marker in marker_times):
        logs = run(["docker", "logs", "--tail", "600", media_container], timeout=20)
        output = logs.stdout + logs.stderr
        for index, slow_id in enumerate(slow_ids):
            if marker_times[index] is None and ("SLOW_MEDIA_REQUEST_STARTED " + slow_id) in output:
                marker_times[index] = time.monotonic() - started
        time.sleep(0.05)
    for thread in threads:
        thread.join(timeout=120)
    require(all(not thread.is_alive() for thread in threads), "The concurrent different-source playback requests did not finish.")
    return marker_times, results


def concurrency_limit_check(
    api: JellyfinApi,
    container: str,
    media_container: str,
    media_sha1: str,
    media_size: int,
) -> tuple[dict[str, object], JellyfinApi, str]:
    """Prove the global plugin probe limit with real slow sources: default 2 overlaps, configured 1 serializes."""
    config_path = f"/Plugins/{PLUGIN_ID}/Configuration"
    nonce = uuid.uuid4().hex[:8]
    names = [f"Concurrency A {nonce}", f"Concurrency B {nonce}", f"Concurrency C {nonce}"]
    paths: list[Path] = []
    slow_ids: dict[str, str] = {}
    result: dict[str, object] = {}
    try:
        for name in names:
            slow_id = uuid.uuid4().hex
            slow_ids[name] = slow_id
            paths.append(temporary_versioned_fixture(name, f"http://media:8080/slow/{slow_id}/fixture.mp4", media_sha1, media_size))
        api.refresh_library()
        item_ids = [api.wait_for_named_library_item(name)["Id"] for name in names]

        # Default limit 2: with three independent changed sources, at most two probes may execute at once
        # and the third must wait for a freed permit.
        default_before = plugin_events_for_ids(container, item_ids)
        default_markers, default_results = _concurrent_slow_probes(api, media_container, item_ids, [slow_ids[name] for name in names])
        default_after = plugin_events_for_ids(container, item_ids)
        default_starts = [safe_event(line) for line in event_delta(default_before, default_after) if "probe started" in line]
        require(all(status == 200 for status in default_results.values()), f"The default-limit concurrent playback requests failed: {default_results}.")
        require(all(marker is not None for marker in default_markers), "The default-limit concurrent probes did not all reach the slow media request.")
        default_overlap = sum(1 for marker in default_markers if marker is not None and marker < 1.0)  # type: ignore[operator]
        default_max = max(default_markers)  # type: ignore[type-var]
        require(default_overlap == 2, f"Exactly two of three sources must overlap under the default limit of 2; observed {default_overlap}.")
        require(default_max >= 2.5, f"The third source did not wait for a freed permit under the default limit of 2 (last start {default_max:.2f}s).")
        require(len(default_starts) == 3, f"The default-limit run did not start exactly three probes: {default_starts}.")

        # Save a concurrency change to 1 but do not restart. The running pool was captured at startup with 2
        # permits, so the saved value must NOT hot-apply: the next concurrent run must still overlap two probes.
        not_hot_status, _ = api.request_response(
            config_path,
            method="POST",
            data=b'{"Enabled":true,"PlaybackAutoCheck":true,"MaxConcurrentProbes":1,"DetailedLog":false}',
        )
        require(not_hot_status == 204, "Jellyfin did not accept the saved concurrency-1 configuration.")
        for name, path in zip(names, paths):
            slow_id = uuid.uuid4().hex
            slow_ids[name] = slow_id
            path.write_bytes(write_versioned_fixture(path.read_bytes(), f"http://media:8080/slow/{slow_id}/fixture.mp4", media_sha1, media_size))
        not_hot_before = plugin_events_for_ids(container, item_ids)
        not_hot_markers, not_hot_results = _concurrent_slow_probes(api, media_container, item_ids, [slow_ids[name] for name in names])
        not_hot_after = plugin_events_for_ids(container, item_ids)
        not_hot_starts = [safe_event(line) for line in event_delta(not_hot_before, not_hot_after) if "probe started" in line]
        require(all(status == 200 for status in not_hot_results.values()), f"The pre-restart concurrency playback requests failed: {not_hot_results}.")
        require(all(marker is not None for marker in not_hot_markers), "The pre-restart concurrent probes did not all reach the slow media request.")
        not_hot_overlap = sum(1 for marker in not_hot_markers if marker is not None and marker < 1.0)  # type: ignore[operator]
        require(not_hot_overlap == 2, f"A saved concurrency change was hot-applied before restart; overlap was {not_hot_overlap} instead of 2.")

        # Configured limit 1: after a real restart every source must wait for the previous one to finish.
        for name, path in zip(names, paths):
            slow_id = uuid.uuid4().hex
            slow_ids[name] = slow_id
            path.write_bytes(write_versioned_fixture(path.read_bytes(), f"http://media:8080/slow/{slow_id}/fixture.mp4", media_sha1, media_size))
        configured_status, _ = api.request_response(
            config_path,
            method="POST",
            data=b'{"Enabled":true,"PlaybackAutoCheck":true,"MaxConcurrentProbes":1,"DetailedLog":false}',
        )
        require(configured_status == 204, "Jellyfin did not accept the concurrency-1 configuration.")
        container = restart_isolated_server()
        api = JellyfinApi()
        item_ids = [api.wait_for_named_library_item(name)["Id"] for name in names]
        limited_before = plugin_events_for_ids(container, item_ids)
        limited_markers, limited_results = _concurrent_slow_probes(api, media_container, item_ids, [slow_ids[name] for name in names])
        limited_after = plugin_events_for_ids(container, item_ids)
        limited_starts = [safe_event(line) for line in event_delta(limited_before, limited_after) if "probe started" in line]
        require(all(status == 200 for status in limited_results.values()), f"The concurrency-1 concurrent playback requests failed: {limited_results}.")
        require(all(marker is not None for marker in limited_markers), "The concurrency-1 concurrent probes did not all reach the slow media request.")
        ordered = sorted(marker for marker in limited_markers if marker is not None)  # type: ignore[type-var]
        limited_gaps = [round(ordered[index + 1] - ordered[index], 3) for index in range(len(ordered) - 1)]
        require(all(gap >= 2.5 for gap in limited_gaps), f"A source started before the previous finished under the configured limit of 1 (start gaps {limited_gaps}).")
        require(len(limited_starts) == 3, f"The concurrency-1 run did not start exactly three probes in total: {limited_starts}.")
        result = {
            "default_limit_2": {
                "start_gaps_seconds": [round(marker, 3) for marker in default_markers if marker is not None],
                "max_concurrent": default_overlap,
                "probe_starts": len(default_starts),
                "http_statuses": default_results,
            },
            "configured_limit_1": {
                "start_gaps_seconds": limited_gaps,
                "probe_starts": len(limited_starts),
                "http_statuses": limited_results,
            },
            "saved_before_restart_still_limit_2": {
                "overlap": not_hot_overlap,
                "probe_starts": len(not_hot_starts),
                "http_statuses": not_hot_results,
            },
        }

        restore_status, _ = api.request_response(
            config_path,
            method="POST",
            data=b'{"Enabled":true,"PlaybackAutoCheck":true,"MaxConcurrentProbes":2,"DetailedLog":false}',
        )
        require(restore_status == 204, "Jellyfin did not accept the restored default concurrency.")
        container = restart_isolated_server()
        api = JellyfinApi()
        return result, api, container
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
        if paths:
            try:
                api.refresh_library()
                for name in names:
                    api.wait_for_named_library_item_absent(name)
            except Exception:  # Cleanup failures are surfaced through the fixture restoration summary.
                pass


def independent_native_refresh_check(
    api: JellyfinApi,
    container: str,
    media_container: str,
    item_id: str,
    current_url: str,
    media_sha1: str,
    media_size: int,
) -> tuple[dict[str, object], JellyfinApi, str]:
    """Prove a native manual FullRefresh is not gated by the plugin's saturated probe pool."""
    config_path = f"/Plugins/{PLUGIN_ID}/Configuration"
    nonce = uuid.uuid4().hex[:8]
    name = f"Independent Slow {nonce}"
    slow_id = uuid.uuid4().hex
    path = temporary_versioned_fixture(name, f"http://media:8080/slow/{slow_id}/fixture.mp4", media_sha1, media_size)
    try:
        api.refresh_library()
        slow_item_id = api.wait_for_named_library_item(name)["Id"]
        limited_status, _ = api.request_response(
            config_path,
            method="POST",
            data=b'{"Enabled":true,"PlaybackAutoCheck":true,"MaxConcurrentProbes":1,"DetailedLog":false}',
        )
        require(limited_status == 204, "Jellyfin did not accept the concurrency-1 configuration for the independence check.")
        container = restart_isolated_server()
        api = JellyfinApi()
        slow_item_id = api.wait_for_named_library_item(name)["Id"]

        result_holder: dict[str, object] = {}

        def slow_playback() -> None:
            try:
                status, _ = api.playback_info(slow_item_id, timeout=120)
                result_holder["slow_status"] = status
            except Exception as error:  # Retain thread failures for the owning assertion.
                result_holder["slow_error"] = type(error).__name__

        worker = threading.Thread(target=slow_playback, name="isolated-independent-slow", daemon=True)
        worker.start()
        wait_for_slow_media_request(media_container, slow_id)

        # The plugin pool is now saturated by the slow plugin probe. An independent native FullRefresh of a
        # different item must still complete without waiting for the plugin permit.
        details_before = api.item_details(item_id)
        started = time.monotonic()
        refresh_status, _ = api.force_full_refresh(item_id)
        require(refresh_status == 204, "Jellyfin rejected the independent manual FullRefresh request.")
        api.wait_for_item_refresh(item_id, details_before.get("Etag"), timeout=30)
        elapsed = time.monotonic() - started

        worker.join(timeout=120)
        require(not worker.is_alive(), "The saturated slow plugin probe did not finish.")
        require("slow_error" not in result_holder, "The saturated slow plugin probe failed outside the HTTP path.")
        require(elapsed < 2.5, f"The independent native FullRefresh waited for the plugin pool permit (elapsed {elapsed:.2f}s).")
        result = {
            "status": "PASS",
            "plugin_pool_limit": 1,
            "native_refresh_elapsed_ms": int(elapsed * 1000),
            "slow_plugin_probe_status": result_holder.get("slow_status"),
            "native_refresh_not_blocked": True,
        }
    finally:
        path.unlink(missing_ok=True)
        try:
            api.refresh_library()
            api.wait_for_named_library_item_absent(name)
        except Exception:
            pass
        restore_status, _ = api.request_response(
            config_path,
            method="POST",
            data=b'{"Enabled":true,"PlaybackAutoCheck":true,"MaxConcurrentProbes":2,"DetailedLog":false}',
        )
        if restore_status == 204:
            container = restart_isolated_server()
            api = JellyfinApi()
    return result, api, container


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
    first_trust_path: Path | None = None
    no_stream_path: Path | None = None
    alternate_version_path: Path | None = None
    alternate_version_id: str | None = None
    linked_primary_id: str | None = None
    temporary_media_paths: list[Path] = []
    summary: dict[str, object] = {"fixture_restoration": "not needed"}
    exit_code = 1
    try:
        summary["deployment"] = deploy_plugin()
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

        # Create a fresh project, let Jellyfin save its stream with the plugin disabled, then verify the first active request trusts it.
        first_trust_name = "First Trust Control " + uuid.uuid4().hex[:10]
        first_trust_path = temporary_versioned_fixture(first_trust_name, current_url, current_sha1, len(media_a))
        api.refresh_library()
        first_trust_item = api.wait_for_named_library_item(first_trust_name)
        first_trust_item_id = first_trust_item["Id"]
        container = restart_isolated_server()
        api = JellyfinApi()
        first_trust_disable = api.plugin_action(False)
        require(first_trust_disable == 204, "Jellyfin did not accept the isolated first-trust plugin-disable request.")
        plugin_disabled = True
        container = restart_isolated_server()
        api = JellyfinApi()
        disabled_first_trust = delegated_playback(api, container, first_trust_item_id, current_url)
        first_trust_native_streams = api.saved_stream_snapshot(first_trust_item_id)
        require(
            disabled_first_trust["http_status"] == 200
            and disabled_first_trust["path_matches_manifest"]
            and disabled_first_trust["has_video"]
            and not disabled_first_trust["plugin_events"]
            and "Video" in first_trust_native_streams["stream_types"],
            "Native playback did not save the fresh item's matching primary stream while the plugin was disabled.",
        )
        first_trust_enable = api.plugin_action(True)
        require(first_trust_enable == 204, "Jellyfin did not accept the isolated first-trust plugin-enable request.")
        plugin_disabled = False
        container = restart_isolated_server()
        api = JellyfinApi()
        summary["plugin_status_after_restart"] = api.plugin_status()
        first_trust = call_playback(api, container, first_trust_item_id, current_url)
        ensure_success(first_trust, current_url, 0)
        require(first_trust["plugin_event"] is not None and "FirstTrust" in str(first_trust["plugin_event"]), "The fresh native-saved item was not accepted through FirstTrust.")
        summary["first_trust"] = {
            **first_trust,
            "native_saved_primary_before_enable": True,
            "native_url_matched_manifest": disabled_first_trust["path_matches_manifest"],
        }
        first_trust_repeat = call_playback(api, container, first_trust_item_id, current_url)
        ensure_success(first_trust_repeat, current_url, 0)
        require("FirstTrust" not in str(first_trust_repeat["plugin_event"]), "FirstTrust repeated after the fresh item's fingerprint had been persisted.")
        summary["first_trust_repeat"] = first_trust_repeat

        no_stream_name = "Missing Primary Stream Control " + uuid.uuid4().hex[:10]
        no_stream_url = missing_fixture_url(current_url)
        no_stream_path = temporary_versioned_fixture(no_stream_name, no_stream_url, current_sha1, len(media_a))
        api.refresh_library()
        no_stream_item = api.wait_for_named_library_item(no_stream_name)
        no_stream_id = no_stream_item["Id"]
        missing_primary = call_playback(api, container, no_stream_id, no_stream_url)
        require(missing_primary["http_status"] >= 400, "A STRM with no saved primary stream unexpectedly succeeded against a missing media URL.")
        require(missing_primary["probe_calls"] == 1, "A STRM without a primary stream did not reach one native probe attempt.")
        require(fingerprint_row(no_stream_id, no_stream_id) is None, "A failed first probe created a trusted SQLite fingerprint without a saved primary stream.")
        summary["first_play_without_primary_stream"] = missing_primary

        # The main fixture's history now survives restart and must be reused without a new trust handoff.
        api = JellyfinApi()
        item = api.fixture_item()
        item_id = item["Id"]
        warmup = call_playback(api, container, item_id, current_url)
        require(
            warmup["http_status"] == 200
            and warmup["path_matches_manifest"]
            and warmup["has_video"]
            and warmup["probe_calls"] in {0, 1},
            "The isolated fixture could not establish a valid saved native source and fingerprint.",
        )
        summary["warmup"] = warmup
        container = restart_isolated_server()
        api = JellyfinApi()
        summary["plugin_status_after_restart"] = api.plugin_status()
        item = api.fixture_item()
        item_id = item["Id"]
        current_url, current_sha1, current_size = parse_manifest(FIXTURE.read_bytes())
        require(current_sha1 == hashlib.sha1(media_a).hexdigest() and current_size == str(len(media_a)), "The fixture content fingerprint changed during server restart.")
        restart_first = call_playback(api, container, item_id, current_url)
        ensure_success(restart_first, current_url, 0)
        require("FirstTrust" not in str(restart_first["plugin_event"]), "The persisted main-fixture fingerprint was discarded on restart.")
        summary["fingerprint_reused_after_restart"] = restart_first

        unchanged_repeat = call_playback(api, container, item_id, current_url)
        ensure_success(unchanged_repeat, current_url, 0)
        summary["unchanged_repeat"] = unchanged_repeat

        summary["same_source_sharing"] = same_source_sharing_check(api, container, media_container, item_id, current_url)

        baseline_with_sha = fingerprint_row(item_id, item_id)
        require(baseline_with_sha and baseline_with_sha["sha1"] == current_sha1, "The accepted baseline is missing its initial media SHA-1.")
        FIXTURE.write_bytes(write_versioned_fixture(FIXTURE.read_bytes(), current_url, None, len(media_a)))
        require(parse_manifest(FIXTURE.read_bytes())[1] is None, "The temporary missing-SHA case still contains a SHA-1 marker.")
        temporarily_missing_sha = call_playback(api, container, item_id, current_url)
        ensure_success(temporarily_missing_sha, current_url, 0)
        retained_while_sha_missing = fingerprint_row(item_id, item_id)
        require(retained_while_sha_missing == baseline_with_sha, "A temporary missing SHA-1 overwrote the valid historical content identity.")

        FIXTURE.write_bytes(write_versioned_fixture(FIXTURE.read_bytes(), current_url, current_sha1, len(media_a)))
        restored_sha = call_playback(api, container, item_id, current_url)
        ensure_success(restored_sha, current_url, 0)
        require(fingerprint_row(item_id, item_id) == baseline_with_sha, "Restoring the same SHA-1 changed the trusted baseline.")
        summary["temporary_missing_sha_preserves_history"] = {
            "missing_sha_playback": temporarily_missing_sha,
            "restored_sha_playback": restored_sha,
            "fingerprint_before": baseline_with_sha,
            "fingerprint_while_missing": retained_while_sha_missing,
        }

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

        summary["same_url_content_and_size_changes"] = same_url_content_and_size_change_check(
            api,
            container,
            media_container,
            item_id,
            changed_url,
            current_sha1,
            len(media_a),
            media_a,
        )
        summary["replay_and_mtime_zero_probe"] = replay_and_mtime_zero_probe_check(
            api,
            container,
            item_id,
            changed_url,
            current_sha1,
            len(media_a),
        )

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
            and ("fingerprint retained" in str(failed_probe["plugin_event"]) or "not accepted" in str(failed_probe["plugin_event"])),
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

        retained_fingerprint = fingerprint_row(item_id, item_id)
        require(
            retained_fingerprint is not None
            and retained_fingerprint["url_hash"] == expected_url_hash(persisted_url),
            "The failed changed URL overwrote the accepted SQLite fingerprint before restart.",
        )
        summary["failed_url_fingerprint_before_restart"] = retained_fingerprint

        # Keep the rejected URL on disk across restart; prove the old baseline survives before repairing the failed target.
        container = restart_isolated_server()
        api = JellyfinApi()
        summary["plugin_status_after_failed_url_restart"] = api.plugin_status()
        item = api.fixture_item()
        item_id = item["Id"]
        failed_after_restart = call_playback(api, container, item_id, failed_url)
        require(failed_after_restart["http_status"] >= 400, "The failed URL was trusted after Jellyfin restarted.")
        require(failed_after_restart["probe_calls"] == 1, "The failed URL did not execute one native retry after Jellyfin restarted.")
        retained_after_restart = fingerprint_row(item_id, item_id)
        require(retained_after_restart == retained_fingerprint, "The failed URL changed the persisted SQLite baseline across restart.")
        summary["failed_url_after_restart"] = {
            **failed_after_restart,
            "old_fingerprint_retained": retained_after_restart,
        }

        # Repair the same failed local target while keeping the rejected Manifest/URL, and prove the same rejected version
        # is retried, probed and committed rather than recovered by changing to another URL.
        failed_media_path = local_media_path_for_url(failed_url)
        require(failed_media_path is not None, "The failed URL does not map to a repairable local media target.")
        require(not failed_media_path.exists(), "The failed URL unexpectedly already has a served media file.")
        failed_media_path.write_bytes(media_a)
        temporary_media_paths.append(failed_media_path)
        same_failed_manifest = FIXTURE.read_bytes()
        same_url_retry = call_playback(api, container, item_id, failed_url)
        ensure_success(same_url_retry, failed_url, 1)
        require("fingerprint committed" in str(same_url_retry["plugin_event"]), "The repaired same failed URL was not probed and committed.")
        same_url_fingerprint = fingerprint_row(item_id, item_id)
        require(
            same_url_fingerprint is not None
            and same_url_fingerprint["url_hash"] == expected_url_hash(failed_url)
            and same_url_fingerprint["url_hash"] != retained_fingerprint["url_hash"],
            "The same rejected version was not accepted under its own URL identity after local repair.",
        )
        require(FIXTURE.read_bytes() == same_failed_manifest, "The same-URL repair changed the rejected Manifest instead of repairing its local target.")
        summary["same_failed_url_repaired"] = {
            "playback": same_url_retry,
            "fingerprint": same_url_fingerprint,
            "manifest_unchanged": True,
        }

        recovered_url = unique_query_url(persisted_url, "recovery-" + uuid.uuid4().hex[:12])
        FIXTURE.write_bytes(write_versioned_fixture(FIXTURE.read_bytes(), recovered_url, current_sha1, len(media_a)))
        recovered_after_failure = call_playback(api, container, item_id, recovered_url)
        ensure_success(recovered_after_failure, recovered_url, 1)
        require(
            recovered_after_failure["plugin_event"] is not None
            and "fingerprint committed" in str(recovered_after_failure["plugin_event"]),
            "A repaired, new URL was not probed and committed after the persisted failure.",
        )
        recovered_fingerprint = fingerprint_row(item_id, item_id)
        require(
            recovered_fingerprint is not None
            and recovered_fingerprint["url_hash"] == expected_url_hash(recovered_url)
            and recovered_fingerprint["url_hash"] != retained_fingerprint["url_hash"],
            "The repaired URL did not replace the retained fingerprint with its new accepted identity.",
        )
        persisted_url = recovered_url
        summary["recovered_after_failure"] = recovered_after_failure
        summary["recovered_fingerprint"] = recovered_fingerprint

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

        primary_for_versions, _, _ = parse_manifest(FIXTURE.read_bytes())
        require(primary_for_versions == refreshed_url, "The main STRM fixture changed unexpectedly before the native multi-version test.")
        alternate_version_path = ROOT / "artifacts" / "dev-env" / "strm" / (
            "Alternate Version Control " + uuid.uuid4().hex[:10] + ".strm"
        )
        linked_primary_id = item_id
        multiversion_summary, api, container, alternate_version_id = multiversion_and_sqlite_failure_check(
            api,
            container,
            item_id,
            primary_for_versions,
            current_sha1,
            len(media_a),
            alternate_version_path,
        )
        summary["native_multiversion_and_sqlite_recovery"] = multiversion_summary

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

        summary["global_concurrency_limit"], api, container = concurrency_limit_check(
            api,
            container,
            media_container,
            current_sha1,
            len(media_a),
        )

        summary["independent_native_refresh"], api, container = independent_native_refresh_check(
            api,
            container,
            media_container,
            item_id,
            refreshed_url,
            current_sha1,
            len(media_a),
        )

        summary["core_configuration_api"] = configuration_api_check(api, container, item_id, refreshed_url)
        api = JellyfinApi()
        container = isolated_container_name()
        summary["plugin_status_after_configuration"] = api.plugin_status()

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
        temporary_cleanup_ok = True
        try:
            if api is not None and container is not None:
                api = JellyfinApi()
                if linked_primary_id is not None:
                    unlink_status = api.delete_alternate_sources(linked_primary_id)
                    require(unlink_status == 204, "The isolated multi-version relationship could not be removed during cleanup.")
                removed_names: list[str] = []
                for temporary_path in (alternate_version_path, first_trust_path, no_stream_path):
                    if temporary_path is not None:
                        removed_names.append(temporary_path.stem)
                        temporary_path.unlink(missing_ok=True)
                removed_media = 0
                for media_path in temporary_media_paths:
                    media_path.unlink(missing_ok=True)
                    removed_media += 1
                if removed_names:
                    api.refresh_library()
                    for name in removed_names:
                        api.wait_for_named_library_item_absent(name)
                summary["temporary_fixture_cleanup"] = {
                    "status": "PASS",
                    "alternate_versions_unlinked": linked_primary_id is not None,
                    "temporary_strm_files_removed": len(removed_names),
                    "temporary_media_files_removed": removed_media,
                    "library_items_absent": True,
                }
            else:
                for temporary_path in (alternate_version_path, first_trust_path, no_stream_path):
                    if temporary_path is not None:
                        temporary_path.unlink(missing_ok=True)
                for media_path in temporary_media_paths:
                    media_path.unlink(missing_ok=True)
                summary["temporary_fixture_cleanup"] = {"status": "PARTIAL", "reason": "Jellyfin API was not available to verify the temporary library items."}
                temporary_cleanup_ok = False
        except Exception as error:
            summary["temporary_fixture_cleanup"] = {"status": "FAIL", "error": type(error).__name__}
            temporary_cleanup_ok = False
        summary["fixture_restoration"] = restore_fixture_and_sync(api, item_id, container, original)
        if exit_code == 0 and (
            plugin_disabled
            or not temporary_cleanup_ok
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
