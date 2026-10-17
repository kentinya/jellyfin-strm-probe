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
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
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
# A bounded long delay keeps the joined probes executing while the 130-candidate batch reaches the selected
# source and the native stop request is issued; the post-stop convergence round uses stable, non-delayed URLs.
STOP_DELAY_SECONDS = 45
BATCH_OBJECT_LIMIT = 128

ACTIVE_RECORDER: "EvidenceRecorder | None" = None

# Every counter a completed batch summary must report. A missing field is a hard failure: it must
# never silently become a zero that trivially satisfies a later "== 0" probe assertion.
REQUIRED_SUMMARY_FIELDS = (
    "candidates", "raw_candidates", "duplicates", "checked", "skipped", "first_trust",
    "need_probe", "reliable_success", "probe_incomplete", "check_stage_incomplete",
    "not_processed", "missing", "revoked", "read_incomplete", "unread", "actual_probe_calls",
    "batch_reads", "candidate_fetch_ms", "batch_read_ms", "candidate_fetch_failed",
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

_SCRUB_KEYS = ("url", "path", "token", "password", "cookie", "authorization", "access", "secret",
               "credential", "message", "error", "exception", "traceback")
_URL_TEXT = re.compile(r"(?i)\b(?:https?|ftp|file)://[^\s\"'<>]+")
_BEARER_TEXT = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_SECRET_PAIR_TEXT = re.compile(r"(?i)\b(token|cookie|authorization|password|secret|api[_-]?key)=([^\s&;,]+)")
_ABSOLUTE_PATH_TEXT = re.compile(r"(?<![\w:])/(?:[^\s,;\"'<>]+/?)+")
_WINDOWS_PATH_TEXT = re.compile(r"(?i)\b[A-Z]:\\(?:[^\s,;\"'<>]+\\?)+")


def _digest_value(value: str) -> dict[str, object]:
    return {"sha256": digest(value), "length": len(value)}


def redact_log_text(value: str) -> str:
    """Keep log context while replacing URLs, credentials and absolute paths with stable digests."""
    result = _URL_TEXT.sub(lambda match: f"[url sha256={digest(match.group(0))}]", value)
    result = _BEARER_TEXT.sub(lambda match: f"[credential sha256={digest(match.group(0))}]", result)
    result = _SECRET_PAIR_TEXT.sub(
        lambda match: f"{match.group(1)}=[secret sha256={digest(match.group(2))}]", result)
    result = _ABSOLUTE_PATH_TEXT.sub(lambda match: f"[path sha256={digest(match.group(0))}]", result)
    result = _WINDOWS_PATH_TEXT.sub(lambda match: f"[path sha256={digest(match.group(0))}]", result)
    return result


def _scrub(value: object, key: str = "") -> object:
    """Redact anything that could carry a signed URL, token, cookie or private path."""
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return _digest_value(str(value))
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "length": len(value)}
    if isinstance(value, dict):
        return {str(k): _scrub(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(item, key) for item in value]
    if isinstance(value, str):
        lowered = key.lower()
        if (lowered.endswith("_sha256") or lowered.endswith("_sha1")
                or lowered in {"sha1", "url_hash", "native_url_hash", "content_hash"}):
            return value
        if any(marker in key.lower() for marker in _SCRUB_KEYS):
            return _digest_value(value)
        return redact_log_text(value)
    return value


def _safe_exception(error: BaseException) -> dict[str, object]:
    message = str(error)
    return {"type": type(error).__name__, "message": _digest_value(message),
            "redacted_context": redact_log_text(message)}


def current_source_id_for_hash(auth: str, item_id: str, expected_hash: str) -> str | None:
    """Return the current native MediaSource id whose path hashes to ``expected_hash``."""
    status, payload = pe.request_json("GET", f"/Items/{item_id}?Fields=MediaSources,MediaStreams,Path",
                                      headers={"Authorization": auth})
    require(status == 200, "The current item read failed while resolving a source identity.")
    for source in payload.get("MediaSources", []):
        path = source.get("Path") or ""
        if source.get("Id") and digest(path) == expected_hash:
            return str(source["Id"])
    return None


def assert_committed_address_survives(auth: str, item_id: str, expected_hash: str, label: str) -> None:
    """After a restart, prove a committed address is still returned and explicit selection still works.

    The physical source id can be re-keyed by a native library scan, so the current identity is resolved
    from the current native MediaSources rather than assumed to be the pre-scan id; the fingerprint is then
    read for that current (item_id, source_key) pair and the explicit selection must return exactly that
    current source with the committed address.
    """
    status, payload = pe.request_json("GET", f"/Items/{item_id}?Fields=MediaSources,MediaStreams,Path",
                                      headers={"Authorization": auth})
    require(status == 200, "The current item read failed while resolving a source identity.")
    current_id = next((str(source["Id"]) for source in payload.get("MediaSources", [])
                       if source.get("Id") and digest(source.get("Path") or "") == expected_hash), None)
    require(current_id is not None,
            f"The {label} committed address is no longer present in the current native source set after the restart.")
    row = fingerprint_row_for_key(item_id, current_id)
    require(row is not None and row["url_hash"] == expected_hash,
            f"The {label} current source has no committed fingerprint for its address after the restart.")
    current_source = next(source for source in payload.get("MediaSources", [])
                          if canonical_guid(source.get("Id"), f"{label} restarted source") == canonical_guid(current_id, label))
    streams = current_source.get("MediaStreams") or []
    require(any(stream.get("Type") in {"Video", "Audio"} for stream in streams),
            f"The {label} restarted source has no required main stream.")
    validate_source_reconciliation({"item_id": item_id, "source_key": current_id, "url_hash": expected_hash,
                                    "sha1": row["sha1"], "file_size": row["file_size"]},
                                   current_source, row, f"restarted {label}")
    status, response = playback_info_selected(auth, item_id, current_id)
    require(status == 200, f"The explicit {label} selection failed after the restart ({status}).")
    _require_selected_source(response, current_id, expected_hash, label)


class EvidenceRecorder:
    """Incrementally persist redacted, reviewable evidence outside the instance workspace."""

    def __init__(self, directory: Path, run_id: str) -> None:
        if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
            raise RuntimeError("The evidence directory must be new or empty; refusing to overwrite an earlier run.")
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.run_id = run_id
        self.rounds_dir = directory / "rounds"
        self.rounds_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir = directory / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = directory / "events.jsonl"
        self.events_path.open("x", encoding="utf-8").close()
        self.monotonic_origin = time.monotonic()
        self.started_utc = now_utc()
        self.container_identity: dict | None = None
        self.metadata: dict[str, object] = {}
        self.raw_files: dict[str, str] = {}
        self.source = self._source_identity()
        self.record("run_start", source=self.source, run_id=run_id)

    @staticmethod
    def _source_identity() -> dict:
        head = run("git", "rev-parse", "HEAD").stdout.strip()
        status = run("git", "status", "--porcelain", "--untracked-files=all").stdout
        diff = run("git", "diff", "HEAD", "--binary").stdout
        untracked_paths = [line[3:] for line in status.splitlines() if line.startswith("?? ")]
        untracked = []
        for relative in sorted(untracked_paths):
            path = ROOT / relative
            if path.is_file() and not path.is_symlink():
                untracked.append({"name_sha256": digest(relative), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            elif path.is_symlink():
                untracked.append({"name_sha256": digest(relative), "sha256": digest(os.readlink(path))})
        exact_diff_hash = digest(diff)
        content_identity = digest(json.dumps({"head": head, "diff": exact_diff_hash, "untracked": untracked},
                                             sort_keys=True, separators=(",", ":")))
        return {"head": head, "dirty": bool(status.strip()), "status_sha256": digest(status),
                "tracked_diff_sha256": exact_diff_hash, "untracked_file_sha256": digest(
                    json.dumps(untracked, sort_keys=True, separators=(",", ":"))),
                "working_content_sha256": content_identity}

    def set_container_identity(self, identity: dict, *, component: str = "jellyfin") -> None:
        if component == "jellyfin":
            self.container_identity = identity
        self.record("container_identity", component=component, identity=identity)

    def set_metadata(self, **metadata: object) -> None:
        self.metadata.update(metadata)
        self.record("run_metadata", metadata=metadata)

    def write_raw(self, relative_name: str, content: str) -> str:
        relative = Path(relative_name)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("Evidence files must use safe relative paths.")
        target = self.directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        safe = "\n".join(redact_log_text(line) for line in content.splitlines()) + "\n"
        with target.open("x", encoding="utf-8") as handle:
            handle.write(safe)
        self.raw_files[relative.as_posix()] = "redacted raw observation"
        return relative.as_posix()

    def record(self, kind: str, **data: object) -> None:
        line = {
            "utc": now_utc().isoformat(),
            "monotonic": round(time.monotonic() - self.monotonic_origin, 6),
            "run_id": self.run_id,
            "kind": kind,
            "container_identity": self.container_identity,
            "data": _scrub(data),
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")

    def snapshot(self, name: str, data: object) -> None:
        path = self.rounds_dir / (name + ".json")
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(_scrub(data), ensure_ascii=False, indent=2, sort_keys=True))
        self.raw_files[path.relative_to(self.directory).as_posix()] = "redacted per-round evidence snapshot"

    def finish(self, status: str, summary: dict, raw_files: dict[str, str]) -> None:
        self.record("run_finish", status=status, summary=summary)
        result = self.directory / "result.json"
        with result.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(_scrub(summary), ensure_ascii=False, indent=2, sort_keys=True))
        index = ["# Scan acceptance evidence index", "",
                 f"- Run id: `{self.run_id}`",
                 f"- Source head: `{self.source['head']}` (dirty: {self.source['dirty']})",
                 f"- Working content SHA-256: `{self.source['working_content_sha256']}`",
                 f"- Overall status: **{status}**", "",
                 f"- Started: `{self.started_utc.isoformat()}`",
                 f"- Elapsed seconds: `{time.monotonic() - self.monotonic_origin:.3f}`",
                 f"- Working directory: `.` (repository root)",
                 f"- Command: `{self.metadata.get('command', 'python3 scripts/run_isolated_scan_integration.py')}`",
                 f"- Exit code: `{self.metadata.get('exit_code', 'UNAVAILABLE')}`",
                 f"- Runtime: `{json.dumps(_scrub(self.metadata.get('runtime', {})), ensure_ascii=False, sort_keys=True)}`",
                 f"- Inputs: `{json.dumps(_scrub(self.metadata.get('inputs', {})), ensure_ascii=False, sort_keys=True)}`",
                 f"- Runtime identities: `{json.dumps(_scrub(self.metadata.get('runtime_identities', {})), ensure_ascii=False, sort_keys=True)}`",
                 f"- Deployment: `{json.dumps(_scrub(self.metadata.get('deployment', {})), ensure_ascii=False, sort_keys=True)}`",
                 "",
                 "## Raw files", ""]
        for name, description in {**self.raw_files, **raw_files}.items():
            index.append(f"- `{name}` — {description}")
        index.append("")
        index.append("`events.jsonl` is append-only; `rounds/` holds per-round snapshots and `logs/` holds "
                     "timestamped Jellyfin/media logs with URL, credential and path values redacted. "
                     "This evidence is local to this machine unless copied to a durable artifact store.")
        with (self.directory / "INDEX.md").open("x", encoding="utf-8") as handle:
            handle.write("\n".join(index) + "\n")


# ---------------------------------------------------------------------------------------------------------------------
# Native API helpers (package instance)
# ---------------------------------------------------------------------------------------------------------------------


def api_auth() -> str:
    return pkg.api_auth()


def container() -> str:
    return pe.container_name("jellyfin")


def media_container() -> str:
    return pe.container_name("media")


def docker_container_identity(name: str) -> dict:
    result = run("docker", "inspect", "--format",
                 "{{.Id}} {{.State.StartedAt}} {{.Image}} {{.Config.Image}}", name, timeout=30)
    require(result.returncode == 0, f"Could not read the container identity for {name}.")
    values = result.stdout.strip().split(maxsplit=3)
    require(len(values) == 4, f"The container identity response for {name} was incomplete.")
    return {"name": name, "id": values[0], "started_at": values[1], "image_id": values[2],
            "configured_image": values[3], "identity": f"{values[0]} {values[1]} {values[2]} {values[3]}"}


def container_identity() -> dict:
    return docker_container_identity(container())


def task_list(auth: str) -> list[dict]:
    status, tasks = pe.request_json("GET", "/ScheduledTasks", headers={"Authorization": auth})
    require(status == 200, "The scheduled-task listing failed.")
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("task_poll", tasks=tasks, http_status=status)
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
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("task_start_request", task_id=task_id, status=status, observed_at=now_utc())
    return status


def stop_task(auth: str, task_id: str) -> int:
    status, _ = pe.request_json("DELETE", "/ScheduledTasks/Running/" + task_id, headers={"Authorization": auth})
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("task_stop_request", task_id=task_id, status=status, observed_at=now_utc())
    return status


def set_triggers(auth: str, task_id: str, triggers: list[dict]) -> int:
    status, _ = pe.request_json("POST", f"/ScheduledTasks/{task_id}/Triggers",
                                headers={"Authorization": auth}, body=triggers)
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("task_trigger_update", task_id=task_id, triggers=triggers, status=status)
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
    status = pkg.plugin_action(auth, enabled)
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("plugin_enablement_request", enabled=enabled, status=status)
    return status


def restart() -> str:
    if ACTIVE_RECORDER is not None:
        collect_runtime_evidence("before-restart", require_running=False)
    result = pkg.restart()
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.set_container_identity(container_identity())
        try:
            ACTIVE_RECORDER.record("media_container_identity", identity=docker_container_identity(media_container()))
        except RuntimeError as error:
            ACTIVE_RECORDER.record("media_container_identity_unavailable", error=_safe_exception(error))
    return result


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


def native_items_in_library(auth: str, library_id: str) -> list[dict]:
    """Read current native objects through the selected library relationship."""
    query = urlencode({"ParentId": dashed(library_id), "Recursive": "true", "Limit": "5000",
                       "Fields": "MediaSources,MediaStreams,Path,DateModified"})
    status, payload = pe.request_json("GET", "/Items?" + query, headers={"Authorization": auth})
    require(status == 200, "The selected-library native item query failed.")
    items = payload.get("Items", [])
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("native_library_query", library_id=library_id, status=status,
                               total_record_count=payload.get("TotalRecordCount"),
                               items=[{"item_id": item.get("Id"), "name": item.get("Name"),
                                       "path_sha256": digest(str(item.get("Path") or "")),
                                       "source_ids": [source.get("Id") for source in item.get("MediaSources", [])]}
                                      for item in items])
    return items


def merge_selected_library_items(selected_items: list[dict], all_native_items: list[dict],
                                 library_root: str) -> list[dict]:
    """Retain alternate-version items omitted by the user-library DTO query, keyed by current native path."""
    root = library_root.replace("\\", "/").rstrip("/")

    def is_current_path(item: dict) -> bool:
        path = str(item.get("Path") or "").replace("\\", "/")
        return bool(path) and path.startswith(root + "/")

    global_by_id: dict[str, dict] = {}
    for item in all_native_items:
        if not item.get("Id") or not is_current_path(item):
            continue
        item_id = canonical_guid(item["Id"], "global current library item")
        require(item_id not in global_by_id,
                f"The native API returned duplicate current item identity {item_id} across library paths.")
        global_by_id[item_id] = item

    selected_ids = set()
    for item in selected_items:
        if not item.get("Id") or not is_current_path(item):
            continue
        item_id = canonical_guid(item["Id"], "selected current library item")
        selected_ids.add(item_id)
        current = global_by_id.get(item_id)
        require(current is not None,
                f"The selected-library query returned item {item_id} absent from the current native item set.")
        require(str(current.get("Path") or "").replace("\\", "/")
                == str(item.get("Path") or "").replace("\\", "/"),
                f"The current native item {item_id} has conflicting selected-library paths.")

    return [global_by_id[item_id] for item_id in sorted(global_by_id)]


def expand_alternate_source_items(current_items: list[dict], library_root: str,
                                  resolve_item: Callable[[str], dict | None]) -> list[dict]:
    """Resolve hidden physical version item IDs exposed by a grouped item's native MediaSources."""
    root = library_root.replace("\\", "/").rstrip("/")
    by_id = {canonical_guid(item["Id"], "current candidate item"): item
             for item in current_items if item.get("Id")}
    pending = [canonical_guid(source["Id"], "current candidate MediaSource")
               for item in current_items for source in item.get("MediaSources", [])
               if source.get("Id")]
    for source_id in pending:
        if source_id in by_id:
            continue
        alternate = resolve_item(source_id)
        if alternate is None or not alternate.get("Id"):
            continue
        alternate_id = canonical_guid(alternate["Id"], "resolved alternate item")
        path = str(alternate.get("Path") or "").replace("\\", "/")
        if not path.startswith(root + "/"):
            continue
        existing = by_id.get(alternate_id)
        require(existing is None or str(existing.get("Path") or "").replace("\\", "/") == path,
                f"Alternate version {alternate_id} has conflicting current native paths.")
        by_id[alternate_id] = alternate
    return [by_id[item_id] for item_id in sorted(by_id)]


def current_native_item_by_id(auth: str, item_id: str) -> dict | None:
    canonical_item = canonical_guid(item_id, "current native item lookup")
    status, item = pe.request_json(
        "GET", f"/Items/{dashed(canonical_item)}?Fields=MediaSources,MediaStreams,Path,DateModified",
        headers={"Authorization": auth})
    if status == 404:
        return None
    require(status == 200, "The exact current native item lookup failed.")
    require(canonical_guid(item.get("Id"), "returned current native item") == canonical_item,
            "The exact native item lookup returned a different item identity.")
    return item


def current_library_items(auth: str, library_id: str, selected_items: list[dict] | None = None) -> list[dict]:
    """Read selected-library members including native alternate versions from the global current-item query."""
    root = library_root_path(auth, library_id)
    if selected_items is None:
        selected_items = native_items_in_library(auth, library_id)
    global_items = native_items(auth)
    current = merge_selected_library_items(selected_items, global_items, root)
    current = expand_alternate_source_items(current, root,
                                            lambda source_id: current_native_item_by_id(auth, source_id))
    if ACTIVE_RECORDER is not None:
        root_ids = {canonical_guid(item["Id"], "selected query item") for item in selected_items
                    if item.get("Id") and str(item.get("Path") or "").replace("\\", "/").startswith(
                        root.replace("\\", "/").rstrip("/") + "/")}
        current_ids = {canonical_guid(item["Id"], "current root item") for item in current if item.get("Id")}
        ACTIVE_RECORDER.record("native_library_candidate_identity_union", library_id=library_id,
                               library_root_sha256=digest(root), selected_query_count=len(selected_items),
                               selected_query_media_count=len(root_ids), global_current_count=len(global_items),
                               current_root_candidate_count=len(current),
                               alternate_version_ids=sorted(current_ids - root_ids))
    return current


def selected_library_project_items(selected_items: list[dict], library_root: str) -> list[dict]:
    """Keep the library query's visible project DTOs, which own grouped alternate MediaSources."""
    root = library_root.replace("\\", "/").rstrip("/")
    projects: dict[str, dict] = {}
    for item in selected_items:
        item_id = item.get("Id")
        path = str(item.get("Path") or "").replace("\\", "/")
        if not item_id or not path.startswith(root + "/"):
            continue
        item_key = canonical_guid(item_id, "selected-library project item")
        require(item_key not in projects,
                f"The selected-library query returned duplicate project identity {item_key}.")
        projects[item_key] = item
    return [projects[item_key] for item_key in sorted(projects)]


def map_candidate_items_to_projects(candidate_manifest: dict, project_items: list[dict]) -> dict[str, str]:
    """Map every native candidate ID to its visible library project through current MediaSource IDs."""
    candidate_ids = {canonical_guid(row["item_id"], "candidate project mapping item")
                     for row in candidate_manifest.get("items", [])}
    project_by_id = {canonical_guid(item.get("Id"), "visible library project") : item
                     for item in project_items if item.get("Id")}
    require(len(project_by_id) == len(project_items), "A visible library project has no unique native item identity.")
    mapping: dict[str, str] = {}
    for project_id, item in project_by_id.items():
        if project_id in candidate_ids:
            mapping[project_id] = project_id
        for source in item.get("MediaSources") or []:
            if not source.get("Id"):
                continue
            source_id = canonical_guid(source["Id"], "visible project MediaSource")
            if source_id not in candidate_ids:
                continue
            previous = mapping.get(source_id)
            require(previous is None or previous == project_id,
                    f"Candidate {source_id} maps to multiple current library projects.")
            mapping[source_id] = project_id
    unmapped = sorted(candidate_ids - set(mapping))
    require(not unmapped,
            "Current candidate IDs are neither visible library projects nor grouped MediaSources: "
            + ", ".join(unmapped[:8]))
    return mapping


def current_native_source(auth: str, item_id: str, source_key: str) -> tuple[dict, dict]:
    """Read an exact current native item/source pair; missing identities are hard failures."""
    item_key = canonical_guid(item_id, "current native item")
    source_id = canonical_guid(source_key, "current native source")
    status, item = pe.request_json(
        "GET", f"/Items/{dashed(item_key)}?Fields=MediaSources,MediaStreams,Path,DateModified",
        headers={"Authorization": auth})
    require(status == 200, "The exact current native item read failed.")
    returned_item = canonical_guid(item.get("Id"), "returned native item")
    require(returned_item == item_key, "The native API returned a different project identity.")
    matches = [source for source in item.get("MediaSources", [])
               if source.get("Id") and canonical_guid(source.get("Id"), "returned MediaSource") == source_id]
    require(len(matches) == 1,
            f"The current native item did not return exactly one requested MediaSourceId (found {len(matches)}).")
    return item, matches[0]


def fixture_manifest_path(item: dict, source_id: str, fixture: dict) -> Path | None:
    """Resolve a current source to the actual owned STRM file used to create that source."""
    source_key = canonical_guid(source_id, "fixture manifest source")
    by_source = fixture.get("manifest_paths_by_source", {})
    candidate = by_source.get(source_key)
    if candidate is not None and Path(candidate).is_file():
        return Path(candidate)
    names = [str(item.get("Name") or "")]
    native_path = str(item.get("Path") or "").replace("\\", "/")
    if native_path.lower().endswith(".strm"):
        names.append(Path(native_path).stem)
    for name in names:
        candidate = fixture.get("manifest_paths_by_name", {}).get(name)
        if candidate is not None and Path(candidate).is_file():
            return Path(candidate)
        if name:
            for directory in (fixture.get("strm_dir"), fixture.get("local_dir")):
                if directory is None:
                    continue
                path = Path(directory) / (name + ".strm")
                if path.is_file():
                    return path
    return None


def current_source_state(auth: str, item_id: str, source_key: str, fixture: dict,
                         recorder: EvidenceRecorder | None = None, label: str = "source") -> dict:
    item, source = current_native_source(auth, item_id, source_key)
    streams = source.get("MediaStreams")
    if streams is None and len(item.get("MediaSources", [])) == 1:
        streams = item.get("MediaStreams", [])
    streams = streams or []
    path = source.get("Path")
    manifest_path = fixture_manifest_path(item, source_key, fixture)
    manifest = read_versioned_manifest(manifest_path) if manifest_path is not None else None
    row = fingerprint_row_for_key(item_id, source_key)
    state = {
        "item_id": canonical_guid(item_id, "source-state item"),
        "source_key": canonical_guid(source_key, "source-state source"),
        "name_sha256": digest(str(item.get("Name") or "")),
        "native_path_sha256": digest(str(item.get("Path") or "")),
        "native_url_hash": expected_url_hash(str(path)) if path else None,
        "etag": item.get("Etag"),
        "date_modified": item.get("DateModified"),
        "stream_types": sorted({str(stream.get("Type")) for stream in streams if stream.get("Type")}),
        "has_main_stream": any(stream.get("Type") in {"Video", "Audio"} for stream in streams),
        "manifest": manifest,
        "fingerprint": row,
    }
    if recorder is not None:
        recorder.record("source_snapshot", label=label, state=state)
    return {"item": item, "source": source, **state}


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


def fingerprint_row_for_key(item_id: str, source_key: str) -> dict | None:
    """Return only the exact current project/source row; an orphan row cannot stand in for it."""
    return pkg.fingerprint_row(item_id, source_key)


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
    if ACTIVE_RECORDER is not None:
        configuration = pkg.configuration_file()
        config_hash = hashlib.sha256(configuration.read_bytes()).hexdigest() if configuration.is_file() else None
        ACTIVE_RECORDER.record("configuration_write", http_status=status, payload=payload,
                               configuration_sha256=config_hash)
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


def collect_runtime_evidence(stage: str, *, require_running: bool) -> dict[str, dict]:
    """Persist the current Jellyfin/media logs and latest raw task poll before restart or cleanup."""
    recorder = ACTIVE_RECORDER
    if recorder is None:
        return {}
    stage_name = re.sub(r"[^A-Za-z0-9_-]", "-", stage)
    collected: dict[str, dict] = {}
    for component, name_resolver in (("jellyfin", container), ("media", media_container)):
        try:
            name = name_resolver()
        except Exception as error:
            recorder.record("log_capture_unavailable", stage=stage, component=component,
                            reason=_safe_exception(error))
            if require_running:
                raise RuntimeError(f"Could not resolve the {component} container before {stage}.") from error
            continue
        inspected = run("docker", "inspect", "--format",
                        "{{.Id}} {{.State.StartedAt}} {{.Image}} {{.Config.Image}}", name, timeout=30)
        if inspected.returncode != 0:
            recorder.record("log_capture_unavailable", stage=stage, component=component,
                            status=inspected.returncode, reason=_safe_exception(RuntimeError("container inspect failed")))
            if require_running:
                raise RuntimeError(f"Could not inspect the {component} container before {stage}.")
            continue
        values = inspected.stdout.strip().split(maxsplit=3)
        require(len(values) == 4, f"The {component} container identity was incomplete before {stage}.")
        identity = {"name": name, "id": values[0], "started_at": values[1], "image_id": values[2],
                    "configured_image": values[3],
                    "identity": f"{values[0]} {values[1]} {values[2]} {values[3]}"}
        if component == "jellyfin":
            recorder.set_container_identity(identity)
        else:
            recorder.record("media_container_identity", identity=identity)
        logs = run("docker", "logs", "--timestamps", "--since", identity["started_at"], name, timeout=90)
        if logs.returncode != 0:
            recorder.record("log_capture_failed", stage=stage, component=component,
                            identity=identity, status=logs.returncode)
            if require_running:
                raise RuntimeError(f"Could not read the {component} logs before {stage}.")
            continue
        raw = logs.stdout + logs.stderr
        safe = "\n".join(redact_log_text(line) for line in raw.splitlines())
        file_name = (f"logs/{stage_name}-{component}-{digest(identity['id'])[:12]}-"
                     f"{time.time_ns()}.log.txt")
        relative = recorder.write_raw(file_name, safe)
        collected[component] = {"identity": identity, "file": relative, "line_count": len(raw.splitlines()),
                                "sha256": digest(safe)}
        recorder.record("raw_log_capture", stage=stage, component=component, identity=identity,
                        since=identity["started_at"], file=relative,
                        line_count=len(raw.splitlines()), sha256=digest(safe))
    if require_running and "jellyfin" in collected:
        try:
            tasks = task_list(api_auth())
            recorder.snapshot(f"task-state-{stage_name}-{time.time_ns()}", {"stage": stage, "tasks": tasks})
        except Exception as error:
            recorder.record("task_snapshot_failed", stage=stage, error=_safe_exception(error))
            raise RuntimeError(f"Could not preserve the final Jellyfin task state before {stage}.") from error
    if require_running and set(collected) != {"jellyfin", "media"}:
        raise RuntimeError(f"The required Jellyfin/media logs were incomplete before {stage}.")
    return collected


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
        source = re.search(r"source_key ([0-9a-fA-F-]+)", line)
        running = re.search(r"running probes (\d+)", line)
        if timestamp is None or not (item and running):
            continue
        if since is not None and timestamp < since:
            continue
        entries.append({"item_id": item.group(1).lower().replace("-", ""),
                        "source_key": source.group(1).lower().replace("-", "") if source else None,
                        "running": int(running.group(1)), "timestamp": timestamp})
    return entries


def probe_join_events(name: str, since: datetime.datetime | None = None) -> list[dict]:
    """Return only joins to probes that had actually started, never preparing or permit waits."""
    entries: list[dict] = []
    for line in docker_log_lines(name):
        if "Batch joined a running native probe for item" in line:
            prefix = "Batch joined a running native probe for item"
            direction = "batch"
        elif "Joined a running native probe for item" in line:
            prefix = "Joined a running native probe for item"
            direction = "playback"
        else:
            continue
        timestamp = parse_docker_timestamp(line)
        item = re.search(re.escape(prefix) + r" ([0-9a-fA-F-]+)", line)
        source = re.search(r"source_key ([0-9a-fA-F-]+)", line)
        if timestamp is None or item is None or (since is not None and timestamp < since):
            continue
        entries.append({"item_id": canonical_guid(item.group(1), "joined probe item"),
                        "source_key": canonical_guid(source.group(1), "joined probe source") if source else None,
                        "direction": direction, "timestamp": timestamp})
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
                source = re.search(r"source ([0-9a-fA-F-]+)", line)
                if source is None:
                    source = re.search(r"source_key ([0-9a-fA-F-]+)", line)
                entries.append({"kind": kind, "item_id": item.group(1).lower().replace("-", "") if item else None,
                                "source_key": source.group(1).lower().replace("-", "") if source else None,
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


def canonical_guid(value: object, label: str) -> str:
    require(bool(value), f"The {label} has no native Guid identity.")
    try:
        return uuid.UUID(str(value)).hex
    except (ValueError, AttributeError) as error:
        raise RuntimeError(f"The {label} has an invalid native Guid identity.") from error


def guid_sort_key(value: object) -> tuple[int, int, int, int, int, int]:
    """Match .NET Guid.CompareTo field ordering used by BatchCheckRunner's fixed ID list."""
    return uuid.UUID(str(value)).fields


def build_candidate_manifest(items: list[dict], library_id: str, library_root: str,
                             batch_size: int = BATCH_OBJECT_LIMIT) -> dict:
    """Record the native item-ID set, source mapping, Guid ordering and fixed batch boundaries."""
    require(batch_size > 0, "The candidate manifest batch size must be positive.")
    root = library_root.rstrip("/")
    rows: dict[str, dict] = {}
    for item in items:
        path = str(item.get("Path") or "").replace("\\", "/")
        if not path.startswith(root + "/"):
            continue
        item_id = canonical_guid(item.get("Id"), "candidate item")
        require(item_id not in rows, f"The native candidate query returned duplicate item id {item_id}.")
        source_ids = sorted({canonical_guid(source.get("Id"), "candidate MediaSource")
                             for source in item.get("MediaSources", []) if source.get("Id")},
                            key=guid_sort_key)
        rows[item_id] = {
            "item_id": item_id,
            "name_sha256": digest(str(item.get("Name") or "")),
            "item_path_sha256": digest(path),
            "source_ids": source_ids,
            "source_count": len(source_ids),
        }
    ordered = sorted(rows.values(), key=lambda row: guid_sort_key(row["item_id"]))
    for ordinal, row in enumerate(ordered):
        row["ordinal"] = ordinal
        row["batch_index"] = ordinal // batch_size
        row["batch_offset"] = ordinal % batch_size
    batches = []
    for batch_index, start in enumerate(range(0, len(ordered), batch_size)):
        batch_rows = ordered[start:start + batch_size]
        batches.append({"batch_index": batch_index, "first_ordinal": start,
                        "last_ordinal": start + len(batch_rows) - 1,
                        "item_ids": [row["item_id"] for row in batch_rows]})
    return {"library_id": canonical_guid(library_id, "selected library"),
            "library_root_sha256": digest(root), "candidate_count": len(ordered),
            "batch_size": batch_size, "items": ordered, "batches": batches}


def plan_scope_change(candidate_manifest: dict, fixture: dict,
                      batch_size: int = BATCH_OBJECT_LIMIT) -> dict:
    """Choose a real first-batch hold and two changed bulk sources in a later fixed batch."""
    fixed = {row["item_id"]: row for row in candidate_manifest.get("items", [])}
    fixture_records = []
    for name in fixture.get("bulk_names", []):
        item = fixture.get("items", {}).get(name)
        if item is None:
            continue
        item_id = canonical_guid(item.get("Id"), f"fixture {name}")
        row = fixed.get(item_id)
        if row is not None:
            fixture_records.append({**row, "fixture_name": name})
    first_batch = [row for row in fixture_records if row["ordinal"] < batch_size]
    later_batch = [row for row in fixture_records if row["ordinal"] >= batch_size]
    require(first_batch, "No bulk fixture source falls in the first fixed batch for the hold probe.")
    require(len(later_batch) >= 2,
            "Fewer than two bulk fixture sources fall after the first fixed object batch; cannot prove unread targets.")
    hold = first_batch[0]
    delete, move_out = later_batch[:2]
    require(hold["source_count"] == 1 and delete["source_count"] == 1 and move_out["source_count"] == 1,
            "Scope-change hold/delete/move targets must each resolve to one physical source.")
    return {"hold": hold, "delete": delete, "move_out": move_out,
            "batch_size": batch_size, "candidate_count": candidate_manifest["candidate_count"]}


def validate_scope_change_round(candidate_manifest: dict, plan: dict,
                                probe_item_ids_before_mutation: list[str],
                                probe_item_ids_after_round: list[str],
                                moved_out_current_item_ids: list[str], summary_fields: dict) -> None:
    """Validate the evidence produced by the actual scope-change round orchestration."""
    fixed = {row["item_id"]: row for row in candidate_manifest.get("items", [])}
    hold = plan.get("hold", {})
    delete = plan.get("delete", {})
    move_out = plan.get("move_out", {})
    require(hold.get("item_id") in fixed and delete.get("item_id") in fixed and move_out.get("item_id") in fixed,
            "A scope-change target was not present in the actual captured candidate identity set.")
    require(hold.get("batch_index") == 0,
            "The held probe source was not in the first native Guid-ordered object batch.")
    require(delete.get("batch_index", 0) >= 1 and move_out.get("batch_index", 0) >= 1,
            "Delete/move-out targets were not in a later, unread object batch.")
    before = {canonical_guid(item_id, "pre-mutation probe item") for item_id in probe_item_ids_before_mutation}
    after = {canonical_guid(item_id, "round probe item") for item_id in probe_item_ids_after_round}
    moved_current = {canonical_guid(item_id, "moved-out current item") for item_id in moved_out_current_item_ids}
    targets = {delete["item_id"], move_out["item_id"]}
    require(not (targets & before),
            "A delete/move-out target had already started a real probe before the in-window mutation.")
    require(not (targets & after),
            "A delete/move-out target started a real batch probe after it left the fixed scope.")
    require(not (moved_current & after),
            "A re-keyed/current identity for the moved-out source was admitted to the stopped scope-change round.")
    require(summary_fields.get("candidates") == candidate_manifest.get("candidate_count"),
            "The batch summary candidate count does not match the recorded fixed native item-ID set.")
    require(summary_fields.get("batch_reads", 0) >= 2,
            "The scope-change round did not reach the later object batch containing its delete/move targets.")
    safe_settlements = summary_fields.get("missing", 0) + summary_fields.get("check_stage_incomplete", 0)
    require(safe_settlements == 2,
            "The deleted and moved-out fixed candidates were not both accounted as missing or safely incomplete.")
    require(summary_fields.get("actual_probe_calls", 0) == summary_fields.get("reliable_success", 0) == 1
            and summary_fields.get("probe_incomplete", 0) == 0,
            "The scope-change round did not limit actual probes to its one held source and settle it reliably.")


def validate_source_reconciliation(expected: dict, native_source: dict, fingerprint: dict | None,
                                   label: str) -> None:
    """Compare current Manifest, native source and all five fields at the exact current project/source key."""
    expected_item = canonical_guid(expected.get("item_id"), f"{label} expected item")
    expected_source = canonical_guid(expected.get("source_key"), f"{label} expected source")
    actual_source = canonical_guid(native_source.get("Id"), f"{label} native source")
    path = native_source.get("Path")
    require(bool(path), f"The {label} current native source has no address.")
    require(actual_source == expected_source,
            f"The {label} native source identity does not match its current Manifest/source mapping.")
    require(expected_url_hash(str(path)) == expected.get("url_hash"),
            f"The {label} native address does not match the current STRM Manifest.")
    streams = native_source.get("MediaStreams") or []
    require(any(stream.get("Type") in {"Video", "Audio"} for stream in streams),
            f"The {label} current native source has no required main media stream.")
    require(fingerprint is not None, f"The {label} exact current project/source fingerprint row is missing.")
    actual_item = canonical_guid(fingerprint.get("item_id"), f"{label} fingerprint item")
    actual_key = canonical_guid(fingerprint.get("source_key"), f"{label} fingerprint source")
    require(actual_item == expected_item and actual_key == expected_source,
            f"The {label} fingerprint belongs to a stale/orphan project or source identity.")
    expected_fields = {"item_id": expected_item, "source_key": expected_source,
                       "url_hash": expected.get("url_hash"), "sha1": expected.get("sha1"),
                       "file_size": expected.get("file_size")}
    actual_fields = {"item_id": actual_item, "source_key": actual_key,
                     "url_hash": fingerprint.get("url_hash"), "sha1": fingerprint.get("sha1"),
                     "file_size": fingerprint.get("file_size")}
    require(actual_fields == expected_fields,
            f"The {label} five-field fingerprint does not match its current Manifest: {actual_fields}.")


def expected_fingerprint_row(item_id: str, source_key: str, manifest: dict,
                              previous: dict | None) -> dict:
    """Build the exact five-field expectation, retaining SHA-1 only for the same unchanged version."""
    canonical_item = canonical_guid(item_id, "expected fingerprint item")
    canonical_source = canonical_guid(source_key, "expected fingerprint source")
    url_hash = manifest.get("url_hash")
    require(bool(url_hash), "The current supported STRM Manifest has no valid URL hash.")
    sha1 = manifest.get("sha1")
    if sha1 is None and previous is not None:
        same_version = (previous.get("item_id") == canonical_item
                        and previous.get("source_key") == canonical_source
                        and previous.get("url_hash") == url_hash
                        and previous.get("file_size") == manifest.get("file_size")
                        and isinstance(previous.get("sha1"), str)
                        and re.fullmatch(r"[0-9a-f]{40}", previous["sha1"]) is not None)
        if same_version:
            sha1 = previous["sha1"]
    return {"item_id": canonical_item, "source_key": canonical_source,
            "url_hash": url_hash, "sha1": sha1, "file_size": manifest.get("file_size")}


def validate_url_race_intermediate(native_state: dict, baseline_a: dict,
                                   allowed_native_hashes: set[str], label: str) -> None:
    """Keep the A fingerprint through a scan that may persist its observed B or current C address."""
    require(native_state.get("native_url_hash") in allowed_native_hashes,
            f"The {label} native address matches neither the trusted A, scan-observed B, nor current C URL.")
    require(native_state.get("has_main_stream"), f"The {label} native source has no required main stream.")
    require(native_state.get("fingerprint") == baseline_a,
            f"The {label} observation changed the complete trusted A fingerprint row.")


def validate_stop_round_snapshot(baseline_rows: dict[str, dict], started_item_ids: set[str],
                                 observed_rows: dict[str, dict | None], native_states: dict[str, dict],
                                 expected_rows: dict[str, dict], *, joined_item_ids: set[str],
                                 reliable_success: int) -> None:
    """Require the stopped round's own save/commit results before any later convergence run."""
    baseline = {canonical_guid(key, "stop baseline item"): value for key, value in baseline_rows.items()}
    started = {canonical_guid(key, "started stop item") for key in started_item_ids}
    joined = {canonical_guid(key, "joined stop item") for key in joined_item_ids}
    rows = {canonical_guid(key, "observed stop item"): value for key, value in observed_rows.items()}
    states = {canonical_guid(key, "native stop item"): value for key, value in native_states.items()}
    expected = {canonical_guid(key, "expected stop item"): value for key, value in expected_rows.items()}
    require(joined and joined <= started, "The stop-round snapshot does not include a still-running joined source.")
    require(reliable_success == len(started),
            "The stopped round summary did not exactly count the actually started/joined successful sources.")
    require(set(rows) == set(baseline) == set(expected) == set(states),
            "The stop-round before/after snapshot is missing one or more changed source identities.")
    for item_id in baseline:
        row = rows[item_id]
        native = states[item_id]
        if item_id in started:
            require(row == expected[item_id],
                    f"Started/joined item {item_id} did not commit the stop-round five-field row before re-run.")
            require(native.get("url_hash") == expected[item_id].get("url_hash") and native.get("has_main_stream"),
                    f"Started/joined item {item_id} did not persist its new native address and main stream.")
        else:
            require(row == baseline[item_id],
                    f"Unstarted item {item_id} changed its trusted five-field row during the stopped round.")
            require(native.get("url_hash") == baseline[item_id].get("url_hash") and native.get("has_main_stream"),
                    f"Unstarted item {item_id} did not retain its old native address and main stream.")


def require_recovery_source_success(expected: dict, native_source: dict, fingerprint: dict | None,
                                   summary_fields: dict, outcomes: list[dict], label: str) -> None:
    validate_source_reconciliation(expected, native_source, fingerprint, label)
    require(summary_fields.get("need_probe") == 1 and summary_fields.get("actual_probe_calls") == 1
            and summary_fields.get("reliable_success") == 1 and summary_fields.get("probe_incomplete") == 0,
            f"The {label} recovery round did not perform exactly one successful required probe.")
    require(any(event.get("kind") == "accepted" for event in outcomes),
            f"The {label} recovery round has no successful native probe/commit event.")


def require_refresh_completed(before: dict, after: dict, events: list[dict], item_name: str,
                              started_at: datetime.datetime, completed_at: datetime.datetime, label: str) -> None:
    relevant = [event for event in events if event.get("item_name") == item_name
                and started_at <= event.get("timestamp", started_at) <= completed_at]
    started = [event for event in relevant if event.get("kind") == "started"]
    ended = [event for event in relevant if event.get("kind") == "completed"]
    require(started and ended and min(event["timestamp"] for event in ended) >= min(
        event["timestamp"] for event in started),
        f"The {label} has no matching native processing start and completion observed in this operation window.")
    before_etag = before.get("Etag", before.get("etag"))
    after_etag = after.get("Etag", after.get("etag"))
    require(before_etag is not None and after_etag is not None,
            f"The {label} did not record native ETag state before and after processing.")
    require(before_etag != after_etag,
            f"The {label} did not observe a changed native ETag for the requested processing operation.")


def require_no_new_round(entries_before_settlement: int, entries_before_stop: int, label: str) -> None:
    """A re-run or timer must not actually enter a new round while the old round is draining (BR-42-3)."""
    require(entries_before_settlement == entries_before_stop,
            f"A {label} actually entered a new round during the stopped round's drain "
            f"({entries_before_settlement} > {entries_before_stop} entries before settlement).")


def select_stop_round_sources(names: list[str], item_ids_by_name: dict[str, str],
                              first_batch: list[str], second_batch: list[str]) -> tuple[list[str], str]:
    """Choose early named fixtures within batch one, independent of their random GUID order."""
    first_batch_ids = {canonical_guid(item_id, "first stop candidate batch") for item_id in first_batch}
    first_names = [name for name in names
                   if canonical_guid(item_ids_by_name[name], f"stop fixture {name}") in first_batch_ids]
    require(len(first_names) >= 3, "The stop fixture has fewer than three named candidates in its first object batch.")
    require(bool(second_batch), "The stop fixture has no candidate in its later object batch.")
    return first_names[:3], canonical_guid(second_batch[0], "unread stop candidate")


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
    require(not path.exists(), f"Refusing to overwrite an existing scenario STRM fixture: {path.name}.")
    lines = ["# strm-probe-version:1"]
    if sha1 is not None:
        lines.append(f"# strm-probe-sha1:{sha1}")
    if size is not None:
        lines.append(f"# strm-probe-size:{size}")
    lines.append(url)
    data = ("\n".join(lines) + "\n").encode("utf-8")
    result = pe.write_owned_bytes(path, data, label=f"scan STRM {name}")
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("strm_create", operation="create", file_identity=path,
                               manifest_sha256=hashlib.sha256(data).hexdigest(), url_hash=expected_url_hash(url),
                               sha1=sha1, file_size=size, observed_at=now_utc())
    return result


def rewrite_strm(path: Path, url: str, sha1: str | None, size: int | None) -> None:
    pe.require_owned_path(path, label=f"rewrite {path.name}")
    old_bytes = path.read_bytes()
    data = old_bytes.decode("utf-8-sig")
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
    new_bytes = ("\n".join(result) + "\n").encode("utf-8")
    pe.write_owned_bytes(path, new_bytes, label=f"rewrite {path.name}")
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("strm_rewrite", operation="replace-owned-fixture", file_identity=path,
                               old_manifest_sha256=hashlib.sha256(old_bytes).hexdigest(),
                               new_manifest_sha256=hashlib.sha256(new_bytes).hexdigest(),
                               url_hash=expected_url_hash(url), sha1=sha1, file_size=size,
                               observed_at=now_utc())


def advance_fixture_mtime_for_native_refresh(path: Path) -> dict:
    """Move an owned fixture beyond Jellyfin's one-second HasChanged threshold without changing content."""
    pe.require_owned_path(path, label=f"advance refresh fixture mtime {path.name}")
    before = path.stat(follow_symlinks=False)
    target_mtime_ns = max(time.time_ns(), before.st_mtime_ns + 2_000_000_000)
    os.utime(path, ns=(before.st_atime_ns, target_mtime_ns), follow_symlinks=False)
    after = path.stat(follow_symlinks=False)
    require(after.st_mtime_ns - before.st_mtime_ns > 1_000_000_000,
            "The native FullRefresh fixture did not advance beyond Jellyfin's one-second file-change threshold.")
    return {"content_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "before_mtime_ns": before.st_mtime_ns, "after_mtime_ns": after.st_mtime_ns,
            "advanced_ns": after.st_mtime_ns - before.st_mtime_ns, "observed_at": now_utc()}


def read_versioned_manifest(path: Path) -> dict | None:
    """Read the exact supported fixture fields without following writes or inferring from mtime."""
    data = path.read_bytes()
    text = data.decode("utf-8-sig")
    version = None
    sha1_value = None
    size_value = None
    url = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# strm-probe-version:"):
            version = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("# strm-probe-sha1:"):
            sha1_value = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("# strm-probe-size:"):
            size_value = stripped.split(":", 1)[1].strip()
        elif not stripped.startswith("#") and url is None:
            url = stripped
    if version != "1":
        return None
    require(bool(url), f"A supported fixture manifest is missing its URL: {path.name}.")
    sha1 = sha1_value.lower() if sha1_value and re.fullmatch(r"[0-9a-fA-F]{40}", sha1_value) else None
    try:
        parsed_size = int(size_value) if size_value is not None else None
    except ValueError:
        parsed_size = None
    if parsed_size is not None and (parsed_size < 0 or parsed_size > 2**63 - 1):
        parsed_size = None
    return {"url": url, "url_hash": expected_url_hash(url), "sha1": sha1,
            "file_size": parsed_size, "manifest_sha256": hashlib.sha256(data).hexdigest(),
            "file_identity_sha256": digest(str(path))}


def delete_owned_fixture(path: Path, label: str) -> None:
    pe.require_owned_path(path, label=label)
    require(path.is_file(), f"The {label} fixture disappeared before its recorded deletion.")
    data = path.read_bytes()
    path.unlink()
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("fixture_file_mutation", operation="delete", label=label,
                               old_file_identity=path, old_manifest_sha256=hashlib.sha256(data).hexdigest(),
                               observed_at=now_utc())


def move_owned_fixture(source: Path, destination: Path, label: str) -> None:
    pe.require_owned_path(source, label=label)
    pe.require_owned_path(destination.parent, label=f"{label} destination directory")
    require(source.is_file(), f"The {label} source fixture does not exist.")
    require(not destination.exists(), f"Refusing to overwrite an existing {label} destination fixture.")
    data = source.read_bytes()
    source_identity = source
    shutil.move(str(source), str(destination))
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("fixture_file_mutation", operation="move", label=label,
                               old_file_identity=source_identity, new_file_identity=destination,
                               manifest_sha256=hashlib.sha256(data).hexdigest(), observed_at=now_utc())


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
    if ACTIVE_RECORDER is not None:
        collect_runtime_evidence("before-instance-rebuild", require_running=False)
    clear_strm_fixtures()
    pe.prepare_clean_instance()
    deployment = pe.deploy_archive(package)
    package_sha256 = hashlib.sha256(package.read_bytes()).hexdigest()
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("package_deployment", archive_sha256=package_sha256,
                              folder_sha256=digest(str(deployment.get("folder", ""))),
                              extracted=deployment.get("extracted"))
    deployed_payload = pkg.deployed_matches_archive(package)
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("package_payload_verified", archive_sha256=package_sha256,
                              result=deployed_payload)
        ACTIVE_RECORDER.set_metadata(deployment={"archive_sha256": package_sha256,
                                                 "folder_sha256": digest(str(deployment.get("folder", ""))),
                                                 "payload": deployed_payload})
    restart()
    auth = api_auth()
    require(pe.public_info().get("Version") == "12.2.0", "The package instance is not Jellyfin 12.2.0.")
    require(str(plugin_status(auth)).lower() in {"active", "0"}, "The plugin is not Active after archive-only install.")
    if ACTIVE_RECORDER is not None:
        images = pe.load_image_lock()
        identities = {"jellyfin": docker_container_identity(container()),
                      "media": docker_container_identity(media_container())}
        ACTIVE_RECORDER.set_metadata(runtime_identities=identities,
                                     locked_images=images,
                                     configuration_sha256=(hashlib.sha256(pkg.configuration_file().read_bytes()).hexdigest()
                                                           if pkg.configuration_file().is_file() else None))
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


def index_fixture_source_paths(fixture: dict) -> None:
    """Map every original source identity to the actual owned STRM file backing it."""
    by_name: dict[str, Path] = {}
    by_source: dict[str, Path] = {}
    for name, item in fixture.get("items", {}).items():
        matches = [Path(directory) / (name + ".strm")
                   for directory in (fixture["strm_dir"], fixture["local_dir"])
                   if (Path(directory) / (name + ".strm")).is_file()]
        require(len(matches) == 1, f"The actual STRM file for fixture {name!r} was missing or ambiguous.")
        path = matches[0]
        by_name[name] = path
        for source in item.get("MediaSources", []):
            if source.get("Id"):
                by_source[canonical_guid(source["Id"], f"fixture {name} source")] = path
    fixture["manifest_paths_by_name"] = by_name
    fixture["manifest_paths_by_source"] = by_source


def capture_candidate_manifest(auth: str, library_id: str, fixture: dict,
                               recorder: EvidenceRecorder | None = None, label: str = "candidate") -> dict:
    """Capture the actual native item-ID set, Guid order, batches, sources and current STRM manifests."""
    root = library_root_path(auth, library_id)
    native = current_library_items(auth, library_id)
    manifest = build_candidate_manifest(native, library_id, root, batch_size=BATCH_OBJECT_LIMIT)
    native_by_id = {canonical_guid(item.get("Id"), "native candidate"): item for item in native if item.get("Id")}
    for row in manifest["items"]:
        item = native_by_id.get(row["item_id"])
        require(item is not None, "The fixed candidate manifest lost a current native item identity.")
        source_manifest_rows = []
        for source in item.get("MediaSources", []):
            if not source.get("Id"):
                require(not str(item.get("Path") or "").lower().endswith(".strm"),
                        f"A versioned STRM candidate {row['item_id']} has a MediaSource without an identity.")
                continue
            source_id = canonical_guid(source["Id"], "native candidate MediaSource")
            path = fixture_manifest_path(item, source_id, fixture)
            if path is None:
                source_manifest_rows.append({"source_key": source_id, "classification": "non-fixture"})
                continue
            parsed = read_versioned_manifest(path)
            source_manifest_rows.append({
                "source_key": source_id,
                "classification": "versioned-strm" if parsed is not None else "legacy-strm",
                "manifest_sha256": parsed["manifest_sha256"] if parsed else hashlib.sha256(path.read_bytes()).hexdigest(),
                "url_hash": parsed["url_hash"] if parsed else None,
                "sha1": parsed["sha1"] if parsed else None,
                "file_size": parsed["file_size"] if parsed else None,
            })
        if str(item.get("Path") or "").lower().endswith(".strm"):
            require(source_manifest_rows and all(row.get("classification") == "versioned-strm"
                                                 for row in source_manifest_rows),
                    f"The current supported STRM candidate {row['item_id']} has no readable versioned source Manifest.")
        row["sources"] = source_manifest_rows
    if recorder is not None:
        recorder.record("candidate_manifest", label=label, manifest=manifest)
        recorder.snapshot(f"candidate-manifest-{label}-{time.time_ns()}", manifest)
    return manifest


def fixture_source_id(fixture: dict, name: str) -> str:
    item = fixture.get("items", {}).get(name)
    require(item is not None, f"The fixture item {name!r} has no recorded native identity.")
    sources = [source for source in item.get("MediaSources", []) if source.get("Id")]
    require(len(sources) == 1,
            f"The fixture source {name!r} must have exactly one physical source before merge, found {len(sources)}.")
    return canonical_guid(sources[0]["Id"], f"fixture source {name}")


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
    fixture = {"nonce": nonce, "media_sha": media_sha, "media_size": media_size, "plain_url": plain_url,
               "bulk_names": bulk_names, "out_name": out_name, "playback_name": playback_name,
               "movein_name": movein_name, "batch_name": batch_name, "mv_a_name": mv_a_name,
               "mv_b_name": mv_b_name, "content_name": content_name, "size_name": size_name,
               "race_name": race_name, "items": items, "strm_dir": strm_dir, "local_dir": local_dir}
    index_fixture_source_paths(fixture)
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("fixture_manifest_index", entries=[
            {"name": name, "item_id": item.get("Id"),
             "source_ids": [source.get("Id") for source in item.get("MediaSources", [])],
             "manifest": read_versioned_manifest(fixture["manifest_paths_by_name"][name])}
            for name, item in items.items()])
    return fixture


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
    baseline_rows: dict[str, dict] = {}
    for name in [*fixture["bulk_names"], fixture["batch_name"], fixture["mv_a_name"], fixture["mv_b_name"],
                 fixture["content_name"], fixture["size_name"], fixture["race_name"]]:
        item = fixture["items"][name]
        source_id = fixture_source_id(fixture, name)
        row = fingerprint_row_for_key(item["Id"], source_id)
        require(row is not None, f"The first-trust baseline has no exact project/source row for {name}.")
        baseline_rows[f"{canonical_guid(item['Id'], name)}:{source_id}"] = row
    fixture["baseline_rows"] = baseline_rows
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("first_trust_fingerprint_baseline", rows=baseline_rows)
        ACTIVE_RECORDER.snapshot(f"first-trust-baseline-{time.time_ns()}", baseline_rows)
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


def wait_for_probe_join(item_id: str, source_key: str, since: datetime.datetime,
                        timeout: int = 30) -> dict:
    deadline = time.monotonic() + timeout
    expected_item = canonical_guid(item_id, "expected joined item")
    expected_source = canonical_guid(source_key, "expected joined source")
    while time.monotonic() < deadline:
        matches = [event for event in probe_join_events(container(), since=since)
                   if event["item_id"] == expected_item and event["source_key"] == expected_source
                   and event["direction"] == "batch"]
        if matches:
            return matches[0]
        time.sleep(0.2)
    raise RuntimeError("The batch did not join the exact playback source after its native probe had started.")


def native_refresh_log_events(item_name: str, item_id: str, since: datetime.datetime,
                              until: datetime.datetime | None = None) -> list[dict]:
    """Read only this operation's exact-item Jellyfin refresh processing markers."""
    expected_item = canonical_guid(item_id, "FullRefresh item")
    events = []
    for line in docker_log_lines(container()):
        timestamp = parse_docker_timestamp(line)
        if timestamp is None or timestamp < since or (until is not None and timestamp > until):
            continue
        if item_name not in line and expected_item not in line.lower().replace("-", ""):
            continue
        if "File changed, pruning extracted data" in line:
            events.append({"kind": "started", "item_name": item_name, "item_id": expected_item,
                           "timestamp": timestamp})
        elif "Error refreshing item" in line:
            events.append({"kind": "failed", "item_name": item_name, "item_id": expected_item,
                           "timestamp": timestamp})
    return events


def wait_for_full_refresh_completion(auth: str, item_id: str, source_key: str, item_name: str,
                                     before_state: dict, expected_url_hash: str,
                                     started_at: datetime.datetime, fixture: dict,
                                     timeout: int = 90) -> tuple[dict, list[dict], datetime.datetime]:
    """Require this operation's item processing marker and a changed, stable native state as its end signal."""
    deadline = time.monotonic() + timeout
    marker_seen = False
    stable_candidate = None
    while time.monotonic() < deadline:
        events = native_refresh_log_events(item_name, item_id, started_at)
        if any(event["kind"] == "failed" for event in events):
            raise RuntimeError("Jellyfin logged a native FullRefresh failure for the requested item.")
        marker_seen = marker_seen or any(event["kind"] == "started" for event in events)
        state = current_source_state(auth, item_id, source_key, fixture, label="FullRefresh polling")
        etag_changed = (before_state.get("etag") is not None and state.get("etag") is not None
                        and state["etag"] != before_state["etag"])
        if marker_seen and etag_changed and state["native_url_hash"] == expected_url_hash and state["has_main_stream"]:
            signature = (state["etag"], state["native_url_hash"], tuple(state["stream_types"]))
            if signature == stable_candidate:
                completed_at = now_utc()
                completion = {"kind": "completed", "item_name": item_name,
                              "item_id": canonical_guid(item_id, "FullRefresh completed item"),
                              "timestamp": completed_at, "etag": state["etag"],
                              "native_url_hash": state["native_url_hash"]}
                return state, [*events, completion], completed_at
            stable_candidate = signature
        else:
            stable_candidate = None
        time.sleep(0.5)
    raise RuntimeError("The exact FullRefresh operation did not expose a processing marker and stable native end state before timeout.")


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
    candidate_manifest = capture_candidate_manifest(auth, libraries["strm"], fixture, recorder, "overlap")
    require(candidate_manifest["candidate_count"] >= BULK_COUNT,
            f"The selected library captured too few native candidate item IDs: {candidate_manifest['candidate_count']}.")

    batch_id = uuid.uuid4().hex
    playback_id = uuid.uuid4().hex
    batch_path = fixture["strm_dir"] / (fixture["batch_name"] + ".strm")
    playback_path = fixture["local_dir"] / (fixture["playback_name"] + ".strm")
    content_path = fixture["strm_dir"] / (fixture["content_name"] + ".strm")
    size_path = fixture["strm_dir"] / (fixture["size_name"] + ".strm")

    batch_b_url = delay_url(fixture["plain_url"], PROBE_DELAY_SECONDS, batch_id)
    playback_url = delay_url(fixture["plain_url"], PROBE_DELAY_SECONDS, playback_id)
    batch_c_url = unique_url(fixture["plain_url"], "batch-c-" + uuid.uuid4().hex[:8])
    batch_item_id = items[fixture["batch_name"]]["Id"]
    batch_source_id = fixture_source_id(fixture, fixture["batch_name"])
    baseline_a = fingerprint_row_for_key(batch_item_id, batch_source_id)
    require(baseline_a is not None, "The URL race source has no complete trusted A baseline before URL B.")
    recorder.record("source_snapshot", label="URL race before B", state=current_source_state(
        auth, batch_item_id, batch_source_id, fixture, recorder, "URL race before B"))
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
    batch_probe = probe_start_for_item(probe_starts, batch_item_id)
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
    batch_row = fingerprint_row_for_key(batch_item_id, batch_source_id)
    require(batch_row == baseline_a,
            f"The URL-B probe did not preserve the complete trusted A fingerprint row: {batch_row}.")
    b_state = current_source_state(auth, batch_item_id, batch_source_id, fixture, recorder, "URL race after B")
    current_c_hash = expected_url_hash(batch_c_url)
    validate_url_race_intermediate(b_state, baseline_a,
                                   {baseline_a["url_hash"], expected_url_hash(batch_b_url), current_c_hash},
                                   "URL race after B")
    outcomes = probe_outcome_events(container(), since=round_started)
    batch_outcomes = [event for event in outcomes
                      if event["item_id"] == items[fixture["batch_name"]]["Id"].lower().replace("-", "")]
    require(any(event["kind"] in {"manifest_changed", "failed", "not_committed"} for event in batch_outcomes),
            f"No mid-probe rejection/change event was observed for the batch source: {batch_outcomes}.")

    round_summary = latest_summary_after(round_started)
    fields = summary_fields_complete(round_summary)
    recorder.record("overlap_round", container=container_before, scan=scan_interval, overlap=scan_overlap,
                    candidate_manifest=candidate_manifest, changes=changes, summary=fields,
                    baseline_a=baseline_a, after_b=batch_row, after_b_native=b_state,
                    native_b_observed_during_scan=b_state["native_url_hash"] == expected_url_hash(batch_b_url))
    recorder.snapshot("overlap-round", {"scan": scan_overlap, "changes": changes, "fields": fields,
                                        "candidate_manifest": candidate_manifest,
                                        "batch_probe_start": batch_probe, "playback_probe_start": playback_probe,
                                        "baseline_a": baseline_a, "after_b": batch_row,
                                        "after_b_native": b_state,
                                        "native_b_observed_during_scan":
                                            b_state["native_url_hash"] == expected_url_hash(batch_b_url)})

    result = {
        "captured_candidates": candidate_manifest["candidate_count"],
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
    final = run_plugin_task_completed(auth, "post-overlap change round")
    summary_line = latest_summary_after(round_started)
    fields = summary_fields_complete(summary_line)
    outcomes = probe_outcome_events(container(), since=round_started)
    actual_starts = probe_start_events(container(), since=round_started)
    expected_sources = []
    for name in (fixture["batch_name"], fixture["content_name"], fixture["size_name"]):
        item = items[name]
        source_id = fixture_source_id(fixture, name)
        path = fixture["manifest_paths_by_source"][source_id]
        manifest = read_versioned_manifest(path)
        require(manifest is not None, f"The expected current manifest for {name} is not versioned.")
        expected = expected_fingerprint_row(item["Id"], source_id, manifest,
                                            fingerprint_row_for_key(item["Id"], source_id))
        start = probe_start_for_item(actual_starts, item["Id"])
        require(start is not None, f"The post-overlap run never actually started the required probe for {name}.")
        accepted = [event for event in outcomes if event["item_id"] == canonical_guid(item["Id"], name)
                    and event["kind"] == "accepted" and event["timestamp"] >= start["timestamp"]]
        require(accepted, f"The post-overlap run did not report a committed native probe for {name}.")
        state = current_source_state(auth, item["Id"], source_id, fixture, recorder,
                                     f"post-overlap {name}")
        validate_source_reconciliation(expected, state["source"], state["fingerprint"], name)
        expected_sources.append({"name": name, "expected": expected, "state": state,
                                 "probe_start": start, "accepted": accepted[-1]})
    require((fields.get("need_probe") or 0) >= 3 and (fields.get("actual_probe_calls") or 0) >= 3,
            f"The post-overlap summary does not account for the three required source probes: {summary_line}.")
    recorder.record("post_overlap_commit", task_result=task_result(final), summary=fields,
                    sources=expected_sources, outcomes=outcomes)
    recorder.snapshot(f"post-overlap-commit-{time.time_ns()}", {"summary": fields,
                                                               "sources": expected_sources,
                                                               "outcomes": outcomes})
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
    fixed = capture_candidate_manifest(auth, libraries["strm"], fixture, recorder, "scope-change")
    plan = plan_scope_change(fixed, fixture, batch_size=BATCH_OBJECT_LIMIT)
    hold_name = plan["hold"]["fixture_name"]
    delete_name = plan["delete"]["fixture_name"]
    moveout_name = plan["move_out"]["fixture_name"]
    hold_item_id = items[hold_name]["Id"]
    delete_id = plan["delete"]["item_id"]
    moveout_id = plan["move_out"]["item_id"]
    delete_source_id = plan["delete"]["source_ids"][0]
    moveout_source_id = plan["move_out"]["source_ids"][0]
    require(fixed["candidate_count"] == plan["candidate_count"],
            "The scope-change plan does not derive from the actual native fixed candidate identity set.")
    delete_baseline = fingerprint_row_for_key(delete_id, delete_source_id)
    moveout_baseline = fingerprint_row_for_key(moveout_id, moveout_source_id)
    require(delete_baseline is not None and moveout_baseline is not None,
            "The later-batch delete/move-out targets lack complete first-trust baseline rows.")

    hold_source_id = fixture_source_id(fixture, hold_name)
    hold_path = fixture["manifest_paths_by_source"][hold_source_id]
    hold_id = uuid.uuid4().hex
    hold_url = delay_url(fixture["plain_url"], PROBE_DELAY_SECONDS, hold_id)
    rewrite_strm(hold_path, hold_url, fixture["media_sha"], fixture["media_size"])

    round_started = now_utc()
    task = find_task_by_key(auth, TASK_KEY)
    previous = last_start(task)
    require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the scope-change batch start.")
    hold_backend_start = wait_for_backend_event(hold_id, "start", round_started)
    hold_probe = probe_start_for_item(probe_start_events(container(), since=round_started), hold_item_id)
    require(hold_probe is not None, "No real plugin probe start was observed for the scope-change hold source.")
    before_native_scan = probe_start_events(container(), since=round_started)
    target_ids = {delete_id, moveout_id}
    require(not ({event["item_id"] for event in before_native_scan} & target_ids),
            "A later-batch delete/move-out target had already started a real probe before the scan window.")

    # Start the native scan and wait until it is Running before issuing the finite scope changes.
    scan_task = find_task_by_key(auth, SCAN_TASK_KEY)
    scan_previous = last_start(scan_task)
    require(start_task(auth, scan_task["Id"]) == 204, "Jellyfin did not accept the scope-change native scan start.")
    wait_for_scan_running(auth, scan_task["Id"])

    changes: list[dict] = []
    probe_ids_at_mutation = [event["item_id"] for event in probe_start_events(container(), since=round_started)]
    require(not (set(probe_ids_at_mutation) & target_ids),
            "A delete/move-out target was processed before its identity could be safely mutated.")
    mutation_probe_snapshot = {"utc": now_utc(), "candidate_manifest": fixed,
                               "plan": plan, "started_item_ids": probe_ids_at_mutation}
    recorder.record("scope_change_mutation_boundary", evidence=mutation_probe_snapshot)
    recorder.snapshot(f"scope-change-boundary-{time.time_ns()}", mutation_probe_snapshot)
    # Delete a captured candidate (its file only; the library item is reconciled by the scan).
    delete_path = fixture["manifest_paths_by_source"][delete_source_id]
    delete_owned_fixture(delete_path, f"captured delete target {delete_name}")
    fixture["manifest_paths_by_name"].pop(delete_name, None)
    changes.append({"change": "delete_captured", "utc": now_utc().isoformat(),
                    "item_id": delete_id, "source_id": delete_source_id,
                    "old_file_identity": delete_path})
    # Move a captured candidate out of the selected library.
    moveout_old_path = fixture["manifest_paths_by_source"][moveout_source_id]
    moveout_new_path = fixture["local_dir"] / (moveout_name + ".strm")
    move_owned_fixture(moveout_old_path, moveout_new_path, f"captured move-out target {moveout_name}")
    fixture["manifest_paths_by_name"][moveout_name] = moveout_new_path
    fixture["manifest_paths_by_source"][moveout_source_id] = moveout_new_path
    changes.append({"change": "move_out_captured", "utc": now_utc().isoformat(),
                    "item_id": moveout_id, "source_id": moveout_source_id,
                    "old_file_identity": moveout_old_path, "new_file_identity": moveout_new_path})
    # Add a new STRM and move an out-of-scope STRM in, after the fixed set was captured.
    added_name = f"Scan Added {fixture['nonce']}"
    added_path = write_strm_to(fixture["strm_dir"], added_name, fixture["plain_url"],
                  fixture["media_sha"], fixture["media_size"])
    fixture["manifest_paths_by_name"][added_name] = added_path
    changes.append({"change": "add_after_capture", "utc": now_utc().isoformat(),
                    "new_file_identity": added_path})
    moved_in_name = fixture["movein_name"]
    movein_old_path = fixture["manifest_paths_by_name"][moved_in_name]
    movein_new_path = fixture["strm_dir"] / (moved_in_name + ".strm")
    move_owned_fixture(movein_old_path, movein_new_path, f"move-in target {moved_in_name}")
    fixture["manifest_paths_by_name"][moved_in_name] = movein_new_path
    for item_source in items[moved_in_name].get("MediaSources", []):
        if item_source.get("Id"):
            fixture["manifest_paths_by_source"][canonical_guid(item_source["Id"], moved_in_name)] = movein_new_path
    changes.append({"change": "move_in_after_capture", "utc": now_utc().isoformat(),
                    "item_id": items[moved_in_name]["Id"], "old_file_identity": movein_old_path,
                    "new_file_identity": movein_new_path})

    # Wait for the scan to complete and bind its authoritative interval.
    scan_after = wait_for_new_execution(auth, scan_task["Id"], scan_previous, timeout=MAX_WAIT)
    scan_interval = require_completed_execution(scan_after, scan_previous, "scope-change native scan")
    for change in changes:
        require_change_in_window(_parse_utc(change["utc"]), scan_interval, change["change"])

    final = wait_for_new_execution(auth, task["Id"], previous, timeout=MAX_WAIT)
    require_completed_execution(final, previous, "scope-change batch")
    hold_backend_finish = wait_for_backend_event(hold_id, "finish", round_started)
    assert_scan_probe_overlap(scan_interval, hold_backend_start, hold_backend_finish, "scope-change hold")

    # A scan can enter Running after its folder enumeration has already begun. If a filesystem
    # mutation lands after that directory was read, the first scan correctly has no new membership
    # to publish. Run a separate native reconciliation scan after the fixed-set batch settles so
    # current-library membership is read from a scan that starts with the final fixture layout.
    reconciliation_task, reconciliation_interval = run_native_scan_completed(
        auth, "post-scope native reconciliation scan")
    recorder.record("scope_change_native_reconciliation", task_result=task_result(reconciliation_task),
                    scan_interval=reconciliation_interval)

    summary = latest_summary_after(round_started)
    fields = summary_fields_complete(summary)
    require(fields.get("candidate_fetch_failed") is False, f"The scope-change round failed its candidate fetch: {summary}.")
    moved_out_current = [item for item in native_items(auth) if item.get("Name") == moveout_name]
    current_selected_items = current_library_items(auth, libraries["strm"])
    current_selected_ids = {canonical_guid(item["Id"], "current selected-library item")
                            for item in current_selected_items if item.get("Id")}
    moved_out_current_ids = [canonical_guid(item["Id"], "moved-out current item")
                             for item in moved_out_current if item.get("Id")]
    require(not (set(moved_out_current_ids) & current_selected_ids),
            "The moved-out source still belongs to the selected library after the native scan.")
    # The deleted captured candidate must be reconciled away before the stable-set check; the round
    # itself completed without failing on it (safe settlement), so no new probe or failure escaped.
    wait_for_item_absent(auth, delete_name)

    after_round_starts = probe_start_events(container(), since=round_started)
    validate_scope_change_round(
        fixed, plan, probe_ids_at_mutation, [event["item_id"] for event in after_round_starts],
        moved_out_current_ids, fields)
    require(fingerprint_row_for_key(delete_id, delete_source_id) == delete_baseline,
            "The fixed-set deleted source's old five-field fingerprint changed before the next run.")
    require(fingerprint_row_for_key(moveout_id, moveout_source_id) == moveout_baseline,
            "The fixed-set moved-out source's old five-field fingerprint changed before the next run.")
    moved_out_rows = {item_id: all_fingerprint_rows() for item_id in moved_out_current_ids}
    for item_id, rows in moved_out_rows.items():
        if item_id != canonical_guid(moveout_id, "captured move-out item"):
            require(not any(row["item_id"] == item_id for row in rows),
                    "A re-keyed moved-out current identity received a fingerprint row during the prohibited round.")

    # Save the scope-change result before any later run can overwrite or conceal it.
    recorder.record("scope_change_round_settled", plan=plan, summary=fields,
                    probe_ids_at_mutation=probe_ids_at_mutation,
                    probe_ids_after_round=[event["item_id"] for event in after_round_starts],
                    moved_out_current_ids=moved_out_current_ids,
                    deleted_baseline=delete_baseline, moved_out_baseline=moveout_baseline,
                    safe_target_settlements={"missing": fields["missing"],
                                             "check_stage_incomplete": fields["check_stage_incomplete"]})
    recorder.snapshot(f"scope-change-settled-{time.time_ns()}", {
        "candidate_manifest": fixed, "plan": plan, "changes": changes, "summary": fields,
        "probe_ids_at_mutation": probe_ids_at_mutation,
        "probe_ids_after_round": [event["item_id"] for event in after_round_starts],
        "moved_out_current_ids": moved_out_current_ids,
        "deleted_baseline": delete_baseline, "moved_out_baseline": moveout_baseline,
        "safe_target_settlements": {"missing": fields["missing"],
                                    "check_stage_incomplete": fields["check_stage_incomplete"]},
        "current_selected_item_ids": sorted(current_selected_ids),
    })

    # The added and moved-in items must not be processed in the fixed-set round.
    added_item = wait_for_item(auth, added_name)
    moved_in_item = wait_for_item(auth, moved_in_name)
    added_sources = [source for source in added_item.get("MediaSources", []) if source.get("Id")]
    require(added_sources, "The newly added STRM has no native source identity after the scan.")
    added_source_id = canonical_guid(added_sources[0]["Id"], "newly added current source")
    require(fingerprint_row_for_key(added_item["Id"], added_source_id) is None,
            "A STRM added during the fixed-set run was processed by the same round.")
    moved_in_source_id = canonical_guid((moved_in_item.get("MediaSources") or [{}])[0].get("Id"),
                                        "moved-in current source")
    require(fingerprint_row_for_key(moved_in_item["Id"], moved_in_source_id) is None,
            "A STRM moved in during the fixed-set run was processed by the same round.")
    # The next round must discover them.
    discovery_started = now_utc()
    run_plugin_task_completed(auth, "post-scope discovery round")
    added_item = wait_for_item(auth, added_name)
    moved_in_item = wait_for_item(auth, moved_in_name)
    for name, item in ((added_name, added_item), (moved_in_name, moved_in_item)):
        sources = [source for source in item.get("MediaSources", []) if source.get("Id")]
        require(sources, f"The next round's native object {name} has no source identity.")
        source_id = canonical_guid(sources[0]["Id"], f"discovered {name} source")
        source_file = fixture["manifest_paths_by_name"][name]
        fixture["items"][name] = item
        fixture["manifest_paths_by_source"][source_id] = source_file
        manifest = read_versioned_manifest(source_file)
        require(manifest is not None, f"The newly discovered fixture {name} has no versioned Manifest.")
        row = fingerprint_row_for_key(item["Id"], source_id)
        expected = expected_fingerprint_row(item["Id"], source_id, manifest, row)
        require(row == expected, f"The next round did not establish the exact current source identity for {name}.")
    next_round_events = probe_outcome_events(container(), since=discovery_started)
    recorder.record("scope_change_next_round_discovery", identities={
        "added": {"item_id": added_item["Id"], "source_ids": [source.get("Id") for source in added_item.get("MediaSources", [])]},
        "moved_in": {"item_id": moved_in_item["Id"], "source_ids": [source.get("Id") for source in moved_in_item.get("MediaSources", [])]},
    }, outcomes=next_round_events)

    recorder.record("scope_change_round", changes=changes, summary=fields,
                    candidate_manifest=fixed, plan=plan,
                    scan=[scan_interval[0].isoformat(), scan_interval[1].isoformat()])
    recorder.snapshot(f"scope-change-round-{time.time_ns()}", {"changes": changes, "fields": fields,
                                                                "candidate_manifest": fixed, "plan": plan})
    return {"move_out_not_batch_probed": True, "add_discovered_next_round": True,
            "move_in_discovered_next_round": True, "delete_settled": True,
            "scope_change_summary": summary, "added_name": added_name,
            "captured_candidates": fixed["candidate_count"],
            "delete_target": {"item_id": delete_id, "source_id": delete_source_id,
                              "batch_index": plan["delete"]["batch_index"]},
            "move_out_target": {"item_id": moveout_id, "source_id": moveout_source_id,
                                "current_item_ids": moved_out_current_ids,
                                "batch_index": plan["move_out"]["batch_index"]},
            "held_first_batch_source": {"item_id": hold_item_id, "batch_index": plan["hold"]["batch_index"]}}


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

    # Change A's current fixture manifest, then require this operation's own processing marker, ETag/native
    # address change and stable end state. The Jellyfin FullRefresh must not itself commit the plugin fingerprint.
    refresh_url = unique_url(fixture["plain_url"], "mv-refresh-" + uuid.uuid4().hex[:8])
    rewrite_strm(mv_a_path, refresh_url, fixture["media_sha"], fixture["media_size"])
    before_row_a = fingerprint_row_for_key(canonical, mv_a)
    before_row_b = fingerprint_row_for_key(canonical, mv_b)
    require(before_row_a == ra and before_row_b == rb,
            "The exact merged project/source rows changed before independent FullRefresh.")
    before_native_a = current_source_state(auth, canonical, mv_a, fixture, recorder, "before FullRefresh A")
    before_native_b = current_source_state(auth, canonical, mv_b, fixture, recorder, "before FullRefresh B")
    refresh_started = now_utc()
    mtime_evidence = advance_fixture_mtime_for_native_refresh(mv_a_path)
    recorder.record("full_refresh_fixture_mtime", item_id=canonical, source_key=mv_a,
                    manifest=read_versioned_manifest(mv_a_path), mtime=mtime_evidence)
    refresh_status = force_full_refresh(auth, dashed(canonical))
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("full_refresh_request", item_id=canonical, source_key=mv_a,
                               status=refresh_status, started_at=refresh_started)
    require(refresh_status == 204, f"Jellyfin rejected the independent FullRefresh ({refresh_status}).")
    refreshed_a, refresh_events, refresh_completed = wait_for_full_refresh_completion(
        auth, canonical, mv_a, fixture["mv_a_name"], before_native_a,
        expected_url_hash(refresh_url), refresh_started, fixture)
    require_refresh_completed(before_native_a, refreshed_a, refresh_events,
                              fixture["mv_a_name"], refresh_started, refresh_completed,
                              "independent FullRefresh")
    after_native_b = current_source_state(auth, canonical, mv_b, fixture, recorder, "after FullRefresh B")
    require(fingerprint_row_for_key(canonical, mv_a) == before_row_a
            and fingerprint_row_for_key(canonical, mv_b) == before_row_b,
            "The native FullRefresh directly changed a plugin fingerprint before a verified plugin probe.")
    require(after_native_b["fingerprint"] == before_row_b and after_native_b["has_main_stream"],
            "The independent FullRefresh corrupted the unselected version's source or exact fingerprint row.")
    if ACTIVE_RECORDER is not None:
        ACTIVE_RECORDER.record("full_refresh_completed", item_id=canonical, source_key=mv_a,
                               before=before_native_a, after=refreshed_a, events=refresh_events,
                               completed_at=refresh_completed)
        ACTIVE_RECORDER.snapshot(f"full-refresh-{time.time_ns()}", {
            "request_status": refresh_status, "started_at": refresh_started,
            "completed_at": refresh_completed, "before_a": before_native_a,
            "after_a": refreshed_a, "before_b": before_native_b,
            "after_b": after_native_b, "events": refresh_events,
            "row_a_before_and_after": before_row_a, "row_b_before_and_after": before_row_b,
        })

    # Only a new plugin task run may verify and commit A's refreshed manifest version.
    plugin_round_started = now_utc()
    refresh_round = run_plugin_task_completed(auth, "post-FullRefresh source commit")
    refresh_summary = summary_fields_complete(latest_summary_after(plugin_round_started))
    a_starts = probe_start_events(container(), since=plugin_round_started)
    a_start = probe_start_for_item(a_starts, canonical)
    a_outcomes = [event for event in probe_outcome_events(container(), since=plugin_round_started)
                  if event["item_id"] == canonical and event["kind"] == "accepted"]
    require(a_start is not None and a_outcomes,
            "The plugin did not perform and accept a real source-A probe after independent FullRefresh.")
    refreshed_manifest = read_versioned_manifest(mv_a_path)
    require(refreshed_manifest is not None, "The refreshed version-A Manifest is unreadable.")
    expected_a = expected_fingerprint_row(canonical, mv_a, refreshed_manifest, before_row_a)
    final_native_a = current_source_state(auth, canonical, mv_a, fixture, recorder, "after plugin FullRefresh reconciliation")
    validate_source_reconciliation(expected_a, final_native_a["source"], final_native_a["fingerprint"],
                                   "post-FullRefresh version A")
    require((refresh_summary.get("need_probe") or 0) == 1
            and (refresh_summary.get("actual_probe_calls") or 0) == 1
            and (refresh_summary.get("reliable_success") or 0) == 1,
            f"The post-FullRefresh batch did not account for exactly one successful A probe: {refresh_summary}.")
    ra = final_native_a["fingerprint"]
    url_a = refresh_url
    require(fingerprint_row_for_key(canonical, mv_b) == rb,
            "The post-FullRefresh A probe changed the distinct version-B fingerprint.")

    # Explicit MediaSourceId selection must return the selected version's own source identity and address.
    status_a, response_a = playback_info_selected(auth, dashed(canonical), mv_a)
    status_b, response_b = playback_info_selected(auth, dashed(canonical), mv_b)
    require(status_a == 200 and status_b == 200, "The explicit multi-version PlaybackInfo request failed.")
    _require_selected_source(response_a, mv_a, ra["url_hash"], "A")
    _require_selected_source(response_b, mv_b, rb["url_hash"], "B")
    recorder.record("multi_version_refresh", shared_project=True, refresh_status=refresh_status,
                    refresh_round=task_result(refresh_round), refresh_summary=refresh_summary,
                    source_a=final_native_a, source_b=after_native_b)
    return {"multi_version_rows": 2, "shared_project": True,
            "independent_full_refresh_status": refresh_status, "cross_version_fingerprint_stable": True,
            "selected_version_a_matches": True, "selected_version_b_matches": True,
            "full_refresh_completed_at": refresh_completed.isoformat(),
            "post_refresh_actual_probe_calls": refresh_summary.get("actual_probe_calls"),
            "committed_url_a_hash": ra["url_hash"], "committed_url_b_hash": rb["url_hash"]}


def _require_selected_source(response: dict, source_id: str, expected_hash: str, label: str) -> None:
    """Reject unfiltered, wrong-version, wrong-address and unusable explicit-source responses."""
    sources = response.get("MediaSources") or []
    require(len(sources) == 1,
            f"The selected version {label} response was not filtered to exactly one source (count {len(sources)}).")
    source = sources[0]
    require(canonical_guid(source.get("Id"), f"selected {label} source") == canonical_guid(source_id, label),
            f"The selected version {label} response returned a different MediaSourceId.")
    require(bool(source.get("Path")) and expected_url_hash(str(source["Path"])) == expected_hash,
            f"The selected version {label} did not return its own expected address.")
    streams = source.get("MediaStreams") or []
    require(any(stream.get("Type") in {"Video", "Audio"} for stream in streams),
            f"The selected version {label} has no required main media stream.")


def convergence(auth: str, fixture: dict, recorder: EvidenceRecorder, multi_version: dict) -> dict:
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

    reconciliation = reconcile_expected_sources(auth, libraries["strm"], fixture, recorder)
    # Restart and prove the committed addresses survive, covering a URL-changed source and a merged
    # multi-version source. A native scan may re-key a physical source id, so the current identity is
    # resolved from the current native MediaSources before the explicit selection check.
    batch_item = fixture["items"][fixture["batch_name"]]["Id"]
    batch_row = fingerprint_row(batch_item)
    require(batch_row is not None, "The URL-changed source has no committed fingerprint before restart.")
    mv_a = fixture["items"][fixture["mv_a_name"]]["Id"]
    mv_rows = [row for row in fingerprint_rows_for_source(mv_a)
               if row["url_hash"] == multi_version["committed_url_a_hash"]]
    require(mv_rows, "The multi-version source has no committed fingerprint for its changed address before restart.")
    canonical = dashed(mv_rows[0]["item_id"])
    restart()
    auth = api_auth()
    status, response = playback_info(auth, batch_item)
    require(status == 200 and source_path_matches_hash(response, batch_row["url_hash"]),
            "The URL-changed batch source address did not survive the restart.")
    assert_committed_address_survives(auth, canonical, multi_version["committed_url_a_hash"], "multi-version")
    recorder.record("convergence", stable=fields, repeat=repeat_fields, reconciliation=reconciliation)
    recorder.snapshot("convergence", {"stable": fields, "repeat": repeat_fields,
                                      "reconciliation": reconciliation})
    return {"stable_summary": summary, "repeat_summary": repeat,
            "stable_zero_probe": True, "restart_address_stable": True,
            "reconciled_sources": reconciliation["source_count"],
            "scan": [stable_scan[0].isoformat(), stable_scan[1].isoformat()]}


def reconcile_expected_sources(auth: str, library_id: str, fixture: dict,
                               recorder: EvidenceRecorder | None = None) -> dict:
    """Reconcile current library members to their actual versioned STRM files and exact five-field rows."""
    root = library_root_path(auth, library_id)
    selected_items = native_items_in_library(auth, library_id)
    project_items = selected_library_project_items(selected_items, root)
    current_items = current_library_items(auth, library_id, selected_items=selected_items)
    expected_set = build_candidate_manifest(current_items, library_id, root, batch_size=BATCH_OBJECT_LIMIT)
    candidate_project_map = map_candidate_items_to_projects(expected_set, project_items)
    checked: list[dict] = []
    ordinary: list[dict] = []
    legacy: list[dict] = []
    source_keys: set[tuple[str, str]] = set()
    problems: list[str] = []
    native_by_id = {canonical_guid(item.get("Id"), "reconciliation project"): item
                    for item in project_items if item.get("Id")}

    for item_id in sorted(native_by_id):
        item = native_by_id.get(item_id)
        item_path = str(item.get("Path") or "")
        is_strm = item_path.lower().endswith(".strm")
        sources = item.get("MediaSources") or []
        if is_strm and not sources:
            problems.append(f"supported/legacy STRM item {item_id} has no current native MediaSource identities")
            continue
        for source in sources:
            source_value = source.get("Id")
            manifest_path = None
            if source_value:
                manifest_path = fixture_manifest_path(item, str(source_value), fixture)
            if manifest_path is None and is_strm:
                name = str(item.get("Name") or "")
                manifest_path = fixture.get("manifest_paths_by_name", {}).get(name)
                if manifest_path is None and name:
                    for directory in (fixture.get("strm_dir"), fixture.get("local_dir")):
                        if directory is None:
                            continue
                        candidate = Path(directory) / (name + ".strm")
                        if candidate.is_file():
                            manifest_path = candidate
                            break
            if not is_strm:
                ordinary.append({"item_id": item_id, "source_id": source_value,
                                 "path_sha256": digest(item_path)})
                continue
            if manifest_path is None:
                problems.append(f"STRM item {item_id} has no resolvable current fixture manifest")
                continue
            try:
                manifest = read_versioned_manifest(Path(manifest_path))
            except (OSError, UnicodeDecodeError, RuntimeError) as error:
                problems.append(f"STRM item {item_id} has an unreadable current fixture manifest ({type(error).__name__})")
                continue
            if manifest is None:
                legacy.append({"item_id": item_id, "source_id": source_value,
                               "manifest_sha256": hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()})
                continue
            if not source_value:
                problems.append(f"supported versioned STRM item {item_id} has no current source identity")
                continue
            try:
                source_key = canonical_guid(source_value, "current STRM MediaSource")
            except RuntimeError:
                problems.append(f"supported versioned STRM item {item_id} has an invalid source identity")
                continue
            key = (item_id, source_key)
            if key in source_keys:
                problems.append(f"the current library query returned duplicate project/source key {key}")
                continue
            source_keys.add(key)
            previous = fingerprint_row_for_key(item_id, source_key)
            expected = expected_fingerprint_row(item_id, source_key, manifest, previous)
            try:
                validate_source_reconciliation(expected, source, previous, f"current source {item_id}/{source_key}")
            except RuntimeError as error:
                problems.append(f"source {item_id}/{source_key} did not reconcile ({type(error).__name__})")
                continue
            checked.append({"item_id": item_id, "source_key": source_key,
                            "manifest_sha256": manifest["manifest_sha256"],
                            "row": expected, "native_url_hash": expected_url_hash(str(source.get("Path") or "")),
                            "has_main_stream": True})
            if recorder is not None:
                recorder.record("source_reconciliation", item_id=item_id, source_key=source_key,
                                manifest=manifest, expected=expected, native_source=source, fingerprint=previous)

    require(not problems, "The stable expected set did not reconcile: " + "; ".join(problems[:8]))
    require(checked, "The stable expected set was empty; no supported current versioned STRM source was reconciled.")
    actual = {(row["item_id"], row["source_key"]) for row in checked}
    require(len(actual) == len(checked), "The stable source result contained duplicate current project/source identities.")
    result = {"source_count": len(checked), "sources": checked,
              "candidate_item_count": expected_set["candidate_count"],
              "project_item_count": len(project_items),
              "candidate_project_map": candidate_project_map,
              "ordinary_count": len(ordinary), "ordinary": ordinary,
              "legacy_count": len(legacy), "legacy": legacy,
              "candidate_manifest": expected_set}
    if recorder is not None:
        recorder.record("source_reconciliation_complete", result=result)
        recorder.snapshot(f"source-reconciliation-{time.time_ns()}", result)
    return result


# ---------------------------------------------------------------------------------------------------------------------
# Stop scenario
# ---------------------------------------------------------------------------------------------------------------------


def scenario_stop(package: Path, evidence_dir: Path | None, nonce: str, recorder: EvidenceRecorder) -> dict:
    """Playback owns a real probe first, batch joins it, then both settle through a native batch stop."""
    summary: dict[str, object] = {}
    auth = deploy_fresh(package)
    pe.add_library_authenticated(auth, OUT_OF_SCOPE_LIBRARY, ["/media/local"])
    auth = api_auth()
    media_sha, media_size = pe.media_sha1(pe.MEDIA_MP4)
    plain_url = "http://media:8080/" + pe.MEDIA_MP4
    names = [f"Scan Stop {nonce} {index:03d}" for index in range(BULK_COUNT)]
    paths = {name: write_strm_to(pe.WORK / "strm", name, plain_url, media_sha, media_size) for name in names}
    refresh_library(auth)
    items = {name: wait_for_item(auth, name) for name in names}
    fixture = {"nonce": nonce, "media_sha": media_sha, "media_size": media_size, "plain_url": plain_url,
               "bulk_names": names, "items": items, "strm_dir": pe.WORK / "strm",
               "local_dir": pe.WORK / "media"}
    index_fixture_source_paths(fixture)

    require(plugin_action(auth, False) == 204, "The plugin disable failed.")
    restart()
    auth = api_auth()
    prepare_native_streams(auth, [items[name] for name in names], plain_url)
    require(plugin_action(auth, True) == 204, "The plugin enable failed.")
    restart()
    auth = api_auth()
    libraries = scope_to_strm_library(auth)
    baseline_started = now_utc()
    baseline_task = run_plugin_task_completed(auth, "stop baseline round")
    baseline_summary = latest_summary_after(baseline_started)
    baseline_fields = summary_fields_complete(baseline_summary)
    require((baseline_fields.get("batch_reads") or 0) >= 2,
            f"The stop fixture did not cross the 128-object batch boundary: {baseline_summary}.")
    for name in names:
        item_id = items[name]["Id"]
        source_key = fixture_source_id(fixture, name)
        require(fingerprint_row_for_key(item_id, source_key) is not None,
                f"The stop scenario did not create the exact baseline row for {name}.")

    candidate_manifest = capture_candidate_manifest(auth, libraries["strm"], fixture, recorder, "stop")
    require(candidate_manifest["candidate_count"] == BULK_COUNT,
            f"The stop candidate set is not exactly the 130-object fixture: {candidate_manifest['candidate_count']}.")
    rows_by_id = {row["item_id"]: row for row in candidate_manifest["items"]}
    names_by_id = {canonical_guid(item["Id"], name): name for name, item in items.items()}
    require(set(rows_by_id) == set(names_by_id),
            "The native sorted candidate ID set does not match the fixture's current project identities.")
    first_batch = candidate_manifest["batches"][0]["item_ids"]
    second_batch = candidate_manifest["batches"][1]["item_ids"]
    first_names, unread_id = select_stop_round_sources(
        names, {name: item["Id"] for name, item in items.items()}, first_batch, second_batch)
    require(len(first_names) == 3 and second_batch,
            "The stop candidate manifest does not contain three first-batch sources and a later-batch target.")
    playback_first_name, second_name, queued_name = first_names
    changed_names = [playback_first_name, second_name, queued_name, names_by_id[unread_id]]
    changed_ids = [canonical_guid(items[name]["Id"], f"stop source {name}") for name in changed_names]
    playback_first_id, second_id, queued_id = changed_ids[:3]
    request_ids = {name: uuid.uuid4().hex for name in changed_names}
    baseline_rows: dict[str, dict] = {}
    baseline_states: dict[str, dict] = {}
    expected_rows: dict[str, dict] = {}
    for item_id, name in zip(changed_ids, changed_names):
        item = items[name]
        source_key = fixture_source_id(fixture, name)
        row = fingerprint_row_for_key(item_id, source_key)
        require(row is not None, f"Changed stop source {name} has no exact baseline row.")
        baseline_rows[item_id] = row
        baseline_states[item_id] = current_source_state(auth, item_id, source_key, fixture, recorder,
                                                        f"stop baseline {name}")

    playback_url = delay_url(plain_url, STOP_DELAY_SECONDS, request_ids[changed_names[0]])
    batch_url = delay_url(plain_url, STOP_DELAY_SECONDS, request_ids[changed_names[1]])
    queued_url = delay_url(plain_url, STOP_DELAY_SECONDS, request_ids[changed_names[2]])
    unread_url = unique_url(plain_url, "stop-unread-" + uuid.uuid4().hex[:8])
    for name, url in zip(changed_names, (playback_url, batch_url, queued_url, unread_url)):
        rewrite_strm(paths[name], url, media_sha, media_size)
    target_urls = dict(zip(changed_names, (playback_url, batch_url, queued_url, unread_url)))

    first_name = changed_names[0]
    first_item = items[first_name]
    first_source_key = fixture_source_id(fixture, first_name)
    request_started = now_utc()
    playback_holder: dict = {}

    def playback() -> None:
        try:
            playback_holder["result"] = playback_info(auth, first_item["Id"])
        except Exception as error:
            playback_holder["error"] = type(error).__name__

    playback_worker = threading.Thread(target=playback, name="scan-stop-playback-owner", daemon=True)
    playback_worker.start()
    playback_backend_start = wait_for_backend_event(request_ids[first_name], "start", request_started)
    playback_probe = probe_start_for_item(probe_start_events(container(), since=request_started), first_item["Id"])
    require(playback_probe is not None,
            "The stop scenario's playback-first source did not own an actually started native probe.")

    task = find_task_by_key(auth, TASK_KEY)
    previous = last_start(task)
    require(start_task(auth, task["Id"]) == 204, "Jellyfin did not accept the stop-scenario batch start.")
    joined = wait_for_probe_join(first_item["Id"], first_source_key, request_started)
    second_name = changed_names[1]
    second_item = items[second_name]
    batch_backend_start = wait_for_backend_event(request_ids[second_name], "start", request_started)
    second_probe = probe_start_for_item(probe_start_events(container(), since=request_started), second_item["Id"])
    require(second_probe is not None,
            "The stopped batch did not start the second source while the first remained joined and running.")
    entries_before_stop = len(batch_entry_events(request_started))

    stop_status = stop_task(auth, task["Id"])
    require(stop_status == 204, "Jellyfin did not accept the native stop.")
    stopped_at = now_utc()
    try:
        second_start_status = start_task(auth, task["Id"])
    except Exception as error:
        second_start_status = {"error": type(error).__name__}
    saw_cancelling = False
    progress_during_cancel: list[float] = []
    final = None
    drain_deadline = time.monotonic() + MAX_WAIT
    while time.monotonic() < drain_deadline:
        current = next((candidate for candidate in task_list(auth) if candidate.get("Id") == task["Id"]), None)
        if current is not None:
            state_name = task_state_name(current)
            if state_name in {"cancelling", "2"}:
                saw_cancelling = True
                percentage = current.get("CurrentProgressPercentage")
                if percentage is not None:
                    progress_during_cancel.append(float(percentage))
            if last_start(current) != previous and task_status(current) in {"cancelled", "1"}:
                final = current
                break
        time.sleep(0.1)
    require(saw_cancelling, "The stopped round never reported a Cancelling state.")
    require(final is not None, "The original stopped task did not settle as Cancelled before timeout.")
    status_value = task_status(final)
    require_progress_below_100(progress_during_cancel)
    playback_worker.join(timeout=MAX_WAIT)
    require(not playback_worker.is_alive(), "The joined playback owner did not finish during batch stop drain.")
    require("error" not in playback_holder, "The joined playback owner failed during the batch stop drain.")
    require(playback_holder.get("result", (None,))[0] == 200,
            "The playback-first owner did not return a successful native PlaybackInfo response.")
    playback_backend_finish = wait_for_backend_event(request_ids[first_name], "finish", request_started)
    batch_backend_finish = wait_for_backend_event(request_ids[second_name], "finish", request_started)
    cancelled_events = [event for event in task_completion_events(request_started) if event["status"] == "Cancelled"]
    require(cancelled_events, "No current-round Cancelled completion was logged.")
    cancelled_at = cancelled_events[0]["timestamp"]
    probe_events_after_stop = [event for event in probe_start_events(container(), since=stopped_at)
                               if event["timestamp"] < cancelled_at]
    require_no_probe_during_drain(probe_events_after_stop)
    entries_before_cancel = [entry for entry in batch_entry_events(request_started)
                             if entry["timestamp"] < cancelled_at]
    require_no_new_round(len(entries_before_cancel), entries_before_stop, "re-run")

    summary_line = first_summary_after(request_started)
    fields = summary_fields_complete(summary_line)
    probe_events = probe_start_events(container(), since=request_started)
    started_ids = {event["item_id"] for event in probe_events
                   if event["item_id"] in {playback_first_id, second_id}}
    require(started_ids == {playback_first_id, second_id},
            f"The stopped round did not have exactly the playback owner plus one batch owner started: {started_ids}.")
    joined_ids = {joined["item_id"]}
    require(fields.get("reliable_success") == len(started_ids),
            f"The stopped round must count both actual successful source executions, including the joined source: {summary_line}.")
    require((fields.get("revoked") or 0) >= 1,
            f"The native stop did not revoke any unstarted source: {summary_line}.")
    require((fields.get("reliable_success") or 0) + (fields.get("revoked") or 0) < BULK_COUNT,
            f"The stopped round claimed to have settled the whole cross-batch candidate set: {summary_line}.")
    require((fields.get("checked") or 0) < BULK_COUNT,
            f"The stopped round claimed to have checked the whole cross-batch candidate set: {summary_line}.")
    require(fields.get("batch_reads") == 1,
            f"The stopped round read a later candidate object batch before stop settled: {summary_line}.")

    # Freeze every changed source's full native address/main-stream state and five-field row before any re-run.
    observed_rows: dict[str, dict | None] = {}
    native_states: dict[str, dict] = {}
    for item_id, name in zip(changed_ids, changed_names):
        source_key = fixture_source_id(fixture, name)
        state = current_source_state(auth, item_id, source_key, fixture, recorder,
                                     f"stop settled {name} before rerun")
        observed_rows[item_id] = state["fingerprint"]
        native_states[item_id] = {"url_hash": state["native_url_hash"],
                                  "has_main_stream": state["has_main_stream"],
                                  "etag": state["etag"], "stream_types": state["stream_types"]}
        manifest = read_versioned_manifest(paths[name])
        require(manifest is not None, f"The stop source {name} lost its current versioned Manifest.")
        if item_id in started_ids:
            expected_rows[item_id] = expected_fingerprint_row(item_id, source_key, manifest,
                                                              baseline_rows[item_id])
        else:
            expected_rows[item_id] = baseline_rows[item_id]
    require(playback_backend_start < stopped_at and batch_backend_start < stopped_at
            and playback_backend_finish > stopped_at and batch_backend_finish > stopped_at,
            "Both actual probes were not still executing when stop was issued and then completed after it.")
    validate_stop_round_snapshot(
        baseline_rows, started_ids, observed_rows, native_states, expected_rows,
        joined_item_ids=joined_ids, reliable_success=fields.get("reliable_success", 0))
    snapshot_completed_at = now_utc()
    all_entries = batch_entry_events(request_started)
    entries_after_cancel_before_snapshot = [entry for entry in all_entries
                                            if cancelled_at <= entry["timestamp"] <= snapshot_completed_at]
    require(not entries_after_cancel_before_snapshot,
            "A queued re-run entered before complete native/fingerprint stop snapshots were saved.")
    stop_snapshot = {
        "stop_status": stop_status, "status": status_value, "task_result": task_result(final),
        "summary": summary_line, "fields": fields, "candidate_manifest": candidate_manifest,
        "changed_item_ids": changed_ids, "started_item_ids": sorted(started_ids),
        "joined_item_ids": sorted(joined_ids), "baseline_rows": baseline_rows,
        "observed_rows": observed_rows, "expected_rows": expected_rows,
        "native_states": native_states, "saw_cancelling": saw_cancelling,
        "progress_during_cancel": progress_during_cancel, "second_start_status": second_start_status,
        "entries_before_stop": entries_before_stop, "entries_before_cancel": len(entries_before_cancel),
        "entries_after_cancel_before_snapshot": len(entries_after_cancel_before_snapshot),
        "snapshot_completed_at": snapshot_completed_at,
    }
    summary["stop"] = stop_snapshot
    recorder.record("stop_round_settled_before_rerun", snapshot=stop_snapshot,
                    joined_event=joined, playback_probe=playback_probe, batch_probe=second_probe)
    recorder.snapshot(f"stop-round-before-rerun-{time.time_ns()}", stop_snapshot)

    # Only now may a queued request or an explicit new round run. Detect a queued second execution rather than
    # blindly issuing another start that could mask the stopped round's outcome.
    wait_for_stable_idle(auth, task["Id"])
    entries_now = batch_entry_events(request_started)
    post_cancel_entries = [entry for entry in entries_now if entry["timestamp"] > cancelled_at]
    if post_cancel_entries:
        convergence_final = wait_for_new_execution(auth, task["Id"], last_start(final), timeout=MAX_WAIT)
        require_completed_execution(convergence_final, last_start(final), "queued post-stop convergence")
        convergence_mode = "queued-rerun-after-snapshot"
    else:
        convergence_final = run_plugin_task_completed(auth, "stop convergence run")
        convergence_mode = "explicit-rerun-after-snapshot"
    wait_for_stable_idle(auth, task["Id"])
    for name in changed_names:
        item_id = canonical_guid(items[name]["Id"], name)
        source_key = fixture_source_id(fixture, name)
        row = fingerprint_row_for_key(item_id, source_key)
        manifest = read_versioned_manifest(paths[name])
        require(manifest is not None, f"The convergence Manifest for {name} is unreadable.")
        expected = expected_fingerprint_row(item_id, source_key, manifest, row)
        require(row == expected,
                f"The post-stop convergence did not establish the exact current five-field row for {name}.")
        state = current_source_state(auth, item_id, source_key, fixture, recorder,
                                     f"stop convergence {name}")
        validate_source_reconciliation(expected, state["source"], state["fingerprint"], name)
    round_started = now_utc()
    run_plugin_task_completed(auth, "stop unchanged re-check")
    recheck_summary = latest_summary_after(round_started)
    recheck_fields = summary_fields_complete(recheck_summary)
    require_zero_probes(recheck_fields, recheck_summary, "post-settlement unchanged re-check")
    summary["converged"] = True
    summary["convergence_mode"] = convergence_mode
    recorder.record("stop_convergence", mode=convergence_mode, task_result=task_result(convergence_final),
                    recheck_summary=recheck_fields)
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
    fixture = {"nonce": nonce, "media_sha": media_sha, "media_size": media_size, "plain_url": plain_url,
               "items": {fail_name: fail_item, healthy_name: healthy_item, versioned_name: versioned_item},
               "strm_dir": pe.WORK / "strm", "local_dir": pe.WORK / "media"}
    index_fixture_source_paths(fixture)
    fail_source_id = fixture_source_id(fixture, fail_name)
    healthy_source_id = fixture_source_id(fixture, healthy_name)
    fail_before = fingerprint_row_for_key(fail_item["Id"], fail_source_id)
    require(fail_before is not None, "The failing source did not receive a baseline.")
    rewrite_strm(fail_path, missing_url(plain_url), media_sha, media_size)
    healthy_url = unique_url(plain_url, "healthy-" + uuid.uuid4().hex[:8])
    rewrite_strm(healthy_path, healthy_url, media_sha, media_size)
    failure_round_started = now_utc()
    failure_task = run_plugin_task_completed(auth, "single-item failure round")
    failure_summary = summary_fields_complete(latest_summary_after(failure_round_started))
    failure_starts = probe_start_events(container(), since=failure_round_started)
    failure_outcomes = probe_outcome_events(container(), since=failure_round_started)
    require(probe_start_for_item(failure_starts, fail_item["Id"]) is not None,
            "The failing source did not reach an actually started native probe.")
    require(any(event["kind"] == "failed" and event["item_id"] == canonical_guid(fail_item["Id"], "failed source")
                for event in failure_outcomes),
            "The unreachable source has no failed native probe outcome in this batch round.")
    fail_after = fingerprint_row_for_key(fail_item["Id"], fail_source_id)
    require(fail_after == fail_before, "A failed single-item probe overwrote its trusted baseline.")
    healthy_manifest = read_versioned_manifest(healthy_path)
    require(healthy_manifest is not None, "The healthy failure-isolation source lost its versioned manifest.")
    healthy_expected = expected_fingerprint_row(healthy_item["Id"], healthy_source_id,
                                                healthy_manifest,
                                                fingerprint_row_for_key(healthy_item["Id"], healthy_source_id))
    healthy_state = current_source_state(auth, healthy_item["Id"], healthy_source_id, fixture, recorder,
                                         "healthy source beside failure")
    validate_source_reconciliation(healthy_expected, healthy_state["source"], healthy_state["fingerprint"],
                                   "healthy source beside failure")
    require(probe_start_for_item(failure_starts, healthy_item["Id"]) is not None
            and any(event["kind"] == "accepted" and event["item_id"] == canonical_guid(healthy_item["Id"], "healthy source")
                    for event in failure_outcomes),
            "The healthy changed source did not independently start and commit beside the failure.")
    require((failure_summary.get("need_probe") or 0) == 2
            and (failure_summary.get("actual_probe_calls") or 0) == 2
            and (failure_summary.get("reliable_success") or 0) == 1
            and (failure_summary.get("probe_incomplete") or 0) >= 1,
            f"The single-item failure summary does not isolate one failure from one success: {failure_summary}.")
    summary["single_item_failure_isolated"] = True

    # Repair the failed route to a reachable address, then require the new native save and exact row.
    repaired_url = unique_url(plain_url, "repaired-" + uuid.uuid4().hex[:8])
    rewrite_strm(fail_path, repaired_url, media_sha, media_size)
    repair_started = now_utc()
    repair_task = run_plugin_task_completed(auth, "single-item repair round")
    repair_summary = summary_fields_complete(latest_summary_after(repair_started))
    repair_outcomes = [event for event in probe_outcome_events(container(), since=repair_started)
                       if event["item_id"] == canonical_guid(fail_item["Id"], "repaired source")]
    repair_manifest = read_versioned_manifest(fail_path)
    require(repair_manifest is not None, "The repaired source has no readable versioned manifest.")
    repair_expected = expected_fingerprint_row(fail_item["Id"], fail_source_id, repair_manifest, fail_before)
    repaired_state = current_source_state(auth, fail_item["Id"], fail_source_id, fixture, recorder,
                                          "repaired failed source")
    require_recovery_source_success(repair_expected, repaired_state["source"], repaired_state["fingerprint"],
                                   repair_summary, repair_outcomes, "repaired failure source")
    repair_status, repair_playback = playback_info(auth, fail_item["Id"])
    require(repair_status == 200, "PlaybackInfo failed after the recovery source was repaired.")
    _require_selected_source(repair_playback, fail_source_id, repair_expected["url_hash"], "repaired source")
    recorder.record("single_item_repair", before=fail_before, after=repaired_state,
                    task_result=task_result(repair_task), summary=repair_summary,
                    outcomes=repair_outcomes, playback_status=repair_status)
    recorder.snapshot(f"single-item-repair-{time.time_ns()}", {
        "expected": repair_expected, "native_source": repaired_state["source"],
        "fingerprint": repaired_state["fingerprint"], "summary": repair_summary,
        "outcomes": repair_outcomes, "playback_status": repair_status,
    })

    # Disabling the plugin before a real change must start no probe on any route.
    disable_status = configure(auth, {"Enabled": False, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2,
                                      "DetailedLog": False, "BatchAllLibraries": True, "BatchLibraryIds": ""})
    require(disable_status == 204, f"The plugin disable configuration was not saved ({disable_status}).")
    config_status, disabled_config = pe.request_json("GET", f"/Plugins/{PLUGIN_ID}/Configuration",
                                                       headers={"Authorization": auth})
    require(config_status == 200 and disabled_config.get("Enabled") is False,
            "The disabled configuration was not read back as the effective persisted state.")
    disabled_url = unique_url(plain_url, "disabled-" + uuid.uuid4().hex[:8])
    rewrite_strm(healthy_path, disabled_url, media_sha, media_size)
    before_activity = backend_activity()
    run_plugin_task_completed(auth, "disabled no-probe round")
    after_activity = backend_activity()
    require_no_new_activity(before_activity, after_activity, "A disabled plugin")
    scope_all_libraries(auth)
    enabled_status, enabled_config = pe.request_json("GET", f"/Plugins/{PLUGIN_ID}/Configuration",
                                                       headers={"Authorization": auth})
    require(enabled_status == 200 and enabled_config.get("Enabled") is True,
            "The enabled configuration was not persisted before the SQLite recovery control.")
    recorder.record("disabled_configuration_control", disable_status=disable_status,
                    persisted_disabled=disabled_config, persisted_enabled=enabled_config,
                    before_activity=before_activity, after_activity=after_activity)
    summary["disabled_no_probe"] = {"persisted_readback": True, "no_probe": True}

    # A SQLite global fault must fail the task without starting a probe on any route, and recover.
    database = pkg.fingerprint_database()
    require(database.is_file(), "The plugin fingerprint database is missing.")
    backup = database.with_suffix(".db.bak-" + uuid.uuid4().hex[:8])
    pe.require_owned_path(database, label="isolated plugin fingerprint database")
    pending_source_id = healthy_source_id
    pending_old_row = fingerprint_row_for_key(healthy_item["Id"], pending_source_id)
    require(pending_old_row is not None, "The SQLite recovery source has no old trusted row before the fault.")
    pending_manifest = read_versioned_manifest(healthy_path)
    require(pending_manifest is not None and pending_manifest["url_hash"] != pending_old_row["url_hash"],
            "The SQLite recovery fixture does not contain a reachable changed source pending verification.")
    pending_native_before = current_source_state(auth, healthy_item["Id"], pending_source_id, fixture, recorder,
                                                 "pending SQLite recovery before fault")
    recorder.record("sqlite_fault_precondition", old_row=pending_old_row,
                    pending_manifest=pending_manifest, native_state=pending_native_before)
    shutil.copy2(database, backup)
    try:
        database.unlink()
        database.mkdir()
        before_activity = backend_activity()
        final = run_plugin_task(auth)
        status_value = task_status(final)
        require(status_value in {"failed", "3"}, f"A SQLite fault did not fail the task: {status_value}.")
        require_no_new_activity(before_activity, backend_activity(), "A SQLite fault")
        fault_events = probe_start_events(container(), since=now_utc() - datetime.timedelta(minutes=5))
        require(not [event for event in fault_events if event["item_id"] == canonical_guid(healthy_item["Id"], "SQLite source")],
                "A probe started for the pending source while the fingerprint store was unavailable.")
        summary["store_fault"] = {"status": status_value, "task_result": task_result(final),
                                  "before_activity": before_activity, "after_activity": backend_activity()}
    finally:
        if database.is_dir():
            database.rmdir()
        shutil.move(str(backup), str(database))
        if ACTIVE_RECORDER is not None:
            ACTIVE_RECORDER.record("sqlite_fault_restore", database_identity=database,
                                   restored_sha256=hashlib.sha256(database.read_bytes()).hexdigest(),
                                   observed_at=now_utc())
    restart()
    auth = api_auth()
    restored_row = fingerprint_row_for_key(healthy_item["Id"], pending_source_id)
    require(restored_row == pending_old_row,
            "Restoring the plugin store did not preserve the complete old five-field source baseline.")
    recovery_started = now_utc()
    recovered = run_plugin_task_completed(auth, "store recovery run")
    recovery_summary = summary_fields_complete(latest_summary_after(recovery_started))
    recovery_outcomes = [event for event in probe_outcome_events(container(), since=recovery_started)
                         if event["item_id"] == canonical_guid(healthy_item["Id"], "SQLite recovery item")]
    pending_manifest = read_versioned_manifest(healthy_path)
    require(pending_manifest is not None, "The pending SQLite recovery Manifest is unreadable.")
    pending_expected = expected_fingerprint_row(healthy_item["Id"], pending_source_id,
                                                pending_manifest, pending_old_row)
    recovered_state = current_source_state(auth, healthy_item["Id"], pending_source_id, fixture, recorder,
                                           "SQLite source after recovery")
    require_recovery_source_success(pending_expected, recovered_state["source"], recovered_state["fingerprint"],
                                   recovery_summary, recovery_outcomes, "SQLite recovered pending source")
    playback_status, playback_response = playback_info(auth, healthy_item["Id"])
    require(playback_status == 200, "PlaybackInfo failed after the SQLite recovery probe committed.")
    _require_selected_source(playback_response, pending_source_id, pending_expected["url_hash"],
                             "SQLite recovered source")
    stable_started = now_utc()
    run_plugin_task_completed(auth, "store recovery unchanged re-check")
    stable_summary = summary_fields_complete(latest_summary_after(stable_started))
    require_zero_probes(stable_summary, latest_summary_after(stable_started), "recovered unchanged source re-check")
    recorder.record("sqlite_recovery_complete", old_row=pending_old_row,
                    expected=pending_expected, native_state=recovered_state,
                    task_result=task_result(recovered), summary=recovery_summary,
                    unchanged_summary=stable_summary)
    recorder.snapshot(f"sqlite-recovery-{time.time_ns()}", {
        "old_row": pending_old_row, "expected": pending_expected,
        "native_state": recovered_state, "summary": recovery_summary,
        "outcomes": recovery_outcomes, "playback_status": playback_status,
        "unchanged_summary": stable_summary,
    })
    summary["store_recovered"] = {"required_probe_committed": True, "unchanged_zero_probe": True}
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
    global ACTIVE_RECORDER
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
    ACTIVE_RECORDER = recorder
    try:
        root_relative_package = package.relative_to(ROOT).as_posix()
    except ValueError:
        external_hash = hashlib.sha256(package.read_bytes()).hexdigest() if package.is_file() else "UNAVAILABLE"
        root_relative_package = f"<external archive sha256:{external_hash}>"
    command = (f"python3 scripts/run_isolated_scan_integration.py --package {root_relative_package} "
               f"--scenario {args.scenario} --evidence-dir <unique-evidence-dir>")
    if args.workspace is not None:
        command += " --workspace <isolated-run-workspace>"
    try:
        sdk_config = json.loads((ROOT / "global.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        sdk_config = {}
    lock_inputs = {}
    for lock_path in [ROOT / "global.json", ROOT / "dev" / "environment-spec.json",
                      ROOT / "artifacts" / "dev-env" / "images.lock.json",
                      *sorted(ROOT.glob("**/packages.lock.json"))]:
        if lock_path.is_file() and ".git" not in lock_path.parts and "artifacts/package-env" not in lock_path.as_posix():
            lock_inputs[lock_path.relative_to(ROOT).as_posix()] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    recorder.set_metadata(
        command=command,
        runtime={"python": sys.version.split()[0], "python_executable_sha256": digest(sys.executable),
                 "platform": platform.platform(), "dotnet_sdk": sdk_config.get("sdk", {}).get("version", "UNAVAILABLE")},
        inputs={"lock_files_sha256": lock_inputs, "scenario": args.scenario,
                "package_sha256": hashlib.sha256(package.read_bytes()).hexdigest() if package.is_file() else "UNAVAILABLE",
                "evidence_directory": "unique external run directory"})
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
        recorder.set_metadata(package_identity=summary["package_identity"],
                              image_lock_sha256=lock_inputs.get("artifacts/dev-env/images.lock.json"))
        recorder.record("package", identity=summary["package_identity"], workspace=workspace)
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
    except Exception as error:
        summary["status"] = "FAIL"
        summary["error"] = _safe_exception(error)
        exit_code = 1
        recorder.record("failure", error=summary["error"])
    finally:
        if before_state is not None:
            try:
                collect_runtime_evidence("before-instance-cleanup", require_running=True)
                summary["raw_runtime_evidence"] = "captured before restoration and cleanup"
            except Exception as capture_error:
                summary["evidence_capture_error"] = _safe_exception(capture_error)
                summary["status"] = "FAIL"
                exit_code = 1
        if ORIGINAL_TRIGGERS is not None:
            try:
                restore_triggers(api_auth(), ORIGINAL_TRIGGERS)
                summary["trigger_restoration"] = "restored and verified"
            except Exception as trigger_error:
                summary["trigger_restoration"] = {"status": "NOT RESTORED", **_safe_exception(trigger_error)}
                summary["status"] = "FAIL"
                exit_code = 1
        if before_state is not None:
            try:
                summary["instance_reconciliation"] = pe.reconcile_instance_state(before_state)
            except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError) as teardown_error:
                summary["teardown_error"] = _safe_exception(teardown_error)
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
            summary["evidence_error"] = _safe_exception(record_error)
            summary["status"] = "FAIL"
            exit_code = 1
        if workspace is not None and not args.keep_workspace:
            try:
                summary["cleanup"] = pe.cleanup_instance()
            except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError) as cleanup_error:
                summary["cleanup_error"] = _safe_exception(cleanup_error)
                summary["status"] = "FAIL"
                exit_code = 1
        if recorder is not None:
            summary["exit_code"] = exit_code
            recorder.set_metadata(exit_code=exit_code, final_status=summary.get("status", "FAIL"),
                                  counts={key: value for key, value in summary.items()
                                          if key.endswith("_count") or key in REQUIRED_SUMMARY_FIELDS})
            try:
                recorder.finish(str(summary.get("status", "FAIL")), summary, {
                    "events.jsonl": "append-only redacted event stream",
                })
            except OSError as evidence_error:
                summary["status"] = "FAIL"
                summary["exit_code"] = 1
                exit_code = 1
                summary["evidence_finalize_error"] = _safe_exception(evidence_error)
        ACTIVE_RECORDER = None
        print(json.dumps(_scrub(summary), ensure_ascii=False, indent=2, sort_keys=True))
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
    summary["convergence"] = convergence(auth, fixture, recorder, summary["multi_version_and_refresh"])
    return summary


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
