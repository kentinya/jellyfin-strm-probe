#!/usr/bin/env python3
"""Exercise the native batch check task against the repository's isolated Jellyfin instance.

The script only uses the repository's isolated Compose project, temporary hand-written STRM
fixtures and the local synthetic media service. It saves the plugin configuration and every
native scheduled task trigger before the run, restores them in a finally block and verifies the
restoration, so a failed or interrupted run never leaves the isolated instance changed.

Scenarios:
  suite    (default) runs discovery, stop, sharing, scope and failure in one isolated session
  discovery   discovery / no default trigger / manual run / real wall-clock trigger / restart persistence /
           new STRM first trust / changed-URL commit against the old baseline / repeat zero-probe / restart
  stop     real native stop of started probes: per-source settlement, no new entry during settlement, next run
  sharing  batch and playback sharing one actually running same-source probe, in both start orders
  scope    explicit partial scope over two real libraries: multi-batch, multi-version, range-outside zero work,
           incremental next-round discovery, invalid save rejection and disabled no-new-probe
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


def find_task(api: base.JellyfinApi) -> dict:
    tasks = base.request_json(api.base_url + "/ScheduledTasks", headers=api.headers, timeout=20)
    matches = [task for task in tasks if task.get("Name") == TASK_NAME]
    base.require(len(matches) == 1, f"Expected exactly one native task named {TASK_NAME!r}, found {len(matches)}.")
    return matches[0]


def task_state_name(task: dict) -> str:
    return str(task.get("State", "")).lower()


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


def batch_events(container: str) -> list[str]:
    logs = base.run(["docker", "logs", "--tail", "4000", container], timeout=20)
    base.require(logs.returncode == 0, "Could not read the isolated Jellyfin container logs.")
    return [line for line in (logs.stdout + logs.stderr).splitlines() if "STRM media information check finished" in line]


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


def summary_fields(line: str | None) -> dict[str, int | bool | None]:
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
        "candidate_fetch_ms": parse_summary_field(line, "candidate fetch"),
        "candidate_fetch_allocated_bytes": parse_summary_field(line, "candidate fetch allocated"),
        "batch_reads": parse_summary_field(line, "batch reads"),
        "batch_read_ms": parse_summary_field(line, "batch read"),
        "batch_read_allocated_bytes": parse_summary_field(line, "batch read allocated"),
    }
    numeric["stop_requested"] = "stop requested True" in line
    numeric["store_unavailable"] = "store unavailable True" in line
    numeric["scope_unavailable"] = "scope unavailable True" in line
    numeric["candidate_fetch_failed"] = "candidate fetch failed True" in line
    numeric["disabled"] = "disabled True" in line
    return numeric


def slow_request_ids_started(container: str) -> set[str]:
    """Return the set of delayed-probe request ids that actually began, so per-source settlement can be reconciled."""
    logs = base.run(["docker", "logs", "--tail", "8000", container], timeout=20)
    base.require(logs.returncode == 0, "Could not read the isolated media service counters.")
    marker = "SLOW_MEDIA_REQUEST_STARTED "
    started: set[str] = set()
    for line in (logs.stdout + logs.stderr).splitlines():
        index = line.find(marker)
        if index >= 0:
            started.add(line[index + len(marker):].strip())
    return started


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
        # The candidate identity set and native batch reads must report their time and allocation cost.
        base.require((repeat_fields.get("candidate_fetch_ms") or 0) >= 0, f"The run did not report candidate fetch timing: {summary_line}.")
        base.require((repeat_fields.get("batch_reads") or 0) >= 1, f"The run did not report its native batch read count: {summary_line}.")
        base.require((repeat_fields.get("batch_read_ms") or 0) >= 0, f"The run did not report native batch read timing: {summary_line}.")
        base.require((repeat_fields.get("candidate_fetch_allocated_bytes") or 0) >= 0, f"The run did not report candidate identity allocation: {summary_line}.")
        base.require((repeat_fields.get("batch_read_allocated_bytes") or 0) >= 0, f"The run did not report batch read allocation: {summary_line}.")

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
        try:
            api.refresh_library()
            api.wait_for_named_library_item_absent(name)
        except Exception:
            pass
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


def scenario_stop(api: base.JellyfinApi, container: str, media_container: str) -> dict:
    """Real native stop: per-source settlement, no new entry during settlement, next run without repeats."""
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

        # Establish a plain-URL baseline so the changed slow URL requires a real probe.
        run_task(api)
        baseline_rows = {name: fingerprint_row(items[name]["Id"]) for name in names}
        for name, path in zip(names, paths):
            base.require(baseline_rows[name] is not None, f"The batch did not create a baseline for {name}.")
            base.require(baseline_rows[name]["url_hash"] == base.expected_url_hash(plain_url), f"The baseline for {name} is not the plain URL.")

        # Give each source a distinct slow request id so its actual start can be reconciled per source.
        slow_ids = {name: uuid.uuid4().hex for name in names}
        for name, path in zip(names, paths):
            path.write_bytes(base.write_versioned_fixture(path.read_bytes(), slow_url(plain_url, slow_ids[name]), sha1, len(media)))

        task = find_task(api)
        before_counts = base.media_request_counts(media_container)
        before_started = slow_request_ids_started(media_container)
        before_summaries = len(batch_events(container))
        status, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="POST")
        base.require(status == 204, "Jellyfin did not accept the stop-scenario batch start.")

        # Wait until at least one probe from this run has actually started.
        deadline = time.monotonic() + 60
        started: set[str] = set()
        while time.monotonic() < deadline:
            started = slow_request_ids_started(media_container) - before_started
            if started:
                break
            time.sleep(0.2)
        base.require(bool(started), "The batch stop scenario never reached a real probe.")
        stop_status = stop_task(api)
        base.require(stop_status == 204, "Jellyfin did not accept the native stop.")

        # During settlement a repeated manual start and any scheduler entry must not actually begin a new run:
        # the old round stays Cancelling, no new summary/query is emitted and no additional slow probe request appears.
        settling = find_task(api)
        base.require(task_state_name(settling) in {"cancelling", "2", "running", "1"}, f"The stopped task was not settling: {task_state_name(settling)}.")
        counts_at_stop = base.media_request_counts(media_container)
        second_start, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="POST")
        time.sleep(2)
        during = find_task(api)
        base.require(task_state_name(during) in {"cancelling", "2", "running", "1"}, "A repeated manual start began a new run during settlement.")
        counts_during = base.media_request_counts(media_container)
        base.require(
            counts_during["slow_requests_started"] == counts_at_stop["slow_requests_started"],
            "A repeated manual start during settlement began a new probe.",
        )
        base.require(len(batch_events(container)) == before_summaries, "A new batch run completed during the settlement window.")

        final = wait_for_idle(api, timeout=MAX_WAIT_SECONDS)
        status_value = str((final.get("LastExecutionResult") or {}).get("Status", "")).lower()
        base.require(status_value in {"cancelled", "2"}, f"The stopped batch task did not record Cancelled: {status_value}.")
        # Exactly one batch summary (the stopped round) may have completed; a second manual start during settlement
        # must have been rejected by the native worker rather than starting another run.
        base.require(len(batch_events(container)) == before_summaries + 1, "The settlement window produced more than one completed batch run.")
        stop_summary = latest_batch_summary(container)["line"]
        assert_summary_equations(summary_fields(stop_summary))

        # Per-source settlement: an actually started source must have committed its new slow URL after the stop;
        # a source that never started must keep its previous baseline and be settled as revoked.
        committed = []
        revoked = []
        for name in names:
            row = fingerprint_row(items[name]["Id"])
            if slow_ids[name] in started:
                base.require(row is not None and row["url_hash"] == base.expected_url_hash(slow_url(plain_url, slow_ids[name])), f"The actually started source {name} did not commit its new address after the stop.")
                committed.append(name)
            else:
                base.require(row == baseline_rows[name], f"The never-started source {name} did not retain its baseline after the stop.")
                revoked.append(name)
        base.require(len(committed) >= 1, "No actually started probe settled after the native stop.")
        base.require(len(committed) + len(revoked) == len(names), "Every stop-scenario source must settle exactly once.")

        # After settlement the next run must succeed and must not re-probe the already committed source. The
        # still-revoked sources still carry their changed slow URL, so they probe once with their original id.
        after_stop_started = slow_request_ids_started(media_container)
        next_run = run_task(api)
        base.require(str((next_run.get("LastExecutionResult") or {}).get("Status", "")).lower() in {"completed", "0"}, "The next run after settlement did not complete.")
        next_summary = latest_batch_summary(container)["line"]
        next_fields = summary_fields(next_summary)
        assert_summary_equations(next_fields)
        newly_started = slow_request_ids_started(media_container) - after_stop_started
        for name in committed:
            base.require(slow_ids[name] not in newly_started, f"The next run re-probed the already committed source {name}.")
        for name in revoked:
            base.require(slow_ids[name] in newly_started, f"The next run did not re-check the revoked source {name}.")
        return {
            "stop_http_status": stop_status,
            "task_status": status_value,
            "started_source_count_before_stop": len(started),
            "second_start_http_status": second_start,
            "new_probe_during_settlement": counts_during["slow_requests_started"] - counts_at_stop["slow_requests_started"],
            "new_run_during_settlement": False,
            "committed_after_stop": committed,
            "revoked_after_stop": revoked,
            "stop_summary": stop_summary,
            "next_run_summary": next_summary,
            "next_run_reprobed_committed": False,
            "next_run_after_settlement": True,
            "cleanup_fixture": names,
        }
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
        try:
            api.refresh_library()
            for name in names:
                api.wait_for_named_library_item_absent(name)
        except Exception:
            pass


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
        try:
            api.refresh_library()
            api.wait_for_named_library_item_absent(name)
        except Exception:
            pass


def wait_for_slow_start(media_container: str, before_counts: dict[str, int], timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if base.media_request_counts(media_container)["slow_requests_started"] > before_counts["slow_requests_started"]:
            return
        time.sleep(0.2)
    raise RuntimeError("The batch/playback sharing scenario never reached a real slow probe request.")


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
        # The native multi-version pair is checked per source under one canonical project identity.
        mv_primary_after = fingerprint_row(mv_primary["Id"])
        mv_alt_after = fingerprint_row(mv_alt["Id"])
        base.require(mv_primary_after is not None and mv_alt_after is not None, "The multi-version pair did not receive a fingerprint row for each version.")
        after_counts = base.media_request_counts(media_container)
        base.require(after_counts["slow_requests_started"] == before_counts["slow_requests_started"], "First-trust candidates started a native probe.")

        # A STRM added after the fixed set must be discovered by the next round, not the current one.
        with incremental_path.open("xb") as fixture:
            fixture.write(base.write_versioned_fixture(FIXTURE.read_bytes(), base.unique_query_url(plain_url, nonce + "inc"), sha1, len(media)))
        api.refresh_library()
        incremental = api.wait_for_named_library_item(incremental_name)
        run_task(api)
        next_summary = latest_batch_summary(container)["line"]
        base.require(fingerprint_row(incremental["Id"]) is not None, "A STRM added after the fixed set was not discovered by the next round.")

        # Switching the explicit scope to the local library now processes the local STRM candidate.
        switched = configure(api, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": False, "BatchLibraryIds": local_library})
        base.require(switched == 204, f"Jellyfin rejected the switched explicit scope ({switched}).")
        run_task(api)
        base.require(fingerprint_row(local_strm_item["Id"]) is not None, "The switched explicit scope did not process the local STRM candidate.")

        # Disabling the plugin must stop the batch before it starts new probes.
        configure(api, {"Enabled": False, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": False, "BatchLibraryIds": strm_library})
        before_disabled = base.media_request_counts(media_container)
        run_task(api)
        after_disabled = base.media_request_counts(media_container)
        base.require(after_disabled["slow_requests_started"] == before_disabled["slow_requests_started"], "A disabled plugin still started a new batch probe.")

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
            "switched_scope_processed": True,
            "next_round_summary": next_summary,
            "disabled_started_no_new_probe": True,
        }
    finally:
        for path in all_paths:
            path.unlink(missing_ok=True)
        incremental_path.unlink(missing_ok=True)
        try:
            configure(api, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": True, "BatchLibraryIds": ""})
            api.refresh_library()
            for name in (*bulk_names, local_strm_name, mv_primary_name, mv_alt_name, incremental_name):
                api.wait_for_named_library_item_absent(name)
        except Exception:
            pass
    return result


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
    parser.add_argument("--scenario", choices=["suite", "discovery", "stop", "sharing", "scope", "failure"], default="suite")
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
        if args.scenario in {"suite", "sharing"}:
            summary["scenario_sharing"] = scenario_sharing(api, container, media_container)
        if args.scenario in {"suite", "scope"}:
            summary["scenario_scope"] = scenario_scope(api, container, media_container)
        if args.scenario in {"suite", "failure"}:
            summary["scenario_failure"] = scenario_failure(api, container)

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
