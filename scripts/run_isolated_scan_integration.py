#!/usr/bin/env python3
"""Acceptance for the full native library scan overlapping playback and batch probes.

This tool consumes the single-version plugin ZIP under test and installs it into the
dedicated package-acceptance instance (``scripts/package_environment.py``); it never calls
the development deployment helper and never mounts the source tree. It drives the real
native full library scan task (key ``RefreshLibrary``) and the plugin batch task (key
``StrmProbeOptimizerBatchCheck``) against isolated libraries and synthetic media.

The scenarios:
  all       overlap + stop + recovery in one session, with failures preserved
  overlap   a real native full scan whose Running interval intersects an actually started
            batch probe and an actually started playback probe on a different source, plus
            finite add/delete/move/URL/content changes, URL re-change during a probe,
            multi-version isolation, an independent FullRefresh and a converging stable-set
            re-check with restart
  stop      real native stop of a batch that has started and unstarted work: started work
            settles and commits, unstarted work is revoked, and a later run converges
  recovery  disabled / ordinary / legacy inputs delegate, a SQLite global fault fails the
            task without probing and recovers after restart

Evidence is printed as a single JSON document; pass ``--evidence-dir`` to persist it.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

import package_environment as pe  # noqa: E402
import package_plugin as pp  # noqa: E402
import run_isolated_package_integration as pkg  # noqa: E402
import run_isolated_batch_integration as batch  # noqa: E402

ROOT = pe.ROOT
PLUGIN_ID = pkg.PLUGIN_ID
PLUGIN_VERSION = "0.1.0.0"
TASK_NAME = "STRM 媒体信息检查"
TASK_KEY = "StrmProbeOptimizerBatchCheck"
SCAN_TASK_KEY = "RefreshLibrary"
MAX_WAIT = 300
# The bulk candidate set must cross the fixed 128-object batch boundary so a real second batch
# read happens; 130 is the smallest set that does so deterministically.
BULK_COUNT = 130
OUT_OF_SCOPE_LIBRARY = "Package Local Fixtures"
# A delay long enough to hold an actually started probe open across the whole native scan.
PROBE_DELAY_SECONDS = 20
# A shorter delay used for the URL re-change-during-probe race, leaving time to rewrite to C.
RACE_DELAY_SECONDS = 8


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return pe.run(*args, timeout=timeout)


# ---------------------------------------------------------------------------------------------------------------------
# Native API helpers (package instance)
# ---------------------------------------------------------------------------------------------------------------------


def api_auth() -> str:
    return pkg.api_auth()


def container() -> str:
    return pe.container_name("jellyfin")


def media_container() -> str:
    return pe.container_name("media")


def task_list(auth: str) -> list[dict]:
    status, tasks = pe.request_json("GET", "/ScheduledTasks", headers={"Authorization": auth})
    require(status == 200, "The scheduled-task listing failed.")
    return tasks


def find_task_by_key(auth: str, key: str) -> dict:
    matches = [task for task in task_list(auth) if task.get("Key") == key]
    require(len(matches) == 1, f"Expected exactly one native task with key {key!r}, found {len(matches)}.")
    return matches[0]


def task_state_name(task: dict) -> str:
    return str(task.get("State", "")).lower()


def last_start(task: dict) -> str | None:
    return (task.get("LastExecutionResult") or {}).get("StartTimeUtc")


def start_task(auth: str, task_id: str) -> int:
    status, _ = pe.request_json("POST", "/ScheduledTasks/Running/" + task_id, headers={"Authorization": auth})
    return status


def stop_task(auth: str, task_id: str) -> int:
    status, _ = pe.request_json("DELETE", "/ScheduledTasks/Running/" + task_id, headers={"Authorization": auth})
    return status


def set_triggers(auth: str, task_id: str, triggers: list[dict]) -> int:
    status, _ = pe.request_json("POST", f"/ScheduledTasks/{task_id}/Triggers",
                                headers={"Authorization": auth}, body=triggers)
    return status


def wait_for_new_execution(auth: str, task_id: str, previous_start: str | None, timeout: int = MAX_WAIT) -> dict:
    deadline = time.monotonic() + timeout
    observed = False
    while time.monotonic() < deadline:
        current = next((task for task in task_list(auth) if task.get("Id") == task_id), None)
        require(current is not None, "The native task disappeared while waiting for its execution.")
        if last_start(current) != previous_start:
            observed = True
        if observed and task_state_name(current) in {"idle", "0"}:
            return current
        time.sleep(0.25)
    raise RuntimeError("The native task did not settle before the timeout.")


def run_plugin_task(auth: str, timeout: int = MAX_WAIT) -> dict:
    task = find_task_by_key(auth, TASK_KEY)
    previous = last_start(task)
    require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the manual batch task start.")
    return wait_for_new_execution(auth, task["Id"], previous, timeout)


def plugin_status(auth: str) -> str:
    return pkg.plugin_status(auth)


def plugin_action(auth: str, enabled: bool) -> int:
    return pkg.plugin_action(auth, enabled)


def restart() -> str:
    return pkg.restart()


def plugin_events() -> list[str]:
    return pkg.plugin_events()


def latest_summary() -> str | None:
    """Return the most recent redacted batch summary line, read with a large timestamped tail."""
    lines = [line for line in docker_log_lines(container()) if "STRM media information check finished" in line]
    return batch.base.safe_event(lines[-1]) if lines else None


def item_by_name(auth: str, name: str) -> dict:
    """Resolve one library item by name with a high limit so a large fixture set is not truncated."""
    status, payload = pe.request_json(
        "GET", "/Items?" + "Recursive=true&Limit=1000&Fields=MediaSources,Path,MediaStreams",
        headers={"Authorization": auth})
    require(status == 200, "The package-instance item listing failed.")
    matches = [item for item in payload.get("Items", []) if item.get("Name") == name]
    require(len(matches) == 1, f"Expected exactly one package-instance item named {name!r}, found {len(matches)}.")
    return matches[0]


def wait_for_item(auth: str, name: str, timeout: int = 90) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return item_by_name(auth, name)
        except RuntimeError:
            time.sleep(0.5)
    raise RuntimeError(f"The package instance did not scan the item {name!r}.")


def wait_for_item_absent(auth: str, name: str, timeout: int = 90) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, payload = pe.request_json(
            "GET", "/Items?" + "Recursive=true&Limit=1000&Fields=Path",
            headers={"Authorization": auth})
        if not any(item.get("Name") == name for item in payload.get("Items", [])):
            return
        time.sleep(0.5)
    raise RuntimeError(f"The package instance still contains {name!r}.")


def playback_info(auth: str, item_id: str, timeout: int = 120) -> tuple[int, dict]:
    return pkg.playback_info(auth, item_id, timeout=timeout)


def saved_stream_types(auth: str, item_id: str) -> list[str]:
    return pkg.saved_stream_types(auth, item_id)


def source_for_url(response: dict, expected_url: str) -> dict | None:
    return pkg.source_for_url(response, expected_url)


def fingerprint_row(source_item_id: str) -> dict | None:
    """Return the minimal fingerprint row for one physical source from the package instance."""
    return pkg.fingerprint_row(source_item_id, source_item_id)


def all_fingerprint_rows() -> list[dict]:
    """Return every minimal fingerprint row (five fields only)."""
    import sqlite3 as _sqlite3

    database = pkg.fingerprint_database()
    require(database.is_file(), "The plugin fingerprint database is missing.")
    uri = database.as_posix() + "?mode=ro"
    with _sqlite3.connect("file:" + uri, uri=True, timeout=10) as connection:
        connection.row_factory = _sqlite3.Row
        rows = connection.execute(
            "SELECT item_id, source_key, url_hash, sha1, file_size FROM strm_fingerprint").fetchall()
    return [dict(row) for row in rows]


def fingerprint_rows_for_source(source_item_id: str) -> list[dict]:
    key = uuid.UUID(source_item_id).hex
    return [row for row in all_fingerprint_rows() if row["source_key"] == key]


def dashed(value: str) -> str:
    return str(uuid.UUID(value))


def source_path_matches_hash(response: dict, expected_hash: str) -> bool:
    """Check whether a PlaybackInfo response contains a source whose path hashes to the expected URL hash."""
    import hashlib as _hashlib

    for source in response.get("MediaSources", []):
        path = source.get("Path") or ""
        if _hashlib.sha256(path.encode()).hexdigest() == expected_hash:
            return True
    return False


def expected_url_hash(url: str) -> str:
    return pkg.expected_url_hash(url)


def library_ids(auth: str) -> dict[str, str]:
    status, folders = pe.request_json("GET", "/Library/VirtualFolders", headers={"Authorization": auth})
    require(status == 200, "The virtual-folder listing failed.")
    by_suffix: dict[str, str] = {}
    for folder in folders:
        for info in folder.get("LibraryOptions", {}).get("PathInfos", []):
            suffix = str(info.get("Path", "")).rstrip("/").rsplit("/", 1)[-1]
            if suffix:
                by_suffix[suffix] = folder["ItemId"]
    return by_suffix


def refresh_library(auth: str) -> None:
    """Queue a native library refresh, retrying with a fresh token on a stale session."""
    deadline = time.monotonic() + 30
    last_status = None
    while time.monotonic() < deadline:
        status, _ = pe.request_json("POST", "/Library/Refresh", headers={"Authorization": auth})
        if status in (200, 204):
            return
        last_status = status
        if status == 401:
            auth = api_auth()
        time.sleep(1)
    raise RuntimeError(f"The library refresh was not accepted (last HTTP {last_status}).")


def run_native_scan(auth: str, timeout: int = MAX_WAIT) -> dict:
    """Trigger the real native full library scan task and wait for it to settle."""
    task = find_task_by_key(auth, SCAN_TASK_KEY)
    previous = last_start(task)
    require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the native full scan start.")
    return wait_for_new_execution(auth, task["Id"], previous, timeout=timeout)


def force_full_refresh(auth: str, item_id: str) -> int:
    query = urlencode({"metadataRefreshMode": "FullRefresh", "imageRefreshMode": "None",
                       "replaceAllMetadata": "false"})
    status, _ = pe.request_json("POST", f"/Items/{item_id}/Refresh?{query}", headers={"Authorization": auth})
    return status


def merge_versions(auth: str, item_ids: list[str]) -> int:
    query = urlencode({"ids": ",".join(item_ids)})
    status, _ = pe.request_json("POST", "/Videos/MergeVersions?" + query, headers={"Authorization": auth})
    return status


def configure(auth: str, payload: dict) -> int:
    status, _ = pe.request_json("POST", f"/Plugins/{PLUGIN_ID}/Configuration",
                                headers={"Authorization": auth}, body=payload)
    return status


def current_user_id(auth: str) -> str:
    """Return the authenticated user's id so an explicit MediaSourceId PlaybackInfo POST is possible."""
    credentials = json.loads(pe.credentials_path().read_text(encoding="utf-8"))
    status, users = pe.request_json("GET", "/Users", headers={"Authorization": auth})
    require(status == 200, "The user listing failed.")
    match = next((user for user in users if user.get("Name") == credentials["username"]), None)
    require(match is not None, "The authenticated package user was not found.")
    return match["Id"]


