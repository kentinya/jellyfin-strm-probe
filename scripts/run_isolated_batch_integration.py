#!/usr/bin/env python3
"""Exercise the native batch check task against the repository's isolated Jellyfin instance.

The script only uses the repository's isolated Compose project, temporary hand-written STRM
fixtures and the local synthetic media service. It saves the plugin configuration and every
native scheduled task trigger before the run, restores them in a finally block and verifies the
restoration, so a failed or interrupted run never leaves the isolated instance changed.

Scenarios:
  suite    (default) runs discovery, stop, shared_stop, sharing, scope, mixed and failure in one isolated session
  discovery   discovery / no default trigger / manual run / real wall-clock trigger / restart persistence /
           new STRM first trust / changed-URL commit against the old baseline / repeat zero-probe / restart
  stop     real native stop of started probes: per-source settlement, settlement-window manual and timer run do
           not enter a new round, current-round Cancelled bound, next run re-probes only revoked sources
  shared_stop  both start orders of a batch joined to a running playback probe: joined probe commits, batch
           Cancelled, and an independent different-library playback actually starts a new probe while settling
  sharing  batch and playback sharing one actually running same-source probe, in both start orders
  scope    explicit partial scope over two real libraries: multi-batch, multi-version, range-outside zero work,
           in-round fixed-set add/delete safety and next-round convergence, invalid save rejection, disabled
  mixed    a batch scoped to one library and a concurrent playback in another overlap under the default
           concurrency, with the peak attributed per owner; independent FullRefresh not gated
  failure  an unavailable fingerprint store is reported as a batch failure instead of a silent completion
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_isolated_plugin_integration as base  # noqa: E402

ROOT = base.ROOT
FIXTURE = base.FIXTURE
FINGERPRINT_DATABASE = base.FINGERPRINT_DATABASE
CONFIGURATION_FILE = base.CONFIGURATION_FILE
PLUGIN_ID = base.PLUGIN_ID
TASK_NAME = "STRM 媒体信息检查"
TASK_DATA_DIRECTORY = ROOT / "artifacts" / "dev-env" / "config" / "config" / "ScheduledTasks"
MAX_WAIT_SECONDS = 120
TASK_KEY = "StrmProbeOptimizerBatchCheck"

# Cleanup failures (temporary library entries that could not be removed or a restore that could not be verified)
# are recorded here and turned into a final failure in main(). A shared STRM/config restore succeeding does not
# prove the per-scenario temporary entries were removed.
CLEANUP_PROBLEMS: list[str] = []


def record_cleanup_problem(message: str) -> None:
    CLEANUP_PROBLEMS.append(message)


def cleanup_fixtures(api: base.JellyfinApi, names: list[str]) -> None:
    """Remove this scenario's temporary library entries and verify they are gone. A failure is recorded so the
    run cannot report PASS while the isolated instance still contains leftover entries."""
    try:
        api.refresh_library()
    except Exception as error:
        record_cleanup_problem(f"library refresh during cleanup failed: {type(error).__name__}")
    for name in names:
        try:
            api.wait_for_named_library_item_absent(name)
        except Exception as error:
            record_cleanup_problem(f"temporary library item {name!r} was not removed: {type(error).__name__}")


def find_task(api: base.JellyfinApi) -> dict:
    tasks = base.request_json(api.base_url + "/ScheduledTasks", headers=api.headers, timeout=20)
    matches = [task for task in tasks if task.get("Name") == TASK_NAME]
    base.require(len(matches) == 1, f"Expected exactly one native task named {TASK_NAME!r}, found {len(matches)}.")
    return matches[0]


def task_state_name(task: dict) -> str:
    return str(task.get("State", "")).lower()


def task_id_for(api: base.JellyfinApi) -> str:
    """Return the current task id, so a scenario can start the task without re-reading it twice."""
    return find_task(api)["Id"]


def wait_for_idle(api: base.JellyfinApi, timeout: int = MAX_WAIT_SECONDS) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = find_task(api)
        if task_state_name(task) in {"idle", "0"}:
            return task
        time.sleep(0.5)
    raise RuntimeError("The native batch task did not return to Idle before the timeout.")


def last_start(task: dict) -> str | None:
    return (task.get("LastExecutionResult") or {}).get("StartTimeUtc")


def run_task(api: base.JellyfinApi, timeout: int = MAX_WAIT_SECONDS) -> dict:
    task = find_task(api)
    previous_start = last_start(task)
    status, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="POST")
    base.require(status == 204, "Jellyfin did not accept the manual batch task start.")
    return wait_for_run(api, previous_start, timeout)


def wait_for_run(api: base.JellyfinApi, previous_start: str | None, timeout: int = MAX_WAIT_SECONDS) -> dict:
    deadline = time.monotonic() + timeout
    observed = False
    while time.monotonic() < deadline:
        current = find_task(api)
        result = current.get("LastExecutionResult") or {}
        if task_state_name(current) in {"running", "cancelling", "1", "2"} or last_start(current) != previous_start:
            observed = True
        if observed and task_state_name(current) in {"idle", "0"}:
            return current
        time.sleep(0.25)
    raise RuntimeError("The native batch task did not settle before the timeout.")


def stop_task(api: base.JellyfinApi) -> int:
    task = find_task(api)
    status, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="DELETE")
    return status


def set_triggers(api: base.JellyfinApi, task_id: str, triggers: list[dict]) -> int:
    status, _ = api.request_response(
        f"/ScheduledTasks/{task_id}/Triggers",
        method="POST",
        data=json.dumps(triggers).encode("utf-8"),
    )
    return status


def batch_events(container: str, since: float | None = None) -> list[str]:
    """Return the redacted batch summary lines. When ``since`` (seconds of day) is given, only summaries at or
    after it are returned, which binds them to the current round despite ``--tail`` truncation in long sessions."""
    logs = base.run(["docker", "logs", "--tail", "4000", container], timeout=20)
    base.require(logs.returncode == 0, "Could not read the isolated Jellyfin container logs.")
    events: list[str] = []
    for line in (logs.stdout + logs.stderr).splitlines():
        if "STRM media information check finished" not in line:
            continue
        if since is not None:
            try:
                if parse_log_epoch(line) < since:
                    continue
            except RuntimeError:
                continue
        events.append(line)
    return events


def batch_run_entries(container: str, since: float | None = None) -> list[str]:
    """Return the redacted markers for every round that actually entered ExecuteAsync and began a run. When
    ``since`` (seconds of day) is given, only entries at or after it are returned, which binds the markers to the
    current round despite ``--tail`` truncation across a long multi-scenario session."""
    logs = base.run(["docker", "logs", "--tail", "8000", container], timeout=20)
    base.require(logs.returncode == 0, "Could not read the isolated Jellyfin container logs.")
    entries: list[str] = []
    for line in (logs.stdout + logs.stderr).splitlines():
        if "STRM media information check entered" not in line:
            continue
        if since is not None:
            try:
                if parse_log_epoch(line) < since:
                    continue
            except RuntimeError:
                continue
        entries.append(line)
    return entries


def trigger_arm_times(container: str) -> list[float]:
    """Return the epoch seconds at which the native DailyTrigger logged it would fire for this task."""
    logs = base.run(["docker", "logs", "--tail", "4000", container], timeout=20)
    base.require(logs.returncode == 0, "Could not read the isolated Jellyfin container logs.")
    import re

    times: list[float] = []
    for line in (logs.stdout + logs.stderr).splitlines():
        if "Daily trigger for" not in line or TASK_NAME not in line or "set to fire at" not in line:
            continue
        match = re.search(r"set to fire at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+ [+-]\d{2}:\d{2})", line)
        if not match:
            continue
        try:
            times.append(datetime.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S.%f %z").timestamp())
        except ValueError:
            continue
    return times


def parse_log_epoch(line: str) -> float:
    """Parse the leading Jellyfin log timestamp (for example '[04:43:37.205]') into seconds of day. Log lines are
    within one run's day, so this is enough to order this round's events against the armed trigger time-of-day."""
    import re

    match = re.match(r"\[(\d{2}):(\d{2}):(\d{2})\.(\d+)\]", line)
    if not match:
        raise RuntimeError(f"Could not parse a log timestamp from {line!r}.")
    hours, minutes, seconds, fraction = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(fraction) / (10 ** len(fraction))


def now_time_of_day_seconds() -> float:
    """The current UTC seconds-of-day, matching the server log timestamps (the isolated server logs in UTC)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.hour * 3600 + now.minute * 60 + now.second + now.microsecond / 1_000_000


def current_round_completion(container: str, since: float) -> str | None:
    """Return the first native completion of this task logged at or after ``since`` (seconds of day). It binds the
    result to the current round instead of a positional index that ``--tail`` truncation can invalidate."""
    for timestamp, status in task_completion_events_with_time(container):
        if timestamp >= since:
            return status
    return None


def trigger_arm_time_of_day_seconds(container: str) -> float:
    """Return the seconds-of-day at which the most recent DailyTrigger for this task will fire. It is parsed from
    the same 'set to fire at' line as the absolute arm time but kept in the server's local time-of-day frame so it
    can be compared against log-line timestamps that carry no date."""
    logs = base.run(["docker", "logs", "--tail", "4000", container], timeout=20)
    base.require(logs.returncode == 0, "Could not read the isolated Jellyfin container logs.")
    import re

    for line in reversed((logs.stdout + logs.stderr).splitlines()):
        if "Daily trigger for" not in line or TASK_NAME not in line or "set to fire at" not in line:
            continue
        match = re.search(r"set to fire at (\d{4}-\d{2}-\d{2} (\d{2}):(\d{2}):(\d{2}))\.", line)
        if match:
            hours, minutes, seconds = match.group(2), match.group(3), match.group(4)
            return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    raise RuntimeError("No DailyTrigger arm line was found for this task.")


def native_scan_state(api: base.JellyfinApi) -> dict:
    """Return the native library scan task's own state, which owns the post-scan task sequence.

    The pinned ``TaskManager`` drains its queue whenever any task completes and only executes queued
    work from an Idle worker; queued work that is still busy at that moment is not retained. A scan
    (with its nine post-scan tasks) therefore has to be settled before a queued batch run is
    measured, or the queued run can be dropped by native scheduling rather than by the plugin.
    """
    tasks = base.request_json(api.base_url + "/ScheduledTasks", headers=api.headers, timeout=20)
    scan = next((task for task in tasks if task.get("Key") == "RefreshLibrary"), None)
    base.require(scan is not None, "The isolated server did not expose its native library scan task.")
    return {"id": scan.get("Id"), "state": task_state_name(scan),
            "lastStart": last_start(scan),
            "lastStatus": str((scan.get("LastExecutionResult") or {}).get("Status", ""))}


