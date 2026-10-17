#!/usr/bin/env python3
"""Acceptance for the full native library scan overlapping playback and batch probes.

This tool consumes the single-version plugin ZIP under test and installs it into the
dedicated package-acceptance instance (``scripts/package_environment.py``); it never calls
the development deployment helper and never mounts the source tree. It drives the real
native full library scan task (key ``RefreshLibrary``) and the plugin batch task (key
``StrmProbeOptimizerBatchCheck``) against isolated libraries and synthetic media.

The scenarios:
  all       overlap + controls + stop + recovery in one session, with failures preserved
  overlap   a real native full scan whose Running interval intersects actually started batch
            and playback probes; finite add/delete/move/URL/content changes issued while the
            scan is Running and the probes are executing; URL re-change during a probe;
            multi-version isolation; an independent FullRefresh; a converging stable-set
            re-check with per-source reconciliation and restart
  controls  real timed trigger, two-direction same-source sharing, different-source mixed
            concurrency peak on the ZIP-installed candidate
  stop      real native stop of a cross-batch batch with started and unstarted work: started
            work settles and commits, unstarted work is revoked, a re-run during the drain is
            refused, and a later run converges
  recovery  single-item media failure isolation, disabled / ordinary / legacy inputs
            delegate, a SQLite global fault fails the task without probing and recovers

Evidence is recorded incrementally into ``--evidence-dir`` (events.jsonl, per-round
snapshots, an INDEX and the final result). Only redacted digests and identities are stored;
no signed URL, token, cookie or private path is ever written.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
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
# A shorter delay for the stop scenario, so the started probes are still executing when the stop is issued
# while the convergence round stays bounded.
STOP_DELAY_SECONDS = 12

# Every counter a completed batch summary must report. A missing field is a hard failure: it must
# never silently become a zero that trivially satisfies a later "== 0" probe assertion.
REQUIRED_SUMMARY_FIELDS = (
    "candidates", "raw_candidates", "duplicates", "checked", "skipped", "first_trust",
    "need_probe", "reliable_success", "probe_incomplete", "check_stage_incomplete",
    "not_processed", "missing", "revoked", "read_incomplete", "unread", "actual_probe_calls",
    "batch_reads", "candidate_fetch_ms", "batch_read_ms",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return pe.run(*args, timeout=timeout)


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------------------------------
# Evidence recorder (BR-42-4)
# ---------------------------------------------------------------------------------------------------------------------

_SCRUB_KEYS = ("url", "path", "token", "password", "cookie", "authorization", "access")


def _scrub(value: object, key: str = "") -> object:
    """Redact anything that could carry a signed URL, token, cookie or private path."""
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _scrub(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(item, key) for item in value]
    if isinstance(value, str) and any(marker in key.lower() for marker in _SCRUB_KEYS):
        return {"sha256": digest(value), "length": len(value)}
    return value


class EvidenceRecorder:
    """Incrementally persist redacted, reviewable evidence outside the instance workspace."""

    def __init__(self, directory: Path, run_id: str) -> None:
        self.directory = directory
        self.run_id = run_id
        self.rounds_dir = directory / "rounds"
        self.rounds_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = directory / "events.jsonl"
        self.events_path.write_text("", encoding="utf-8")
        self.monotonic_origin = time.monotonic()
        self.source = self._source_identity()
        self.record("run_start", source=self.source, run_id=run_id)

    @staticmethod
    def _source_identity() -> dict:
        head = run("git", "rev-parse", "HEAD").stdout.strip()
        status = run("git", "status", "--porcelain").stdout
        tracked = run("git", "diff", "HEAD", "--stat").stdout
        return {"head": head, "dirty": bool(status.strip()),
                "status_sha256": digest(status), "tracked_diff_sha256": digest(tracked)}

    def record(self, kind: str, **data: object) -> None:
        line = {
            "utc": now_utc().isoformat(),
            "monotonic": round(time.monotonic() - self.monotonic_origin, 6),
            "run_id": self.run_id,
            "kind": kind,
            "data": _scrub(data),
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")

    def snapshot(self, name: str, data: object) -> None:
        path = self.rounds_dir / (name + ".json")
        path.write_text(json.dumps(_scrub(data), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def finish(self, status: str, summary: dict, raw_files: dict[str, str]) -> None:
        (self.directory / "result.json").write_text(
            json.dumps(_scrub(summary), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        index = ["# Scan acceptance evidence index", "",
                 f"- Run id: `{self.run_id}`",
                 f"- Source head: `{self.source['head']}` (dirty: {self.source['dirty']})",
                 f"- Overall status: **{status}**", "",
                 "## Raw files", ""]
        for name, description in raw_files.items():
            index.append(f"- `{name}` — {description}")
        index.append("")
        index.append("`events.jsonl` is append-only; `rounds/` holds per-round snapshots. "
                     "All URLs/tokens/paths are stored as SHA-256 digests only.")
        (self.directory / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------------------------------------------------
# Native API helpers (package instance)
# ---------------------------------------------------------------------------------------------------------------------


def api_auth() -> str:
    return pkg.api_auth()


def container() -> str:
    return pe.container_name("jellyfin")


def media_container() -> str:
    return pe.container_name("media")


def container_identity() -> dict:
    result = run("docker", "inspect", "--format", "{{.Id}} {{.State.StartedAt}}", container(), timeout=30)
    require(result.returncode == 0, "Could not read the package Jellyfin container identity.")
    return {"identity": result.stdout.strip()}


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


def task_result(task: dict) -> dict:
    return task.get("LastExecutionResult") or {}


def task_status(task: dict) -> str:
    return str(task_result(task).get("Status", "")).lower()


def last_start(task: dict) -> str | None:
    return task_result(task).get("StartTimeUtc")


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
    """Wait until a new execution has started and settled; do not require any particular status."""
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


def execution_interval(task: dict) -> tuple[datetime.datetime, datetime.datetime]:
    result = task_result(task)
    start = result.get("StartTimeUtc")
    end = result.get("EndTimeUtc")
    require(bool(start) and bool(end), f"The native task has no execution interval: {result}.")
    return (_parse_utc(start), _parse_utc(end))


def require_completed_execution(task: dict, previous_start: str | None, label: str) -> tuple[datetime.datetime, datetime.datetime]:
    """Require this round's own execution to have reached a successful Completed terminal state."""
    result = task_result(task)
    status = task_status(task)
    require(status in {"completed", "0"},
            f"The {label} did not complete (status {status!r}); a Failed/Cancelled/timeout result is never accepted: {result}.")
    require(bool(result.get("StartTimeUtc")) and bool(result.get("EndTimeUtc")),
            f"The {label} Completed without a full start/end interval: {result}.")
    require(result.get("StartTimeUtc") != previous_start,
            f"The {label} result belongs to the previous round (start {result.get('StartTimeUtc')}).")
    return execution_interval(task)


def run_plugin_task(auth: str, timeout: int = MAX_WAIT) -> dict:
    task = find_task_by_key(auth, TASK_KEY)
    previous = last_start(task)
    require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the manual batch task start.")
    return wait_for_new_execution(auth, task["Id"], previous, timeout)


def run_plugin_task_completed(auth: str, label: str, timeout: int = MAX_WAIT) -> dict:
    task = find_task_by_key(auth, TASK_KEY)
    previous = last_start(task)
    require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the manual batch task start.")
    final = wait_for_new_execution(auth, task["Id"], previous, timeout)
    require_completed_execution(final, previous, label)
    return final


def run_native_scan_completed(auth: str, label: str, timeout: int = MAX_WAIT) -> tuple[dict, tuple[datetime.datetime, datetime.datetime]]:
    task = find_task_by_key(auth, SCAN_TASK_KEY)
    previous = last_start(task)
    require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the native full scan start.")
    final = wait_for_new_execution(auth, task["Id"], previous, timeout)
    interval = require_completed_execution(final, previous, label)
    return final, interval


def plugin_status(auth: str) -> str:
    return pkg.plugin_status(auth)


def plugin_action(auth: str, enabled: bool) -> int:
    return pkg.plugin_action(auth, enabled)


def restart() -> str:
    return pkg.restart()


def item_by_name(auth: str, name: str) -> dict:
    """Resolve one library item by name with a high limit so a large fixture set is not truncated."""
    status, payload = pe.request_json(
        "GET", "/Items?" + "Recursive=true&Limit=5000&Fields=MediaSources,Path,MediaStreams",
        headers={"Authorization": auth})
    require(status == 200, "The package-instance item listing failed.")
    matches = [item for item in payload.get("Items", []) if item.get("Name") == name]
    require(len(matches) == 1, f"Expected exactly one package-instance item named {name!r}, found {len(matches)}.")
    return matches[0]