def playback_info_selected(auth: str, item_id: str, media_source_id: str) -> tuple[int, dict]:
    """Request PlaybackInfo for one explicit media source, proving multi-version selection."""
    user_id = current_user_id(auth)
    status, response = pe.request_json(
        "POST", f"/Items/{item_id}/PlaybackInfo?UserId={user_id}",
        headers={"Authorization": auth}, body={"UserId": user_id, "MediaSourceId": media_source_id})
    return status, response


def configuration_payload_from_xml(data: bytes) -> dict:
    return batch.configuration_payload_from_xml(data)


# ---------------------------------------------------------------------------------------------------------------------
# Log parsing (full UTC timestamps via docker --timestamps)
# ---------------------------------------------------------------------------------------------------------------------


def docker_log_lines(name: str, tail: int = 40000) -> list[str]:
    logs = run("docker", "logs", "--timestamps", "--tail", str(tail), name, timeout=30)
    require(logs.returncode == 0, f"Could not read the container logs for {name}.")
    return (logs.stdout + logs.stderr).splitlines()


def parse_docker_timestamp(line: str) -> datetime.datetime | None:
    match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)", line)
    if not match:
        return None
    try:
        return datetime.datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
    except ValueError:
        return None


def probe_start_events(name: str, since: datetime.datetime | None = None) -> list[dict]:
    entries: list[dict] = []
    for line in docker_log_lines(name):
        if "Native STRM probe started" not in line:
            continue
        timestamp = parse_docker_timestamp(line)
        item = re.search(r"probe started for item ([0-9a-fA-F-]+)", line)
        running = re.search(r"running probes (\d+)", line)
        if timestamp is None or not (item and running):
            continue
        if since is not None and timestamp < since:
            continue
        entries.append({"item_id": item.group(1).lower().replace("-", ""),
                        "running": int(running.group(1)), "timestamp": timestamp})
    return entries


def delay_request_events(name: str, since: datetime.datetime | None = None) -> list[dict]:
    entries: list[dict] = []
    for line in docker_log_lines(name):
        marker = "SLOW_MEDIA_REQUEST_STARTED "
        if marker not in line:
            continue
        timestamp = parse_docker_timestamp(line)
        if timestamp is None:
            continue
        if since is not None and timestamp < since:
            continue
        request_id = line.split(marker, 1)[1].strip()
        entries.append({"request_id": request_id, "timestamp": timestamp})
    return entries


def probe_start_for_item(events: list[dict], item_id: str) -> dict | None:
    key = item_id.lower().replace("-", "")
    return next((event for event in events if event["item_id"] == key), None)


def _parse_utc(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def scan_execution_interval(task: dict) -> tuple[datetime.datetime, datetime.datetime]:
    result = task.get("LastExecutionResult") or {}
    start = result.get("StartTimeUtc")
    end = result.get("EndTimeUtc")
    require(bool(start) and bool(end), f"The native scan task has no execution interval: {result}.")
    return (_parse_utc(start), _parse_utc(end))


def intervals_intersect(a_start: datetime.datetime, a_end: datetime.datetime,
                        b_start: datetime.datetime, b_end: datetime.datetime) -> bool:
    return a_start <= b_end and b_start <= a_end


def assert_scan_probe_overlap(scan_interval: tuple[datetime.datetime, datetime.datetime],
                              probe_start: datetime.datetime, probe_end: datetime.datetime,
                              label: str) -> dict:
    """Fail unless the scan interval and the actually started probe execution truly intersect.

    ``probe_start``/``probe_end`` bound one real probe execution (the observed backend request
    start and its completion). A queued, permitted or merely accepted request is never accepted.
    """
    scan_start, scan_end = scan_interval
    require(probe_end > probe_start, f"The {label} probe has no positive execution interval.")
    require(intervals_intersect(scan_start, scan_end, probe_start, probe_end),
            f"The native scan interval [{scan_start.isoformat()}, {scan_end.isoformat()}] does not intersect "
            f"the actually started {label} probe interval [{probe_start.isoformat()}, {probe_end.isoformat()}].")
    return {"scan_start": scan_start.isoformat(), "scan_end": scan_end.isoformat(),
            "probe_start": probe_start.isoformat(), "probe_end": probe_end.isoformat(), "overlapped": True}


# ---------------------------------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------------------------------


def write_strm_to(directory: Path, name: str, url: str, sha1: str | None, size: int | None) -> Path:
    path = directory / (name + ".strm")
    lines = ["# strm-probe-version:1"]
    if sha1 is not None:
        lines.append(f"# strm-probe-sha1:{sha1}")
    if size is not None:
        lines.append(f"# strm-probe-size:{size}")
    lines.append(url)
    return pe.write_owned_bytes(path, ("\n".join(lines) + "\n").encode("utf-8"), label=f"scan STRM {name}")


def rewrite_strm(path: Path, url: str, sha1: str | None, size: int | None) -> None:
    pe.require_owned_path(path, label=f"rewrite {path.name}")
    data = path.read_bytes().decode("utf-8-sig")
    body = [line for line in data.splitlines()
            if line.strip() and not line.strip().startswith("#")]
    result = ["# strm-probe-version:1"]
    if sha1 is not None:
        result.append(f"# strm-probe-sha1:{sha1}")
    if size is not None:
        result.append(f"# strm-probe-size:{size}")
    result.append(url)
    if body:
        result.extend(body[1:])
    pe.write_owned_bytes(path, ("\n".join(result) + "\n").encode("utf-8"), label=f"rewrite {path.name}")


def delay_url(base_url: str, seconds: float, request_id: str) -> str:
    parts = urlsplit(base_url)
    leaf = parts.path.rsplit("/", 1)[-1] or "package-mp4.mp4"
    return urlunsplit((parts.scheme, parts.netloc, f"/delay/{seconds:g}/{request_id}/{leaf}", "", ""))


def unique_url(base_url: str, key: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode({"scan_case": key}), ""))


