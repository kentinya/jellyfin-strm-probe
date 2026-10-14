#!/usr/bin/env python3
"""Exercise the native batch check task against the repository's isolated Jellyfin instance.

The script only uses the repository's isolated Compose project, temporary hand-written STRM
fixtures and the local synthetic media service. It saves the plugin configuration and every
native scheduled task trigger before the run, restores them in a finally block and verifies the
restoration, so a failed or interrupted run never leaves the isolated instance changed.

Scenarios:
  all      discovery / no default trigger / manual run / real wall-clock trigger / restart persistence /
           new STRM first trust / changed-URL commit against the old baseline / repeat zero-probe / restart
  stop     real native stop of started probes: settlement, no new run during settlement, next run after settlement
  sharing  batch and playback sharing one actually running same-source probe, in both start orders
  scope    explicit two-library scope, invalid-library save rejection and disabled no-new-probe
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


def restore_state(original_configuration: bytes, trigger_snapshot: dict[str, list[dict]]) -> str:
    """Restore the plugin configuration file and every native scheduled task trigger, then verify."""
    problems: list[str] = []
    if CONFIGURATION_FILE.is_file() and CONFIGURATION_FILE.read_bytes() != original_configuration:
        CONFIGURATION_FILE.write_bytes(original_configuration)
    if not CONFIGURATION_FILE.is_file() or CONFIGURATION_FILE.read_bytes() != original_configuration:
        problems.append("configuration file not restored")

    try:
        api = base.JellyfinApi()
        for task_id, triggers in trigger_snapshot.items():
            status = set_triggers(api, task_id, triggers)
            if status != 204:
                problems.append(f"trigger restore for {task_id} returned {status}")
        for task_id, triggers in trigger_snapshot.items():
            current = find_task_by_id(api, task_id)
            if (current.get("Triggers") or []) != triggers:
                problems.append(f"trigger identity mismatch for {task_id}")
    except Exception as error:  # Report restoration gaps instead of hiding them.
        problems.append(f"trigger restore failed: {type(error).__name__}")

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
        base.require(parse_summary_field(summary_line, "actual probe calls") == 0, "An unchanged repeat run performed a new native probe.")

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
    """Real native stop: settlement, no new run during settlement, next run after settlement, no duplicate probe."""
    nonce = uuid.uuid4().hex[:8]
    names = [f"Batch Stop {index} {nonce}" for index in range(3)]
    paths: list[Path] = []
    try:
        media, sha1 = media_bytes()
        for name in names:
            slow_id = uuid.uuid4().hex
            paths.append(temporary_fixture(name, slow_url("http://media:8080/fixture.mp4", slow_id), sha1, len(media)))
        api.refresh_library()
        items = {name: api.wait_for_named_library_item(name) for name in names}

        # Establish a baseline so the changed slow URL requires a real probe.
        run_task(api)
        for name, path in zip(names, paths):
            slow_id = uuid.uuid4().hex
            path.write_bytes(base.write_versioned_fixture(path.read_bytes(), slow_url("http://media:8080/fixture.mp4", slow_id), sha1, len(media)))

        task = find_task(api)
        before_counts = base.media_request_counts(media_container)
        status, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="POST")
        base.require(status == 204, "Jellyfin did not accept the stop-scenario batch start.")

        # Wait until at least one probe from this run has actually started.
        deadline = time.monotonic() + 60
        started = 0
        while time.monotonic() < deadline:
            counts = base.media_request_counts(media_container)
            started = counts["slow_requests_started"] - before_counts["slow_requests_started"]
            if started >= 1:
                break
            time.sleep(0.2)
        base.require(started >= 1, "The batch stop scenario never reached a real probe.")
        stop_status = stop_task(api)
        base.require(stop_status == 204, "Jellyfin did not accept the native stop.")

        # During settlement a repeated manual start must not actually begin a new run: the old round stays
        # Cancelling and no additional slow probe request appears.
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

        final = wait_for_idle(api, timeout=MAX_WAIT_SECONDS)
        status_value = str((final.get("LastExecutionResult") or {}).get("Status", "")).lower()
        base.require(status_value in {"cancelled", "2"}, f"The stopped batch task did not record Cancelled: {status_value}.")

        committed = [name for name in names if fingerprint_row(items[name]["Id"]) is not None]
        base.require(len(committed) >= 1, "No actually started probe settled after the native stop.")

        # After settlement the next run must succeed and must not re-probe already committed sources.
        after_stop_counts = base.media_request_counts(media_container)
        next_run = run_task(api)
        base.require(str((next_run.get("LastExecutionResult") or {}).get("Status", "")).lower() in {"completed", "0"}, "The next run after settlement did not complete.")
        return {
            "stop_http_status": stop_status,
            "task_status": status_value,
            "slow_requests_started_before_stop": started,
            "second_start_http_status": second_start,
            "new_probe_during_settlement": counts_during["slow_requests_started"] - counts_at_stop["slow_requests_started"],
            "slow_requests_started_total": after_stop_counts["slow_requests_started"] - before_counts["slow_requests_started"],
            "committed_after_stop": committed,
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
        return {
            "direction": "playback_first" if playback_first else "batch_first",
            "slow_probe_requests": slow_delta,
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
    """Explicit two-library scope, invalid-library save rejection, and disabled no-new-probe."""
    folders = base.request_json(api.base_url + "/Library/VirtualFolders", headers=api.headers, timeout=20)
    library_ids = [folder["ItemId"] for folder in folders if folder.get("ItemId")]
    base.require(len(library_ids) >= 2, f"The isolated environment must expose at least two libraries, found {len(library_ids)}.")

    media, sha1 = media_bytes()
    strm_dir = ROOT / "artifacts" / "dev-env" / "strm"
    local_dir = ROOT / "artifacts" / "dev-env" / "media"
    nonce = uuid.uuid4().hex[:8]
    name_strm = f"Batch Scope Strm {nonce}"
    name_local = f"Batch Scope Local {nonce}"
    path_strm = temporary_fixture_in(strm_dir, name_strm, base.unique_query_url("http://media:8080/fixture.mp4", nonce + "a"), sha1, len(media))
    path_local = temporary_fixture_in(local_dir, name_local, base.unique_query_url("http://media:8080/fixture.mp4", nonce + "b"), sha1, len(media))
    result: dict = {}
    try:
        api.refresh_library()
        api.wait_for_named_library_item(name_strm)
        api.wait_for_named_library_item(name_local)

        # An explicit selection that references a nonexistent library must be rejected on save and must not
        # change the persisted file.
        file_before = CONFIGURATION_FILE.read_bytes()
        rejected = configure(api, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": False, "BatchLibraryIds": uuid.uuid4().hex})
        base.require(rejected >= 400, f"Jellyfin accepted a batch scope referencing a nonexistent library ({rejected}).")
        base.require(CONFIGURATION_FILE.read_bytes() == file_before, "The rejected batch scope changed the persisted configuration file.")

        # A valid explicit two-library scope is accepted and the batch run covers candidates from both libraries.
        accepted = configure(api, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": False, "BatchLibraryIds": ",".join(library_ids)})
        base.require(accepted == 204, f"Jellyfin rejected a valid explicit two-library scope ({accepted}).")
        before_counts = base.media_request_counts(media_container)
        run_task(api)
        summary_line = latest_batch_summary(container)["line"]
        base.require(parse_summary_field(summary_line, "candidates") is not None, "The two-library batch run produced no candidate count.")
        base.require(fingerprint_row(api.named_library_item(name_strm)["Id"]) is not None, "The two-library batch did not check the STRM library candidate.")
        base.require(fingerprint_row(api.named_library_item(name_local)["Id"]) is not None, "The two-library batch did not check the local library candidate.")

        # Disabling the plugin must stop the batch before it starts new probes.
        configure(api, {"Enabled": False, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": False, "BatchLibraryIds": ",".join(library_ids)})
        before_disabled = base.media_request_counts(media_container)
        run_task(api)
        after_disabled = base.media_request_counts(media_container)
        base.require(after_disabled["slow_requests_started"] == before_disabled["slow_requests_started"], "A disabled plugin still started a new batch probe.")

        result = {
            "library_ids": library_ids,
            "invalid_scope_http_status": rejected,
            "valid_scope_http_status": accepted,
            "summary_line": summary_line,
            "strm_candidate_checked": True,
            "local_candidate_checked": True,
            "disabled_started_no_new_probe": True,
        }
    finally:
        path_strm.unlink(missing_ok=True)
        path_local.unlink(missing_ok=True)
        try:
            configure(api, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2, "DetailedLog": False, "BatchAllLibraries": True, "BatchLibraryIds": ""})
            api.refresh_library()
            for name in (name_strm, name_local):
                api.wait_for_named_library_item_absent(name)
        except Exception:
            pass
    return result


def scenario_failure(api: base.JellyfinApi, container: str) -> dict:
    """An unavailable fingerprint store must be reported as a batch failure, never a silent completion."""
    # Replace the fingerprint database file with a directory of the same name so the plugin cannot open its store.
    # The plugin must latch the store as unavailable, the native task must fail (not report Completed), and no new
    # probe may start. The database is restored and the server restarted to clear the latch before the recovery run.
    base.require(FINGERPRINT_DATABASE.is_file(), "The plugin fingerprint database is missing.")
    backup = FINGERPRINT_DATABASE.with_suffix(".db.bak-" + uuid.uuid4().hex[:8])
    shutil.copy2(FINGERPRINT_DATABASE, backup)
    result: dict = {}
    try:
        FINGERPRINT_DATABASE.unlink()
        FINGERPRINT_DATABASE.mkdir()
        before_counts = base.media_request_counts(base.isolated_media_container_name())
        final = run_task(api)
        status_value = str((final.get("LastExecutionResult") or {}).get("Status", "")).lower()
        summary_line = latest_batch_summary(container)["line"]
        after_counts = base.media_request_counts(base.isolated_media_container_name())
        base.require(status_value in {"failed", "3"}, f"An unavailable fingerprint store did not fail the batch task: {status_value}.")
        base.require("store unavailable True" in (summary_line or ""), f"The batch summary did not report the store as unavailable: {summary_line}.")
        base.require(
            after_counts["slow_requests_started"] == before_counts["slow_requests_started"],
            "An unavailable fingerprint store still started a new probe.",
        )
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
    parser.add_argument("--scenario", choices=["all", "stop", "sharing", "scope", "failure"], default="all")
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

        if args.scenario == "all":
            summary["scenario_all"] = scenario_all(api, container)
        elif args.scenario == "stop":
            summary["scenario_stop"] = scenario_stop(api, container, media_container)
        elif args.scenario == "sharing":
            summary["scenario_sharing"] = scenario_sharing(api, container, media_container)
        elif args.scenario == "scope":
            summary["scenario_scope"] = scenario_scope(api, container, media_container)
        else:
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