def native_items(auth: str) -> list[dict]:
    status, payload = pe.request_json(
        "GET", "/Items?" + "Recursive=true&Limit=5000&Fields=MediaSources,Path,MediaStreams",
        headers={"Authorization": auth})
    require(status == 200, "The package-instance item listing failed.")
    return payload.get("Items", [])


def wait_for_item(auth: str, name: str, timeout: int = 120) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return item_by_name(auth, name)
        except RuntimeError:
            time.sleep(0.5)
    raise RuntimeError(f"The package instance did not scan the item {name!r}.")


def wait_for_item_absent(auth: str, name: str, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, payload = pe.request_json(
            "GET", "/Items?" + "Recursive=true&Limit=5000&Fields=Path",
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


def expected_url_hash(url: str) -> str:
    return pkg.expected_url_hash(url)


def source_path_matches_hash(response: dict, expected_hash: str) -> bool:
    import hashlib as _hashlib

    for source in response.get("MediaSources", []):
        path = source.get("Path") or ""
        if _hashlib.sha256(path.encode()).hexdigest() == expected_hash:
            return True
    return False


def library_roots(auth: str) -> dict[str, str]:
    """Map a library directory suffix (strm/local/...) to its native folder id."""
    status, folders = pe.request_json("GET", "/Library/VirtualFolders", headers={"Authorization": auth})
    require(status == 200, "The virtual-folder listing failed.")
    by_suffix: dict[str, str] = {}
    for folder in folders:
        for info in folder.get("LibraryOptions", {}).get("PathInfos", []):
            suffix = str(info.get("Path", "")).rstrip("/").rsplit("/", 1)[-1]
            if suffix:
                by_suffix[suffix] = folder["ItemId"]
    return by_suffix


def library_root_path(auth: str, library_id: str) -> str:
    status, folders = pe.request_json("GET", "/Library/VirtualFolders", headers={"Authorization": auth})
    require(status == 200, "The virtual-folder listing failed.")
    for folder in folders:
        if folder.get("ItemId") == library_id:
            paths = [str(info.get("Path", "")) for info in folder.get("LibraryOptions", {}).get("PathInfos", [])]
            require(len(paths) == 1, f"Expected exactly one root for library {library_id!r}: {paths}.")
            return paths[0].rstrip("/")
    raise RuntimeError(f"No native library matched id {library_id!r}.")


def refresh_library(auth: str) -> None:
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


def docker_log_lines(name: str, tail: int = 30000) -> list[str]:
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


def _parse_utc(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


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


def probe_outcome_events(name: str, since: datetime.datetime | None = None) -> list[dict]:
    """Return per-item probe terminal events (accepted/rejected/failed/changed) with UTC times."""
    patterns = {
        "accepted": "Native probe accepted for STRM item",
        "failed": "Native STRM probe failed for item",
        "canceled": "Native STRM probe canceled for item",
        "not_committed": "Native probe result was not committed for item",
        "manifest_changed": "STRM manifest changed during native probe for item",
    }
    entries: list[dict] = []
    for line in docker_log_lines(name):
        timestamp = parse_docker_timestamp(line)
        if timestamp is None:
            continue
        if since is not None and timestamp < since:
            continue
        for kind, marker in patterns.items():
            if marker in line:
                item = re.search(r"item ([0-9a-fA-F-]+)", line)
                entries.append({"kind": kind, "item_id": item.group(1).lower().replace("-", "") if item else None,
                                "timestamp": timestamp})
                break
    return entries


def backend_request_events(name: str, since: datetime.datetime | None = None) -> list[dict]:
    """Return the delayed backend probe start and observed finish markers with UTC times."""
    entries: list[dict] = []
    for line in docker_log_lines(name):
        timestamp = parse_docker_timestamp(line)
        if timestamp is None:
            continue
        if since is not None and timestamp < since:
            continue
        for marker, kind in (("SLOW_MEDIA_REQUEST_STARTED ", "start"), ("PROBE_MEDIA_REQUEST_FINISHED ", "finish")):
            if marker in line:
                request_id = line.split(marker, 1)[1].strip()
                entries.append({"kind": kind, "request_id": request_id, "timestamp": timestamp})
                break
    return entries


def probe_start_for_item(events: list[dict], item_id: str) -> dict | None:
    key = item_id.lower().replace("-", "")
    return next((event for event in events if event["item_id"] == key), None)


def batch_entry_events(since: datetime.datetime | None = None, tail: int = 8000) -> list[dict]:
    """Return the plugin task's ExecuteAsync entry markers with UTC times."""
    entries: list[dict] = []
    for line in docker_log_lines(container(), tail=tail):
        if "STRM media information check entered" not in line:
            continue
        timestamp = parse_docker_timestamp(line)
        if timestamp is None:
            continue
        if since is not None and timestamp < since:
            continue
        entries.append({"timestamp": timestamp})
    return entries


def task_completion_events(since: datetime.datetime | None = None) -> list[dict]:
    """Return the native worker terminal statuses for the batch task with UTC times."""
    events: list[dict] = []
    for line in docker_log_lines(container()):
        if TASK_NAME not in line or " after " not in line:
            continue
        timestamp = parse_docker_timestamp(line)
        if timestamp is None:
            continue
        if since is not None and timestamp < since:
            continue
        for status in ("Completed", "Cancelled", "Failed", "Aborted"):
            if f"{TASK_NAME} {status} after" in line:
                events.append({"status": status, "timestamp": timestamp})
                break
    return events


def intervals_intersect(a_start: datetime.datetime, a_end: datetime.datetime,
                        b_start: datetime.datetime, b_end: datetime.datetime) -> bool:
    return a_start <= b_end and b_start <= a_end


def assert_scan_probe_overlap(scan_interval: tuple[datetime.datetime, datetime.datetime],
                              probe_start: datetime.datetime, probe_end: datetime.datetime,
                              label: str) -> dict:
    """Fail unless the scan interval and an actually started probe execution truly intersect.

    ``probe_start``/``probe_end`` bound one real probe execution: the observed backend request
    start and its observed completion. A queued, permitted or merely accepted request is never
    accepted, and a computed (configured-delay) end is never accepted.
    """
    scan_start, scan_end = scan_interval
    require(probe_end > probe_start, f"The {label} probe has no positive observed execution interval.")
    require(intervals_intersect(scan_start, scan_end, probe_start, probe_end),
            f"The native scan interval [{scan_start.isoformat()}, {scan_end.isoformat()}] does not intersect "
            f"the observed {label} probe interval [{probe_start.isoformat()}, {probe_end.isoformat()}].")
    return {"scan_start": scan_start.isoformat(), "scan_end": scan_end.isoformat(),
            "probe_start": probe_start.isoformat(), "probe_end": probe_end.isoformat(), "overlapped": True}


def require_change_in_window(op_time: datetime.datetime,
                             scan_interval: tuple[datetime.datetime, datetime.datetime],
                             label: str) -> None:
    """A finite change must be issued while the native scan is actually Running (BR-42-1)."""
    scan_start, scan_end = scan_interval
    require(scan_start <= op_time <= scan_end,
            f"The {label} change at {op_time.isoformat()} was issued outside the Running scan interval "
            f"[{scan_start.isoformat()}, {scan_end.isoformat()}]; a post-scan change does not satisfy BR-42-1.")


def require_captured(captured_source_ids: set[str], source_id: str, label: str) -> None:
    """A delete/move-out target must have actually belonged to the fixed candidate set (BR-42-1)."""
    key = source_id.lower().replace("-", "")
    require(key in captured_source_ids,
            f"The {label} target {source_id} was never in the captured candidate set; deleting an object that "
            "was not part of the fixed set does not prove in-round settlement.")


def require_no_new_round(entries_before_settlement: int, entries_before_stop: int, label: str) -> None:
    """A re-run or timer must not actually enter a new round while the old round is draining (BR-42-3)."""
    require(entries_before_settlement == entries_before_stop,
            f"A {label} actually entered a new round during the stopped round's drain "
            f"({entries_before_settlement} > {entries_before_stop} entries before settlement).")


def require_no_probe_during_drain(probes_during_drain: list[dict]) -> None:
    """No new probe may start after the stop, before the stopped round settles (BR-42-3)."""
    require(not probes_during_drain,
            f"A new probe started during the stopped round's drain: {probes_during_drain}.")


def require_progress_below_100(progress_during_cancel: list[float]) -> None:
    """A stopped round must not report Completed/100% while it is Cancelling (BR-42-3)."""
    require(all(value < 100.0 for value in progress_during_cancel),
            f"The stopped round reported 100% while cancelling: {progress_during_cancel}.")


def require_no_new_activity(before: dict[str, int], after: dict[str, int], label: str) -> None:
    """A disabled / faulted plugin must start no backend or plugin probe on any route (BR-42-3)."""
    require(before == after,
            f"{label} still started backend/probe work on some route: {before} -> {after}.")


# ---------------------------------------------------------------------------------------------------------------------
# Summary binding
# ---------------------------------------------------------------------------------------------------------------------


def latest_summary_after(round_started: datetime.datetime) -> str | None:
    """Return the latest redacted batch summary whose own UTC timestamp is at or after the round start."""
    lines = [line for line in docker_log_lines(container()) if "STRM media information check finished" in line]
    for line in reversed(lines):
        timestamp = parse_docker_timestamp(line)
        if timestamp is not None and timestamp >= round_started:
            return batch.base.safe_event(line)
    return None


def first_summary_after(round_started: datetime.datetime) -> str | None:
    """Return the earliest redacted batch summary at or after the round start (the stopped round's own
    summary, before any queued re-run that settles after it)."""
    lines = [line for line in docker_log_lines(container()) if "STRM media information check finished" in line]
    for line in lines:
        timestamp = parse_docker_timestamp(line)
        if timestamp is not None and timestamp >= round_started:
            return batch.base.safe_event(line)
    return None


def summary_fields_complete(summary_line: str | None) -> dict:
    """Parse a summary and require every counter to be present; a missing field is a hard failure."""
    require(summary_line is not None, "No batch summary was emitted for this round.")
    fields = batch.summary_fields(summary_line)
    missing = [name for name in REQUIRED_SUMMARY_FIELDS if fields.get(name) is None]
    require(not missing, f"The batch summary is missing required counter(s) {missing}: {summary_line}.")
    batch.assert_summary_equations(fields)
    return fields


def require_zero_probes(fields: dict, summary_line: str, label: str) -> None:
    require(fields.get("actual_probe_calls") == 0,
            f"The {label} performed plugin probes although none were expected: {summary_line}.")


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


def missing_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    parent = parts.path.rsplit("/", 1)[0]
    return urlunsplit((parts.scheme, parts.netloc, parent + "/missing-" + uuid.uuid4().hex + ".mp4", "", ""))


def unique_url(base_url: str, key: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode({"scan_case": key}), ""))


def native_prepare_stream(auth: str, item: dict, url: str, timeout: int = 120) -> bool:
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
    removed = 0
    for directory in (pe.WORK / "strm", pe.WORK / "media"):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.strm")):
            pe.require_owned_path(path, label=f"scenario fixture {path.name}")
            path.unlink()
            removed += 1
    return removed


ORIGINAL_TRIGGERS: dict[str, list[dict]] | None = None


def deploy_fresh(package: Path) -> str:
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
    libraries = library_roots(auth)
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


def capture_candidate_sources(auth: str, library_id: str) -> set[str]:
    """The fixed candidate identity set as the native source ids under the selected library root."""
    root = library_root_path(auth, library_id)
    ids: set[str] = set()
    for item in native_items(auth):
        path = item.get("Path") or ""
        if not path.startswith(root):
            continue
        for source in item.get("MediaSources", []):
            if source.get("Id"):
                ids.add(str(source["Id"]).lower().replace("-", ""))
    return ids


def bulk_fixture(auth: str, nonce: str) -> dict:
    strm_dir = pe.WORK / "strm"
    local_dir = pe.WORK / "media"
    media_sha, media_size = pe.media_sha1(pe.MEDIA_MP4)
    plain_url = "http://media:8080/" + pe.MEDIA_MP4
    bulk_names = [f"Scan Bulk {nonce} {index:03d}" for index in range(BULK_COUNT)]
    for name in bulk_names:
        write_strm_to(strm_dir, name, plain_url, media_sha, media_size)
    out_name = f"Scan Out Of Scope {nonce}"
    write_strm_to(local_dir, out_name, plain_url, media_sha, media_size)
    playback_name = f"Scan Playback {nonce}"
    write_strm_to(local_dir, playback_name, plain_url, media_sha, media_size)
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
    round_started = now_utc()
    run_plugin_task_completed(auth, "baseline first-trust run")
    summary = latest_summary_after(round_started)
    fields = summary_fields_complete(summary)
    require_zero_probes(fields, summary, "baseline first-trust run")
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


def wait_for_backend_event(request_id: str, kind: str, since: datetime.datetime, timeout: int = 90) -> datetime.datetime:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        matches = [event for event in backend_request_events(media_container(), since=since)
                   if event["request_id"] == request_id and event["kind"] == kind]
        if matches:
            return matches[0]["timestamp"]
        time.sleep(0.2)
    raise RuntimeError(f"The delayed backend request {request_id} never observed a {kind} event.")


def wait_for_scan_running(auth: str, task_id: str, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = next((task for task in task_list(auth) if task.get("Id") == task_id), None)
        require(task is not None, "The native scan task disappeared while waiting for Running.")
        if task_state_name(task) in {"running", "1"}:
            return
        if task_state_name(task) in {"idle", "0"} and task_status(task) in {"completed", "failed", "cancelled"}:
            # It already settled; the window was too short to observe Running.
            raise RuntimeError("The native scan settled before its Running state could be observed.")
        time.sleep(0.05)
    raise RuntimeError("The native scan never reported Running.")


def overlap_round(auth: str, fixture: dict, recorder: EvidenceRecorder) -> dict:
    """Real three-way overlap with finite changes issued while the scan is Running."""
    items = fixture["items"]
    libraries = library_roots(auth)
    captured = capture_candidate_sources(auth, libraries["strm"])
    require(len(captured) >= BULK_COUNT, f"The selected library captured too few candidate sources: {len(captured)}.")

    batch_id = uuid.uuid4().hex
    playback_id = uuid.uuid4().hex
    batch_path = fixture["strm_dir"] / (fixture["batch_name"] + ".strm")
    playback_path = fixture["local_dir"] / (fixture["playback_name"] + ".strm")
    content_path = fixture["strm_dir"] / (fixture["content_name"] + ".strm")
    size_path = fixture["strm_dir"] / (fixture["size_name"] + ".strm")

    batch_b_url = delay_url(fixture["plain_url"], PROBE_DELAY_SECONDS, batch_id)
    playback_url = delay_url(fixture["plain_url"], PROBE_DELAY_SECONDS, playback_id)
    batch_c_url = unique_url(fixture["plain_url"], "batch-c-" + uuid.uuid4().hex[:8])
    rewrite_strm(batch_path, batch_b_url, fixture["media_sha"], fixture["media_size"])
    rewrite_strm(playback_path, playback_url, fixture["media_sha"], fixture["media_size"])
    recorder.record("overlap_prepare", batch_sha=digest(batch_b_url), playback_sha=digest(playback_url))

    round_started = now_utc()
    container_before = container_identity()
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
    batch_backend_start = wait_for_backend_event(batch_id, "start", round_started)
    playback_backend_start = wait_for_backend_event(playback_id, "start", round_started)
    probe_starts = probe_start_events(container(), since=round_started)
    batch_probe = probe_start_for_item(probe_starts, items[fixture["batch_name"]]["Id"])
    playback_probe = probe_start_for_item(probe_starts, items[fixture["playback_name"]]["Id"])
    require(batch_probe is not None, f"No real plugin probe start was observed for the batch source: {probe_starts}.")
    require(playback_probe is not None, f"No real plugin probe start was observed for the playback source: {probe_starts}.")

    # Trigger the native full scan and wait until it is actually Running before mutating anything.
    scan_task = find_task_by_key(auth, SCAN_TASK_KEY)
    scan_previous = last_start(scan_task)
    require(start_task(auth, scan_task["Id"]) == 204, "Jellyfin did not accept the native full scan start.")
    wait_for_scan_running(auth, scan_task["Id"])
    scan_running_observed = now_utc()

    # -- Finite changes issued while the scan is Running and both probes are executing --
    changes: list[dict] = []
    # URL B -> C on the source whose batch probe is actually running: B must never commit.
    rewrite_strm(batch_path, batch_c_url, fixture["media_sha"], fixture["media_size"])
    changes.append({"change": "batch_url_b_to_c", "utc": now_utc().isoformat(), "c_sha": digest(batch_c_url)})
    # Content SHA-1 change at the same URL on a not-started source.
    rewrite_strm(content_path, fixture["plain_url"], "a" * 40, fixture["media_size"])
    changes.append({"change": "content_sha1", "utc": now_utc().isoformat()})
    # SHA-1 incomparable + valid Size change on another source.
    rewrite_strm(size_path, fixture["plain_url"], None, fixture["media_size"] + 1)
    changes.append({"change": "size_only", "utc": now_utc().isoformat()})

    # Wait for the scan to reach its authoritative Completed terminal state.
    scan_after = wait_for_new_execution(auth, scan_task["Id"], scan_previous, timeout=MAX_WAIT)
    scan_interval = require_completed_execution(scan_after, scan_previous, "overlap native scan")

    final = wait_for_new_execution(auth, batch_task["Id"], batch_previous, timeout=MAX_WAIT)
    worker.join(timeout=MAX_WAIT)
    require(not worker.is_alive(), "The overlap playback did not finish.")
    require("error" not in playback_holder, "The overlap playback failed outside the HTTP path.")
    require_completed_execution(final, batch_previous, "overlap batch")

    # Every in-window change must have been issued while the scan was Running.
    for change in changes:
        require_change_in_window(_parse_utc(change["utc"]), scan_interval, change["change"])

    batch_backend_finish = wait_for_backend_event(batch_id, "finish", round_started)
    playback_backend_finish = wait_for_backend_event(playback_id, "finish", round_started)
    scan_overlap = {
        "batch": assert_scan_probe_overlap(scan_interval, batch_backend_start, batch_backend_finish, "batch"),
        "playback": assert_scan_probe_overlap(scan_interval, playback_backend_start, playback_backend_finish, "playback"),
    }

    # B must be rejected and the trusted A baseline preserved; the next run must commit C.
    batch_row = fingerprint_row(items[fixture["batch_name"]]["Id"])
    require(batch_row is not None and batch_row["url_hash"] == expected_url_hash(fixture["plain_url"]),
            f"The URL changed during the batch probe was committed as the trusted fingerprint: {batch_row}.")
    require(batch_row["url_hash"] != expected_url_hash(batch_c_url),
            "The mid-probe C address was committed without a real successful probe.")
    outcomes = probe_outcome_events(container(), since=round_started)
    batch_outcomes = [event for event in outcomes
                      if event["item_id"] == items[fixture["batch_name"]]["Id"].lower().replace("-", "")]
    require(any(event["kind"] in {"manifest_changed", "failed", "not_committed"} for event in batch_outcomes),
            f"No mid-probe rejection/change event was observed for the batch source: {batch_outcomes}.")

    round_summary = latest_summary_after(round_started)
    fields = summary_fields_complete(round_summary)
    recorder.record("overlap_round", container=container_before, scan=scan_interval, overlap=scan_overlap,
                    changes=changes, summary=fields)
    recorder.snapshot("overlap-round", {"scan": scan_overlap, "changes": changes, "fields": fields,
                                        "batch_probe_start": batch_probe, "playback_probe_start": playback_probe})

    result = {
        "captured_candidates": len(captured),
        "scan_interval": [scan_interval[0].isoformat(), scan_interval[1].isoformat()],
        "scan_running_observed": scan_running_observed.isoformat(),
        "overlap": scan_overlap,
        "changes_in_window": changes,
        "batch_baseline_preserved": True,
        "playback_address": source_for_url(playback_holder["result"][1], playback_url) is not None,
        "overlap_summary": round_summary,
        "actual_probe_calls": fields.get("actual_probe_calls"),
    }
    # The playback source is out of scope and probes its own changed address.
    require(result["playback_address"], "The playback source did not return its changed address after the overlap.")
    return result


def finite_changes(auth: str, fixture: dict, recorder: EvidenceRecorder) -> dict:
    """Content / size changes, the C convergence and add / delete / move scope changes."""
    items = fixture["items"]
    result: dict[str, object] = {}

    # The content SHA-1, size-only and mid-probe C changes were all issued during the overlap window
    # and must all be committed by a real probe in the next fixed-set round.
    batch_path = fixture["strm_dir"] / (fixture["batch_name"] + ".strm")
    c_url = _read_url(batch_path)
    require(c_url is not None and c_url != fixture["plain_url"], "The batch source did not retain its C rewrite.")
    round_started = now_utc()
    run_plugin_task_completed(auth, "post-overlap change round")
    content_row = fingerprint_row(items[fixture["content_name"]]["Id"])
    require(content_row is not None and content_row["sha1"] == "a" * 40,
            "The content SHA-1 change was not probed and committed.")
    size_row = fingerprint_row(items[fixture["size_name"]]["Id"])
    require(size_row is not None and size_row["file_size"] == fixture["media_size"] + 1,
            "The incomparable-SHA-1 size change was not probed and committed.")
    c_row = fingerprint_row(items[fixture["batch_name"]]["Id"])
    require(c_row is not None and c_row["url_hash"] == expected_url_hash(c_url),
            "The later run did not commit the current C address after the mid-probe change.")
    result["content_sha1_change_probed"] = True
    result["size_change_probed"] = True
    result["url_rechange_during_probe"] = {"a_preserved": True, "b_rejected": True, "c_committed": True}

    # Add / delete / move while a held-open probe is executing (set already fixed).
    scope_result = scope_change_round(auth, fixture, recorder)
    result.update(scope_result)
    return result


def _read_url(path: Path) -> str | None:
    data = path.read_bytes().decode("utf-8-sig")
    for line in data.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def scope_change_round(auth: str, fixture: dict, recorder: EvidenceRecorder) -> dict:
    """Delete a captured candidate, move a captured candidate out, add and move in, during a held probe."""
    items = fixture["items"]
    libraries = library_roots(auth)
    captured = capture_candidate_sources(auth, libraries["strm"])

    # Choose two captured-but-not-yet-probed candidates for delete and move-out.
    delete_name = fixture["bulk_names"][0]
    moveout_name = fixture["bulk_names"][1]
    delete_id = items[delete_name]["Id"]
    moveout_id = items[moveout_name]["Id"]
    require_captured(captured, delete_id, "delete")
    require_captured(captured, moveout_id, "move-out")
    require(fingerprint_row(delete_id) is not None and fingerprint_row(moveout_id) is not None,
            "The delete/move-out targets were not in the established baseline.")

    hold_name = fixture["batch_name"]
    hold_path = fixture["strm_dir"] / (hold_name + ".strm")
    hold_id = uuid.uuid4().hex
    hold_url = delay_url(fixture["plain_url"], PROBE_DELAY_SECONDS, hold_id)
    rewrite_strm(hold_path, hold_url, fixture["media_sha"], fixture["media_size"])

    round_started = now_utc()
    task = find_task_by_key(auth, TASK_KEY)
    previous = last_start(task)
    require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the scope-change batch start.")
    hold_backend_start = wait_for_backend_event(hold_id, "start", round_started)
    hold_probe = probe_start_for_item(probe_start_events(container(), since=round_started), items[hold_name]["Id"])
    require(hold_probe is not None, "No real plugin probe start was observed for the scope-change hold source.")

    # Start the native scan and wait until it is Running before issuing the finite scope changes.
    scan_task = find_task_by_key(auth, SCAN_TASK_KEY)
    scan_previous = last_start(scan_task)
    require(start_task(auth, scan_task["Id"]) == 204, "Jellyfin did not accept the scope-change native scan start.")
    wait_for_scan_running(auth, scan_task["Id"])

    changes: list[dict] = []
    # Delete a captured candidate (its file only; the library item is reconciled by the scan).
    (fixture["strm_dir"] / (delete_name + ".strm")).unlink(missing_ok=True)
    changes.append({"change": "delete_captured", "utc": now_utc().isoformat()})
    # Move a captured candidate out of the selected library.
    shutil.move(str(fixture["strm_dir"] / (moveout_name + ".strm")),
                str(fixture["local_dir"] / (moveout_name + ".strm")))
    changes.append({"change": "move_out_captured", "utc": now_utc().isoformat()})
    # Add a new STRM and move an out-of-scope STRM in, after the fixed set was captured.
    added_name = f"Scan Added {fixture['nonce']}"
    write_strm_to(fixture["strm_dir"], added_name, fixture["plain_url"],
                  fixture["media_sha"], fixture["media_size"])
    changes.append({"change": "add_after_capture", "utc": now_utc().isoformat()})
    moved_in_name = fixture["movein_name"]
    shutil.move(str(fixture["local_dir"] / (moved_in_name + ".strm")),
                str(fixture["strm_dir"] / (moved_in_name + ".strm")))
    changes.append({"change": "move_in_after_capture", "utc": now_utc().isoformat()})

    # Wait for the scan to complete and bind its authoritative interval.
    scan_after = wait_for_new_execution(auth, scan_task["Id"], scan_previous, timeout=MAX_WAIT)
    scan_interval = require_completed_execution(scan_after, scan_previous, "scope-change native scan")
    for change in changes:
        require_change_in_window(_parse_utc(change["utc"]), scan_interval, change["change"])

    final = wait_for_new_execution(auth, task["Id"], previous, timeout=MAX_WAIT)
    require_completed_execution(final, previous, "scope-change batch")
    hold_backend_finish = wait_for_backend_event(hold_id, "finish", round_started)
    assert_scan_probe_overlap(scan_interval, hold_backend_start, hold_backend_finish, "scope-change hold")

    summary = latest_summary_after(round_started)
    fields = summary_fields_complete(summary)
    require(fields.get("candidate_fetch_failed") is False, f"The scope-change round failed its candidate fetch: {summary}.")
    # The deleted captured candidate must be reconciled away before the stable-set check; the round
    # itself completed without failing on it (safe settlement), so no new probe or failure escaped.
    wait_for_item_absent(auth, delete_name)

    # The added and moved-in items must not be processed in the fixed-set round.
    added_item = wait_for_item(auth, added_name)
    moved_in_item = wait_for_item(auth, moved_in_name)
    require(fingerprint_row(added_item["Id"]) is None,
            "A STRM added during the fixed-set run was processed by the same round.")
    require(fingerprint_row(moved_in_item["Id"]) is None,
            "A STRM moved in during the fixed-set run was processed by the same round.")
    # The next round must discover them.
    run_plugin_task_completed(auth, "post-scope discovery round")
    require(fingerprint_row(added_item["Id"]) is not None, "The next round did not discover the added STRM.")
    require(fingerprint_row(moved_in_item["Id"]) is not None, "The next round did not discover the moved-in STRM.")
    # The moved-out candidate's new identity (if any) must not be processed by the scoped batch.
    moved_out_now = [item for item in native_items(auth) if item.get("Name") == moveout_name]
    if moved_out_now:
        require(fingerprint_row(moved_out_now[0]["Id"]) is None or fingerprint_row(moved_out_now[0]["Id"]) == fingerprint_row(moveout_id),
                "The moved-out source's new identity was processed by the scoped batch.")

    recorder.record("scope_change_round", changes=changes, summary=fields,
                    scan=[scan_interval[0].isoformat(), scan_interval[1].isoformat()])
    recorder.snapshot("scope-change-round", {"changes": changes, "fields": fields})
    return {"move_out_not_batch_probed": True, "add_discovered_next_round": True,
            "move_in_discovered_next_round": True, "delete_settled": True,
            "scope_change_summary": summary, "added_name": added_name}


def multi_version_and_refresh(auth: str, fixture: dict, recorder: EvidenceRecorder) -> dict:
    """Multi-version isolation with distinct URLs and an independent native FullRefresh."""
    items = fixture["items"]
    mv_a = items[fixture["mv_a_name"]]["Id"]
    mv_b = items[fixture["mv_b_name"]]["Id"]
    mv_a_path = fixture["strm_dir"] / (fixture["mv_a_name"] + ".strm")
    mv_b_path = fixture["strm_dir"] / (fixture["mv_b_name"] + ".strm")
    # Distinct URLs with identical content hash/Size: a legal URL-change probe for each version.
    url_a = unique_url(fixture["plain_url"], "mva-" + uuid.uuid4().hex[:8])
    url_b = unique_url(fixture["plain_url"], "mvb-" + uuid.uuid4().hex[:8])
    rewrite_strm(mv_a_path, url_a, fixture["media_sha"], fixture["media_size"])
    rewrite_strm(mv_b_path, url_b, fixture["media_sha"], fixture["media_size"])
    run_plugin_task_completed(auth, "multi-version commit round")
    rows_a = fingerprint_rows_for_source(mv_a)
    rows_b = fingerprint_rows_for_source(mv_b)
    shared = [(ra, rb) for ra in rows_a for rb in rows_b if ra["item_id"] == rb["item_id"]]
    require(len(shared) == 1,
            f"The multi-version pair must share exactly one canonical project id: a={rows_a}, b={rows_b}.")
    ra, rb = shared[0]
    require(ra["source_key"] != rb["source_key"], "The two versions must keep distinct source keys.")
    require(ra["url_hash"] == expected_url_hash(url_a), "Version A did not commit its own address.")
    require(rb["url_hash"] == expected_url_hash(url_b), "Version B did not commit its own address.")
    canonical = ra["item_id"]

    # An independent native FullRefresh on one version must not change either fingerprint.
    before_a = fingerprint_row(mv_a)
    refresh_status = force_full_refresh(auth, dashed(canonical))
    require(refresh_status == 204, f"Jellyfin rejected the independent FullRefresh ({refresh_status}).")
    # 204 is only acceptance: observe actual native processing before reading the fingerprints.
    refresh_deadline = time.monotonic() + 60
    while time.monotonic() < refresh_deadline:
        if any("File changed, pruning extracted data" in line and fixture["mv_a_name"] in line
               for line in docker_log_lines(container())):
            break
        time.sleep(0.5)
    after_rows_a = [row for row in fingerprint_rows_for_source(mv_a) if row["item_id"] == canonical]
    after_rows_b = [row for row in fingerprint_rows_for_source(mv_b) if row["item_id"] == canonical]
    require(after_rows_a == [ra] and after_rows_b == [rb],
            "The independent FullRefresh changed a version's fingerprint.")

    # Explicit MediaSourceId selection must return the selected version's own source identity and address.
    status_a, response_a = playback_info_selected(auth, dashed(canonical), mv_a)
    status_b, response_b = playback_info_selected(auth, dashed(canonical), mv_b)
    require(status_a == 200 and status_b == 200, "The explicit multi-version PlaybackInfo request failed.")
    _require_selected_source(response_a, mv_a, ra["url_hash"], "A")
    _require_selected_source(response_b, mv_b, rb["url_hash"], "B")
    recorder.record("multi_version_refresh", shared_project=True, refresh_status=refresh_status)
    return {"multi_version_rows": 2, "shared_project": True,
            "independent_full_refresh_status": refresh_status, "cross_version_fingerprint_stable": True,
            "selected_version_a_matches": True, "selected_version_b_matches": True}


def _require_selected_source(response: dict, source_id: str, expected_hash: str, label: str) -> None:
    """Reject an unfiltered or wrong-version response: the requested source id and address must match."""
    key = source_id.lower().replace("-", "")
    matches = [source for source in response.get("MediaSources", [])
               if source.get("Id") and str(source["Id"]).lower().replace("-", "") == key]
    require(len(matches) == 1,
            f"The selected version {label} response did not contain exactly one source with the requested id: "
            f"{[s.get('Id') for s in response.get('MediaSources', [])]}.")
    require(source_path_matches_hash({"MediaSources": matches}, expected_hash),
            f"The selected version {label} did not return its own address.")


def convergence(auth: str, fixture: dict, recorder: EvidenceRecorder) -> dict:
    """A fresh stable-set run converges with zero extra plugin probes and per-source reconciliation."""
    libraries = library_roots(auth)
    _, stable_scan = run_native_scan_completed(auth, "stable-set native scan")
    round_started = now_utc()
    run_plugin_task_completed(auth, "stable-set convergence run")
    summary = latest_summary_after(round_started)
    fields = summary_fields_complete(summary)
    require_zero_probes(fields, summary, "stable-set convergence run")

    round_started = now_utc()
    run_plugin_task_completed(auth, "unchanged re-check run")
    repeat = latest_summary_after(round_started)
    repeat_fields = summary_fields_complete(repeat)
    require_zero_probes(repeat_fields, repeat, "unchanged re-check run")

    reconciliation = reconcile_expected_sources(auth, libraries["strm"])
    # Restart and prove the committed addresses survive, covering a URL-changed source and a merged
    # multi-version source. A merged version must be queried through its canonical project id, because
    # the physical id is no longer the canonical native item after MergeVersions.
    batch_item = fixture["items"][fixture["batch_name"]]["Id"]
    mv_a = fixture["items"][fixture["mv_a_name"]]["Id"]
    batch_row = fingerprint_row(batch_item)
    mv_rows = fingerprint_rows_for_source(mv_a)
    require(batch_row is not None and mv_rows, "Expected committed fingerprints are missing before restart.")
    mv_row = mv_rows[0]
    canonical = dashed(mv_row["item_id"])
    restart()
    auth = api_auth()
    status, response = playback_info(auth, batch_item)
    require(status == 200 and source_path_matches_hash(response, batch_row["url_hash"]),
            "The URL-changed batch source address did not survive the restart.")
    status, response = playback_info_selected(auth, canonical, mv_a)
    require(status == 200, "The multi-version selected PlaybackInfo failed after the restart.")
    _require_selected_source(response, mv_a, mv_row["url_hash"], "A-after-restart")
    recorder.record("convergence", stable=fields, repeat=repeat_fields, reconciliation=reconciliation)
    recorder.snapshot("convergence", {"stable": fields, "repeat": repeat_fields,
                                      "reconciliation": reconciliation})
    return {"stable_summary": summary, "repeat_summary": repeat,
            "stable_zero_probe": True, "restart_address_stable": True,
            "reconciled_sources": reconciliation["source_count"],
            "scan": [stable_scan[0].isoformat(), stable_scan[1].isoformat()]}


def reconcile_expected_sources(auth: str, library_id: str) -> dict:
    """Generate the expected source set from the current native library and reconcile each source.

    A physical source may legitimately carry more than one historical row after a merge or library
    re-association (a prior canonical project id plus the current one). This task does not add orphan
    cleanup, so reconciliation requires the source's current native address to match a committed
    fingerprint for its current identity and does not require older rows to disappear.
    """
    root = library_root_path(auth, library_id)
    checked: list[dict] = []
    problems: list[str] = []
    for item in native_items(auth):
        path = item.get("Path") or ""
        if not path.startswith(root):
            continue
        for source in item.get("MediaSources", []):
            source_id = source.get("Id")
            source_path = source.get("Path")
            if not source_id or not source_path:
                continue
            rows = fingerprint_rows_for_source(source_id)
            if not rows:
                problems.append(f"source {source_id} has no fingerprint row")
                continue
            address_hash = expected_url_hash(source_path)
            if not any(row["url_hash"] == address_hash for row in rows):
                problems.append(f"source {source_id} has no committed fingerprint for its current address")
                continue
            if not source_path_matches_hash({"MediaSources": [source]}, address_hash):
                problems.append(f"source {source_id} native address does not match its fingerprint")
                continue
            streams = {stream.get("Type") for stream in source.get("MediaStreams", [])}
            if "Video" not in streams:
                problems.append(f"source {source_id} has no native video main stream")
                continue
            checked.append({"source_id": source_id, "item_id": item["Id"], "fingerprint_rows": len(rows)})
    require(not problems, "The stable expected set did not reconcile: " + "; ".join(problems[:5]))
    require(checked, "The stable expected set was empty; the selected library exposed no source to reconcile.")
    return {"source_count": len(checked), "sources": checked}


# ---------------------------------------------------------------------------------------------------------------------
# Stop scenario
# ---------------------------------------------------------------------------------------------------------------------


def scenario_stop(package: Path, evidence_dir: Path | None, nonce: str, recorder: EvidenceRecorder) -> dict:
    """Real native stop of a cross-batch batch: started work commits, unstarted work revokes, a re-run
    during the drain does not begin, and a later run converges.

    The fixed candidate set is the full 130-object fixture so the batch genuinely crosses the 128-object
    boundary, but only a small subset is changed with a delay. The two delayed sources occupy the default
    concurrency and are the deterministic started set; the rest of the changed subset is revoked. The
    unchanged majority is skipped, so the convergence run stays bounded.
    """
    summary: dict[str, object] = {}
    auth = deploy_fresh(package)
    media_sha, media_size = pe.media_sha1(pe.MEDIA_MP4)
    plain_url = "http://media:8080/" + pe.MEDIA_MP4
    count = BULK_COUNT
    changed_count = 6
    names = [f"Scan Stop {nonce} {index:03d}" for index in range(count)]
    paths = {name: write_strm_to(pe.WORK / "strm", name, plain_url, media_sha, media_size) for name in names}
    refresh_library(auth)
    items = {name: wait_for_item(auth, name) for name in names}
    # Baseline with the plugin disabled so native streams are persisted, then first-trust with zero probes.
    require(plugin_action(auth, False) == 204, "The plugin disable failed.")
    restart()
    auth = api_auth()
    prepare_native_streams(auth, [items[name] for name in names], plain_url)
    require(plugin_action(auth, True) == 204, "The plugin enable failed.")
    restart()
    auth = api_auth()
    scope_all_libraries(auth)
    round_started = now_utc()
    run_plugin_task_completed(auth, "stop baseline round")
    baseline_summary = latest_summary_after(round_started)
    baseline_fields = summary_fields_complete(baseline_summary)
    # The fixture must genuinely cross the fixed 128-object batch boundary.
    require((baseline_fields.get("batch_reads") or 0) >= 2,
            f"The stop fixture did not cross the 128-object batch boundary: {baseline_summary}.")
    for name in names:
        require(fingerprint_row(items[name]["Id"]) is not None, f"The stop scenario did not baseline {name}.")

    changed_names = names[:changed_count]
    request_ids = {name: uuid.uuid4().hex for name in changed_names}
    for name in changed_names:
        rewrite_strm(paths[name], delay_url(plain_url, STOP_DELAY_SECONDS, request_ids[name]), media_sha, media_size)

    round_started = now_utc()
    task = find_task_by_key(auth, TASK_KEY)
    previous = last_start(task)
    require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the stop-scenario batch start.")
    all_request_ids = set(request_ids.values())
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        started = {event["request_id"] for event in backend_request_events(media_container(), since=round_started)
                   if event["kind"] == "start"}
        if len(started & all_request_ids) >= 2:
            break
        time.sleep(0.2)
    require({event["request_id"] for event in backend_request_events(media_container(), since=round_started)
             if event["kind"] == "start"} & all_request_ids,
            "The stop scenario never reached a real probe.")
    entries_before_stop = len(batch_entry_events(round_started))

    stop_status = stop_task(auth, task["Id"])
    require(stop_status == 204, "Jellyfin did not accept the native stop.")
    stopped_at = now_utc()
    # Admission is now closed: the set of actually started probes is authoritative for the stopped round.
    started_ids = {event["request_id"] for event in backend_request_events(media_container(), since=round_started)
                   if event["kind"] == "start"} & all_request_ids
    saw_cancelling = False
    progress_during_cancel: list[float] = []
    second_start_status = None
    # Attempt a re-run while the old round is draining; it must not actually enter a new round.
    try:
        second_start_status = start_task(auth, task["Id"])
    except Exception:
        second_start_status = None
    drain_deadline = time.monotonic() + 120
    while time.monotonic() < drain_deadline:
        current = next((t for t in task_list(auth) if t.get("Id") == task["Id"]), None)
        if current is not None:
            state = task_state_name(current)
            if state in {"cancelling", "2"}:
                saw_cancelling = True
                percentage = current.get("CurrentProgressPercentage")
                if percentage is not None:
                    progress_during_cancel.append(float(percentage))
            if state in {"idle", "0"} and last_start(current) != previous:
                break
        time.sleep(0.1)
    require(saw_cancelling, "The stopped round never reported a Cancelling state.")
    final = wait_for_new_execution(auth, task["Id"], previous, timeout=MAX_WAIT)
    status_value = task_status(final)
    require(status_value in {"cancelled", "1"}, f"The stopped round did not record Cancelled: {task_result(final)}.")
    require_progress_below_100(progress_during_cancel)
    cancelled_events = [event for event in task_completion_events(round_started) if event["status"] == "Cancelled"]
    require(cancelled_events, "No Cancelled completion was logged for the stopped round.")
    cancelled_at = cancelled_events[0]["timestamp"]

    # No new round may actually enter before the stopped round settled; the re-run is refused.
    entries = batch_entry_events(round_started)
    entries_before_settlement = [entry for entry in entries if entry["timestamp"] < cancelled_at]
    require_no_new_round(len(entries_before_settlement), entries_before_stop, "re-run")
    probes_during_drain = [event for event in probe_start_events(container(), since=stopped_at)
                           if event["timestamp"] < cancelled_at]
    require_no_probe_during_drain(probes_during_drain)

    summary_line = first_summary_after(round_started)
    fields = summary_fields_complete(summary_line)
    started_count = len(started_ids)
    require((fields.get("reliable_success") or 0) == started_count,
            f"The stopped round reliable-success count must equal the started set ({started_count}): {summary_line}.")
    require((fields.get("revoked") or 0) >= 1,
            f"The native stop did not revoke any unstarted source: {summary_line}.")
    require((fields.get("reliable_success") or 0) + (fields.get("revoked") or 0) < count,
            f"The stopped round claimed to have settled the whole cross-batch set: {summary_line}.")
    require((fields.get("checked") or 0) < count,
            f"The stopped round claimed to have checked the whole cross-batch set: {summary_line}.")
    require(fields.get("batch_reads") == 1,
            f"The stopped round read more than the first batch after the stop: {summary_line}.")
    summary["stop"] = {"stop_status": stop_status, "status": status_value, "summary": summary_line,
                       "started": started_count, "reliable_success": fields.get("reliable_success"),
                       "revoked": fields.get("revoked"), "saw_cancelling": saw_cancelling,
                       "progress_during_cancel": progress_during_cancel, "second_start_status": second_start_status,
                       "entries_before_settlement": len(entries_before_settlement), "batch_reads": fields.get("batch_reads")}
    recorder.record("stop_round", status=status_value, started=started_count, revoked=fields.get("revoked"),
                    progress=progress_during_cancel, second_start_status=second_start_status,
                    entries=len(entries_before_settlement), summary=fields)
    recorder.snapshot("stop-round", summary["stop"])

    # Let any queued re-run settle, then run an explicit convergence round: every changed source is
    # committed and every unchanged source is skipped.
    wait_for_stable_idle(auth, task["Id"])
    run_plugin_task_completed(auth, "stop convergence run")
    wait_for_stable_idle(auth, task["Id"])
    for name in changed_names:
        row = fingerprint_row(items[name]["Id"])
        require(row is not None and row["url_hash"] == expected_url_hash(
            delay_url(plain_url, STOP_DELAY_SECONDS, request_ids[name])),
            f"The convergence run did not commit the changed source {name}.")
    # A further unchanged re-check must skip every source with zero plugin probes.
    round_started = now_utc()
    run_plugin_task_completed(auth, "stop unchanged re-check")
    recheck_summary = latest_summary_after(round_started)
    recheck_fields = summary_fields_complete(recheck_summary)
    require_zero_probes(recheck_fields, recheck_summary, "post-settlement unchanged re-check")
    summary["converged"] = True
    return summary


def wait_for_stable_idle(auth: str, task_id: str, stable_seconds: float = 3.0, timeout: int = MAX_WAIT) -> None:
    """Wait until the task is Idle and no new round has started for a stable period."""
    deadline = time.monotonic() + timeout
    stable_since = time.monotonic()
    last_entries = len(batch_entry_events())
    while time.monotonic() < deadline:
        task = next((t for t in task_list(auth) if t.get("Id") == task_id), None)
        require(task is not None, "The batch task disappeared while waiting for a stable idle state.")
        entries = len(batch_entry_events())
        if entries != last_entries or task_state_name(task) not in {"idle", "0"}:
            last_entries = entries
            stable_since = time.monotonic()
        elif time.monotonic() - stable_since >= stable_seconds:
            return
        time.sleep(0.25)
    raise RuntimeError("The batch task never reached a stable idle state.")


# ---------------------------------------------------------------------------------------------------------------------
# Controls scenario
# ---------------------------------------------------------------------------------------------------------------------


def scenario_controls(package: Path, evidence_dir: Path | None, nonce: str, recorder: EvidenceRecorder) -> dict:
    summary: dict[str, object] = {}
    auth = deploy_fresh(package)
    pe.add_library_authenticated(auth, OUT_OF_SCOPE_LIBRARY, ["/media/local"])
    auth = api_auth()
    libraries = scope_to_strm_library(auth)
    require("strm" in libraries and "local" in libraries, f"Missing strm/local libraries: {libraries}.")

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
    summary["sharing"] = _sharing_directions(auth, libraries, nonce)
    auth = api_auth()
    summary["mixed"] = _mixed_concurrency(auth, libraries, nonce)
    recorder.record("controls", timed_trigger=summary["timed_trigger"], sharing=summary["sharing"], mixed=summary["mixed"])
    recorder.snapshot("controls", summary)
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
    run_plugin_task_completed(auth, "sharing baseline run")
    require(fingerprint_row(item["Id"]) is not None, "The sharing source did not get a baseline.")
    request_id = uuid.uuid4().hex
    target_url = delay_url(plain_url, PROBE_DELAY_SECONDS, request_id)
    rewrite_strm(path, target_url, media_sha, media_size)
    round_started = now_utc()
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
        wait_for_backend_event(request_id, "start", round_started)
        require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the sharing batch start.")
        worker.join(timeout=MAX_WAIT)
    else:
        require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the sharing batch start.")
        wait_for_backend_event(request_id, "start", round_started)
        worker = threading.Thread(target=playback, name="scan-share-playback", daemon=True)
        worker.start()
        worker.join(timeout=MAX_WAIT)
    require(not worker.is_alive(), "The sharing playback did not finish.")
    require("error" not in holder, "The sharing playback failed outside the HTTP path.")
    final = wait_for_new_execution(auth, task["Id"], share_previous, timeout=MAX_WAIT)
    require_completed_execution(final, share_previous, "sharing batch")
    backend_count = len([event for event in backend_request_events(media_container(), since=round_started)
                         if event["request_id"] == request_id and event["kind"] == "start"])
    require(backend_count == 1, f"The batch and playback must share exactly one backend probe, observed {backend_count}.")
    summary_line = latest_summary_after(round_started)
    fields = summary_fields_complete(summary_line)
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
    media_sha, media_size = pe.media_sha1(pe.MEDIA_MP4)
    plain_url = "http://media:8080/" + pe.MEDIA_MP4
    batch_name = f"Scan Mixed Batch {nonce}"
    playback_name = f"Scan Mixed Playback {nonce}"
    batch_path = write_strm_to(pe.WORK / "strm", batch_name, plain_url, media_sha, media_size)
    playback_path = write_strm_to(pe.WORK / "media", playback_name, plain_url, media_sha, media_size)
    refresh_library(auth)
    batch_item = wait_for_item(auth, batch_name)
    playback_item = wait_for_item(auth, playback_name)
    run_plugin_task_completed(auth, "mixed baseline run")
    require(fingerprint_row(batch_item["Id"]) is not None, "The mixed batch source did not get a baseline.")
    batch_id = uuid.uuid4().hex
    playback_id = uuid.uuid4().hex
    batch_url = delay_url(plain_url, PROBE_DELAY_SECONDS, batch_id)
    playback_url = delay_url(plain_url, PROBE_DELAY_SECONDS, playback_id)
    rewrite_strm(batch_path, batch_url, media_sha, media_size)
    rewrite_strm(playback_path, playback_url, media_sha, media_size)
    round_started = now_utc()
    holder: dict = {}

    def playback() -> None:
        try:
            holder["result"] = playback_info(auth, playback_item["Id"])
        except Exception as error:
            holder["error"] = type(error).__name__

    task = find_task_by_key(auth, TASK_KEY)
    mixed_previous = last_start(task)
    require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the mixed batch start.")
    wait_for_backend_event(batch_id, "start", round_started)
    worker = threading.Thread(target=playback, name="scan-mixed-playback", daemon=True)
    worker.start()
    wait_for_backend_event(playback_id, "start", round_started)
    worker.join(timeout=MAX_WAIT)
    require(not worker.is_alive(), "The mixed playback did not finish.")
    require("error" not in holder, "The mixed playback failed outside the HTTP path.")
    final = wait_for_new_execution(auth, task["Id"], mixed_previous, timeout=MAX_WAIT)
    require_completed_execution(final, mixed_previous, "mixed batch")
    entries = probe_start_events(container(), since=round_started)
    peak = max((entry["running"] for entry in entries), default=0)
    playback_probe = probe_start_for_item(entries, playback_item["Id"])
    batch_probe = probe_start_for_item(entries, batch_item["Id"])
    require(batch_probe is not None, "No batch probe start was observed in the mixed run.")
    require(playback_probe is not None, "No playback probe start was observed in the mixed run.")
    require(peak == 2, f"The mixed overlap never reached the default concurrency of 2: peak {peak}.")
    require(playback_probe["running"] == 2, f"The playback probe did not overlap a batch probe: {playback_probe}.")
    summary_line = latest_summary_after(round_started)
    fields = summary_fields_complete(summary_line)
    require((fields.get("actual_probe_calls") or 0) == 1, f"The mixed batch must start exactly one scoped call: {summary_line}.")
    return {"peak_running_probes": peak, "playback_start_running": playback_probe["running"],
            "batch_owner_started": True, "configured_concurrency": 2, "summary": summary_line}


# ---------------------------------------------------------------------------------------------------------------------
# Recovery scenario
# ---------------------------------------------------------------------------------------------------------------------


def backend_activity() -> dict[str, int]:
    """A complete snapshot of every backend/probe route plus the plugin encoder starts."""
    counts = batch.slow_request_counts(media_container())
    lines = docker_log_lines(media_container())
    activity = {
        "delay_started": sum(counts.values()),
        "probe_finished": sum("PROBE_MEDIA_REQUEST_FINISHED " in line for line in lines),
        "media_requests": sum("MEDIA_REQUEST " in line for line in lines),
        "plugin_encoder_starts": sum("Native STRM probe started" in line for line in docker_log_lines(container())),
    }
    return activity


def scenario_recovery(package: Path, evidence_dir: Path | None, nonce: str, recorder: EvidenceRecorder) -> dict:
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
    run_plugin_task_completed(auth, "recovery baseline run")
    require(fingerprint_row(versioned_item["Id"]) is not None, "The recovery scenario could not establish a baseline.")
    for item, label in ((ordinary_item, "ordinary"), (legacy_item, "legacy")):
        before = plugin_events()
        status, response = playback_info(auth, item["Id"])
        require(status == 200 and response.get("MediaSources"), f"The {label} input did not return a native source.")
        require(pkg.event_delta(before, plugin_events()) == [], f"The plugin intercepted the {label} input.")
    summary["delegated_inputs"] = True

    # Single-item media failure isolation: one changed source that cannot be probed must keep its
    # baseline and must not prevent a healthy changed source from succeeding.
    fail_name = f"Scan Fail {nonce}"
    healthy_name = f"Scan Healthy {nonce}"
    fail_path = write_strm_to(pe.WORK / "strm", fail_name, plain_url, media_sha, media_size)
    healthy_path = write_strm_to(pe.WORK / "strm", healthy_name, plain_url, media_sha, media_size)
    refresh_library(auth)
    fail_item = wait_for_item(auth, fail_name)
    healthy_item = wait_for_item(auth, healthy_name)
    run_plugin_task_completed(auth, "single-item baseline run")
    fail_before = fingerprint_row(fail_item["Id"])
    require(fail_before is not None, "The failing source did not receive a baseline.")
    rewrite_strm(fail_path, missing_url(plain_url), media_sha, media_size)
    healthy_url = unique_url(plain_url, "healthy-" + uuid.uuid4().hex[:8])
    rewrite_strm(healthy_path, healthy_url, media_sha, media_size)
    run_plugin_task_completed(auth, "single-item failure round")
    fail_after = fingerprint_row(fail_item["Id"])
    require(fail_after == fail_before, "A failed single-item probe overwrote its trusted baseline.")
    healthy_after = fingerprint_row(healthy_item["Id"])
    require(healthy_after is not None and healthy_after["url_hash"] == expected_url_hash(healthy_url),
            "A healthy changed source did not succeed alongside a failing source.")
    summary["single_item_failure_isolated"] = True

    # Disabling the plugin before a real change must start no probe on any route.
    configure(auth, {"Enabled": False, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2,
                     "DetailedLog": False, "BatchAllLibraries": True, "BatchLibraryIds": ""})
    disabled_url = unique_url(plain_url, "disabled-" + uuid.uuid4().hex[:8])
    rewrite_strm(healthy_path, disabled_url, media_sha, media_size)
    before_activity = backend_activity()
    run_plugin_task(auth)
    after_activity = backend_activity()
    require_no_new_activity(before_activity, after_activity, "A disabled plugin")
    scope_all_libraries(auth)
    summary["disabled_no_probe"] = True

    # A SQLite global fault must fail the task without starting a probe on any route, and recover.
    database = pkg.fingerprint_database()
    require(database.is_file(), "The plugin fingerprint database is missing.")
    backup = database.with_suffix(".db.bak-" + uuid.uuid4().hex[:8])
    shutil.copy2(database, backup)
    try:
        database.unlink()
        database.mkdir()
        before_activity = backend_activity()
        final = run_plugin_task(auth)
        status_value = task_status(final)
        require(status_value in {"failed", "3"}, f"A SQLite fault did not fail the task: {status_value}.")
        require_no_new_activity(before_activity, backend_activity(), "A SQLite fault")
        summary["store_fault"] = {"status": status_value}
    finally:
        if database.is_dir():
            database.rmdir()
        shutil.move(str(backup), str(database))
    restart()
    auth = api_auth()
    recovered = run_plugin_task_completed(auth, "store recovery run")
    summary["store_recovered"] = True
    recorder.record("recovery", single_item_failure=True, disabled_no_probe=True,
                    store_fault=summary["store_fault"], store_recovered=True)
    recorder.snapshot("recovery", summary)
    return summary


# ---------------------------------------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------------------------------------


def plugin_events() -> list[str]:
    return pkg.plugin_events()


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
    nonce = uuid.uuid4().hex[:8]
    evidence_dir = args.evidence_dir.resolve() if args.evidence_dir else (ROOT / "artifacts" / "scan-evidence" / nonce)
    summary: dict[str, object] = {"scenario": args.scenario, "package": str(package), "run_id": nonce,
                                  "evidence_dir": str(evidence_dir)}
    recorder = EvidenceRecorder(evidence_dir, nonce)
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
        recorder.record("package", identity=summary["package_identity"], workspace=str(workspace))
        if args.scenario in {"all", "overlap"}:
            summary["overlap"] = scenario_overlap_phase(package, evidence_dir, nonce, recorder)
        if args.scenario in {"all", "controls"}:
            summary["controls"] = scenario_controls(package, evidence_dir, nonce, recorder)
        if args.scenario in {"all", "stop"}:
            summary["stop_scenario"] = scenario_stop(package, evidence_dir, nonce, recorder)
        if args.scenario in {"all", "recovery"}:
            summary["recovery"] = scenario_recovery(package, evidence_dir, nonce, recorder)
        summary["status"] = "PASS"
        exit_code = 0
    except (RuntimeError, OSError, ValueError, KeyError, TypeError, AttributeError, NameError,
            json.JSONDecodeError, subprocess.SubprocessError, pp.PackageError,
            pe.PackageEnvironmentError) as error:
        summary["status"] = "FAIL"
        summary["error"] = f"{type(error).__name__}: {error}"
        exit_code = 1
        recorder.record("failure", error=summary["error"])
    finally:
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
        # Persist the failure/recovery fragment before the instance workspace is destroyed.
        try:
            recorder.record("teardown", trigger_restoration=summary.get("trigger_restoration"),
                            instance_reconciliation=summary.get("instance_reconciliation"),
                            teardown_error=summary.get("teardown_error"))
            recorder.snapshot("teardown", {
                "trigger_restoration": summary.get("trigger_restoration"),
                "instance_reconciliation": summary.get("instance_reconciliation"),
                "teardown_error": summary.get("teardown_error"),
                "status": summary.get("status"),
            })
        except OSError as record_error:
            summary["evidence_error"] = f"{type(record_error).__name__}: {record_error}"
            summary["status"] = "FAIL"
            exit_code = 1
        if workspace is not None and not args.keep_workspace:
            try:
                summary["cleanup"] = pe.cleanup_instance()
            except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError) as cleanup_error:
                summary["cleanup_error"] = f"{type(cleanup_error).__name__}: {cleanup_error}"
                summary["status"] = "FAIL"
                exit_code = 1
        if recorder is not None:
            recorder.finish(str(summary.get("status", "FAIL")), summary, {
                "events.jsonl": "append-only redacted event stream",
                "rounds/": "per-round snapshots",
                "result.json": "final summary",
            })
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


def scenario_overlap_phase(package: Path, evidence_dir: Path | None, nonce: str,
                           recorder: EvidenceRecorder | None) -> dict:
    """Run the overlap scenario and attach the finite-change / multi-version / convergence phases."""
    require(recorder is not None, "An evidence recorder is required for the overlap scenario.")
    auth = deploy_fresh(package)
    recorder.record("instance", container=container_identity())
    summary: dict[str, object] = {}
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
    summary["overlap_round"] = overlap_round(auth, fixture, recorder)
    auth = api_auth()
    summary["finite_changes"] = finite_changes(auth, fixture, recorder)
    auth = api_auth()
    summary["multi_version_and_refresh"] = multi_version_and_refresh(auth, fixture, recorder)
    auth = api_auth()
    summary["convergence"] = convergence(auth, fixture, recorder)
    return summary


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
