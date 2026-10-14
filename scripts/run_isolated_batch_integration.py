#!/usr/bin/env python3
"""Exercise the native batch check task against the repository's isolated Jellyfin instance.

The script only uses the repository's isolated Compose project, temporary hand-written STRM
fixtures and the local synthetic media service. It restores the task triggers, the plugin
configuration, the STRM fixtures and the Jellyfin item addresses in a finally block.

Scenarios:
  all      task discovery / no default trigger / manual run / trigger persistence / restart
  stop     real native stop of started probes with settlement before the next run
  sharing  batch and playback sharing one actually running same-source probe
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
MAX_WAIT_SECONDS = 120


def find_task(api: base.JellyfinApi) -> dict:
    tasks = base.request_json(api.base_url + "/ScheduledTasks", headers=api.headers, timeout=20)
    matches = [task for task in tasks if task.get("Name") == TASK_NAME]
    base.require(len(matches) == 1, f"Expected exactly one native task named {TASK_NAME!r}, found {len(matches)}.")
    return matches[0]


def task_state(api: base.JellyfinApi) -> dict:
    return find_task(api)


def wait_for_idle(api: base.JellyfinApi, timeout: int = MAX_WAIT_SECONDS) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = find_task(api)
        if str(task.get("State", "")).lower() in {"idle", "0"}:
            return task
        time.sleep(0.5)
    raise RuntimeError("The native batch task did not return to Idle before the timeout.")


def run_task(api: base.JellyfinApi, timeout: int = MAX_WAIT_SECONDS) -> dict:
    task = find_task(api)
    previous_start = (task.get("LastExecutionResult") or {}).get("StartTimeUtc")
    status, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="POST")
    base.require(status == 204, "Jellyfin did not accept the manual batch task start.")
    # Wait until the run is actually observed, then until it settles, so a fresh Idle state is never mistaken
    # for the finished run.
    deadline = time.monotonic() + timeout
    observed = False
    while time.monotonic() < deadline:
        current = find_task(api)
        result = current.get("LastExecutionResult") or {}
        if str(current.get("State", "")).lower() in {"running", "cancelling", "1", "2"} or result.get("StartTimeUtc") != previous_start:
            observed = True
        if observed and str(current.get("State", "")).lower() in {"idle", "0"}:
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


def latest_batch_summary(container: str) -> dict | None:
    lines = batch_events(container)
    return {"line": base.safe_event(lines[-1]) if lines else None, "count": len(lines)}


def task_summary_check(task: dict) -> dict:
    result = task.get("LastExecutionResult") or {}
    return {
        "state": task.get("State"),
        "status": result.get("Status"),
        "triggers": task.get("Triggers") or [],
    }


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


def slow_url(current_url: str, request_id: str) -> str:
    parts = urlsplit(current_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/slow/{request_id}/fixture.mp4", "", ""))


def scenario_all(api: base.JellyfinApi, container: str) -> dict[str, object]:
    task = find_task(api)
    base.require(not task.get("Triggers"), f"A fresh install must have no default trigger: {task.get('Triggers')}.")
    manual = run_task(api)
    summary = latest_batch_summary(container)
    base.require(summary["count"] >= 1, "The manual batch run produced no summary event.")
    base.require(str(manual.get("LastExecutionResult", {}).get("Status", "")).lower() in {"completed", "0"}, "The manual batch run did not complete.")

    # Administrator-set trigger persists across a real restart; clearing it restores the default.
    task_id = task["Id"]
    trigger = {"Type": "DailyTrigger", "TimeOfDayTicks": 36000000000}
    status = set_triggers(api, task_id, [trigger])
    base.require(status == 204, "Jellyfin did not accept the administrator trigger.")
    container = base.restart_isolated_server()
    api = base.JellyfinApi()
    after_restart = find_task(api)
    base.require(len(after_restart.get("Triggers") or []) == 1, "The administrator trigger did not persist across a real restart.")
    cleared = set_triggers(api, task_id, [])
    base.require(cleared == 204, "Jellyfin did not accept clearing the trigger.")
    container = base.restart_isolated_server()
    api = base.JellyfinApi()
    restored = find_task(api)
    base.require(not restored.get("Triggers"), "The cleared trigger was not restored to the empty default after restart.")

    # A changed supported STRM is probed and committed by the batch, and a second run skips it.
    name = "Batch Change Control " + uuid.uuid4().hex[:10]
    url = "http://media:8080/fixture.mp4"
    media = (ROOT / "artifacts" / "dev-env" / "media" / "fixture.mp4").read_bytes()
    sha1 = hashlib.sha1(media).hexdigest()
    path = temporary_fixture(name, url, sha1, len(media))
    try:
        api.refresh_library()
        item = api.wait_for_named_library_item(name)
        run_task(api)
        first = fingerprint_row(item["Id"])
        base.require(first is not None, "The batch did not create a first-trust fingerprint for the new STRM.")
        changed_url = base.unique_query_url(url, "batch-change-" + uuid.uuid4().hex[:10])
        path.write_bytes(base.write_versioned_fixture(path.read_bytes(), changed_url, sha1, len(media)))
        run_task(api)
        changed = fingerprint_row(item["Id"])
        base.require(changed is not None and changed["url_hash"] == base.expected_url_hash(changed_url), "The batch did not commit the changed URL.")
        run_task(api)
        repeat = fingerprint_row(item["Id"])
        base.require(repeat == changed, "An unchanged accepted source was re-committed by a later batch run.")
        return {
            "task_id": task_id,
            "manual": task_summary_check(manual),
            "trigger_persisted_after_restart": True,
            "default_trigger_restored": True,
            "new_strm_first_trust": first,
            "changed_url_committed": changed,
            "repeat_run_unchanged": repeat == changed,
        }
    finally:
        path.unlink(missing_ok=True)
        try:
            api.refresh_library()
            api.wait_for_named_library_item_absent(name)
        except Exception:  # Cleanup failures are reported through the fixture restoration summary.
            pass


def scenario_stop(api: base.JellyfinApi, container: str, media_container: str) -> dict[str, object]:
    nonce = uuid.uuid4().hex[:8]
    names = [f"Batch Stop {index} {nonce}" for index in range(3)]
    paths: list[Path] = []
    slow_ids: dict[str, str] = {}
    result: dict[str, object] = {}
    try:
        media = (ROOT / "artifacts" / "dev-env" / "media" / "fixture.mp4").read_bytes()
        sha1 = hashlib.sha1(media).hexdigest()
        for name in names:
            slow_id = uuid.uuid4().hex
            slow_ids[name] = slow_id
            paths.append(temporary_fixture(name, slow_url("http://media:8080/fixture.mp4", slow_id), sha1, len(media)))
        api.refresh_library()
        items = {name: api.wait_for_named_library_item(name) for name in names}

        # Establish a baseline so the changed slow URL requires a real probe.
        run_task(api)
        for name, path in zip(names, paths):
            slow_id = uuid.uuid4().hex
            slow_ids[name] = slow_id
            path.write_bytes(base.write_versioned_fixture(path.read_bytes(), slow_url("http://media:8080/fixture.mp4", slow_id), sha1, len(media)))

        task = find_task(api)
        before_counts = base.media_request_counts(media_container)
        status, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="POST")
        base.require(status == 204, "Jellyfin did not accept the stop-scenario batch start.")

        # Wait until at least one probe from this run has actually started (the slow media request was reached).
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
        final = wait_for_idle(api, timeout=MAX_WAIT_SECONDS)
        status_value = str(final.get("LastExecutionResult", {}).get("Status", "")).lower()
        base.require(status_value in {"cancelled", "2"}, f"The stopped batch task did not record Cancelled: {status_value}.")

        # The actually started probes must have completed and committed, and the next run must succeed.
        committed = [name for name in names if fingerprint_row(items[name]["Id"]) is not None]
        base.require(len(committed) >= 1, "No actually started probe settled after the native stop.")
        after_stop_counts = base.media_request_counts(media_container)
        run_task(api)
        return {
            "stop_http_status": stop_status,
            "task_status": status_value,
            "slow_requests_started_before_stop": started,
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
        except Exception:  # Cleanup failures are reported through the fixture restoration summary.
            pass


def scenario_sharing(api: base.JellyfinApi, container: str, media_container: str) -> dict[str, object]:
    nonce = uuid.uuid4().hex[:8]
    name = f"Batch Share {nonce}"
    path = ROOT / "artifacts" / "dev-env" / "strm" / (name + ".strm")
    try:
        media = (ROOT / "artifacts" / "dev-env" / "media" / "fixture.mp4").read_bytes()
        sha1 = hashlib.sha1(media).hexdigest()
        request_id = uuid.uuid4().hex
        plain_url = "http://media:8080/fixture.mp4"
        target_url = slow_url(plain_url, request_id)
        with path.open("xb") as fixture:
            fixture.write(base.write_versioned_fixture(FIXTURE.read_bytes(), plain_url, sha1, len(media)))
        api.refresh_library()
        item = api.wait_for_named_library_item(name)
        run_task(api)  # baseline first trust on the plain URL

        # Change the URL to the slow URL so the batch must probe; keep the trusted baseline in place.
        path.write_bytes(base.write_versioned_fixture(path.read_bytes(), target_url, sha1, len(media)))

        before_events = base.plugin_events(container, item["Id"])
        before_counts = base.media_request_counts(media_container)
        task = find_task(api)
        status, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="POST")
        base.require(status == 204, "Jellyfin did not accept the sharing-scenario batch start.")

        # Wait for the batch probe to actually reach the slow media request, then play the same source.
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if base.media_request_counts(media_container)["slow_requests_started"] > before_counts["slow_requests_started"]:
                break
            time.sleep(0.2)
        playback_holder: dict[str, object] = {}

        def playback() -> None:
            try:
                playback_holder["result"] = base.call_playback(api, container, item["Id"], target_url)
            except Exception as error:  # Retain thread failures for the owning assertion.
                playback_holder["error"] = type(error).__name__

        worker = threading.Thread(target=playback, name="isolated-batch-share", daemon=True)
        worker.start()
        worker.join(timeout=120)
        base.require(not worker.is_alive(), "The sharing-scenario playback did not finish.")
        base.require("error" not in playback_holder, "The sharing-scenario playback failed outside the HTTP path.")
        final = wait_for_idle(api, timeout=MAX_WAIT_SECONDS)
        after_events = base.plugin_events(container, item["Id"])
        events = [base.safe_event(line) for line in base.event_delta(before_events, after_events)]
        starts = [event for event in events if "probe started" in str(event)]
        after_counts = base.media_request_counts(media_container)
        slow_delta = after_counts["slow_requests_started"] - before_counts["slow_requests_started"]
        base.require(slow_delta == 1, f"The batch and playback must share one actually running probe, observed {slow_delta} slow probe requests.")
        return {
            "task_status": str(final.get("LastExecutionResult", {}).get("Status", "")).lower(),
            "probe_starts": len(starts),
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
    parser.add_argument("--scenario", choices=["all", "stop", "sharing"], default="all")
    args = parser.parse_args()

    base.require(FIXTURE.is_file(), "The isolated STRM fixture is missing.")
    original = FIXTURE.read_bytes()
    api: base.JellyfinApi | None = None
    container: str | None = None
    media_container: str | None = None
    fixture_item_id: str | None = None
    summary: dict[str, object] = {"fixture_restoration": "not needed"}
    exit_code = 1
    try:
        summary["deployment"] = base.deploy_plugin()
        container = base.restart_isolated_server()
        api = base.JellyfinApi()
        base.require(api.public_info().get("Version") == "12.2.0", "The active isolated Jellyfin version is not 12.2.0.")
        summary["plugin_status"] = api.plugin_status()
        media_container = base.isolated_media_container_name()
        try:
            fixture_item_id = api.fixture_item()["Id"]
        except RuntimeError:
            fixture_item_id = None

        if args.scenario == "all":
            summary["scenario_all"] = scenario_all(api, container)
        elif args.scenario == "stop":
            summary["scenario_stop"] = scenario_stop(api, container, media_container)
        else:
            summary["scenario_sharing"] = scenario_sharing(api, container, media_container)

        summary["status"] = "PASS"
        exit_code = 0
    finally:
        summary["fixture_restoration"] = restore_fixture(fixture_item_id, original)
        if exit_code == 0 and summary["fixture_restoration"] != "fixture restored and Jellyfin address synchronized":
            summary["status"] = "FAIL"
            summary["error"] = "The isolated STRM fixture could not be restored and verified."
            exit_code = 1
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, json.JSONDecodeError, base.subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