def post_scan_settled(container: str) -> bool:
    """Whether the newest post-scan sequence in the server log has already reported completion."""
    logs = base.run(["docker", "logs", "--tail", "4000", container], timeout=20)
    base.require(logs.returncode == 0, "Could not read the isolated Jellyfin container logs.")
    lines = (logs.stdout + logs.stderr).splitlines()
    for line in reversed(lines):
        if "All post-scan tasks completed" in line:
            return True
        if "Running post-scan task" in line or "Running 9 post-scan task" in line:
            return False
    return True


def wait_for_native_scan_settled(api: base.JellyfinApi, container: str, timeout: int = MAX_WAIT_SECONDS) -> dict:
    """Wait (read-only) until this server's own native scan and post-scan work has really finished.

    This is a measurement precondition, not a plugin behaviour change: the isolated stop scenario
    must not start its round while a native scan is Running, because that native task's own
    completion drains the scheduled-task queue and can drop the queued batch run the scenario is
    about to observe. Nothing about the native scheduler, the plugin queue or the settlement
    assertions changes.
    """
    deadline = time.monotonic() + timeout
    observed: list[dict] = []
    while time.monotonic() < deadline:
        state = native_scan_state(api)
        observed.append(state)
        if state["state"] in {"idle", "0"} and post_scan_settled(container):
            return {"waited": len(observed) > 1, "observations": len(observed), "settled": state}
        time.sleep(0.5)
    raise RuntimeError(f"The native library scan and its post-scan tasks never settled before the measurement "
                       f"window: {observed[-1] if observed else None}.")


def wait_for_stable_idle(api: base.JellyfinApi, container: str, stable_seconds: float = 3.0, timeout: int = MAX_WAIT_SECONDS) -> dict:
    """Wait until the task is Idle and no new run entry appears for a stable period, so a queued native run that
    started right after a previous settlement is not mistaken for the old round."""
    deadline = time.monotonic() + timeout
    stable_since = time.monotonic()
    last_entries = len(batch_run_entries(container))
    while time.monotonic() < deadline:
        task = find_task(api)
        entries = len(batch_run_entries(container))
        if entries != last_entries or task_state_name(task) not in {"idle", "0"}:
            last_entries = entries
            stable_since = time.monotonic()
        elif time.monotonic() - stable_since >= stable_seconds:
            return task
        time.sleep(0.25)
    raise RuntimeError("The native batch task never reached a stable idle state.")


def latest_batch_summary(container: str) -> dict:
    lines = batch_events(container)
    return {"line": base.safe_event(lines[-1]) if lines else None, "count": len(lines)}


def parse_summary_field(line: str, field: str) -> int | None:
    """Extract one integer counter from the redacted batch summary line."""
    if line is None:
        return None
    import re

    match = re.search(rf"{re.escape(field)}\s+(\d+)", line)
    return int(match.group(1)) if match else None


def parse_summary_float(line: str, field: str) -> float | None:
    """Extract one numeric (possibly fractional) measurement from the redacted batch summary line."""
    if line is None:
        return None
    import re

    match = re.search(rf"{re.escape(field)}\s+(\d+(?:\.\d+)?)", line)
    return float(match.group(1)) if match else None


def summary_fields(line: str | None) -> dict[str, int | float | bool | None]:
    """Extract the redacted batch summary counters needed for reconciliation."""
    if line is None:
        return {}
    numeric = {
        "candidates": parse_summary_field(line, "candidates"),
        "raw_candidates": parse_summary_field(line, "raw"),
        "duplicates": parse_summary_field(line, "duplicates"),
        "checked": parse_summary_field(line, "checked"),
        "skipped": parse_summary_field(line, "skipped"),
        "first_trust": parse_summary_field(line, "first trust"),
        "need_probe": parse_summary_field(line, "need probe"),
        "reliable_success": parse_summary_field(line, "reliable success"),
        "probe_incomplete": parse_summary_field(line, "probe incomplete"),
        "check_stage_incomplete": parse_summary_field(line, "check-stage incomplete"),
        "not_processed": parse_summary_field(line, "not processed"),
        "missing": parse_summary_field(line, "missing"),
        "revoked": parse_summary_field(line, "revoked"),
        "read_incomplete": parse_summary_field(line, "read incomplete"),
        "unread": parse_summary_field(line, "unread"),
        "actual_probe_calls": parse_summary_field(line, "actual probe calls"),
        "candidate_fetch_ms": parse_summary_float(line, "candidate fetch"),
        "candidate_fetch_allocated_bytes": parse_summary_field(line, "candidate fetch allocated"),
        "candidate_set_estimated_bytes": parse_summary_field(line, "candidate set estimated"),
        "candidate_set_measured_capacity_bytes": parse_summary_field(line, "candidate set measured capacity"),
        "candidate_set_retained_bytes": parse_summary_field(line, "candidate set retained"),
        "candidate_fetch_peak_bytes": parse_summary_field(line, "candidate fetch peak"),
        "stop_query_return_ms": parse_summary_float(line, "stop query return"),
        "batch_reads": parse_summary_field(line, "batch reads"),
        "batch_read_ms": parse_summary_float(line, "batch read"),
        "batch_read_allocated_bytes": parse_summary_field(line, "batch read allocated"),
    }
    numeric["total_known"] = "total known True" in line
    numeric["stop_requested"] = "stop requested True" in line
    numeric["store_unavailable"] = "store unavailable True" in line
    numeric["scope_unavailable"] = "scope unavailable True" in line
    numeric["candidate_fetch_failed"] = "candidate fetch failed True" in line
    numeric["disabled"] = "disabled True" in line
    return numeric


# Cost and identity measurements that a run must actually report. A missing field is a hard failure rather
# than a value that trivially satisfies a ``>= 0`` check.
REQUIRED_COST_FIELDS = (
    "candidate_fetch_ms",
    "candidate_fetch_allocated_bytes",
    "candidate_set_estimated_bytes",
    "candidate_set_measured_capacity_bytes",
    "candidate_set_retained_bytes",
    "candidate_fetch_peak_bytes",
    "batch_reads",
    "batch_read_ms",
    "batch_read_allocated_bytes",
)


def require_cost_fields(fields: dict, summary_line: str | None) -> None:
    """Require every cost/identity measurement to be present and non-negative."""
    for field in REQUIRED_COST_FIELDS:
        value = fields.get(field)
        if value is None:
            raise RuntimeError(f"The batch summary did not report {field!r}: {summary_line}.")
        if value < 0:
            raise RuntimeError(f"The batch summary reported a negative {field!r}: {summary_line}.")


def slow_request_ids_started(container: str) -> set[str]:
    """Return the set of delayed-probe request ids that actually began, so per-source settlement can be reconciled."""
    return set(slow_request_counts(container))


def slow_request_counts(container: str) -> dict[str, int]:
    """Return how many times each delayed-probe request id actually began. A set subtraction cannot detect the
    same request id starting twice, so per-source reconciliation uses exact counts instead."""
    logs = base.run(["docker", "logs", "--tail", "8000", container], timeout=20)
    base.require(logs.returncode == 0, "Could not read the isolated media service counters.")
    marker = "SLOW_MEDIA_REQUEST_STARTED "
    counts: dict[str, int] = {}
    for line in (logs.stdout + logs.stderr).splitlines():
        index = line.find(marker)
        if index >= 0:
            request_id = line[index + len(marker):].strip()
            counts[request_id] = counts.get(request_id, 0) + 1
    return counts


def assert_summary_equations(fields: dict) -> None:
    """Verify the documented batch counter equations on a real summary line."""
    checked = fields.get("checked")
    skipped = fields.get("skipped")
    need = fields.get("need_probe")
    check_incomplete = fields.get("check_stage_incomplete")
    reliable = fields.get("reliable_success")
    probe_incomplete = fields.get("probe_incomplete")
    if None in (checked, skipped, need, check_incomplete):
        return
    base.require(checked == skipped + need + check_incomplete, f"checked must equal skipped + need + check-stage incomplete: {fields}.")
    if None not in (need, reliable, probe_incomplete):
        base.require(need == reliable + probe_incomplete, f"need probe must equal reliable success + probe incomplete: {fields}.")


def task_summary(task: dict) -> dict:
    result = task.get("LastExecutionResult") or {}
    return {"state": task.get("State"), "status": result.get("Status"), "triggers": task.get("Triggers") or []}


def fingerprint_count() -> int:
    base.require(FINGERPRINT_DATABASE.is_file(), "The plugin fingerprint database is missing.")
    uri = FINGERPRINT_DATABASE.as_posix() + "?mode=ro"
    with sqlite3.connect("file:" + uri, uri=True, timeout=10) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM strm_fingerprint").fetchone()[0])


def fingerprint_row(item_id: str) -> dict | None:
    base.require(FINGERPRINT_DATABASE.is_file(), "The plugin fingerprint database is missing.")
    uri = FINGERPRINT_DATABASE.as_posix() + "?mode=ro"
    with sqlite3.connect("file:" + uri, uri=True, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT item_id, source_key, url_hash, sha1, file_size FROM strm_fingerprint WHERE source_key = ?",
            (uuid.UUID(item_id).hex,),
        ).fetchone()
    return dict(row) if row is not None else None


def temporary_fixture(name: str, url: str, sha1: str, size: int) -> Path:
    path = ROOT / "artifacts" / "dev-env" / "strm" / (name + ".strm")
    source = FIXTURE.read_bytes()
    with path.open("xb") as fixture:
        fixture.write(base.write_versioned_fixture(source, url, sha1, size))
    return path


def temporary_fixture_in(directory: Path, name: str, url: str, sha1: str, size: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name + ".strm")
    source = FIXTURE.read_bytes()
    with path.open("xb") as fixture:
        fixture.write(base.write_versioned_fixture(source, url, sha1, size))
    return path