def native_prepare_stream(auth: str, item: dict, url: str, timeout: int = 120) -> bool:
    """Let Jellyfin itself probe and persist a primary stream while the plugin is disabled."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, response = playback_info(auth, item["Id"])
        if status == 200 and source_for_url(response, url) and "Video" in saved_stream_types(auth, item["Id"]):
            return True
        time.sleep(0.5)
    return False


def prepare_native_streams(auth: str, items: list[dict], url: str, workers: int = 4) -> None:
    results: dict[str, bool] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(native_prepare_stream, auth, item, url): item["Name"] for item in items}
        for future, name in futures.items():
            results[name] = future.result()
    failed = sorted(name for name, ok in results.items() if not ok)
    require(not failed, f"Native stream preparation did not persist a primary stream for {len(failed)} item(s): {failed[:5]}.")


# ---------------------------------------------------------------------------------------------------------------------
# Trigger snapshot/restore
# ---------------------------------------------------------------------------------------------------------------------


def snapshot_triggers(auth: str) -> dict[str, list[dict]]:
    return {str(task["Id"]): (task.get("Triggers") or []) for task in task_list(auth) if task.get("Id")}


def restore_triggers(auth: str, snapshot: dict[str, list[dict]]) -> None:
    problems: list[str] = []
    for task_id, triggers in snapshot.items():
        status = set_triggers(auth, task_id, triggers)
        if status != 204:
            problems.append(f"trigger restore for {task_id} returned {status}")
    current = {str(task["Id"]): (task.get("Triggers") or []) for task in task_list(auth) if task.get("Id")}
    for task_id, triggers in snapshot.items():
        if current.get(task_id) != triggers:
            problems.append(f"trigger identity mismatch for {task_id}")
    require(not problems, "The native task triggers were not restored: " + "; ".join(problems))


# ---------------------------------------------------------------------------------------------------------------------
# Instance / fixture setup
# ---------------------------------------------------------------------------------------------------------------------


def clear_strm_fixtures() -> int:
    """Remove this run's scenario STRM fixtures (never the generated media files) so each
    scenario starts from a known, isolated fixture set. All paths are run-owned."""
    removed = 0
    for directory in (pe.WORK / "strm", pe.WORK / "media"):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.strm")):
            pe.require_owned_path(path, label=f"scenario fixture {path.name}")
            path.unlink()
            removed += 1
    return removed


# The native scheduled-task triggers recorded on the first fresh instance of this run. Every
# scenario starts from the same fresh instance, so the recorded defaults are restored and verified
# in the run's finally block even if a scenario failed mid-way.
ORIGINAL_TRIGGERS: dict[str, list[dict]] | None = None


def deploy_fresh(package: Path) -> str:
    """Prepare a clean package instance, install only the archive and return a fresh auth token."""
    global ORIGINAL_TRIGGERS
    clear_strm_fixtures()
    pe.prepare_clean_instance()
    pe.deploy_archive(package)
    restart()
    auth = api_auth()
    require(pe.public_info().get("Version") == "12.2.0", "The package instance is not Jellyfin 12.2.0.")
    require(str(plugin_status(auth)).lower() in {"active", "0"}, "The plugin is not Active after archive-only install.")
    if ORIGINAL_TRIGGERS is None:
        ORIGINAL_TRIGGERS = snapshot_triggers(auth)
    return auth


def scope_to_strm_library(auth: str) -> dict[str, str]:
    libraries = library_ids(auth)
    require("strm" in libraries and "local" in libraries,
            f"The package instance must expose strm and local libraries: {libraries}.")
    status = configure(auth, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2,
                              "DetailedLog": False, "BatchAllLibraries": False,
                              "BatchLibraryIds": libraries["strm"]})
    require(status == 204, f"Jellyfin rejected the explicit scope ({status}).")
    return libraries


def scope_all_libraries(auth: str) -> None:
    status = configure(auth, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2,
                              "DetailedLog": False, "BatchAllLibraries": True, "BatchLibraryIds": ""})
    require(status == 204, f"Jellyfin rejected the all-library scope ({status}).")


def bulk_fixture(auth: str, nonce: str) -> dict:
    """Create the two-library fixture set, index it and persist native primary streams.

    The bulk set crosses the fixed 128-object batch boundary. Native stream preparation runs with
    the plugin disabled so the later scoped batch first-trusts them with zero plugin probes.
    """
    strm_dir = pe.WORK / "strm"
    local_dir = pe.WORK / "media"
    media_sha, media_size = pe.media_sha1(pe.MEDIA_MP4)
    plain_url = "http://media:8080/" + pe.MEDIA_MP4
    bulk_names = [f"Scan Bulk {nonce} {index:03d}" for index in range(BULK_COUNT)]
    for name in bulk_names:
        write_strm_to(strm_dir, name, plain_url, media_sha, media_size)
    out_name = f"Scan Out Of Scope {nonce}"
    write_strm_to(local_dir, out_name, plain_url, media_sha, media_size)
    # The playback overlap source lives in the out-of-scope library so the scoped batch never
    # touches it and the playback genuinely starts its own probe on a different source.
    playback_name = f"Scan Playback {nonce}"
    write_strm_to(local_dir, playback_name, plain_url, media_sha, media_size)
    # A source that will be moved from the out-of-scope library into the selected library.
    movein_name = f"Scan Move In {nonce}"
    write_strm_to(local_dir, movein_name, plain_url, media_sha, media_size)
    batch_name = f"Scan Batch {nonce}"
    write_strm_to(strm_dir, batch_name, plain_url, media_sha, media_size)
    mv_a_name, mv_b_name = f"Scan MV A {nonce}", f"Scan MV B {nonce}"
    write_strm_to(strm_dir, mv_a_name, plain_url, media_sha, media_size)
    write_strm_to(strm_dir, mv_b_name, plain_url, media_sha, media_size)
    content_name, size_name = f"Scan Content {nonce}", f"Scan Size {nonce}"
    write_strm_to(strm_dir, content_name, plain_url, media_sha, media_size)
    write_strm_to(strm_dir, size_name, plain_url, media_sha, media_size)
    race_name = f"Scan Race {nonce}"
    write_strm_to(strm_dir, race_name, plain_url, media_sha, media_size)

    refresh_library(auth)
    names = [*bulk_names, out_name, playback_name, movein_name, batch_name, mv_a_name, mv_b_name,
             content_name, size_name, race_name]
    items = {name: wait_for_item(auth, name) for name in names}
    return {"nonce": nonce, "media_sha": media_sha, "media_size": media_size, "plain_url": plain_url,
            "bulk_names": bulk_names, "out_name": out_name, "playback_name": playback_name,
            "movein_name": movein_name, "batch_name": batch_name, "mv_a_name": mv_a_name,
            "mv_b_name": mv_b_name, "content_name": content_name, "size_name": size_name,
            "race_name": race_name, "items": items, "strm_dir": strm_dir, "local_dir": local_dir}


def establish_baselines(auth: str, fixture: dict) -> dict:
    """Disable the plugin, persist native streams, re-enable and first-trust with zero plugin probes."""
    require(plugin_action(auth, False) == 204, "The plugin disable failed.")
    restart()
    auth = api_auth()
    require(str(plugin_status(auth)).lower() not in {"active", "0"}, "The plugin remained active after disable.")
    tracked = [*fixture["bulk_names"], fixture["playback_name"], fixture["batch_name"],
               fixture["mv_a_name"], fixture["mv_b_name"], fixture["content_name"],
               fixture["size_name"], fixture["race_name"]]
    prepare_native_streams(auth, [fixture["items"][name] for name in tracked], fixture["plain_url"])
    require(plugin_action(auth, True) == 204, "The plugin enable failed.")
    restart()
    auth = api_auth()
    require(str(plugin_status(auth)).lower() in {"active", "0"}, "The plugin is not Active after enable.")
    libraries = scope_to_strm_library(auth)
    run_plugin_task(auth)
    summary = latest_summary()
    fields = batch.summary_fields(summary)
    batch.assert_summary_equations(fields)
    require((fields.get("actual_probe_calls") or 0) == 0, f"The baseline first-trust run performed plugin probes: {summary}.")
    require((fields.get("first_trust") or 0) >= BULK_COUNT, f"The baseline run did not first-trust the bulk candidates: {summary}.")
    require(fingerprint_row(fixture["items"][fixture["batch_name"]]["Id"]) is not None,
            "The baseline did not create a fingerprint for the batch source.")
    require(fingerprint_row(fixture["items"][fixture["out_name"]]["Id"]) is None,
            "The out-of-scope local candidate was processed by the scoped batch.")
    require(fingerprint_row(fixture["items"][fixture["movein_name"]]["Id"]) is None,
            "The out-of-scope move-in candidate was processed by the scoped batch.")
    return {"summary": summary, "fields": fields, "libraries": libraries}


# ---------------------------------------------------------------------------------------------------------------------
# Overlap scenario
# ---------------------------------------------------------------------------------------------------------------------


def wait_for_delay(request_id: str, since: datetime.datetime, timeout: int = 90) -> datetime.datetime:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        matches = [event for event in delay_request_events(media_container(), since=since)
                   if event["request_id"] == request_id]
        if matches:
            return matches[0]["timestamp"]
        time.sleep(0.2)
    raise RuntimeError(f"The delayed backend request {request_id} never actually started.")


def scenario_overlap(package: Path, evidence_dir: Path | None, nonce: str) -> dict:
    summary: dict[str, object] = {}
    auth = deploy_fresh(package)
    summary["payload_matches_archive"] = pkg.deployed_matches_archive(package)
    pe.add_library_authenticated(auth, OUT_OF_SCOPE_LIBRARY, ["/media/local"])
    auth = api_auth()
    fixture = bulk_fixture(auth, nonce)
    summary["fixture"] = {"bulk": BULK_COUNT, "out_of_scope": fixture["out_name"],
                          "playback_library": "local", "batch_library": "strm"}
    summary["baseline"] = establish_baselines(auth, fixture)
    auth = api_auth()
    items = fixture["items"]

    merge_status = merge_versions(auth, [items[fixture["mv_a_name"]]["Id"], items[fixture["mv_b_name"]]["Id"]])
    require(merge_status == 204, f"Jellyfin did not merge the multi-version pair ({merge_status}).")

    # -- Real three-way overlap: native full scan × started batch probe × started playback probe --
    batch_id = uuid.uuid4().hex
    playback_id = uuid.uuid4().hex
    batch_path = fixture["strm_dir"] / (fixture["batch_name"] + ".strm")
    playback_path = fixture["local_dir"] / (fixture["playback_name"] + ".strm")
    batch_url = delay_url(fixture["plain_url"], PROBE_DELAY_SECONDS, batch_id)
    playback_url = delay_url(fixture["plain_url"], PROBE_DELAY_SECONDS, playback_id)
    rewrite_strm(batch_path, batch_url, fixture["media_sha"], fixture["media_size"])
    rewrite_strm(playback_path, playback_url, fixture["media_sha"], fixture["media_size"])

    round_started = datetime.datetime.now(datetime.timezone.utc)
    scan_task = find_task_by_key(auth, SCAN_TASK_KEY)
    scan_previous = last_start(scan_task)
    batch_task = find_task_by_key(auth, TASK_KEY)
    batch_previous = last_start(batch_task)
    require(start_task(auth, batch_task["Id"]) == 204, "Jellyfin did not accept the overlap batch start.")
    playback_holder: dict = {}

    def playback() -> None:
        try:
            playback_holder["result"] = playback_info(auth, items[fixture["playback_name"]]["Id"])
        except Exception as error:
            playback_holder["error"] = type(error).__name__

    worker = threading.Thread(target=playback, name="scan-overlap-playback", daemon=True)
    worker.start()
    batch_backend_start = wait_for_delay(batch_id, round_started)
    playback_backend_start = wait_for_delay(playback_id, round_started)
    probe_starts = probe_start_events(container(), since=round_started)
    batch_probe = probe_start_for_item(probe_starts, items[fixture["batch_name"]]["Id"])
    playback_probe = probe_start_for_item(probe_starts, items[fixture["playback_name"]]["Id"])
    require(batch_probe is not None, f"No real plugin probe start was observed for the batch source: {probe_starts}.")
    require(playback_probe is not None, f"No real plugin probe start was observed for the playback source: {probe_starts}.")

    require(start_task(auth, scan_task["Id"]) == 204, "Jellyfin did not accept the native full scan start.")
    scan_after = wait_for_new_execution(auth, scan_task["Id"], scan_previous, timeout=MAX_WAIT)
    scan_interval = scan_execution_interval(scan_after)

    final = wait_for_new_execution(auth, batch_task["Id"], batch_previous, timeout=MAX_WAIT)
    worker.join(timeout=MAX_WAIT)
    require(not worker.is_alive(), "The overlap playback did not finish.")
    require("error" not in playback_holder, "The overlap playback failed outside the HTTP path.")
    require(str((final.get("LastExecutionResult") or {}).get("Status", "")).lower() in {"completed", "0"},
            f"The overlap batch did not complete: {final.get('LastExecutionResult')}.")
    summary["scan_overlap"] = {
        "scan": assert_scan_probe_overlap(
            scan_interval, batch_probe["timestamp"],
            batch_backend_start + datetime.timedelta(seconds=PROBE_DELAY_SECONDS), "batch"),
        "playback": assert_scan_probe_overlap(
            scan_interval, playback_probe["timestamp"],
            playback_backend_start + datetime.timedelta(seconds=PROBE_DELAY_SECONDS), "playback"),
        "batch_backend_requests": len([e for e in delay_request_events(media_container(), since=round_started)
                                       if e["request_id"] == batch_id]),
        "playback_backend_requests": len([e for e in delay_request_events(media_container(), since=round_started)
                                          if e["request_id"] == playback_id]),
        "plugin_probe_starts": len(probe_starts),
    }
    overlap_summary = latest_summary()
    overlap_fields = batch.summary_fields(overlap_summary)
    batch.assert_summary_equations(overlap_fields)
    require((overlap_fields.get("actual_probe_calls") or 0) == 1, f"The overlap batch must start exactly one probe: {overlap_summary}.")
    require((overlap_fields.get("reliable_success") or 0) == 1, f"The overlap batch must count one reliable success: {overlap_summary}.")
    summary["overlap_batch_summary"] = overlap_summary
    auth = api_auth()
    status, batch_response = playback_info(auth, items[fixture["batch_name"]]["Id"])
    require(status == 200 and source_for_url(batch_response, batch_url),
            "The batch source did not return its changed address after the overlap.")
    require(source_for_url(playback_holder["result"][1], playback_url),
            "The playback source did not return its changed address after the overlap.")

    summary["finite_changes"] = _finite_changes(auth, fixture)
    summary["multi_version_and_refresh"] = _multi_version_and_refresh(auth, fixture)
    summary["convergence"] = _convergence(auth, fixture, nonce)
    return summary


def _finite_changes(auth: str, fixture: dict) -> dict:
    """URL re-change during a probe, content SHA-1 change, size-only change, add, delete and move."""
    items = fixture["items"]
    result: dict[str, object] = {}
    # URL re-change during the probe: B (delayed) -> C while the probe is running. B must never
    # become the trusted fingerprint; the old baseline survives and a later run commits C.
    race_id = items[fixture["race_name"]]["Id"]
    race_path = fixture["strm_dir"] / (fixture["race_name"] + ".strm")
    b_id = uuid.uuid4().hex
    b_url = delay_url(fixture["plain_url"], RACE_DELAY_SECONDS, b_id)
    c_url = unique_url(fixture["plain_url"], "race-c-" + uuid.uuid4().hex[:8])
    rewrite_strm(race_path, b_url, fixture["media_sha"], fixture["media_size"])
    round_started = datetime.datetime.now(datetime.timezone.utc)
    task = find_task_by_key(auth, TASK_KEY)
    race_previous = last_start(task)
    require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the race batch start.")
    wait_for_delay(b_id, round_started)
    rewrite_strm(race_path, c_url, fixture["media_sha"], fixture["media_size"])
    final = wait_for_new_execution(auth, task["Id"], race_previous, timeout=MAX_WAIT)
    row_after_race = fingerprint_row(race_id)
    require(row_after_race is not None and row_after_race["url_hash"] != expected_url_hash(b_url),
            "The URL changed during the probe was committed as the trusted fingerprint.")
    run_plugin_task(auth)
    row_c = fingerprint_row(race_id)
    require(row_c is not None and row_c["url_hash"] == expected_url_hash(c_url),
            "The later run did not commit the current C address after the race.")
    result["url_rechange_during_probe"] = {"b_rejected": True, "c_committed": True,
                                           "status": (final.get("LastExecutionResult") or {}).get("Status")}

    # Content SHA-1 change at the same URL must probe.
    content_path = fixture["strm_dir"] / (fixture["content_name"] + ".strm")
    changed_sha = "a" * 40
    rewrite_strm(content_path, fixture["plain_url"], changed_sha, fixture["media_size"])
    run_plugin_task(auth)
    content_row = fingerprint_row(items[fixture["content_name"]]["Id"])
    require(content_row is not None and content_row["sha1"] == changed_sha,
            "The content SHA-1 change was not probed and committed.")
    result["content_sha1_change_probed"] = True

    # SHA-1 incomparable + valid Size change must probe.
    size_id = items[fixture["size_name"]]["Id"]
    size_path = fixture["strm_dir"] / (fixture["size_name"] + ".strm")
    rewrite_strm(size_path, fixture["plain_url"], None, fixture["media_size"] + 1)
    run_plugin_task(auth)
    size_row = fingerprint_row(size_id)
    require(size_row is not None and size_row["file_size"] == fixture["media_size"] + 1,
            "The incomparable-SHA-1 size change was not probed and committed.")
    result["size_change_probed"] = True

    # Move out of scope: a not-yet-processed selected-library STRM moved to the out-of-scope
    # library before the next run must not be batch-probed (no fingerprint row is created).
    moveout_name = f"Scan Move Out {fixture['nonce']}"
    write_strm_to(fixture["strm_dir"], moveout_name, fixture["plain_url"], fixture["media_sha"], fixture["media_size"])
    run_native_scan(auth)
    moveout_item = wait_for_item(auth, moveout_name)
    require(fingerprint_row(moveout_item["Id"]) is None, "The move-out source was processed before it was moved.")
    shutil.move(str(fixture["strm_dir"] / (moveout_name + ".strm")),
                str(fixture["local_dir"] / (moveout_name + ".strm")))
    # Move in scope: an out-of-scope STRM moved into the selected library must be discovered and
    # processed by the next round.
    moved_in_name = fixture["movein_name"]
    shutil.move(str(fixture["local_dir"] / (moved_in_name + ".strm")),
                str(fixture["strm_dir"] / (moved_in_name + ".strm")))
    run_native_scan(auth)
    moved_in_item = wait_for_item(auth, moved_in_name)
    run_plugin_task(auth)
    require(fingerprint_row(moved_in_item["Id"]) is not None,
            "The next round did not discover the moved-in STRM.")
    require(fingerprint_row(moveout_item["Id"]) is None,
            "The moved-out source was batch-probed after leaving the selected scope.")
    result["move_in_discovered"] = True
    result["move_out_not_probed"] = True

    # Add a new STRM: the next round must discover it; delete a bulk candidate safely.
    added_name = f"Scan Added {fixture['nonce']}"
    added_path = write_strm_to(fixture["strm_dir"], added_name, fixture["plain_url"],
                               fixture["media_sha"], fixture["media_size"])
    run_native_scan(auth)
    added_item = wait_for_item(auth, added_name)
    deleted_name = fixture["bulk_names"][0]
    deleted_id = items[deleted_name]["Id"]
    (fixture["strm_dir"] / (deleted_name + ".strm")).unlink(missing_ok=True)
    run_native_scan(auth)
    wait_for_item_absent(auth, deleted_name)
    run_plugin_task(auth)
    require(fingerprint_row(added_item["Id"]) is not None, "The next round did not discover the added STRM.")
    summary_line = latest_summary()
    fields = batch.summary_fields(summary_line)
    batch.assert_summary_equations(fields)
    require(fields.get("candidate_fetch_failed") is False, f"The add/delete round failed its candidate fetch: {summary_line}.")
    result["add_discovered_next_round"] = True
    result["delete_settled"] = True
    result["add_delete_summary"] = summary_line
    result["deleted_id"] = deleted_id
    added_path.unlink(missing_ok=True)
    run_native_scan(auth)
    wait_for_item_absent(auth, added_name)
    return result


def _multi_version_and_refresh(auth: str, fixture: dict) -> dict:
    """Multi-version isolation and an independent native FullRefresh.

    The two physical sources were merged through the native MergeVersions API before this phase.
    One extra batch run re-associates the alternate source under the canonical project id without
    hand-writing any database relation.
    """
    items = fixture["items"]
    mv_a = items[fixture["mv_a_name"]]["Id"]
    mv_b = items[fixture["mv_b_name"]]["Id"]
    run_plugin_task(auth)
    rows_a = fingerprint_rows_for_source(mv_a)
    rows_b = fingerprint_rows_for_source(mv_b)
    shared = [(ra, rb) for ra in rows_a for rb in rows_b if ra["item_id"] == rb["item_id"]]
    require(len(shared) == 1,
            f"The multi-version pair must share exactly one canonical project id: a={rows_a}, b={rows_b}.")
    ra, rb = shared[0]
    require(ra["source_key"] != rb["source_key"], "The two versions must keep distinct source keys.")
    canonical = ra["item_id"]
    # An independent native FullRefresh on one version must not change either version's fingerprint.
    before_a = fingerprint_row(mv_a)
    refresh_status = force_full_refresh(auth, dashed(canonical))
    require(refresh_status == 204, f"Jellyfin rejected the independent FullRefresh ({refresh_status}).")
    after_rows_a = [row for row in fingerprint_rows_for_source(mv_a) if row["item_id"] == canonical]
    after_rows_b = [row for row in fingerprint_rows_for_source(mv_b) if row["item_id"] == canonical]
    require(after_rows_a == [ra] and after_rows_b == [rb],
            "The independent FullRefresh changed a version's fingerprint.")
    # An explicit MediaSourceId selection must return the selected version's own address.
    status_a, response_a = playback_info_selected(auth, dashed(canonical), mv_a)
    status_b, response_b = playback_info_selected(auth, dashed(canonical), mv_b)
    require(status_a == 200 and status_b == 200, "The explicit multi-version PlaybackInfo request failed.")
    require(source_path_matches_hash(response_a, ra["url_hash"]),
            "The selected version A did not return its own address.")
    require(source_path_matches_hash(response_b, rb["url_hash"]),
            "The selected version B did not return its own address.")
    return {"multi_version_rows": 2, "shared_project": True,
            "independent_full_refresh_status": refresh_status, "cross_version_fingerprint_stable": True,
            "selected_version_a_matches": True, "selected_version_b_matches": True}


def _convergence(auth: str, fixture: dict, nonce: str) -> dict:
    """A fresh stable-set run converges with zero extra plugin probes; restart preserves the address."""
    run_native_scan(auth)
    run_plugin_task(auth)
    summary_line = latest_summary()
    fields = batch.summary_fields(summary_line)
    batch.assert_summary_equations(fields)
    require((fields.get("actual_probe_calls") or 0) == 0,
            f"The stable-set convergence run performed plugin probes: {summary_line}.")
    run_plugin_task(auth)
    repeat_line = latest_summary()
    repeat_fields = batch.summary_fields(repeat_line)
    batch.assert_summary_equations(repeat_fields)
    require((repeat_fields.get("actual_probe_calls") or 0) == 0,
            f"The unchanged re-check performed plugin probes: {repeat_line}.")
    # Restart and prove the current committed address survives.
    batch_item = fixture["items"][fixture["batch_name"]]["Id"]
    committed = fingerprint_row(batch_item)
    require(committed is not None, "The batch source has no committed fingerprint before the restart check.")
    restart()
    auth = api_auth()
    status, response = playback_info(auth, batch_item)
    require(status == 200 and source_path_matches_hash(response, committed["url_hash"]),
            "The batch source address did not survive the restart.")
    return {"stable_summary": summary_line, "repeat_summary": repeat_line,
            "stable_zero_probe": True, "restart_address_stable": True}


# ---------------------------------------------------------------------------------------------------------------------
# Stop scenario
# ---------------------------------------------------------------------------------------------------------------------


def scenario_stop(package: Path, evidence_dir: Path | None, nonce: str) -> dict:
    summary: dict[str, object] = {}
    auth = deploy_fresh(package)
    media_sha, media_size = pe.media_sha1(pe.MEDIA_MP4)
    plain_url = "http://media:8080/" + pe.MEDIA_MP4
    names = [f"Scan Stop {nonce} {index}" for index in range(3)]
    paths = [write_strm_to(pe.WORK / "strm", name, plain_url, media_sha, media_size) for name in names]
    refresh_library(auth)
    items = {name: wait_for_item(auth, name) for name in names}
    # Baseline the three sources with the plugin enabled (first trust, zero probes).
    scope_all_libraries(auth)
    run_plugin_task(auth)
    for name in names:
        require(fingerprint_row(items[name]["Id"]) is not None, f"The stop scenario did not baseline {name}.")
    # Give each source a distinct delayed changed URL so started/unstarted is deterministic. The
    # delayed route is longer than the default probe window so unstarted sources stay unstarted.
    request_ids = {name: uuid.uuid4().hex for name in names}
    for name, path in zip(names, paths):
        rewrite_strm(path, delay_url(plain_url, PROBE_DELAY_SECONDS, request_ids[name]), media_sha, media_size)
    round_started = datetime.datetime.now(datetime.timezone.utc)
    task = find_task_by_key(auth, TASK_KEY)
    previous = last_start(task)
    require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the stop-scenario batch start.")
    # Wait until the default concurrency (2) is fully occupied by actually started probes, so the
    # third source is deterministically still unstarted when the stop is issued.
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        started = {event["request_id"] for event in delay_request_events(media_container(), since=round_started)}
        if len(started & set(request_ids.values())) >= 2:
            break
        time.sleep(0.2)
    started_before_stop = {event["request_id"] for event in delay_request_events(media_container(), since=round_started)}
    require(started_before_stop & set(request_ids.values()),
            "The stop scenario never reached a real probe.")
    stop_status = stop_task(auth, task["Id"])
    require(stop_status == 204, "Jellyfin did not accept the native stop.")
    # Bind to this round's own execution result: a bare Idle read can return the previous round's
    # Completed result before the stopped round has settled.
    final = wait_for_new_execution(auth, task["Id"], previous, timeout=MAX_WAIT)
    status_value = str((final.get("LastExecutionResult") or {}).get("Status", "")).lower()
    require(status_value in {"cancelled", "1"}, f"The stopped round did not record Cancelled: {final.get('LastExecutionResult')}.")
    summary_line = latest_summary()
    fields = batch.summary_fields(summary_line)
    batch.assert_summary_equations(fields)
    # The committed/revoked split is derived from the persisted fingerprints rather than from the
    # timing log, so a source that started in the narrow window before the stop is classified by
    # its real outcome. With three sources and the default concurrency of two, at most two can
    # actually start, so the split is deterministic and at least one source is revoked.
    committed: list[str] = []
    revoked: list[str] = []
    for name in names:
        row = fingerprint_row(items[name]["Id"])
        if row is not None and row["url_hash"] == expected_url_hash(
                delay_url(plain_url, PROBE_DELAY_SECONDS, request_ids[name])):
            committed.append(name)
        else:
            revoked.append(name)
    require(committed, "No actually started probe settled after the native stop.")
    require(revoked, "The native stop did not revoke any unstarted source.")
    require(len(committed) + len(revoked) == len(names), "Every stop-scenario source must settle exactly once.")
    require((fields.get("reliable_success") or 0) == len(committed),
            f"The stopped round reliable-success count must equal the committed set ({committed}): {summary_line}.")
    require((fields.get("revoked") or 0) == len(revoked),
            f"The stopped round revoked count must equal the unstarted set ({revoked}): {summary_line}.")
    summary["stop"] = {"stop_status": stop_status, "status": status_value, "summary": summary_line,
                       "committed": committed, "revoked": revoked}
    # A later run converges: revoked sources are re-probed and committed; committed ones are not.
    run_plugin_task(auth)
    for name in revoked:
        row = fingerprint_row(items[name]["Id"])
        require(row is not None and row["url_hash"] == expected_url_hash(
            delay_url(plain_url, PROBE_DELAY_SECONDS, request_ids[name])),
            f"The next run did not converge the revoked source {name}.")
    for name in committed:
        row = fingerprint_row(items[name]["Id"])
        require(row is not None and row["url_hash"] == expected_url_hash(
            delay_url(plain_url, PROBE_DELAY_SECONDS, request_ids[name])),
            f"The next run lost the committed source {name}.")
    summary["converged"] = True
    return summary


# ---------------------------------------------------------------------------------------------------------------------
# Recovery scenario
# ---------------------------------------------------------------------------------------------------------------------


def scenario_controls(package: Path, evidence_dir: Path | None, nonce: str) -> dict:
    """Common controls on the ZIP-installed candidate: real timed trigger, two-direction
    same-source sharing, different-source independence and a mixed-concurrency peak."""
    summary: dict[str, object] = {}
    auth = deploy_fresh(package)
    media_sha, media_size = pe.media_sha1(pe.MEDIA_MP4)
    plain_url = "http://media:8080/" + pe.MEDIA_MP4
    pe.add_library_authenticated(auth, OUT_OF_SCOPE_LIBRARY, ["/media/local"])
    auth = api_auth()
    libraries = scope_to_strm_library(auth)
    require("strm" in libraries and "local" in libraries, f"Missing strm/local libraries: {libraries}.")

    # A real wall-clock trigger: set a daily trigger ~40s ahead, restart, observe the task run by
    # the timer with no manual start, then clear it. The trigger is restored by the caller's finally.
    task = find_task_by_key(auth, TASK_KEY)
    require(not task.get("Triggers"), f"A fresh install must have no default trigger: {task.get('Triggers')}.")
    ticks = batch.future_time_of_day_ticks(seconds_ahead=40)
    require(set_triggers(auth, task["Id"], [{"Type": "DailyTrigger", "TimeOfDayTicks": ticks}]) == 204,
            "Jellyfin did not accept the timed trigger.")
    previous = last_start(task)
    restart()
    auth = api_auth()
    persisted = find_task_by_key(auth, TASK_KEY)
    require(len(persisted.get("Triggers") or []) == 1, "The timed trigger did not survive a restart.")
    fired = _wait_for_trigger_fire(auth, previous, timeout=180)
    require(fired, "The timed trigger did not actually run the task within the window.")
    summary["timed_trigger"] = {"persisted": True, "fired": True}
    require(set_triggers(auth, task["Id"], []) == 204, "Jellyfin did not accept clearing the trigger.")
    auth = api_auth()

    # Two-direction same-source sharing and different-source independence.
    auth = api_auth()
    summary["sharing"] = _sharing_directions(auth, libraries, nonce)
    # Mixed concurrency peak on the ZIP-installed instance.
    auth = api_auth()
    summary["mixed"] = _mixed_concurrency(auth, libraries, nonce)
    return summary


def _wait_for_trigger_fire(auth: str, previous_start: str | None, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = find_task_by_key(auth, TASK_KEY)
        if last_start(task) not in {None, previous_start} and task_state_name(task) in {"idle", "0"}:
            return True
        time.sleep(0.5)
    return False


def _sharing_directions(auth: str, libraries: dict[str, str], nonce: str) -> dict:
    """Both start orders of a batch sharing one actually running same-source playback probe."""
    results: dict[str, object] = {}
    for playback_first in (False, True):
        results["playback_first" if playback_first else "batch_first"] = _sharing_direction(
            auth, libraries, nonce, playback_first=playback_first)
        auth = api_auth()
    return results


def _sharing_direction(auth: str, libraries: dict[str, str], nonce: str, *, playback_first: bool) -> dict:
    media_sha, media_size = pe.media_sha1(pe.MEDIA_MP4)
    plain_url = "http://media:8080/" + pe.MEDIA_MP4
    name = f"Scan Share {nonce} {playback_first}"
    path = write_strm_to(pe.WORK / "strm", name, plain_url, media_sha, media_size)
    refresh_library(auth)
    item = wait_for_item(auth, name)
    # Establish a baseline first trust, then change to a delayed URL that must probe.
    run_plugin_task(auth)
    require(fingerprint_row(item["Id"]) is not None, "The sharing source did not get a baseline.")
    request_id = uuid.uuid4().hex
    target_url = delay_url(plain_url, PROBE_DELAY_SECONDS, request_id)
    rewrite_strm(path, target_url, media_sha, media_size)
    round_started = datetime.datetime.now(datetime.timezone.utc)
    holder: dict = {}

    def playback() -> None:
        try:
            holder["result"] = playback_info(auth, item["Id"])
        except Exception as error:
            holder["error"] = type(error).__name__

    task = find_task_by_key(auth, TASK_KEY)
    share_previous = last_start(task)
    if playback_first:
        worker = threading.Thread(target=playback, name="scan-share-playback", daemon=True)
        worker.start()
        wait_for_delay(request_id, round_started)
        require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the sharing batch start.")
        worker.join(timeout=MAX_WAIT)
    else:
        require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the sharing batch start.")
        wait_for_delay(request_id, round_started)
        worker = threading.Thread(target=playback, name="scan-share-playback", daemon=True)
        worker.start()
        worker.join(timeout=MAX_WAIT)
    require(not worker.is_alive(), "The sharing playback did not finish.")
    require("error" not in holder, "The sharing playback failed outside the HTTP path.")
    wait_for_new_execution(auth, task["Id"], share_previous, timeout=MAX_WAIT)
    backend_count = len([event for event in delay_request_events(media_container(), since=round_started)
                         if event["request_id"] == request_id])
    require(backend_count == 1, f"The batch and playback must share exactly one backend probe, observed {backend_count}.")
    summary_line = latest_summary()
    fields = batch.summary_fields(summary_line)
    batch.assert_summary_equations(fields)
    expected_calls = 0 if playback_first else 1
    require((fields.get("actual_probe_calls") or 0) == expected_calls,
            f"The sharing batch actual call count is wrong for this order: {summary_line}.")
    require((fields.get("reliable_success") or 0) == 1, f"The shared source must count once as a reliable success: {summary_line}.")
    row = fingerprint_row(item["Id"])
    require(row is not None and row["url_hash"] == expected_url_hash(target_url),
            "The shared probe did not commit the new address.")
    return {"direction": "playback_first" if playback_first else "batch_first",
            "backend_probe_requests": backend_count, "actual_probe_calls": fields.get("actual_probe_calls"),
            "reliable_success": fields.get("reliable_success"), "summary": summary_line}


def _mixed_concurrency(auth: str, libraries: dict[str, str], nonce: str) -> dict:
    """A batch probe and a concurrent playback probe on a different source, peak attributed per owner."""
    media_sha, media_size = pe.media_sha1(pe.MEDIA_MP4)
    plain_url = "http://media:8080/" + pe.MEDIA_MP4
    batch_name = f"Scan Mixed Batch {nonce}"
    playback_name = f"Scan Mixed Playback {nonce}"
    batch_path = write_strm_to(pe.WORK / "strm", batch_name, plain_url, media_sha, media_size)
    playback_path = write_strm_to(pe.WORK / "media", playback_name, plain_url, media_sha, media_size)
    refresh_library(auth)
    batch_item = wait_for_item(auth, batch_name)
    playback_item = wait_for_item(auth, playback_name)
    run_plugin_task(auth)
    require(fingerprint_row(batch_item["Id"]) is not None, "The mixed batch source did not get a baseline.")
    batch_id = uuid.uuid4().hex
    playback_id = uuid.uuid4().hex
    batch_url = delay_url(plain_url, PROBE_DELAY_SECONDS, batch_id)
    playback_url = delay_url(plain_url, PROBE_DELAY_SECONDS, playback_id)
    rewrite_strm(batch_path, batch_url, media_sha, media_size)
    rewrite_strm(playback_path, playback_url, media_sha, media_size)
    round_started = datetime.datetime.now(datetime.timezone.utc)
    holder: dict = {}

    def playback() -> None:
        try:
            holder["result"] = playback_info(auth, playback_item["Id"])
        except Exception as error:
            holder["error"] = type(error).__name__

    task = find_task_by_key(auth, TASK_KEY)
    mixed_previous = last_start(task)
    require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the mixed batch start.")
    wait_for_delay(batch_id, round_started)
    worker = threading.Thread(target=playback, name="scan-mixed-playback", daemon=True)
    worker.start()
    wait_for_delay(playback_id, round_started)
    worker.join(timeout=MAX_WAIT)
    require(not worker.is_alive(), "The mixed playback did not finish.")
    require("error" not in holder, "The mixed playback failed outside the HTTP path.")
    wait_for_new_execution(auth, task["Id"], mixed_previous, timeout=MAX_WAIT)
    entries = probe_start_events(container(), since=round_started)
    peak = max((entry["running"] for entry in entries), default=0)
    playback_probe = probe_start_for_item(entries, playback_item["Id"])
    batch_probe = probe_start_for_item(entries, batch_item["Id"])
    require(batch_probe is not None, "No batch probe start was observed in the mixed run.")
    require(playback_probe is not None, "No playback probe start was observed in the mixed run.")
    require(peak == 2, f"The mixed overlap never reached the default concurrency of 2: peak {peak}.")
    require(playback_probe["running"] == 2, f"The playback probe did not overlap a batch probe: {playback_probe}.")
    summary_line = latest_summary()
    fields = batch.summary_fields(summary_line)
    batch.assert_summary_equations(fields)
    require((fields.get("actual_probe_calls") or 0) == 1, f"The mixed batch must start exactly one scoped call: {summary_line}.")
    return {"peak_running_probes": peak, "playback_start_running": playback_probe["running"],
            "batch_owner_started": True, "configured_concurrency": 2, "summary": summary_line}


def scenario_recovery(package: Path, evidence_dir: Path | None, nonce: str) -> dict:
    summary: dict[str, object] = {}
    auth = deploy_fresh(package)
    media_sha, media_size = pe.media_sha1(pe.MEDIA_MP4)
    plain_url = "http://media:8080/" + pe.MEDIA_MP4
    ordinary_file = f"Scan Ordinary {nonce}.mp4"
    ordinary_name = f"Scan Ordinary {nonce}"
    pe.copy_owned(pe.WORK / "media" / pe.MEDIA_MP4, pe.WORK / "strm" / ordinary_file, label="ordinary media")
    legacy_name = f"Scan Legacy {nonce}"
    pe.write_owned_bytes(pe.WORK / "strm" / (legacy_name + ".strm"),
                         (plain_url + "\n").encode(), label="legacy STRM")
    versioned_name = f"Scan Recover {nonce}"
    write_strm_to(pe.WORK / "strm", versioned_name, plain_url, media_sha, media_size)
    refresh_library(auth)
    ordinary_item = wait_for_item(auth, ordinary_name)
    legacy_item = wait_for_item(auth, legacy_name)
    versioned_item = wait_for_item(auth, versioned_name)
    scope_all_libraries(auth)
    run_plugin_task(auth)
    require(fingerprint_row(versioned_item["Id"]) is not None, "The recovery scenario could not establish a baseline.")
    for item, label in ((ordinary_item, "ordinary"), (legacy_item, "legacy")):
        before = plugin_events()
        status, response = playback_info(auth, item["Id"])
        require(status == 200 and response.get("MediaSources"), f"The {label} input did not return a native source.")
        require(pkg.event_delta(before, plugin_events()) == [], f"The plugin intercepted the {label} input.")
    summary["delegated_inputs"] = True

    # Disabling the plugin must start no new batch probe.
    configure(auth, {"Enabled": False, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2,
                     "DetailedLog": False, "BatchAllLibraries": True, "BatchLibraryIds": ""})
    before = len(delay_request_events(media_container()))
    run_plugin_task(auth)
    require(len(delay_request_events(media_container())) == before, "A disabled plugin still started a delayed probe request.")
    scope_all_libraries(auth)
    summary["disabled_no_probe"] = True

    # A SQLite global fault must fail the task without starting a probe and recover after restart.
    database = pkg.fingerprint_database()
    require(database.is_file(), "The plugin fingerprint database is missing.")
    backup = database.with_suffix(".db.bak-" + uuid.uuid4().hex[:8])
    shutil.copy2(database, backup)
    try:
        database.unlink()
        database.mkdir()
        before = len(delay_request_events(media_container()))
        final = run_plugin_task(auth)
        status_value = str((final.get("LastExecutionResult") or {}).get("Status", "")).lower()
        require(status_value in {"failed", "3"}, f"A SQLite fault did not fail the task: {status_value}.")
        require(len(delay_request_events(media_container())) == before, "A SQLite fault still started a probe.")
        summary["store_fault"] = {"status": status_value}
    finally:
        if database.is_dir():
            database.rmdir()
        shutil.move(str(backup), str(database))
    restart()
    auth = api_auth()
    recovered = run_plugin_task(auth)
    require(str((recovered.get("LastExecutionResult") or {}).get("Status", "")).lower() in {"completed", "0"},
            "The batch task did not recover after the store was restored.")
    summary["store_recovered"] = True
    return summary


# ---------------------------------------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--scenario", default="all", choices=["all", "overlap", "stop", "recovery", "controls"])
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--workspace", type=Path,
                        help="Fresh run-owned workspace under artifacts/package-env (default: auto-created).")
    parser.add_argument("--keep-workspace", action="store_true",
                        help="Leave this run's workspace and instance in place for inspection (default: clean up).")
    args = parser.parse_args()

    package = args.package.resolve()
    evidence_dir = args.evidence_dir.resolve() if args.evidence_dir else None
    nonce = uuid.uuid4().hex[:8]
    summary: dict[str, object] = {"scenario": args.scenario, "package": str(package), "run_id": nonce}
    exit_code = 1
    before_state = None
    workspace = None
    try:
        verification = pp.verify_archive(package)
        summary["package_identity"] = {
            "archiveSha256": verification["archiveSha256"], "version": verification["version"],
            "guid": verification["guid"], "targetAbi": verification["targetAbi"],
            "runtime": verification["runtime"], "entries": verification["entries"],
        }
        workspace = pe.select_workspace(args.workspace)
        summary["workspace"] = str(workspace)
        before_state = pe.capture_instance_state()
        if args.scenario in {"all", "overlap"}:
            summary["overlap"] = scenario_overlap(package, evidence_dir, nonce)
        if args.scenario in {"all", "controls"}:
            summary["controls"] = scenario_controls(package, evidence_dir, nonce)
        if args.scenario in {"all", "stop"}:
            summary["stop_scenario"] = scenario_stop(package, evidence_dir, nonce)
        if args.scenario in {"all", "recovery"}:
            summary["recovery"] = scenario_recovery(package, evidence_dir, nonce)
        summary["status"] = "PASS"
        exit_code = 0
    except (RuntimeError, OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError,
            pp.PackageError, pe.PackageEnvironmentError) as error:
        summary["status"] = "FAIL"
        summary["error"] = f"{type(error).__name__}: {error}"
        exit_code = 1
    finally:
        # Restore and verify every native scheduled-task trigger recorded on the first fresh
        # instance, so a scenario failure cannot leave an administrator trigger behind.
        if ORIGINAL_TRIGGERS is not None:
            try:
                restore_triggers(api_auth(), ORIGINAL_TRIGGERS)
                summary["trigger_restoration"] = "restored and verified"
            except Exception as trigger_error:
                summary["trigger_restoration"] = f"NOT RESTORED: {type(trigger_error).__name__}: {trigger_error}"
                summary["status"] = "FAIL"
                exit_code = 1
        if before_state is not None:
            try:
                summary["instance_reconciliation"] = pe.reconcile_instance_state(before_state)
            except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError) as teardown_error:
                summary["teardown_error"] = f"{type(teardown_error).__name__}: {teardown_error}"
                summary["status"] = "FAIL"
                exit_code = 1
        if workspace is not None and not args.keep_workspace:
            try:
                summary["cleanup"] = pe.cleanup_instance()
            except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError) as cleanup_error:
                summary["cleanup_error"] = f"{type(cleanup_error).__name__}: {cleanup_error}"
                summary["status"] = "FAIL"
                exit_code = 1
        if evidence_dir is not None:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / "scan-integration-result.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