def slow_url(current_url: str, request_id: str) -> str:
    parts = urlsplit(current_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/slow/{request_id}/fixture.mp4", "", ""))


def delay_url(current_url: str, seconds: float, request_id: str) -> str:
    """A parameterized delay route so a scenario can hold a probe open for a deterministic settlement window."""
    parts = urlsplit(current_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/delay/{seconds:g}/{request_id}/fixture.mp4", "", ""))


def media_bytes() -> tuple[bytes, str]:
    media = (ROOT / "artifacts" / "dev-env" / "media" / "fixture.mp4").read_bytes()
    return media, hashlib.sha1(media).hexdigest()


def configuration_payload_from_xml(data: bytes) -> dict:
    """Parse the persisted plugin configuration XML back into the API payload shape for an effective re-publish."""
    import xml.etree.ElementTree as ElementTree

    root = ElementTree.fromstring(data.decode("utf-8-sig"))
    def text(name: str, default: str = "") -> str:
        element = root.find(name)
        return element.text if element is not None and element.text is not None else default

    def boolean(name: str, default: bool) -> bool:
        return text(name, str(default)).strip().lower() == "true"

    return {
        "Enabled": boolean("Enabled", True),
        "PlaybackAutoCheck": boolean("PlaybackAutoCheck", True),
        "MaxConcurrentProbes": int(text("MaxConcurrentProbes", "2")),
        "DetailedLog": boolean("DetailedLog", False),
        "BatchAllLibraries": boolean("BatchAllLibraries", True),
        "BatchLibraryIds": text("BatchLibraryIds", ""),
    }


def restore_state(original_configuration: bytes, trigger_snapshot: dict[str, list[dict]]) -> str:
    """Restore the plugin configuration file and effective configuration, and every native scheduled task trigger,
    then verify. It re-publishes the original configuration through the API and restarts the isolated server so the
    effective in-memory configuration is proven to match the restored file, not only the file bytes."""
    problems: list[str] = []
    if CONFIGURATION_FILE.is_file() and CONFIGURATION_FILE.read_bytes() != original_configuration:
        CONFIGURATION_FILE.write_bytes(original_configuration)
    if not CONFIGURATION_FILE.is_file() or CONFIGURATION_FILE.read_bytes() != original_configuration:
        problems.append("configuration file not restored")

    try:
        api = base.JellyfinApi()
        if original_configuration:
            payload = configuration_payload_from_xml(original_configuration)
            status = configure(api, payload)
            if status != 204:
                problems.append(f"effective configuration re-publish returned {status}")
        for task_id, triggers in trigger_snapshot.items():
            status = set_triggers(api, task_id, triggers)
            if status != 204:
                problems.append(f"trigger restore for {task_id} returned {status}")
        for task_id, triggers in trigger_snapshot.items():
            current = find_task_by_id(api, task_id)
            if (current.get("Triggers") or []) != triggers:
                problems.append(f"trigger identity mismatch for {task_id}")
    except Exception as error:  # Report restoration gaps instead of hiding them.
        problems.append(f"trigger/config restore failed: {type(error).__name__}")

    # Restart and read the effective configuration back, so a scope-only file restore cannot leave a different
    # in-memory scope. A restart failure is reported, not swallowed.
    try:
        base.restart_isolated_server()
        api = base.JellyfinApi()
        effective = current_configuration(api)
        expected = configuration_payload_from_xml(original_configuration) if original_configuration else None
        if expected is not None:
            for key, value in expected.items():
                if effective.get(key) != value:
                    problems.append(f"effective configuration {key} mismatch: {effective.get(key)!r} != {value!r}")
    except Exception as error:
        problems.append(f"effective configuration restart verification failed: {type(error).__name__}")

    return "restored and verified" if not problems else "NOT RESTORED: " + "; ".join(problems)


def find_task_by_id(api: base.JellyfinApi, task_id: str) -> dict:
    tasks = base.request_json(api.base_url + "/ScheduledTasks", headers=api.headers, timeout=20)
    matches = [task for task in tasks if str(task.get("Id", "")).lower() == str(task_id).lower()]
    base.require(len(matches) == 1, f"Expected exactly one native task with id {task_id!r}.")
    return matches[0]


def snapshot_triggers(api: base.JellyfinApi) -> dict[str, list[dict]]:
    tasks = base.request_json(api.base_url + "/ScheduledTasks", headers=api.headers, timeout=20)
    return {str(task["Id"]): (task.get("Triggers") or []) for task in tasks if task.get("Id")}


def configure(api: base.JellyfinApi, payload: dict) -> int:
    status, _ = api.request_response(f"/Plugins/{PLUGIN_ID}/Configuration", method="POST", data=json.dumps(payload).encode("utf-8"))
    return status


def current_configuration(api: base.JellyfinApi) -> dict:
    _, body = api.request_response(f"/Plugins/{PLUGIN_ID}/Configuration")
    return json.loads(body)


# ---------------------------------------------------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------------------------------------------------


def scenario_all(api: base.JellyfinApi, container: str) -> dict:
    """Discovery, no default trigger, manual run, real wall-clock trigger, restart, first trust and changed commit."""
    task = find_task(api)
    base.require(not task.get("Triggers"), f"A fresh install must have no default trigger: {task.get('Triggers')}.")
    manual = run_task(api)
    summary = latest_batch_summary(container)
    base.require(summary["count"] >= 1, "The manual batch run produced no summary event.")
    base.require(str((manual.get("LastExecutionResult") or {}).get("Status", "")).lower() in {"completed", "0"}, "The manual batch run did not complete.")

    # A real wall-clock trigger: set a daily trigger ~70s in the future in the server's (UTC) timezone, restart to
    # prove persistence, then observe the task actually run by the timer without any manual start.
    task_id = task["Id"]
    before_trigger_start = last_start(task)
    trigger_ticks = future_time_of_day_ticks(seconds_ahead=70)
    status = set_triggers(api, task_id, [{"Type": "DailyTrigger", "TimeOfDayTicks": trigger_ticks}])
    base.require(status == 204, "Jellyfin did not accept the administrator trigger.")
    container = base.restart_isolated_server()
    api = base.JellyfinApi()
    after_restart = find_task(api)
    base.require(len(after_restart.get("Triggers") or []) == 1, "The administrator trigger did not persist across a real restart.")
    fired = wait_for_trigger_fire(api, before_trigger_start, timeout=180)
    base.require(fired, "The administrator daily trigger did not actually run the task within the window.")
    base.require(str((find_task(api).get("LastExecutionResult") or {}).get("Status", "")).lower() in {"completed", "0"}, "The timer-triggered batch run did not complete.")
    cleared = set_triggers(api, task_id, [])
    base.require(cleared == 204, "Jellyfin did not accept clearing the trigger.")

    # A fresh supported STRM gets a first-trust fingerprint, then a changed URL commits a new baseline, and an
    # unchanged repeat run performs no new probe. Each step is reconciled against the previous fingerprint row.
    media, sha1 = media_bytes()
    name = "Batch Change Control " + uuid.uuid4().hex[:10]
    url = "http://media:8080/fixture.mp4"
    path = temporary_fixture(name, url, sha1, len(media))
    result: dict = {}
    try:
        api.refresh_library()
        item = api.wait_for_named_library_item(name)
        run_task(api)
        first = fingerprint_row(item["Id"])
        base.require(first is not None, "The batch did not create a first-trust fingerprint for the new STRM.")
        base.require(first["url_hash"] == base.expected_url_hash(url), "The first-trust fingerprint has the wrong URL hash.")

        changed_url = base.unique_query_url(url, "batch-change-" + uuid.uuid4().hex[:10])
        path.write_bytes(base.write_versioned_fixture(path.read_bytes(), changed_url, sha1, len(media)))
        run_task(api)
        changed = fingerprint_row(item["Id"])
        base.require(changed is not None, "The batch lost the fingerprint after the URL change.")
        base.require(changed["url_hash"] != first["url_hash"], "The batch did not change the URL hash after the URL change.")
        base.require(changed["url_hash"] == base.expected_url_hash(changed_url), "The changed-URL fingerprint is not the new address.")
        base.require(changed["sha1"] == first["sha1"] and changed["file_size"] == first["file_size"], "The unchanged SHA-1/Size were not preserved.")

        run_task(api)
        repeat = fingerprint_row(item["Id"])
        base.require(repeat == changed, "An unchanged accepted source was re-committed by a later batch run.")
        summary_line = latest_batch_summary(container)["line"]
        repeat_fields = summary_fields(summary_line)
        assert_summary_equations(repeat_fields)
        base.require(repeat_fields.get("actual_probe_calls") == 0, "An unchanged repeat run performed a new native probe.")
        # The candidate identity set and native batch reads must report their time, allocation and capacity cost.
        require_cost_fields(repeat_fields, summary_line)
        base.require((repeat_fields.get("batch_reads") or 0) >= 1, f"The run did not report its native batch read count: {summary_line}.")
        base.require((repeat_fields.get("candidate_set_estimated_bytes") or 0) > 0, f"The run did not report the O(N) candidate identity size estimate: {summary_line}.")

        # Restart and prove the persisted fingerprint and the native address survive.
        container = base.restart_isolated_server()
        api = base.JellyfinApi()
        after_restart_row = fingerprint_row(item["Id"])
        base.require(after_restart_row == changed, "The changed-URL fingerprint did not survive a real restart.")
        playback = base.call_playback(api, container, item["Id"], changed_url)
        base.require(playback["http_status"] == 200 and playback["path_matches_manifest"], "The new address was not used after restart.")

        result = {
            "task_id": task_id,
            "manual": task_summary(manual),
            "trigger_fired_without_manual_start": fired,
            "trigger_persisted_after_restart": True,
            "default_trigger_restored": True,
            "new_strm_first_trust": first,
            "changed_url_committed": changed,
            "repeat_run_unchanged": repeat == changed,
            "repeat_summary": summary_line,
            "fingerprint_after_restart": after_restart_row,
            "address_after_restart": playback["path_matches_manifest"],
        }
    finally:
        path.unlink(missing_ok=True)
        cleanup_fixtures(api, [name])
    return result


def future_time_of_day_ticks(seconds_ahead: int) -> int:
    now = datetime.datetime.now(datetime.timezone.utc)
    if now.hour == 23 and now.minute >= 58:
        time.sleep(120)
        now = datetime.datetime.now(datetime.timezone.utc)
    target = now + datetime.timedelta(seconds=seconds_ahead)
    seconds = target.hour * 3600 + target.minute * 60 + target.second
    return seconds * 10_000_000 + target.microsecond * 10


def wait_for_trigger_fire(api: base.JellyfinApi, previous_start: str | None, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = find_task(api)
        if last_start(task) not in {None, previous_start} and task_state_name(task) in {"idle", "0"}:
            return True
        time.sleep(0.5)
    return False


def task_completion_events(container: str) -> list[str]:
    """Return the native worker completion statuses for this task in log order, e.g. ['Cancelled', 'Completed'].
    A stopped round must log Cancelled; a later queued/scheduled round logs its own status."""
    return [status for _, status in task_completion_events_with_time(container)]


def task_completion_events_with_time(container: str) -> list[tuple[float, str]]:
    """Return (seconds_of_day, status) for every native worker completion of this task in log order. The timestamp
    lets a scenario bind a Cancelled result to the current round even though ``docker logs --tail`` truncates older
    lines, which makes positional binding fragile."""
    logs = base.run(["docker", "logs", "--tail", "8000", container], timeout=20)
    base.require(logs.returncode == 0, "Could not read the isolated Jellyfin container logs.")
    events: list[tuple[float, str]] = []
    for line in (logs.stdout + logs.stderr).splitlines():
        if TASK_NAME not in line or " after " not in line:
            continue
        for status in ("Completed", "Cancelled", "Failed", "Aborted"):
            if f"{TASK_NAME} {status} after" in line:
                try:
                    events.append((parse_log_epoch(line), status))
                except RuntimeError:
                    pass
                break
    return events


def scenario_stop(api: base.JellyfinApi, container: str, media_container: str) -> dict:
    """Real native stop: per-source settlement, no new entry during settlement (manual and timer), next run without repeats."""
    nonce = uuid.uuid4().hex[:8]
    names = [f"Batch Stop {index} {nonce}" for index in range(3)]
    paths: list[Path] = []
    try:
        media, sha1 = media_bytes()
        plain_url = "http://media:8080/fixture.mp4"
        for name in names:
            paths.append(temporary_fixture(name, plain_url, sha1, len(media)))
        api.refresh_library()
        items = {name: api.wait_for_named_library_item(name) for name in names}

        # Establish a plain-URL baseline so the changed delayed URL requires a real probe.
        run_task(api)
        baseline_rows = {name: fingerprint_row(items[name]["Id"]) for name in names}
        for name, path in zip(names, paths):
            base.require(baseline_rows[name] is not None, f"The batch did not create a baseline for {name}.")
            base.require(baseline_rows[name]["url_hash"] == base.expected_url_hash(plain_url), f"The baseline for {name} is not the plain URL.")

        # Give each source a distinct delayed request id and a long delay so the settlement window is deterministic
        # and the started probes are still running when the stop and the timer fire.
        slow_ids = {name: uuid.uuid4().hex for name in names}
        for name, path in zip(names, paths):
            path.write_bytes(base.write_versioned_fixture(path.read_bytes(), delay_url(plain_url, 12, slow_ids[name]), sha1, len(media)))

        # Measurement precondition: this round must not start while the server's own native scan (and its
        # post-scan tasks) is still Running. The native TaskManager drains its queue on any task completion
        # and only starts queued work from an Idle worker, so a scan finishing inside the settlement window
        # can drop the queued batch run this scenario exists to observe. Nothing about the native scheduler
        # or the plugin's settlement rules is changed; the round is only measured from a settled server.
        native_settlement = wait_for_native_scan_settled(api, container)
        task = find_task(api)
        task_id = task["Id"]
        before_counts = base.media_request_counts(media_container)
        before_id_counts = slow_request_counts(media_container)
        armed_before = len(trigger_arm_times(container))
        round_started_at = now_time_of_day_seconds()
        status, _ = api.request_response("/ScheduledTasks/Running/" + task_id, method="POST")
        base.require(status == 204, "Jellyfin did not accept the stop-scenario batch start.")

        # Wait until the batch has started as many probes as the default concurrency allows (2), so the
        # started-before-stop set is deterministic; fall through after a short bound if fewer started.
        deadline = time.monotonic() + 20
        started: set[str] = set()
        while time.monotonic() < deadline:
            current_id_counts = slow_request_counts(media_container)
            started = {rid for rid, count in current_id_counts.items() if count > before_id_counts.get(rid, 0)}
            if len(started) >= 2:
                break
            time.sleep(0.2)
        base.require(bool(started), "The batch stop scenario never reached a real probe.")
        # The current round's own entry marker, filtered by the timestamp captured before the start so a long
        # multi-scenario session cannot inflate the count via --tail truncation. Exactly one entry is expected.
        entries_during_round = len(batch_run_entries(container, since=round_started_at))
        base.require(entries_during_round == 1, f"The current round must have exactly one Execute entry, found {entries_during_round}.")

        # Arm a real wall-clock trigger to fire during the settlement window, so a timer-triggered run (not only a
        # repeated manual start) is proven not to begin a new round before the old one settles.
        trigger_ticks = future_time_of_day_ticks(seconds_ahead=4)
        base.require(set_triggers(api, task_id, [{"Type": "DailyTrigger", "TimeOfDayTicks": trigger_ticks}]) == 204, "Jellyfin did not accept the settlement-window trigger.")
        armed = trigger_arm_times(container)
        base.require(len(armed) > armed_before, "The settlement-window trigger was not armed for this round (no new arm log).")
        armed_fire_at = armed[-1]
        armed_time_of_day = trigger_arm_time_of_day_seconds(container)

        stop_status = stop_task(api)
        base.require(stop_status == 204, "Jellyfin did not accept the native stop.")
        stopped_at = now_time_of_day_seconds()

        # Freeze the started-before-stop set at the stop boundary; this is the stopped round's committed set.
        started_before_stop = {rid for rid, count in slow_request_counts(media_container).items() if count > before_id_counts.get(rid, 0)}

        # During settlement a repeated manual start and the armed timer must not actually begin a new run. A
        # repeated manual start is issued now; the armed timer fires during the window. The old round stays
        # Cancelling until it settles, and only then may a queued run actually enter and start a probe. The
        # assertions below are timestamp-based against the stopped round's own Cancelled completion, so a queued
        # run that legitimately starts right after settlement is not misread as starting during the window.
        settling = find_task(api)
        base.require(task_state_name(settling) in {"cancelling", "2", "running", "1"}, f"The stopped task was not settling: {task_state_name(settling)}.")
        second_start, _ = api.request_response("/ScheduledTasks/Running/" + task_id, method="POST")
        trigger_fired = False
        settlement_deadline = time.monotonic() + 30
        while time.monotonic() < settlement_deadline:
            if time.time() >= armed_fire_at:
                trigger_fired = True
            if task_state_name(find_task(api)) in {"idle", "0"}:
                # The stopped round has settled (its Cancelled completion was logged and the worker is Idle).
                break
            time.sleep(0.2)
        # Bind the stopped round's Cancelled completion and its settle time.
        current_round_result = current_round_completion(container, stopped_at)
        base.require(current_round_result is not None, f"The stopped round produced no native completion after the stop ({task_completion_events(container)}).")
        base.require(current_round_result == "Cancelled", f"The stopped round did not record Cancelled: {current_round_result} ({task_completion_events(container)}).")
        cancelled_at = next(timestamp for timestamp, status in task_completion_events_with_time(container) if status == "Cancelled" and timestamp >= stopped_at)
        # No new round may have entered before the stopped round settled.
        entries_timeline = [(parse_log_epoch(entry), entry) for entry in batch_run_entries(container, since=round_started_at)]
        for entry_at, entry in entries_timeline[1:]:
            base.require(entry_at >= cancelled_at, f"A repeated manual start or the timer actually entered a new round during settlement (entry {entry_at:.3f} < settled {cancelled_at:.3f}; timeline {[round(t, 3) for t, _ in entries_timeline]}).")
        # No new probe may have started during the settlement window [stop, settled). Probe starts are timestamped,
        # so this is deterministic and does not race the queued run's own legitimate probe after settlement.
        settlement_probe_starts = [entry for entry in probe_start_entries(container, since=stopped_at) if entry["timestamp"] < cancelled_at]
        base.require(not settlement_probe_starts, f"A repeated manual start or the timer began a new probe during settlement: {settlement_probe_starts}.")
        base.require(trigger_fired, "The armed settlement-window trigger never fired while the old round was settling.")

        # Clear the trigger so only the already-queued native run (which must run only after settlement) remains.
        base.require(set_triggers(api, task_id, []) == 204, "Jellyfin did not accept clearing the settlement-window trigger.")

        final = wait_for_stable_idle(api, container, timeout=MAX_WAIT_SECONDS)
        status_value = "cancelled"

        # The stopped round is the first summary after the round start; the queued run adds a later one.
        all_summaries = batch_events(container, since=round_started_at)
        base.require(len(all_summaries) >= 1, "The stopped round never completed after settlement.")
        stop_summary = base.safe_event(all_summaries[0])
        stop_fields = summary_fields(stop_summary)
        assert_summary_equations(stop_fields)
        entries_after = len(batch_run_entries(container, since=round_started_at))
        base.require(entries_after >= 2, f"The queued trigger/manual run never actually ran after settlement (entries since round start {entries_after}).")
        # The queued run must be this round's request: it entered after the armed trigger fired, not from a prior
        # container-history event.
        queued_entry_line = batch_run_entries(container, since=round_started_at)[1]
        base.require(parse_log_epoch(queued_entry_line) >= armed_time_of_day, "The queued run entered before the armed settlement trigger fired.")
        base.require(parse_log_epoch(queued_entry_line) >= cancelled_at, "The queued run entered before the stopped round settled.")

        # Per-source settlement of the stopped round: the sources that actually started before the stop committed
        # their new delayed URL and are the stopped round's reliable successes; the rest were revoked without
        # starting and kept their previous baseline.
        committed = [name for name in names if slow_ids[name] in started_before_stop]
        revoked = [name for name in names if slow_ids[name] not in started_before_stop]
        base.require(len(committed) >= 1, "No actually started probe settled after the native stop.")
        base.require(len(committed) + len(revoked) == len(names), "Every stop-scenario source must settle exactly once.")
        for name in committed:
            row = fingerprint_row(items[name]["Id"])
            base.require(row is not None and row["url_hash"] == base.expected_url_hash(delay_url(plain_url, 12, slow_ids[name])), f"The actually started source {name} did not commit its new address after the stop.")
        base.require((stop_fields.get("reliable_success") or 0) == len(committed), f"The stopped round must count each started source once as a reliable success: {stop_summary}.")
        base.require((stop_fields.get("revoked") or 0) == len(revoked), f"The stopped round must count each not-started source as revoked: {stop_summary}.")

        # The run that actually executes after settlement must re-probe only the revoked sources (they kept their
        # old baseline) and must not re-probe the already committed ones. Every source's id count is therefore 1.
        final_id_counts = slow_request_counts(media_container)
        for name in committed:
            base.require(final_id_counts.get(slow_ids[name], 0) == 1, f"The queued run re-probed the already committed source {name} (count {final_id_counts.get(slow_ids[name], 0)}).")
        for name in revoked:
            base.require(final_id_counts.get(slow_ids[name], 0) >= 1, f"The queued run did not re-check the revoked source {name}.")
            row = fingerprint_row(items[name]["Id"])
            base.require(row is not None and row["url_hash"] == base.expected_url_hash(delay_url(plain_url, 12, slow_ids[name])), f"The revoked source {name} was not committed by the run after settlement.")

        # A further explicit run must skip every already committed source and start no new probe.
        before_explicit = {rid: slow_request_counts(media_container).get(rid, 0) for rid in slow_ids.values()}
        next_run = run_task(api)
        base.require(str((next_run.get("LastExecutionResult") or {}).get("Status", "")).lower() in {"completed", "0"}, "The next run after settlement did not complete.")
        next_summary = latest_batch_summary(container)["line"]
        next_fields = summary_fields(next_summary)
        assert_summary_equations(next_fields)
        after_explicit = slow_request_counts(media_container)
        for name in names:
            delta = after_explicit.get(slow_ids[name], 0) - before_explicit[slow_ids[name]]
            base.require(delta == 0, f"A run after settlement re-probed the already accepted source {name} (delta {delta}).")
        return {
            "nativeSettlementBeforeRound": native_settlement,
            "stop_http_status": stop_status,
            "task_status": status_value,
            "native_completions": task_completion_events(container),
            "current_round_completion": current_round_result,
            "started_source_count_before_stop": len(started_before_stop),
            "second_start_http_status": second_start,
            "settlement_trigger_fired": trigger_fired,
            "new_probe_during_settlement": 0,
            "new_run_during_settlement": False,
            "queued_run_after_settlement": entries_after - entries_during_round,
            "stop_query_return_ms": stop_fields.get("stop_query_return_ms"),
            "committed_after_stop": committed,
            "revoked_after_stop": revoked,
            "queued_run_reprobed_committed": False,
            "queued_run_reprobed_revoked": True,
            "next_run_reprobed_any": False,
            "stop_summary": stop_summary,
            "next_run_summary": next_summary,
            "next_run_after_settlement": True,
            "cleanup_fixture": names,
        }
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
        cleanup_fixtures(api, names)


def scenario_sharing(api: base.JellyfinApi, container: str, media_container: str) -> dict:
    """Both start orders must share one actually running probe between the batch and playback."""
    batch_first = _sharing_direction(api, container, media_container, playback_first=False)
    playback_first = _sharing_direction(api, container, media_container, playback_first=True)
    return {"batch_first": batch_first, "playback_first": playback_first}


def _sharing_direction(api: base.JellyfinApi, container: str, media_container: str, *, playback_first: bool) -> dict:
    nonce = uuid.uuid4().hex[:8]
    name = f"Batch Share {nonce}"
    path = ROOT / "artifacts" / "dev-env" / "strm" / (name + ".strm")
    try:
        media, sha1 = media_bytes()
        plain_url = "http://media:8080/fixture.mp4"
        target_url = slow_url(plain_url, uuid.uuid4().hex)
        with path.open("xb") as fixture:
            fixture.write(base.write_versioned_fixture(FIXTURE.read_bytes(), plain_url, sha1, len(media)))
        api.refresh_library()
        item = api.wait_for_named_library_item(name)
        run_task(api)  # baseline first trust on the plain URL
        path.write_bytes(base.write_versioned_fixture(path.read_bytes(), target_url, sha1, len(media)))

        before_counts = base.media_request_counts(media_container)
        playback_holder: dict = {}

        def playback() -> None:
            try:
                playback_holder["result"] = base.call_playback(api, container, item["Id"], target_url)
            except Exception as error:
                playback_holder["error"] = type(error).__name__

        if playback_first:
            worker = threading.Thread(target=playback, name="isolated-batch-share", daemon=True)
            worker.start()
            wait_for_slow_start(media_container, before_counts)
            run_task(api)
            worker.join(timeout=120)
            base.require(not worker.is_alive(), "The playback-first sharing playback did not finish.")
        else:
            task = find_task(api)
            status, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="POST")
            base.require(status == 204, "Jellyfin did not accept the batch-first sharing start.")
            wait_for_slow_start(media_container, before_counts)
            worker = threading.Thread(target=playback, name="isolated-batch-share", daemon=True)
            worker.start()
            worker.join(timeout=120)
            base.require(not worker.is_alive(), "The batch-first sharing playback did not finish.")
            wait_for_idle(api, timeout=MAX_WAIT_SECONDS)

        base.require("error" not in playback_holder, "The sharing playback failed outside the HTTP path.")
        after_counts = base.media_request_counts(media_container)
        slow_delta = after_counts["slow_requests_started"] - before_counts["slow_requests_started"]
        base.require(slow_delta == 1, f"The batch and playback must share one actually running probe, observed {slow_delta} slow probe requests.")
        final = wait_for_idle(api, timeout=MAX_WAIT_SECONDS)
        summary_line = latest_batch_summary(container)["line"]
        fields = summary_fields(summary_line)
        assert_summary_equations(fields)
        # The batch joined one actually running probe. When the batch itself started the shared probe its own
        # actual-call counter is one; when playback started it the batch started none. Either way the source is
        # counted once as a reliable success, the new address is committed, and exactly one real call happened.
        expected_batch_calls = 0 if playback_first else 1
        base.require(fields.get("actual_probe_calls") == expected_batch_calls, f"The batch actual native probe call count is wrong for this start order: {summary_line}.")
        base.require(fields.get("reliable_success") == 1, f"The shared committed source must be counted once as a reliable success: {summary_line}.")
        base.require(fields.get("need_probe") == 1, f"The shared source must be counted once in the need-probe denominator: {summary_line}.")
        row = fingerprint_row(item["Id"])
        base.require(row is not None and row["url_hash"] == base.expected_url_hash(target_url), f"The shared probe did not commit the new address: {row}.")
        return {
            "direction": "playback_first" if playback_first else "batch_first",
            "slow_probe_requests": slow_delta,
            "actual_probe_calls": fields.get("actual_probe_calls"),
            "reliable_success": fields.get("reliable_success"),
            "need_probe": fields.get("need_probe"),
            "committed_url_hash_matches": True,
            "batch_summary": summary_line,
            "playback": playback_holder.get("result"),
            "cleanup_fixture": name,
        }
    finally:
        path.unlink(missing_ok=True)
        cleanup_fixtures(api, [name])


def wait_for_slow_start(media_container: str, before_counts: dict[str, int], timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if base.media_request_counts(media_container)["slow_requests_started"] > before_counts["slow_requests_started"]:
            return
        time.sleep(0.2)
    raise RuntimeError("The batch/playback sharing scenario never reached a real slow probe request.")


def wait_for_request_id_start(media_container: str, request_id: str, before_count: int, timeout: int = 60) -> float:
    """Wait until a specific delayed request id has started one more time, and return the epoch time it was observed."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if slow_request_counts(media_container).get(request_id, 0) > before_count:
            return time.time()
        time.sleep(0.1)
    raise RuntimeError(f"The delayed request {request_id} never started.")


def scenario_scope(api: base.JellyfinApi, container: str, media_container: str) -> dict:
    """Explicit partial scope over two real libraries: multi-batch, multi-version, range-outside zero work and
    incremental next-round discovery. Also rejects an invalid selection and proves a disabled plugin starts nothing."""
    folders = base.request_json(api.base_url + "/Library/VirtualFolders", headers=api.headers, timeout=20)
    by_path: dict[str, str] = {}
    for folder in folders:
        for info in folder.get("LibraryOptions", {}).get("PathInfos", []):
            by_path[str(info.get("Path", ""))] = folder["ItemId"]
    strm_library = next((library_id for path, library_id in by_path.items() if path.rstrip("/").endswith("/strm")), None)
    local_library = next((library_id for path, library_id in by_path.items() if path.rstrip("/").endswith("/local")), None)
    base.require(strm_library is not None and local_library is not None, f"The isolated environment must expose a STRM and a local library: {by_path}.")
    base.require(strm_library != local_library, "The STRM and local candidates must come from distinct libraries.")

    media, sha1 = media_bytes()
    plain_url = "http://media:8080/fixture.mp4"
    strm_dir = ROOT / "artifacts" / "dev-env" / "strm"
    local_dir = ROOT / "artifacts" / "dev-env" / "media"
    nonce = uuid.uuid4().hex[:8]
    # More than one fixed batch (128) of candidates in the STRM library forces a real multi-batch read.
    bulk_count = 130
    bulk_names = [f"Batch Scope Bulk {nonce} {index:03d}" for index in range(bulk_count)]
    bulk_paths = [
        temporary_fixture_in(strm_dir, name, base.unique_query_url(plain_url, f"{nonce}-{index}"), sha1, len(media))
        for index, name in enumerate(bulk_names)
    ]
    # A versioned STRM inside the local library proves an explicit partial scope does not touch the other library.
    local_strm_name = f"Batch Scope Local Strm {nonce}"
    local_strm_path = temporary_fixture_in(local_dir, local_strm_name, base.unique_query_url(plain_url, nonce + "local"), sha1, len(media))
    # A native multi-version pair inside the STRM library proves both versions are checked by source identity.
    mv_primary_name = f"Batch Scope MV A {nonce}"
    mv_alt_name = f"Batch Scope MV B {nonce}"
    mv_primary_path = temporary_fixture_in(strm_dir, mv_primary_name, base.unique_query_url(plain_url, nonce + "mva"), sha1, len(media))
    mv_alt_path = temporary_fixture_in(strm_dir, mv_alt_name, base.unique_query_url(plain_url, nonce + "mvb"), sha1, len(media))
    # A STRM added after the fixed set to prove the next round re-queries and discovers new items.
    incremental_name = f"Batch Scope Increment {nonce}"
    incremental_path = strm_dir / (incremental_name + ".strm")
    all_paths = [*bulk_paths, local_strm_path, mv_primary_path, mv_alt_path]
    result: dict = {}
    try:
        api.refresh_library()
        for name in bulk_names:
            api.wait_for_named_library_item(name)
        api.wait_for_named_library_item(local_strm_name)
        mv_primary = api.wait_for_named_library_item(mv_primary_name)
        mv_alt = api.wait_for_named_library_item(mv_alt_name)
        merge_status = api.merge_versions([mv_primary["Id"], mv_alt["Id"]])
        base.require(merge_status == 204, "Jellyfin did not merge the two isolated STRM versions.")

        # An explicit selection that references a nonexistent library must be rejected on save and must not
        # change the persisted file.
        file_before = CONFIGURATION_FILE.read_bytes()
        rejected = configure(api, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": False, "BatchLibraryIds": uuid.uuid4().hex})
        base.require(rejected >= 400, f"Jellyfin accepted a batch scope referencing a nonexistent library ({rejected}).")
        base.require(CONFIGURATION_FILE.read_bytes() == file_before, "The rejected batch scope changed the persisted configuration file.")

        # Explicit partial scope = the STRM library only.
        accepted = configure(api, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": False, "BatchLibraryIds": strm_library})
        base.require(accepted == 204, f"Jellyfin rejected a valid explicit single-library scope ({accepted}).")
        before_counts = base.media_request_counts(media_container)
        run_task(api)
        summary_line = latest_batch_summary(container)["line"]
        fields = summary_fields(summary_line)
        assert_summary_equations(fields)
        base.require(fields.get("candidates", 0) >= bulk_count, f"The partial-scope run did not capture the multi-batch candidate set: {summary_line}.")
        base.require((fields.get("batch_reads") or 0) >= 2, f"The multi-batch candidate set was not read in more than one batch: {summary_line}.")
        bulk_ids = [api.named_library_item(name)["Id"] for name in bulk_names]
        base.require(all(fingerprint_row(item_id) is not None for item_id in bulk_ids), "The partial-scope run did not first-trust every STRM-library candidate.")
        # Range outside the explicit selection is not processed at all.
        local_strm_item = api.named_library_item(local_strm_name)
        base.require(fingerprint_row(local_strm_item["Id"]) is None, "An out-of-scope library candidate was processed by an explicit partial scope.")
        # The native multi-version pair is checked per source under one canonical project identity. Both source
        # keys must share the same canonical item_id so the (item_id, source_key) association is unique.
        mv_primary_after = fingerprint_row(mv_primary["Id"])
        mv_alt_after = fingerprint_row(mv_alt["Id"])
        base.require(mv_primary_after is not None and mv_alt_after is not None, "The multi-version pair did not receive a fingerprint row for each version.")
        base.require(
            mv_primary_after["item_id"] == mv_alt_after["item_id"],
            "Both versions of one project must share one canonical item_id (canonical item_id + source_key uniqueness).",
        )
        base.require(mv_primary_after["source_key"] != mv_alt_after["source_key"], "The two versions must keep distinct source keys under the shared project.")
        after_counts = base.media_request_counts(media_container)
        # This isolated environment has no pre-probed primary stream for the new fixtures, so every candidate is
        # correctly decided to need a probe rather than first-trusted. Reconcile the real branch instead of
        # asserting an unprobed first trust: every need-probe candidate must have produced exactly one actual call,
        # and the out-of-scope library candidate must never be probed.
        base.require(fields.get("need_probe") == fields.get("actual_probe_calls"), f"Every need-probe candidate must start exactly one native call: {summary_line}.")
        base.require((fields.get("first_trust") or 0) == 0, f"A candidate without an existing primary stream must not be first-trusted: {summary_line}.")
        base.require(after_counts["slow_requests_started"] == before_counts["slow_requests_started"], "A first-trust candidate started a native probe.")

        # A STRM added after the fixed set must be discovered by the next round, not the current one.
        with incremental_path.open("xb") as fixture:
            fixture.write(base.write_versioned_fixture(FIXTURE.read_bytes(), base.unique_query_url(plain_url, nonce + "inc"), sha1, len(media)))
        api.refresh_library()
        incremental = api.wait_for_named_library_item(incremental_name)
        run_task(api)
        next_summary = latest_batch_summary(container)["line"]
        base.require(fingerprint_row(incremental["Id"]) is not None, "A STRM added after the fixed set was not discovered by the next round.")

        # In-round fixed-set mutation: hold a run open with a long-delay source, then add a new STRM and delete an
        # already-captured candidate while the run is still executing. The added item must not be processed this
        # round (the fixed set was already captured) and the deleted candidate must settle safely without failing
        # the run. The next round must then discover the added item and converge.
        in_round_names = [f"Batch Scope InRound {nonce} {index}" for index in range(2)]
        in_round_paths = [temporary_fixture_in(strm_dir, name, plain_url, sha1, len(media)) for name in in_round_names]
        all_paths.extend(in_round_paths)
        api.refresh_library()
        in_round_items = {name: api.wait_for_named_library_item(name) for name in in_round_names}
        in_round_ids = {name: uuid.uuid4().hex for name in in_round_names}
        for name, path in zip(in_round_names, in_round_paths):
            path.write_bytes(base.write_versioned_fixture(path.read_bytes(), delay_url(plain_url, 8, in_round_ids[name]), sha1, len(media)))
        in_round_added_name = f"Batch Scope InRound Added {nonce}"
        in_round_added_path = strm_dir / (in_round_added_name + ".strm")
        before_in_round = slow_request_counts(media_container)
        status, _ = api.request_response("/ScheduledTasks/Running/" + task_id_for(api), method="POST")
        base.require(status == 204, "Jellyfin did not accept the in-round batch start.")
        # Wait until at least one in-round source has actually started, so the candidate set is already fixed.
        in_round_deadline = time.monotonic() + 30
        while time.monotonic() < in_round_deadline:
            started = {rid for rid, count in slow_request_counts(media_container).items() if count > before_in_round.get(rid, 0)}
            if started & set(in_round_ids.values()):
                break
            time.sleep(0.1)
        base.require(bool(started & set(in_round_ids.values())), "The in-round batch never started a probe.")
        # Add a new STRM during the run and delete one already-captured candidate.
        with in_round_added_path.open("xb") as fixture:
            fixture.write(base.write_versioned_fixture(FIXTURE.read_bytes(), base.unique_query_url(plain_url, nonce + "inroundadded"), sha1, len(media)))
        deleted_name = in_round_names[1]
        in_round_paths[1].unlink(missing_ok=True)
        api.refresh_library()
        in_round_added = api.wait_for_named_library_item(in_round_added_name)
        final = wait_for_stable_idle(api, container, timeout=MAX_WAIT_SECONDS)
        base.require(task_state_name(final) in {"idle", "0"}, "The in-round batch did not settle.")
        in_round_summary = latest_batch_summary(container)["line"]
        in_round_fields = summary_fields(in_round_summary)
        assert_summary_equations(in_round_fields)
        # The item added during the fixed-set run must not have been processed by that run.
        base.require(fingerprint_row(in_round_added["Id"]) is None, "A STRM added during the fixed-set run was processed by the same round.")
        # The run must have completed without failing on the deleted candidate.
        base.require(in_round_fields.get("candidate_fetch_failed") is False, f"The in-round run failed its candidate fetch: {in_round_summary}.")
        base.require("store unavailable False" in in_round_summary, f"The in-round run reported a store fault: {in_round_summary}.")
        # The next round must discover the item added during the previous run and converge.
        run_task(api)
        base.require(fingerprint_row(in_round_added["Id"]) is not None, "The next round did not discover the item added during the fixed-set run.")

        # Switching the explicit scope to the local library now processes the local STRM candidate.
        switched = configure(api, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": False, "BatchLibraryIds": local_library})
        base.require(switched == 204, f"Jellyfin rejected the switched explicit scope ({switched}).")
        run_task(api)
        base.require(fingerprint_row(local_strm_item["Id"]) is not None, "The switched explicit scope did not process the local STRM candidate.")

        # Disabling the plugin must stop the batch before it starts new probes. The check covers every media
        # route (ordinary fixture, alternate and delayed), not only the slow counter.
        configure(api, {"Enabled": False, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": False, "BatchLibraryIds": strm_library})
        before_disabled = base.media_request_counts(media_container)
        before_disabled_ids = slow_request_counts(media_container)
        run_task(api)
        after_disabled = base.media_request_counts(media_container)
        after_disabled_ids = slow_request_counts(media_container)
        base.require(
            after_disabled["fixture"] == before_disabled["fixture"]
            and after_disabled["fixture_alt"] == before_disabled["fixture_alt"]
            and after_disabled["slow_requests_started"] == before_disabled["slow_requests_started"],
            "A disabled plugin still started a new batch media request.",
        )
        base.require(after_disabled_ids == before_disabled_ids, "A disabled plugin still started a new delayed probe request.")

        result = {
            "strm_library_id": strm_library,
            "local_library_id": local_library,
            "invalid_scope_http_status": rejected,
            "valid_scope_http_status": accepted,
            "bulk_candidate_count": bulk_count,
            "summary_line": summary_line,
            "candidates": fields.get("candidates"),
            "batch_reads": fields.get("batch_reads"),
            "all_bulk_candidates_checked": True,
            "out_of_scope_library_unprocessed": True,
            "multi_version_rows": 2,
            "incremental_discovered_next_round": True,
            "in_round_added_not_processed_same_round": True,
            "in_round_deleted_settled_safely": True,
            "in_round_added_discovered_next_round": True,
            "in_round_summary": in_round_summary,
            "switched_scope_processed": True,
            "next_round_summary": next_summary,
            "disabled_started_no_new_probe": True,
        }
    finally:
        for path in all_paths:
            path.unlink(missing_ok=True)
        incremental_path.unlink(missing_ok=True)
        in_round_added_path.unlink(missing_ok=True)
        try:
            configure(api, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": True, "BatchLibraryIds": ""})
        except Exception as error:
            record_cleanup_problem(f"scope configuration restore failed: {type(error).__name__}")
        cleanup_fixtures(api, [*bulk_names, local_strm_name, mv_primary_name, mv_alt_name, incremental_name, *in_round_names, in_round_added_name])
    return result


def scenario_shared_stop(api: base.JellyfinApi, container: str, media_container: str) -> dict:
    """Stop a batch that joined an already running playback probe, in both start orders. The started probe must
    finish and commit, the batch must settle as Cancelled without revoking the started work, and an independent
    playback on a different source must actually start and run a new probe while the old round settles."""
    playback_first = _shared_stop_direction(api, container, media_container, playback_first=True)
    batch_first = _shared_stop_direction(api, container, media_container, playback_first=False)
    return {"playback_first": playback_first, "batch_first": batch_first}


def library_ids_by_suffix(api: base.JellyfinApi) -> dict[str, str]:
    """Return the isolated library ids keyed by their directory suffix (for example 'strm' and 'local')."""
    folders = base.request_json(api.base_url + "/Library/VirtualFolders", headers=api.headers, timeout=20)
    by_suffix: dict[str, str] = {}
    for folder in folders:
        for info in folder.get("LibraryOptions", {}).get("PathInfos", []):
            suffix = str(info.get("Path", "")).rstrip("/").rsplit("/", 1)[-1]
            if suffix:
                by_suffix[suffix] = folder["ItemId"]
    return by_suffix


def _shared_stop_direction(api: base.JellyfinApi, container: str, media_container: str, *, playback_first: bool) -> dict:
    nonce = uuid.uuid4().hex[:8]
    name = f"Batch Shared Stop {nonce}"
    other_name = f"Batch Shared Stop Other {nonce}"
    path = ROOT / "artifacts" / "dev-env" / "strm" / (name + ".strm")
    other_path = ROOT / "artifacts" / "dev-env" / "media" / (other_name + ".strm")
    libraries = library_ids_by_suffix(api)
    base.require("strm" in libraries and "local" in libraries, f"The isolated environment must expose strm and local libraries: {libraries}.")
    strm_library = libraries["strm"]
    try:
        media, sha1 = media_bytes()
        plain_url = "http://media:8080/fixture.mp4"
        # A long delay keeps the shared probe running while the batch is stopped, so the joined started probe is
        # still settling when the stop is confirmed.
        target_url = delay_url(plain_url, 8, uuid.uuid4().hex)
        other_slow_id = uuid.uuid4().hex
        other_url = delay_url(plain_url, 4, other_slow_id)
        with path.open("xb") as fixture:
            fixture.write(base.write_versioned_fixture(FIXTURE.read_bytes(), plain_url, sha1, len(media)))
        # The independent source lives in a different library, so the batch (scoped to the STRM library) never
        # processes it and its playback genuinely starts a new probe during the stopped round's settlement.
        with other_path.open("xb") as fixture:
            fixture.write(base.write_versioned_fixture(FIXTURE.read_bytes(), plain_url, sha1, len(media)))
        api.refresh_library()
        item = api.wait_for_named_library_item(name)
        other_item = api.wait_for_named_library_item(other_name)
        # Scope the batch to the STRM library only and baseline the shared item with a batch run.
        accepted = configure(api, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": False, "BatchLibraryIds": strm_library})
        base.require(accepted == 204, f"Jellyfin rejected the shared-stop scope configuration ({accepted}).")
        run_task(api)  # baseline first trust for the shared item
        # Baseline the independent item through a playback on its plain URL (the batch never touches it).
        base.call_playback(api, container, other_item["Id"], plain_url)
        path.write_bytes(base.write_versioned_fixture(path.read_bytes(), target_url, sha1, len(media)))
        other_path.write_bytes(base.write_versioned_fixture(other_path.read_bytes(), other_url, sha1, len(media)))

        before_counts = base.media_request_counts(media_container)
        before_id_counts = slow_request_counts(media_container)
        playback_holder: dict = {}
        other_holder: dict = {}

        def playback() -> None:
            try:
                playback_holder["result"] = base.call_playback(api, container, item["Id"], target_url)
            except Exception as error:
                playback_holder["error"] = type(error).__name__

        def independent_playback() -> None:
            try:
                other_holder["result"] = base.call_playback(api, container, other_item["Id"], other_url)
            except Exception as error:
                other_holder["error"] = type(error).__name__

        task = find_task(api)
        if playback_first:
            worker = threading.Thread(target=playback, name="isolated-shared-stop-playback", daemon=True)
            worker.start()
            wait_for_slow_start(media_container, before_counts)
            status, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="POST")
            base.require(status == 204, "Jellyfin did not accept the shared-stop batch start.")
        else:
            status, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="POST")
            base.require(status == 204, "Jellyfin did not accept the batch-first shared-stop start.")
            wait_for_slow_start(media_container, before_counts)
            worker = threading.Thread(target=playback, name="isolated-shared-stop-playback", daemon=True)
            worker.start()

        # Wait until the batch has joined the running probe (task Running) before stopping it.
        joined_deadline = time.monotonic() + 20
        while time.monotonic() < joined_deadline and task_state_name(find_task(api)) not in {"running", "1"}:
            time.sleep(0.2)
        stop_status = stop_task(api)
        base.require(stop_status == 204, "Jellyfin did not accept the shared-stop stop.")
        stopped_at = now_time_of_day_seconds()
        settling = find_task(api)
        base.require(task_state_name(settling) in {"cancelling", "2", "running", "1"}, f"The shared-stop batch was not settling: {task_state_name(settling)}.")

        # While the old round is still settling, the independent source's playback must actually start a new probe.
        other_before = slow_request_counts(media_container).get(other_slow_id, 0)
        other_worker = threading.Thread(target=independent_playback, name="isolated-shared-stop-independent", daemon=True)
        other_worker.start()
        wait_for_request_id_start(media_container, other_slow_id, other_before)
        state_during_independent = task_state_name(find_task(api))
        base.require(state_during_independent in {"cancelling", "2", "running", "1"}, "The shared-stop batch was no longer settling when the independent probe started.")
        other_worker.join(timeout=120)
        base.require(not other_worker.is_alive(), "The independent playback did not finish.")
        base.require("error" not in other_holder, "The independent playback failed outside the HTTP path.")
        base.require(other_holder["result"]["http_status"] == 200, "An independent playback failed while the stopped batch was settling.")

        worker.join(timeout=120)
        base.require(not worker.is_alive(), "The joined playback did not finish.")
        base.require("error" not in playback_holder, "The joined playback failed outside the HTTP path.")
        final = wait_for_stable_idle(api, container, timeout=MAX_WAIT_SECONDS)
        # Bind the Cancelled result to this round: the first native completion of this task logged after the stop
        # request must be the stopped round recording Cancelled, not an older entry from container history.
        current_round_result = current_round_completion(container, stopped_at)
        base.require(current_round_result is not None, f"The shared-stop round produced no native completion after the stop ({task_completion_events(container)}).")
        base.require(current_round_result == "Cancelled", f"The shared-stop batch did not record Cancelled: {current_round_result} ({task_completion_events(container)}).")
        status_value = "cancelled"
        summary_line = latest_batch_summary(container)["line"]
        fields = summary_fields(summary_line)
        assert_summary_equations(fields)
        # The batch joined one already running probe that actually completed and committed: it is this round's
        # reliable success, never a revoked candidate, and the batch started no additional call of its own when
        # playback started the probe first.
        expected_batch_calls = 1 if (not playback_first) else 0
        base.require(fields.get("actual_probe_calls") == expected_batch_calls, f"The batch actual native call count is wrong for this start order: {summary_line}.")
        base.require(fields.get("reliable_success") == 1, f"The joined committed probe must count once as a reliable success: {summary_line}.")
        base.require((fields.get("revoked") or 0) == 0, f"The joined started probe must not be revoked by the batch stop: {summary_line}.")
        row = fingerprint_row(item["Id"])
        base.require(row is not None and row["url_hash"] == base.expected_url_hash(target_url), f"The joined probe did not commit the new address after the stop: {row}.")
        target_delta = slow_request_counts(media_container).get(target_url.rsplit("/", 2)[-2], 0) - before_id_counts.get(target_url.rsplit("/", 2)[-2], 0)
        base.require(target_delta == 1, f"The shared target probe must have run exactly once: {target_delta}.")
        return {
            "direction": "playback_first" if playback_first else "batch_first",
            "task_status": status_value,
            "native_completions": task_completion_events(container),
            "current_round_completion": current_round_result,
            "stop_http_status": stop_status,
            "joined_actual_probe_calls": fields.get("actual_probe_calls"),
            "joined_reliable_success": fields.get("reliable_success"),
            "joined_revoked": fields.get("revoked"),
            "shared_probe_requests": target_delta,
            "independent_playback_http_status": other_holder["result"]["http_status"],
            "independent_probe_started_while_settling": True,
            "independent_task_state_when_probe_started": state_during_independent,
            "committed_after_stop": True,
            "summary_line": summary_line,
        }
    finally:
        path.unlink(missing_ok=True)
        other_path.unlink(missing_ok=True)
        try:
            configure(api, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": True, "BatchLibraryIds": ""})
        except Exception as error:
            record_cleanup_problem(f"shared-stop scope restore failed: {type(error).__name__}")
        cleanup_fixtures(api, [name, other_name])


def probe_start_lines(container: str) -> list[str]:
    """Return the plugin's own native-probe start log lines, which carry the live running/active-permit counts."""
    logs = base.run(["docker", "logs", "--tail", "8000", container], timeout=20)
    base.require(logs.returncode == 0, "Could not read the isolated Jellyfin container logs.")
    return [line for line in (logs.stdout + logs.stderr).splitlines() if "Native STRM probe started" in line]


def probe_start_entries(container: str, since: float | None = None) -> list[dict]:
    """Parse the plugin's own native-probe start log lines into per-start entries with the project item id and the
    running-probe count reported at that start. When ``since`` (seconds of day) is given, only starts at or after it
    are returned, which binds the entries to the current round despite ``--tail`` truncation."""
    import re

    logs = base.run(["docker", "logs", "--tail", "8000", container], timeout=20)
    base.require(logs.returncode == 0, "Could not read the isolated Jellyfin container logs.")
    entries: list[dict] = []
    for line in (logs.stdout + logs.stderr).splitlines():
        if "Native STRM probe started" not in line:
            continue
        item = re.search(r"probe started for item ([0-9a-fA-F-]+)", line)
        running = re.search(r"running probes (\d+)", line)
        if not (item and running):
            continue
        try:
            timestamp = parse_log_epoch(line)
        except RuntimeError:
            continue
        if since is not None and timestamp < since:
            continue
        entries.append({"item_id": item.group(1).lower(), "running": int(running.group(1)), "timestamp": timestamp})
    return entries


def scenario_mixed(api: base.JellyfinApi, container: str, media_container: str) -> dict:
    """A batch and a concurrent playback on different sources must not exceed the configured startup concurrency.
    The playback source is placed in a different library and the batch is scoped to the STRM library, so the batch
    never processes the playback source. The peak and the overlap are attributed per owner from the plugin's own
    running-probe counter, proving a batch owner and a playback owner actually occupied the pool together."""
    nonce = uuid.uuid4().hex[:8]
    batch_names = [f"Batch Mixed {index} {nonce}" for index in range(2)]
    playback_name = f"Batch Mixed Playback {nonce}"
    batch_paths: list[Path] = []
    playback_path = ROOT / "artifacts" / "dev-env" / "media" / (playback_name + ".strm")
    libraries = library_ids_by_suffix(api)
    base.require("strm" in libraries and "local" in libraries, f"The isolated environment must expose strm and local libraries: {libraries}.")
    strm_library = libraries["strm"]
    try:
        media, sha1 = media_bytes()
        plain_url = "http://media:8080/fixture.mp4"
        for name in batch_names:
            batch_paths.append(temporary_fixture(name, plain_url, sha1, len(media)))
        with playback_path.open("xb") as fixture:
            fixture.write(base.write_versioned_fixture(FIXTURE.read_bytes(), plain_url, sha1, len(media)))
        api.refresh_library()
        batch_items = {name: api.wait_for_named_library_item(name) for name in batch_names}
        playback_item = api.wait_for_named_library_item(playback_name)

        # Scope the batch to the STRM library only, then baseline: the batch first-trusts the two STRM items and
        # a playback first-trusts the local playback item.
        accepted = configure(api, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": False, "BatchLibraryIds": strm_library})
        base.require(accepted == 204, f"Jellyfin rejected the mixed scope configuration ({accepted}).")
        run_task(api)
        base.call_playback(api, container, playback_item["Id"], plain_url)

        # Stagger the batch delays so that when the shorter one finishes, the playback starts and overlaps the
        # still-running longer batch probe under the default concurrency of 2.
        batch_ids = {batch_names[0]: uuid.uuid4().hex, batch_names[1]: uuid.uuid4().hex}
        batch_delays = {batch_names[0]: 8, batch_names[1]: 3}
        for name, path in zip(batch_names, batch_paths):
            path.write_bytes(base.write_versioned_fixture(path.read_bytes(), delay_url(plain_url, batch_delays[name], batch_ids[name]), sha1, len(media)))
        playback_id = uuid.uuid4().hex
        playback_url = delay_url(plain_url, 4, playback_id)
        playback_path.write_bytes(base.write_versioned_fixture(playback_path.read_bytes(), playback_url, sha1, len(media)))

        before_counts = base.media_request_counts(media_container)
        before_id_counts = slow_request_counts(media_container)
        mixed_started_at = now_time_of_day_seconds()
        playback_holder: dict = {}

        def playback() -> None:
            try:
                playback_holder["result"] = base.call_playback(api, container, playback_item["Id"], playback_url)
            except Exception as error:
                playback_holder["error"] = type(error).__name__

        task = find_task(api)
        status, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="POST")
        base.require(status == 204, "Jellyfin did not accept the mixed batch start.")
        # Wait until both batch sources have actually started (the pool is saturated with two batch owners).
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            started = {rid for rid, count in slow_request_counts(media_container).items() if count > before_id_counts.get(rid, 0)}
            if set(batch_ids.values()).issubset(started):
                break
            time.sleep(0.1)
        base.require(set(batch_ids.values()).issubset({rid for rid, count in slow_request_counts(media_container).items() if count > before_id_counts.get(rid, 0)}), "Both batch sources must actually start.")
        # Start the playback on the different-library source; it waits for a freed permit, then overlaps the
        # still-running longer batch probe.
        worker = threading.Thread(target=playback, name="isolated-mixed-playback", daemon=True)
        worker.start()
        wait_for_request_id_start(media_container, playback_id, before_id_counts.get(playback_id, 0))
        worker.join(timeout=120)
        base.require(not worker.is_alive(), "The mixed concurrent playback did not finish.")
        base.require("error" not in playback_holder, "The mixed concurrent playback failed outside the HTTP path.")
        final = wait_for_idle(api, timeout=MAX_WAIT_SECONDS)
        base.require(task_state_name(final) in {"idle", "0"}, "The mixed batch did not settle.")

        after_id_counts = slow_request_counts(media_container)
        started_ids = {rid for rid, count in after_id_counts.items() if count > before_id_counts.get(rid, 0)}
        base.require(set(batch_ids.values()).issubset(started_ids), f"Both batch sources must be probed: {started_ids}.")
        base.require(playback_id in started_ids, "The concurrent playback source must be probed.")
        summary_line = latest_batch_summary(container)["line"]
        fields = summary_fields(summary_line)
        assert_summary_equations(fields)
        # The batch is scoped to the STRM library, so it starts exactly one call per batch source and never the
        # playback source.
        base.require(fields.get("actual_probe_calls") == len(batch_names), f"The batch must start exactly one call per scoped source: {summary_line}.")

        # Attribute the peak per owner from the plugin's own start lines logged after this round started. The
        # playback item's start line must show running 2 (the playback owner plus a still-running batch owner),
        # proving both entries overlapped.
        entries = probe_start_entries(container, since=mixed_started_at)
        peak_running = max((entry["running"] for entry in entries), default=0)
        playback_hex = playback_item["Id"].replace("-", "").lower()
        playback_entry = next((entry for entry in entries if entry["item_id"].replace("-", "").lower() == playback_hex), None)
        batch_item_ids = {item["Id"].replace("-", "").lower() for item in batch_items.values()}
        batch_entry_items = {entry["item_id"] for entry in entries if entry["item_id"].replace("-", "").lower() in batch_item_ids}
        base.require(peak_running <= 2, f"The mixed batch + playback overlap exceeded the default concurrency of 2: peak running probes {peak_running}.")
        base.require(peak_running == 2, f"The mixed overlap never reached the default concurrency of 2, so the limit was not exercised: peak {peak_running}.")
        base.require(playback_entry is not None, "The concurrent playback never started its own probe.")
        base.require(playback_entry["running"] == 2, f"The playback probe did not overlap a batch probe: playback start running={playback_entry['running']}.")
        base.require(bool(batch_entry_items), "No batch owner started a probe to overlap with the playback.")

        # An independent native FullRefresh must not be gated by the plugin pool. This only records the native
        # queue acceptance; the default playback script already holds the real saturated-pool refresh-completion
        # evidence, which is explicitly reused rather than re-derived from this 204 acknowledgement.
        refresh_status, _ = api.force_full_refresh(playback_item["Id"])
        base.require(refresh_status == 204, "Jellyfin rejected the independent manual FullRefresh.")
        return {
            "batch_sources": batch_names,
            "playback_source": playback_name,
            "batch_scope_library": strm_library,
            "summary_line": summary_line,
            "actual_probe_calls": fields.get("actual_probe_calls"),
            "reliable_success": fields.get("reliable_success"),
            "all_batch_sources_started": True,
            "concurrent_playback_probed": True,
            "peak_running_probes": peak_running,
            "playback_start_running": playback_entry["running"],
            "batch_owner_started": True,
            "configured_concurrency": 2,
            "peak_within_limit": peak_running <= 2,
            "batch_playback_overlap_proven": playback_entry["running"] == 2,
            "independent_full_refresh_queued": refresh_status == 204,
            "native_refresh_completion_evidence": "reused from the default playback integration script saturated-pool check",
        }
    finally:
        for path in batch_paths:
            path.unlink(missing_ok=True)
        playback_path.unlink(missing_ok=True)
        try:
            configure(api, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": True, "BatchLibraryIds": ""})
        except Exception as error:
            record_cleanup_problem(f"mixed scope restore failed: {type(error).__name__}")
        cleanup_fixtures(api, [*batch_names, playback_name])


def scenario_failure(api: base.JellyfinApi, container: str) -> dict:
    """An unavailable fingerprint store must be reported as a batch failure, never a silent completion."""
    # Replace the fingerprint database file with a directory of the same name so the plugin cannot open its store.
    # The plugin must latch the store as unavailable, the native task must fail (not report Completed), and no new
    # probe of any kind may start. The database is restored and the server restarted to clear the latch before the
    # recovery run.
    base.require(FINGERPRINT_DATABASE.is_file(), "The plugin fingerprint database is missing.")
    backup = FINGERPRINT_DATABASE.with_suffix(".db.bak-" + uuid.uuid4().hex[:8])
    shutil.copy2(FINGERPRINT_DATABASE, backup)
    result: dict = {}
    try:
        FINGERPRINT_DATABASE.unlink()
        FINGERPRINT_DATABASE.mkdir()
        media_container = base.isolated_media_container_name()
        before_counts = base.media_request_counts(media_container)
        before_started = slow_request_ids_started(media_container)
        final = run_task(api)
        status_value = str((final.get("LastExecutionResult") or {}).get("Status", "")).lower()
        summary_line = latest_batch_summary(container)["line"]
        after_counts = base.media_request_counts(media_container)
        after_started = slow_request_ids_started(media_container)
        base.require(status_value in {"failed", "3"}, f"An unavailable fingerprint store did not fail the batch task: {status_value}.")
        base.require("store unavailable True" in (summary_line or ""), f"The batch summary did not report the store as unavailable: {summary_line}.")
        # No probe of any kind may start: ordinary fixture, alternate or delayed routes must all be unchanged.
        base.require(
            after_counts["fixture"] == before_counts["fixture"]
            and after_counts["fixture_alt"] == before_counts["fixture_alt"]
            and after_counts["slow_requests_started"] == before_counts["slow_requests_started"],
            "An unavailable fingerprint store still started a media request.",
        )
        base.require(after_started == before_started, "An unavailable fingerprint store still started a delayed probe request.")
        result = {"task_status": status_value, "summary_line": summary_line, "store_unavailable_reported": True, "no_new_probe": True}
    finally:
        if FINGERPRINT_DATABASE.is_dir():
            FINGERPRINT_DATABASE.rmdir()
        shutil.move(str(backup), str(FINGERPRINT_DATABASE))

    # The store fault latches until restart; restart, then prove the batch task is usable again.
    container = base.restart_isolated_server()
    api = base.JellyfinApi()
    recovered = run_task(api)
    result["recovered_status"] = str((recovered.get("LastExecutionResult") or {}).get("Status", "")).lower()
    base.require(result["recovered_status"] in {"completed", "0"}, "The batch task did not recover after the store was restored.")
    return result


def restore_fixture(item_id: str | None, original: bytes) -> str:
    """Restore the shared fixture and retry the Jellyfin address sync while the restarted server settles."""
    FIXTURE.write_bytes(original)
    if item_id is None:
        return "fixture restored; Jellyfin address sync not available"
    url, _, _ = base.parse_manifest(original)
    deadline = time.monotonic() + 120
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            api = base.JellyfinApi()
            container = base.isolated_container_name()
            result = base.call_playback(api, container, item_id, url)
            if result["http_status"] == 200 and result["path_matches_manifest"]:
                return "fixture restored and Jellyfin address synchronized"
            last_error = f"http {result['http_status']}"
        except Exception as error:
            last_error = type(error).__name__
        time.sleep(2)
    return f"fixture restored; Jellyfin address sync needs a later playback check ({last_error})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["suite", "discovery", "stop", "sharing", "scope", "failure", "shared_stop", "mixed"], default="suite")
    args = parser.parse_args()

    base.require(FIXTURE.is_file(), "The isolated STRM fixture is missing.")
    original = FIXTURE.read_bytes()
    original_configuration = CONFIGURATION_FILE.read_bytes() if CONFIGURATION_FILE.is_file() else b""
    api: base.JellyfinApi | None = None
    container: str | None = None
    media_container: str | None = None
    fixture_item_id: str | None = None
    trigger_snapshot: dict[str, list[dict]] = {}
    summary: dict = {"fixture_restoration": "not needed"}
    exit_code = 1
    try:
        summary["deployment"] = base.deploy_plugin()
        container = base.restart_isolated_server()
        api = base.JellyfinApi()
        base.require(api.public_info().get("Version") == "12.2.0", "The active isolated Jellyfin version is not 12.2.0.")
        summary["plugin_status"] = api.plugin_status()
        media_container = base.isolated_media_container_name()
        trigger_snapshot = snapshot_triggers(api)
        try:
            fixture_item_id = api.fixture_item()["Id"]
        except RuntimeError:
            fixture_item_id = None

        if args.scenario in {"suite", "discovery"}:
            summary["scenario_discovery"] = scenario_all(api, container)
            # The discovery scenario restarts the isolated server; re-authenticate and re-resolve the container so
            # the following scenarios never reuse a stale session.
            api = base.JellyfinApi()
            container = base.isolated_container_name()
            media_container = base.isolated_media_container_name()
        if args.scenario in {"suite", "stop"}:
            summary["scenario_stop"] = scenario_stop(api, container, media_container)
        if args.scenario in {"suite", "shared_stop"}:
            summary["scenario_shared_stop"] = scenario_shared_stop(api, container, media_container)
        if args.scenario in {"suite", "sharing"}:
            summary["scenario_sharing"] = scenario_sharing(api, container, media_container)
        if args.scenario in {"suite", "scope"}:
            summary["scenario_scope"] = scenario_scope(api, container, media_container)
        if args.scenario in {"suite", "mixed"}:
            summary["scenario_mixed"] = scenario_mixed(api, container, media_container)
        if args.scenario in {"suite", "failure"}:
            summary["scenario_failure"] = scenario_failure(api, container)

        if CLEANUP_PROBLEMS:
            summary["status"] = "FAIL"
            summary["cleanup_problems"] = list(CLEANUP_PROBLEMS)
            summary["error"] = "Temporary isolated fixtures could not be fully removed."
            exit_code = 1
        else:
            summary["status"] = "PASS"
            exit_code = 0
    finally:
        summary["fixture_restoration"] = restore_fixture(fixture_item_id, original)
        summary["state_restoration"] = restore_state(original_configuration, trigger_snapshot)
        if exit_code == 0 and (
            summary["fixture_restoration"] != "fixture restored and Jellyfin address synchronized"
            or summary["state_restoration"] != "restored and verified"
        ):
            summary["status"] = "FAIL"
            summary["error"] = "The isolated STRM fixture, plugin configuration or task triggers could not be restored and verified."
            exit_code = 1
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, json.JSONDecodeError, base.subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
