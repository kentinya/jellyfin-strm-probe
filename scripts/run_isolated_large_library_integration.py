#!/usr/bin/env python3
"""Reuse a stopped prepared STRM library for focused ZIP-installed validation.

The default path copies prepared data into a fresh run-owned workspace, never adopts
an old ownership token, and retains the copy after stopping its isolated services.
Focused results are PARTIAL, not full Task acceptance. Legacy full preparation is
available only with the explicit --fresh option; no live or production source is used.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import closing, contextmanager
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import package_environment as pe  # noqa: E402
import package_plugin as pp  # noqa: E402
import run_isolated_package_integration as pkg  # noqa: E402
import run_isolated_scan_integration as scan  # noqa: E402

ROOT = pe.ROOT
TASK_KEY = "StrmProbeOptimizerBatchCheck"
MAX_TASK_TIMEOUT = 6 * 60 * 60
POLL_SECONDS = 0.5
# A second, genuinely distinct MP4 (longer duration) generated with the pinned Jellyfin FFmpeg. It is the
# "synthetic media B" the controlled same-URL routes actually start serving after a change. It deliberately
# keeps the MP4 container of media A: a same-URL change that also switches container makes Jellyfin persist a
# primary stream whose identity does not match the encoder result, which is outside this Task's controlled
# content/Size change contract.
MEDIA_B_NAME = "large-media-b.mp4"
REQUIRED_SUMMARY_FIELDS = (
    "candidates", "raw_candidates", "duplicates", "checked", "skipped", "first_trust",
    "need_probe", "reliable_success", "probe_incomplete", "check_stage_incomplete",
    "not_processed", "missing", "revoked", "read_incomplete", "unread",
    "actual_probe_calls", "batch_reads", "candidate_fetch_ms", "candidate_fetch_allocated_bytes",
    "candidate_fetch_peak_bytes", "candidate_set_estimated_bytes",
    "candidate_set_measured_capacity_bytes", "candidate_set_retained_bytes",
    "batch_read_ms", "batch_read_allocated_bytes", "candidate_fetch_failed",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# While a retained-library reuse scenario runs, the tool intentionally rewrites a bounded set of
# copied STRM/media inputs (the controlled increment). The tracker records exactly those edits so the
# final input reconciliation can distinguish intended outputs from real corruption. It stays ``None``
# for the legacy fresh path, where all fixtures are new relative to an empty pre-run workspace.
_REUSE_EDIT_TRACKER: dict[str, dict[str, str]] | None = None


def note_owned_edit(path: Path) -> None:
    """Record a bounded, intentional copied-input edit while a reuse scenario is active."""
    if _REUSE_EDIT_TRACKER is None:
        return
    resolved = pe.require_owned_path(path)
    for area, root in (("strm", pe.WORK / "strm"), ("media", pe.WORK / "media")):
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError:
            continue
        _REUSE_EDIT_TRACKER.setdefault(area, {})[relative] = hashlib.sha256(resolved.read_bytes()).hexdigest()
        return


def canonical_guid(value: object, label: str) -> str:
    try:
        return uuid.UUID(str(value)).hex
    except (ValueError, TypeError, AttributeError) as error:
        raise RuntimeError(f"{label} is not a GUID") from error


def reconcile_candidate_identities(expected: list[str], actual: list[str]) -> dict[str, object]:
    """Require exact identity equality; equal counts cannot hide a duplicate and an omission."""
    expected_ids = [canonical_guid(item, "expected candidate") for item in expected]
    actual_ids = [canonical_guid(item, "observed candidate") for item in actual]
    if len(set(expected_ids)) != len(expected_ids):
        raise RuntimeError("The independent expected candidate list contains duplicate identities.")
    if len(set(actual_ids)) != len(actual_ids):
        raise RuntimeError("The native candidate list contains duplicate identities.")
    missing = sorted(set(expected_ids) - set(actual_ids))
    unexpected = sorted(set(actual_ids) - set(expected_ids))
    if missing or unexpected:
        raise RuntimeError(f"Candidate identities do not reconcile: missing={len(missing)} unexpected={len(unexpected)}.")
    return {"count": len(expected_ids), "identity_sha256": digest("\n".join(sorted(expected_ids))),
            "missing": 0, "unexpected": 0}


def require_complete_summary(line: str | None) -> dict[str, int | float | bool]:
    fields = scan.summary_fields_complete(line)
    missing = [name for name in REQUIRED_SUMMARY_FIELDS if name not in fields]
    require(not missing, f"The native batch summary is missing required counters: {missing}.")
    require(not fields["candidate_fetch_failed"], "The native candidate query failed.")
    require(fields["candidates"] == fields["raw_candidates"] - fields["duplicates"],
            "Candidate counters do not reconcile.")
    return fields


def validate_settlement(fields: dict[str, int | float | bool], expected_candidates: int,
                        expected_probe_calls: int, expected_first_trust: int | None = None) -> None:
    accounted = sum(int(fields[name]) for name in
                    ("checked", "not_processed", "missing", "revoked", "unread", "read_incomplete"))
    require(accounted == expected_candidates, f"Candidate settlement does not reconcile: {accounted}/{expected_candidates}.")
    require(fields["candidates"] == expected_candidates, "The run used the wrong fixed candidate count.")
    require(fields["actual_probe_calls"] == expected_probe_calls,
            f"Expected {expected_probe_calls} real plugin probes, got {fields['actual_probe_calls']}.")
    require(fields["actual_probe_calls"] == fields["reliable_success"] + fields["probe_incomplete"],
            "Actual probe calls do not reconcile with reliable success and incomplete probes.")
    require(fields["need_probe"] == fields["reliable_success"] + fields["probe_incomplete"],
            "Need-probe count does not reconcile with completed probe outcomes.")
    for name in ("missing", "revoked", "unread", "read_incomplete", "probe_incomplete",
                 "check_stage_incomplete"):
        require(fields[name] == 0, f"Normal round has incomplete work: {name}={fields[name]}.")
    for name in ("candidate_fetch_failed", "store_unavailable", "scope_unavailable", "disabled",
                 "stop_requested"):
        require(fields.get(name) is False, f"Normal round has an unexpected failure/stop flag: {name}.")
    if expected_first_trust is not None:
        require(fields["first_trust"] == expected_first_trust,
                f"Expected {expected_first_trust} first-trust sources, got {fields['first_trust']}.")
    for name in ("candidate_fetch_ms", "candidate_fetch_allocated_bytes", "candidate_fetch_peak_bytes",
                 "candidate_set_estimated_bytes", "candidate_set_measured_capacity_bytes",
                 "candidate_set_retained_bytes", "batch_read_ms", "batch_read_allocated_bytes", "batch_reads"):
        require(name in fields and fields[name] is not None, f"The settlement is missing the cost field {name}.")
        require(float(fields[name]) >= 0, f"The cost field {name} is negative.")


def system_profile() -> dict[str, object]:
    mem_total = None
    mem_available = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, raw = line.partition(":")
            if key in {"MemTotal", "MemAvailable"}:
                value = int(raw.strip().split()[0]) * 1024
                if key == "MemTotal":
                    mem_total = value
                else:
                    mem_available = value
    except (OSError, ValueError):
        pass
    usage = shutil.disk_usage(ROOT)
    stat = os.statvfs(ROOT)
    return {
        "platform": platform.platform(), "machine": platform.machine(),
        "cpu_count": os.cpu_count(), "memory_total_bytes": mem_total,
        "memory_available_bytes": mem_available, "root_disk_total_bytes": usage.total,
        "root_disk_free_bytes": usage.free, "root_inode_total": stat.f_files,
        "root_inode_free": stat.f_favail,
        "resource_policy": "Fail before publishing PASS on OOM, timeout, or evidence loss; no host tuning or container takeover.",
    }


def docker_stats(container_name: str) -> dict[str, object]:
    # One short exec per service avoids docker stats' multi-second measurement window.
    command = ("for f in memory.current memory.peak memory.max memory.events cpu.stat pids.current; do "
               "echo SECTION:$f; cat /sys/fs/cgroup/$f; done; "
               "echo SECTION:process; cat /proc/1/status; "
               "echo SECTION:handles; ls /proc/1/fd | wc -l")
    result = pe.run(*pe.DOCKER, "exec", container_name, "sh", "-c", command, timeout=20)
    require(result.returncode == 0, "Could not sample the owned container resources.")
    sections: dict[str, list[str]] = {}
    current = None
    for line in result.stdout.splitlines():
        if line.startswith("SECTION:"):
            current = line.partition(":")[2]
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    def number(name: str, *, optional: bool = False) -> int | None:
        raw = sections.get(name, [])
        if optional and not raw:
            return None
        require(len(raw) == 1 and raw[0].isdigit(), f"Missing numeric cgroup metric {name}.")
        return int(raw[0])
    process = {line.partition(":")[0]: line.partition(":")[2].strip()
               for line in sections.get("process", []) if ":" in line}
    require(all(name in process for name in ("VmRSS", "Threads")), "Missing process metrics.")
    events = dict(line.split() for line in sections.get("memory.events", []))
    cpu = dict(line.split() for line in sections.get("cpu.stat", []))
    require("oom" in events and "oom_kill" in events and "usage_usec" in cpu,
            "Missing cgroup CPU/OOM metrics.")
    return {"memory_bytes": number("memory.current"), "peak_bytes": number("memory.peak", optional=True),
            "limit_bytes": number("memory.max"), "processes": number("pids.current"),
            "rss_bytes": int(process["VmRSS"].split()[0]) * 1024,
            "threads": int(process["Threads"]), "handles": number("handles"),
            "cpu_usage_usec": int(cpu["usage_usec"]),
            "oom": int(events["oom"]), "oom_kill": int(events["oom_kill"])}


class RunBudget:
    """A fixed per-level safety budget, not a product performance SLA."""

    def __init__(self, host: dict, timeout: int) -> None:
        available = host.get("memory_available_bytes")
        require(isinstance(available, int) and available > 0, "Host memory cannot be observed.")
        self.deadline = time.monotonic() + timeout
        self.limits = {"jellyfin": {"cpus": min(4, host["cpu_count"] or 1),
                                     "mem_limit": int(available * 0.60)},
                       "media": {"cpus": min(2, host["cpu_count"] or 1),
                                  "mem_limit": int(available * 0.05)}}
        self.floors = {"memory_available_bytes": int(available * 0.20),
                       "root_disk_free_bytes": int(host["root_disk_free_bytes"] * 0.20),
                       "root_inode_free": int(host["root_inode_free"] * 0.20)}
        self.orchestrator_limit = int(available * 0.10)
        self.failure: str | None = None

    def check(self, host: dict | None = None, services: dict | None = None,
              orchestrator_rss: int | None = None) -> None:
        reason = self.failure
        if time.monotonic() >= self.deadline:
            reason = reason or "level_timeout"
        if host is not None:
            for key, floor in self.floors.items():
                if not isinstance(host.get(key), int) or host[key] < floor:
                    reason = reason or key
        for name, metrics in (services or {}).items():
            if (metrics["oom"] or metrics["oom_kill"]
                    or metrics["memory_bytes"] >= self.limits[name]["mem_limit"] * 0.95):
                reason = reason or name + "_resource_limit"
        if orchestrator_rss is not None and orchestrator_rss > self.orchestrator_limit:
            reason = reason or "orchestrator_rss"
        if reason:
            self.failure = reason
            raise RuntimeError("Run budget exceeded: " + reason)


class ResourceSampler:
    def __init__(self, container_name: str, recorder: scan.EvidenceRecorder,
                 budget: RunBudget | None = None) -> None:
        self.container_name = container_name
        self.recorder = recorder
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._sample, name="large-library-resource-sampler", daemon=True)
        self.failure: str | None = None
        self.lock = threading.Lock()
        self.budget = budget

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stopped.set()
        # Two bounded Docker observations can be in flight when teardown starts.
        self.thread.join(timeout=45)
        require(not self.thread.is_alive(), "Resource sampler did not stop cleanly.")
        require(self.failure is None, f"Resource sampling failed: {self.failure}.")

    @contextmanager
    def restart_gap(self):
        # Planned restarts are explicit gaps, not missing-container errors silently ignored.
        with self.lock:
            self.recorder.record("resource_sampling_gap_started", reason="planned_restart")
            try:
                yield
            finally:
                self.recorder.record("resource_sampling_gap_ended", reason="planned_restart")

    def sample_once(self) -> None:
        host = system_profile()
        started = time.monotonic()
        jellyfin = docker_stats(self.container_name)
        media = docker_stats(pe.container_name("media"))
        rss = next(int(line.split()[1]) * 1024 for line in Path("/proc/self/status").read_text().splitlines()
                   if line.startswith("VmRSS:"))
        self.recorder.record("resource_sample", docker_stats=jellyfin, media_stats=media,
                             host_memory=host["memory_available_bytes"],
                             disk_free_bytes=host["root_disk_free_bytes"],
                             inode_free=host["root_inode_free"], orchestrator_rss_bytes=rss,
                             sample_duration_seconds=time.monotonic() - started)
        if self.budget is not None:
            self.budget.check(host, {"jellyfin": jellyfin, "media": media}, rss)

    def _sample(self) -> None:
        while not self.stopped.wait(1):
            with self.lock:
                if self.stopped.is_set():
                    break
                try:
                    self.sample_once()
                except Exception as error:  # Sampling failures must not become a clean run.
                    self.failure = type(error).__name__
                    if self.budget is not None:
                        self.budget.failure = self.budget.failure or "resource_sampling_failed"
                    self.recorder.record("resource_sampling_failed", error=self.failure)
                    self.stopped.set()


def sampled_restart(sampler: ResourceSampler) -> None:
    with sampler.restart_gap():
        scan.restart()


def container_identity(name: str) -> dict[str, object]:
    result = pe.run(*pe.DOCKER, "inspect", name, timeout=20)
    require(result.returncode == 0, "Could not inspect the owned package container.")
    item = json.loads(result.stdout)[0]
    mounts = [{"destination": mount.get("Destination"), "source_sha256": digest(str(mount.get("Source", ""))),
               "read_only": not bool(mount.get("RW"))} for mount in item.get("Mounts", [])]
    return {"container_id": item.get("Id"), "image": item.get("Config", {}).get("Image"),
            "started_at": item.get("State", {}).get("StartedAt"), "mounts": mounts}


def current_task(auth: str) -> dict:
    tasks = scan.task_list(auth)
    matches = [task for task in tasks if task.get("Key") == TASK_KEY]
    require(len(matches) == 1, f"Expected one native batch task with key {TASK_KEY}.")
    return matches[0]


def run_query_stage_stop(auth: str, recorder: scan.EvidenceRecorder, container_name: str,
                         timeout: int) -> dict:
    """Start the native batch and stop it during the real synchronous candidate query.

    The query window is short (tens to a few hundred milliseconds), so a background watcher reads only new log
    lines and issues the native stop the moment the query-start marker appears, before any object read begins. It
    injects no test wait, cancellation source or query change; it only observes the existing redacted diagnostics.
    """
    task = current_task(auth)
    previous = scan.last_start(task)
    started = scan.now_utc()
    follower = DockerLogFollower(container_name, started)
    state: dict[str, object] = {"query_started_utc": None, "read_started": False,
                                "stop_status": None, "stop_requested_utc": None,
                                "stop_acknowledged_utc": None}
    lock = threading.Lock()
    stop_flag = threading.Event()

    def watcher() -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not stop_flag.is_set():
            lines = current_round_log_lines(follower.drain(), started)
            if any("STRM_BATCH_OBJECT_READ_STARTED" in line for line in lines):
                state["read_started"] = True
            if not stop_flag.is_set() and any("STRM_BATCH_CANDIDATE_QUERY_STARTED LibraryId " in line
                                             for line in lines):
                with lock:
                    if stop_flag.is_set():
                        continue
                    state["query_started_utc"] = scan.now_utc().isoformat()
                    state["stop_requested_utc"] = scan.now_utc().isoformat()
                    try:
                        status = scan.stop_task(auth, task["Id"])
                    except Exception as error:  # noqa: BLE001 - recorded, never fatal
                        state["stop_status"] = f"error:{type(error).__name__}"
                    else:
                        state["stop_status"] = status
                        state["stop_acknowledged_utc"] = scan.now_utc().isoformat()
                    stop_flag.set()
            time.sleep(0.005)

    watcher_thread = threading.Thread(target=watcher, name="query-stage-stop-watcher", daemon=True)
    try:
        watcher_thread.start()
        status = scan.start_task(auth, task["Id"])
        require(status == 204, f"Jellyfin rejected the native batch start ({status}).")
        recorder.record("batch_task_started", task_key=TASK_KEY, task_id=task["Id"], started_utc=started)
        deadline = time.monotonic() + timeout
        saw_run = False
        progress: list[float] = []
        while time.monotonic() < deadline:
            observed = current_task(auth)
            task_state = scan.task_state_name(observed)
            result = scan.task_result(observed)
            if task_state in {"running", "cancelling", "1", "2"} or scan.last_start(observed) != previous:
                saw_run = True
            raw_progress = observed.get("CurrentProgressPercentage")
            if raw_progress is not None:
                progress.append(float(raw_progress))
            if saw_run and task_state in {"idle", "0"} and result:
                stop_flag.set()
                watcher_thread.join(timeout=5)
                return {"task": observed, "result": result, "start_time_previous": previous,
                        "stopped": state["stop_status"] == 204, "progress": progress,
                        "started_utc": started, "ended_utc": scan.now_utc(), **state}
            time.sleep(0.05)
        raise RuntimeError("The native batch task exceeded the fixed run timeout during the query-stage stop.")
    finally:
        stop_flag.set()
        watcher_thread.join(timeout=5)
        follower.close()


def query_stop_observed(execution: dict, events: list[dict]) -> bool:
    """Count only an acknowledged stop inside a recorded native per-library query."""
    if (execution.get("stopped") is not True or execution.get("read_started") is True
            or scan.task_status(execution.get("task", {})) not in {"cancelled", "1"}
            or any(value != 0 for value in execution.get("progress", []))
            or any(event["kind"] in {"OBJECT_READ_STARTED", "CANDIDATE_ID"} for event in events)):
        return False
    try:
        requested = dt.datetime.fromisoformat(execution["stop_requested_utc"])
        acknowledged = dt.datetime.fromisoformat(execution["stop_acknowledged_utc"])
        entered: dict[str, dt.datetime] = {}
        for event in events:
            library = re.search(r"LibraryId ([0-9a-fA-F-]{32,36})", event.get("redacted_line", ""))
            if library is None:
                continue
            instant = dt.datetime.fromisoformat(event["timestamp"])
            if event["kind"] == "CANDIDATE_QUERY_STARTED":
                entered[library.group(1)] = instant
            elif event["kind"] == "CANDIDATE_QUERY_RETURNED" and library.group(1) in entered:
                if entered[library.group(1)] <= requested <= acknowledged < instant:
                    return True
    except (KeyError, TypeError, ValueError):
        return False
    return False


def overall_acceptance_status(required_stages: dict[str, bool]) -> tuple[str, int]:
    """Map required-stage outcomes to the overall acceptance status and process exit code.

    A required stage that is not satisfied (for example the real in-query stop was never observed) must fail
    closed: the run cannot report an overall PASS or exit 0 even when every other observation succeeded. The
    attempt evidence and cleanup are still recorded by the caller.
    """
    unmet = sorted(name for name, satisfied in required_stages.items() if not satisfied)
    if unmet:
        return "FAIL", 1
    return "PASS", 0


def run_query_stage_stop_attempts(perform_attempt: Callable[[], tuple[dict, list[dict]]],
                                  max_attempts: int = 3) -> dict[str, object]:
    """Run the natural in-query stop attempts and return the observed stage plus every attempt's evidence.

    Each attempt records its own start instant, execution and phase events so an unobserved attempt is kept
    rather than overwritten. ``observed`` is only true when a real in-query stop was seen; an unobserved stage
    is left for the caller to fail the overall acceptance result closed.
    """
    attempts: list[dict[str, object]] = []
    stage_stop: dict | None = None
    stage_events: list[dict] = []
    observed = False
    for index in range(max_attempts):
        attempt_started = scan.now_utc()
        stop, events = perform_attempt()
        attempt_observed = query_stop_observed(stop, events)
        attempts.append({"attempt": index + 1, "started_utc": attempt_started.isoformat(),
                         "observed": attempt_observed,
                         "query_started_utc": stop.get("query_started_utc"),
                         "stop_requested_utc": stop.get("stop_requested_utc"),
                         "stop_acknowledged_utc": stop.get("stop_acknowledged_utc"),
                         "stop_status": stop.get("stop_status"),
                         "object_read_started": any(
                             event["kind"] == "OBJECT_READ_STARTED" for event in events),
                         "execution": stop, "events": events})
        if attempt_observed:
            observed = True
            stage_stop = stop
            stage_events = events
            break
    return {"observed": observed, "attempts": attempts, "stop": stage_stop, "events": stage_events}


def run_task(auth: str, recorder: scan.EvidenceRecorder, timeout: int = MAX_TASK_TIMEOUT,
             *, stop_after: Callable[[dict, dict], bool] | None = None,
             on_stop: Callable[[dict], None] | None = None,
             poll_seconds: float = POLL_SECONDS) -> dict:
    task = current_task(auth)
    previous = scan.last_start(task)
    started = scan.now_utc()
    status = scan.start_task(auth, task["Id"])
    require(status == 204, f"Jellyfin rejected the native batch start ({status}).")
    recorder.record("batch_task_started", task_key=TASK_KEY, task_id=task["Id"], started_utc=started)
    deadline = time.monotonic() + timeout
    saw_run = False
    stopped = False
    progress: list[float] = []
    while time.monotonic() < deadline:
        observed = current_task(auth)
        state = scan.task_state_name(observed)
        result = scan.task_result(observed)
        if state in {"running", "cancelling", "1", "2"} or scan.last_start(observed) != previous:
            saw_run = True
        raw_progress = observed.get("CurrentProgressPercentage")
        if raw_progress is not None:
            progress.append(float(raw_progress))
        if stop_after is not None and not stopped and stop_after(observed, result):
            stop_status = scan.stop_task(auth, observed["Id"])
            require(stop_status == 204, f"Jellyfin rejected the native stop ({stop_status}).")
            recorder.record("batch_stop_requested", status=stop_status, state=state,
                            progress=raw_progress, result=result)
            stopped = True
            if on_stop is not None:
                on_stop(observed)
        if saw_run and state in {"idle", "0"} and result:
            final = {"task": observed, "result": result, "start_time_previous": previous,
                     "stopped": stopped, "progress": progress,
                     "started_utc": started, "ended_utc": scan.now_utc()}
            recorder.record("batch_task_settled", state=state, result=result, stopped=stopped,
                            progress=progress, started_utc=started, ended_utc=final["ended_utc"])
            return final
        time.sleep(poll_seconds)
    raise RuntimeError("The native batch task exceeded the fixed run timeout.")


def full_docker_log(container_name: str, since: dt.datetime | None = None) -> list[str]:
    """Read the complete log stream (optionally from a UTC instant). A fixed --tail would drop the
    round summary or phase marker once 3000 candidates emit per-candidate identity lines across many rounds."""
    args = [*pe.DOCKER, "logs", "--timestamps"]
    if since is not None:
        args += ["--since", str(since.timestamp())]
    result = pe.run(*args, container_name, timeout=120)
    require(result.returncode == 0, "Could not read the full owned Jellyfin log stream.")
    return (result.stdout + result.stderr).splitlines()


class LogTail:
    """Incrementally read only new container log lines so a fast stop poll never re-reads the whole log.

    A look-back overlap plus a global seen-set keeps the read cheap while guaranteeing no line is missed
    between the moment ``docker logs`` returns and the moment the next ``--since`` cursor is chosen.
    """

    def __init__(self, container_name: str, start: dt.datetime) -> None:
        self.container = container_name
        self.since = start.timestamp() - 2.0
        self.seen: set[str] = set()

    def poll(self) -> list[str]:
        result = pe.run(*pe.DOCKER, "logs", "--timestamps", "--since", f"{self.since:.6f}",
                        self.container, timeout=60)
        require(result.returncode == 0, "Could not read the incremental owned Jellyfin log stream.")
        lines = self._dedupe((result.stdout + result.stderr).splitlines())
        self.since = time.time() - 2.0
        return lines

    def _dedupe(self, lines: list[str]) -> list[str]:
        fresh: list[str] = []
        for line in lines:
            key = digest(line)
            if key in self.seen:
                continue
            self.seen.add(key)
            fresh.append(line)
        return fresh


class DockerLogFollower:
    """Stream new container log lines with low latency so a stop can be issued during the short,
    synchronous candidate query.

    The real query window is only tens to a few hundred milliseconds; re-spawning ``docker logs --since``
    every poll adds that process's start-up cost and misses the window. A single follow process reads the
    existing redacted diagnostics as they are written and injects no test wait, cancellation source or
    native-query change. The initial look-back is filtered per attempt by ``current_round_log_lines``.
    """

    def __init__(self, container_name: str, since: dt.datetime,
                 *, popen: Callable[..., object] | None = None) -> None:
        self.container = container_name
        self._lines: list[str] = []
        self._lock = threading.Lock()
        args = [*pe.DOCKER, "logs", "--follow", "--timestamps",
                "--since", f"{since.timestamp() - 2.0:.6f}", container_name]
        self._process = (popen or subprocess.Popen)(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=ROOT)
        self._thread = threading.Thread(target=self._read, name="docker-log-follower", daemon=True)
        self._thread.start()

    def _read(self) -> None:
        stream = getattr(self._process, "stdout", None)
        if stream is None:
            return
        # ``readline`` returns each line as soon as it is flushed; iterating the file object directly can
        # block on an internal read-ahead buffer and miss the short synchronous query window.
        while True:
            line = stream.readline()
            if not line:
                break
            with self._lock:
                self._lines.append(line.rstrip("\n"))

    def drain(self) -> list[str]:
        with self._lock:
            lines, self._lines = self._lines, []
        return lines

    def close(self) -> None:
        try:
            self._process.terminate()
        except Exception:  # noqa: BLE001 - a dead follow process is not fatal
            pass
        try:
            self._process.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                self._process.kill()
            except Exception:  # noqa: BLE001
                pass
        self._thread.join(timeout=5)


def current_round_log_lines(lines: list[str], started: dt.datetime) -> list[str]:
    """Discard overlap lines from before this task attempt started."""
    current: list[str] = []
    for line in lines:
        timestamp = scan.parse_docker_timestamp(line)
        if timestamp is not None and timestamp >= started:
            current.append(line)
    return current


def probe_starts_since(container_name: str, since: dt.datetime) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for line in full_docker_log(container_name, since):
        if "Native STRM probe started" not in line:
            continue
        timestamp = scan.parse_docker_timestamp(line)
        item = re.search(r"probe started for item ([0-9a-fA-F-]+)", line)
        source = re.search(r"source_key ([0-9a-fA-F-]+)", line)
        running = re.search(r"running probes (\d+)", line)
        if timestamp is None or timestamp < since or not (item and running):
            continue
        entries.append({"item_id": canonical_guid(item.group(1), "probe item"),
                        "source_key": canonical_guid(source.group(1), "probe source") if source else None,
                        "running": int(running.group(1)), "timestamp": timestamp})
    return entries


def parse_probe_start_line(line: str) -> dict[str, object] | None:
    if "Native STRM probe started" not in line:
        return None
    item = re.search(r"probe started for item ([0-9a-fA-F-]+)", line)
    source = re.search(r"source_key ([0-9a-fA-F-]+)", line)
    running = re.search(r"running probes (\d+)", line)
    if not (item and running):
        return None
    return {"item_id": canonical_guid(item.group(1), "probe item"),
            "source_key": canonical_guid(source.group(1), "probe source") if source else None,
            "running": int(running.group(1))}


def latest_summary_since(container_name: str, since: dt.datetime) -> str | None:
    latest = None
    for line in full_docker_log(container_name, since):
        if "STRM media information check finished" not in line:
            continue
        timestamp = scan.parse_docker_timestamp(line)
        if timestamp is not None and timestamp >= since:
            latest = scan.batch.base.safe_event(line)
    return latest


def batch_log_events(container: str, since: dt.datetime) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in full_docker_log(container, since):
        if "STRM_BATCH_" not in line:
            continue
        timestamp = scan.parse_docker_timestamp(line)
        if timestamp is None or timestamp < since:
            continue
        marker = line.split("STRM_BATCH_", 1)[1].split(" ", 1)[0]
        event: dict[str, object] = {"timestamp": timestamp.isoformat(), "kind": marker,
                                    "line_sha256": digest(line), "redacted_line": scan.redact_log_text(line)}
        offset = re.search(r"CandidateOffset\s*[:=]\s*(\d+)", line)
        candidate_id = re.search(r"STRM_BATCH_CANDIDATE_ID\s+([0-9a-fA-F-]{32,36})", line)
        if offset:
            event["candidate_offset"] = int(offset.group(1))
        if candidate_id:
            event["candidate_id"] = canonical_guid(candidate_id.group(1), "logged candidate")
        events.append(event)
    return events


def plugin_probe_count(container: str, since: dt.datetime) -> int:
    return len(probe_starts_since(container, since))


def file_source_id(item: dict, label: str) -> str:
    sources = [source for source in item.get("MediaSources", []) if source.get("Id")]
    require(len(sources) == 1, f"{label} must resolve to exactly one physical source.")
    return canonical_guid(sources[0]["Id"], label)


def fingerprint_map(allow_missing: bool = False) -> dict[tuple[str, str], dict[str, object]]:
    if allow_missing and not pkg.fingerprint_database().is_file():
        # The SQLite store is created lazily on first write, so before the first trust round the database
        # legitimately does not exist yet and the expected row set is empty.
        return {}
    rows = scan.all_fingerprint_rows()
    result = {}
    for row in rows:
        key = (canonical_guid(row["item_id"], "fingerprint item id"),
               canonical_guid(row["source_key"], "fingerprint source key"))
        require(key not in result, "The fingerprint database contains duplicate project/source rows.")
        require(set(row) == {"item_id", "source_key", "url_hash", "sha1", "file_size"},
                "The fingerprint row does not contain exactly the documented five fields.")
        result[key] = row
    return result


def expected_row(item: dict, source_key: str, manifest_path: Path) -> dict[str, object]:
    manifest = scan.read_versioned_manifest(manifest_path)
    require(manifest is not None, "A fixture manifest is missing or invalid.")
    sha1 = manifest["sha1"]
    return {"item_id": canonical_guid(item["Id"], "expected item id"),
            "source_key": canonical_guid(source_key, "expected source key"),
            "url_hash": manifest["url_hash"], "sha1": sha1, "file_size": manifest["file_size"]}


def reconcile_rows(expected: dict[tuple[str, str], dict], actual: dict[tuple[str, str], dict]) -> dict[str, object]:
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    mismatched = sorted(key for key in set(expected) & set(actual) if expected[key] != actual[key])
    require(not missing and not unexpected and not mismatched,
            f"Fingerprint rows do not reconcile: missing={len(missing)} unexpected={len(unexpected)} mismatched={len(mismatched)}.")
    identity = "\n".join(f"{key[0]}:{key[1]}:{expected[key]['url_hash']}:{expected[key]['sha1']}:{expected[key]['file_size']}"
                         for key in sorted(expected))
    return {"rows": len(expected), "identity_sha256": digest(identity), "missing": 0,
            "unexpected": 0, "mismatched": 0}


def paged_native_items(auth: str, extra: dict[str, str],
                       fields: str = "MediaSources,Path,MediaStreams,DateModified", page: int = 500) -> list[dict]:
    """Read every native item through the real paged query; a fixed 5000 limit cannot hold 3000 candidates.

    A concurrent login with the same device identity can invalidate an earlier token, so a 401 refreshes the
    session once instead of failing a long run on a stale token.
    """
    from urllib.parse import urlencode

    items: list[dict] = []
    start = 0
    while True:
        params = {"Recursive": "true", "StartIndex": str(start), "Limit": str(page), "Fields": fields}
        params.update(extra)
        status, payload = pe.request_json("GET", "/Items?" + urlencode(params),
                                          headers={"Authorization": auth}, timeout=120)
        if status == 401:
            auth = pkg.api_auth()
            status, payload = pe.request_json("GET", "/Items?" + urlencode(params),
                                              headers={"Authorization": auth}, timeout=120)
        require(status == 200, "The paged native item query failed.")
        batch = payload.get("Items", [])
        items.extend(batch)
        total = payload.get("TotalRecordCount")
        if not batch or (total is not None and start + len(batch) >= total):
            break
        start += len(batch)
    return items


def wait_items_by_name(auth: str, names: list[str], timeout: int = 900) -> dict[str, dict]:
    """Resolve every fixture name from one paged listing instead of an O(N^2) per-name listing."""
    wanted = list(dict.fromkeys(names))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        by_name: dict[str, list[dict]] = {}
        for item in paged_native_items(auth, {}):
            by_name.setdefault(str(item.get("Name")), []).append(item)
        if all(len(by_name.get(name, [])) == 1 for name in wanted):
            return {name: by_name[name][0] for name in wanted}
        time.sleep(1)
    raise RuntimeError("The package instance did not index every fixture item before the timeout.")


def ensure_distinct_media_b() -> tuple[str, int]:
    """Generate the distinct same-container media B with the pinned Jellyfin FFmpeg if it is absent."""
    pe.workspace()
    target = pe.WORK / "media" / MEDIA_B_NAME
    if not target.is_file():
        images = pe.load_image_lock()
        command = [
            *pe.DOCKER, "run", "--rm", "--entrypoint", "/usr/lib/jellyfin-ffmpeg/ffmpeg",
            "-v", f"{pe.WORK / 'media'}:/out", images["server"],
            "-y", "-f", "lavfi", "-i", "testsrc=duration=5:size=160x90:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=660:duration=5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", f"/out/{MEDIA_B_NAME}",
        ]
        result = pe.run(*command, timeout=180)
        require(result.returncode == 0,
                f"Could not generate the distinct media B fixture: {result.stderr.strip()[-300:]}")
    data = target.read_bytes()
    return hashlib.sha1(data).hexdigest(), len(data)


def build_fixture(count: int, run_id: str) -> dict[str, object]:
    sha1, size = pe.media_sha1(pe.MEDIA_MP4)
    url = "http://media:8080/" + pe.MEDIA_MP4
    names = [f"Large {run_id} {index:05d}" for index in range(count)]
    paths: dict[str, Path] = {}
    urls: dict[str, str] = {}
    # All bulk sources share one controlled URL. Per-source routes are created only for the handful of
    # increment controls that must change bytes without touching their neighbours; a route per candidate
    # would otherwise be indexed by the out-of-scope library and add thousands of native items.
    for name in names:
        urls[name] = url
        paths[name] = pe.write_strm(name, url, sha1, size)
    controls = {
        "ordinary": f"Large ordinary {run_id}",
        "legacy": f"Large legacy {run_id}",
        "unknown": f"Large unknown {run_id}",
        "out_of_scope": f"Large out {run_id}",
    }
    ordinary_path = pe.WORK / "strm" / (controls["ordinary"] + ".mp4")
    pe.copy_owned(pe.WORK / "media" / pe.MEDIA_MP4, ordinary_path, label="ordinary media control")
    paths[controls["legacy"]] = pe.write_owned_bytes(
        pe.WORK / "strm" / (controls["legacy"] + ".strm"), (url + "\n").encode(), label="legacy STRM control")
    paths[controls["unknown"]] = pe.write_owned_bytes(
        pe.WORK / "strm" / (controls["unknown"] + ".strm"),
        ("# strm-probe-version:99\n" + url + "\n").encode(), label="unknown protocol control")
    paths[controls["out_of_scope"]] = pe.write_owned_bytes(
        pe.WORK / "media" / (controls["out_of_scope"] + ".strm"),
        (f"# strm-probe-version:1\n# strm-probe-sha1:{sha1}\n# strm-probe-size:{size}\n{url}\n").encode(),
        label="out-of-scope STRM control")
    urls[controls["legacy"]] = url
    urls[controls["unknown"]] = url
    return {"names": names, "paths": paths, "urls": urls, "controls": controls,
            "sha1": sha1, "size": size, "ordinary_path": ordinary_path,
            "strm_dir": pe.WORK / "strm", "local_dir": pe.WORK / "media"}


def assign_increment_controls(fixture: dict, items: dict, candidate_ids: list[str],
                              recorder: scan.EvidenceRecorder) -> None:
    """Choose three sources from each of four actual Guid batches, before native preparation/trust."""
    ordered = sorted((canonical_guid(value, "control candidate") for value in candidate_ids),
                     key=scan.guid_sort_key)
    require(len(ordered) == len(set(ordered)), "Increment candidate IDs contain duplicates.")
    names = {canonical_guid(items[name]["Id"], name): name for name in fixture["names"]}
    batches = []
    for offset in range(0, len(ordered), 128):
        eligible = [(position, names[value]) for position, value in
                    enumerate(ordered[offset:offset + 128], offset) if value in names]
        if len(eligible) >= 3:
            batches.append(eligible)
    require(len(batches) >= 4, "Increment controls require four distinct real Guid batches.")
    selected = [batches[index * (len(batches) - 1) // 3][:3] for index in range(4)]
    observations = []
    for column, (group, prefix) in enumerate((("url_group", "u"), ("content_group", "c"),
                                            ("size_group", "s"))):
        fixture[group] = []
        for index, batch in enumerate(selected):
            position, name = batch[column]
            route = create_source_route(f"{prefix}{index}-{uuid.uuid4().hex[:8]}", pe.MEDIA_MP4)
            fixture["urls"][name] = route
            fixture["paths"][name] = pe.write_strm(
                name, route, None if group == "size_group" else fixture["sha1"], fixture["size"])
            note_owned_edit(fixture["paths"][name])
            fixture[group].append(name)
            observations.append({"group": group, "item_id": ordered[position],
                                 "position": position, "batch": position // 128})
    recorder.record("increment_control_batches", controls=observations, batch_size=128)


def create_source_route(key: str, media_name: str) -> str:
    relative = Path("large-source") / f"{key}.mp4"
    source = pe.WORK / "media" / media_name
    target = pe.WORK / "media" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise RuntimeError("A per-source media route already exists.")
    os.link(source, target)
    note_owned_edit(target)
    return "http://media:8080/" + relative.as_posix()


def replace_source_route(url: str, media_name: str) -> None:
    from urllib.parse import urlsplit

    relative = Path(urlsplit(url).path.lstrip("/"))
    target = pe.require_owned_path(pe.WORK / "media" / relative, label="per-source media route")
    require(target.is_file() and not target.is_symlink(), "The per-source media route is not a regular owned file.")
    target.unlink()
    pe.copy_owned(pe.WORK / "media" / media_name, target, label="replace per-source media bytes")
    note_owned_edit(target)


def wait_native_task_idle(auth: str, key: str, timeout: int = 300) -> None:
    """Wait until the native library task is idle so a fresh manual run actually starts a new execution.

    Creating the library itself kicks off an async scan; starting the task while it is still Running coalesces
    into the same run, so the tool must wait for Idle before requesting its own scan.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = scan.find_task_by_key(auth, key)
        if scan.task_state_name(task) in {"idle", "0"}:
            return
        time.sleep(1)
    raise RuntimeError(f"The native task {key!r} did not return to Idle before the timeout.")


def indexed_strm_count(auth: str) -> int:
    return len([item for item in paged_native_items(auth, {})
                if str(item.get("Path") or "").lower().endswith(".strm")])


def resolve_fixture_items(auth: str, names: list[str]) -> dict[str, dict] | None:
    """Return the name->item map only when every fixture name currently resolves exactly once."""
    by_name: dict[str, list[dict]] = {}
    for item in paged_native_items(auth, {}):
        by_name.setdefault(str(item.get("Name")), []).append(item)
    if all(len(by_name.get(name, [])) == 1 for name in names):
        return {name: by_name[name][0] for name in names}
    return None


def prepare_indexed_fixture(auth: str, fixture: dict[str, object], recorder: scan.EvidenceRecorder) -> dict[str, dict]:
    """Index every fixture through one real native scan and poll until all items appear.

    Jellyfin's library scan is asynchronous: the scheduled task can report Completed while items are still
    being persisted, and a manual start during the library-creation scan coalesces into that earlier run. The
    tool waits for Idle, starts a fresh scan, and then polls the paged native query until every fixture name
    resolves exactly once (or the fixed deadline fails the run).
    """
    wanted = list(fixture["names"]) + [name for name in fixture["controls"].values()
                                        if name != fixture["controls"]["out_of_scope"]]
    wait_native_task_idle(auth, scan.SCAN_TASK_KEY)
    task, interval = scan.run_native_scan_completed(auth, "large-library indexing", timeout=3600)
    recorder.record("fixture_scan_completed", task=task, interval=interval)
    items = poll_fixture_items(auth, wanted, recorder, deadline_seconds=3600)
    item_ids = [canonical_guid(item["Id"], "fixture item") for item in items.values()]
    require(len(set(item_ids)) == len(item_ids), "Jellyfin merged two physical fixture files into one item.")
    return items


def poll_fixture_items(auth: str, names: list[str], recorder: scan.EvidenceRecorder,
                       deadline_seconds: int) -> dict[str, dict]:
    deadline = time.monotonic() + deadline_seconds
    last = -1
    while time.monotonic() < deadline:
        try:
            resolved = resolve_fixture_items(auth, names)
        except RuntimeError:
            resolved = None
        if resolved is not None:
            return resolved
        count = indexed_strm_count(auth)
        if count != last:
            recorder.record("fixture_index_progress", indexed_strm=count, expected=len(names))
            last = count
        time.sleep(5)
    raise RuntimeError(f"The package instance did not index all {len(names)} STRM fixtures before the timeout.")


def prepare_native_streams(auth: str, items: list[dict], urls: dict[str, str], recorder: scan.EvidenceRecorder,
                           sampler: ResourceSampler) -> None:
    require(scan.plugin_action(auth, False) == 204, "Could not disable the plugin for native stream preparation.")
    sampled_restart(sampler)
    auth = scan.api_auth()
    workers = min(2, len(items))
    failures: list[str] = []
    started = time.monotonic()
    def prepare_worker(offset: int) -> list[str]:
        errors = []
        for item in items[offset::workers]:
            if sampler.budget is not None and sampler.budget.failure:
                break
            try:
                if not scan.native_prepare_stream(auth, item, urls[item["Name"]], timeout=180):
                    errors.append(canonical_guid(item["Id"], "unprepared item"))
            except Exception as error:
                errors.append(f"{canonical_guid(item['Id'], 'unprepared item')}:{type(error).__name__}")
        return errors

    # Only two worker futures exist; aborts stop subsequent admission and drain current calls.
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="native-stream-prepare") as pool:
        futures = [pool.submit(prepare_worker, offset) for offset in range(workers)]
        for future in as_completed(futures, timeout=MAX_TASK_TIMEOUT):
            failures.extend(future.result())
    if sampler.budget is not None:
        sampler.budget.check()
    require(not failures, f"Native stream preparation failed for {len(failures)} sources.")
    recorder.record("native_stream_preparation_completed", count=len(items), workers=workers,
                    elapsed_seconds=time.monotonic() - started)
    require(scan.plugin_action(scan.api_auth(), True) == 204, "Could not re-enable the plugin after preparation.")
    sampled_restart(sampler)


def selected_library_ids(auth: str) -> tuple[str, str]:
    libraries = scan.library_roots(auth)
    require("strm" in libraries and "local" in libraries, f"The isolated instance libraries are incomplete: {libraries}.")
    status = scan.configure(auth, {"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2,
                                   "DetailedLog": True, "BatchAllLibraries": False,
                                   "BatchLibraryIds": libraries["strm"]})
    require(status == 204, f"Could not select the isolated STRM library ({status}).")
    return libraries["strm"], libraries["local"]


def capture_candidates(auth: str, library_id: str, fixture: dict[str, object], items: dict[str, dict],
                       recorder: scan.EvidenceRecorder, label: str) -> dict[str, object]:
    """Read the real native candidate set without the versioned-manifest strictness of the scan helper.

    The selected library intentionally also holds a legacy and an unknown-protocol STRM control plus an
    ordinary video; those are native candidates that must settle without a probe, so the candidate set is
    built directly from the native query rather than reusing a helper that refuses a non-versioned STRM.
    """
    root = scan.library_root_path(auth, library_id)
    native = scan.current_library_items(auth, library_id)
    manifest = scan.build_candidate_manifest(native, library_id, root)
    native_ids = [row["item_id"] for row in manifest["items"]]
    require(len(native_ids) == len(set(native_ids)), "The native library candidate manifest contains duplicates.")
    supported_ids = [canonical_guid(items[name]["Id"], name) for name in fixture["names"]]
    for item_id in supported_ids:
        require(item_id in native_ids, f"Supported fixture candidate {item_id} is absent from native candidate set.")
    in_scope_controls = {name: canonical_guid(items[name]["Id"], name)
                         for key, name in fixture["controls"].items()
                         if key != "out_of_scope" and name in items}
    for name, item_id in in_scope_controls.items():
        require(item_id in native_ids, f"The in-scope {name} control is absent from the native candidate set.")
    require(len(set(supported_ids) & set(in_scope_controls.values())) == 0,
            "A supported fixture identity collides with an in-scope control identity.")
    recorder.record("candidate_manifest", label=label, manifest=manifest)
    recorder.snapshot(f"candidate-manifest-{label}-{time.time_ns()}", manifest)
    return {"manifest": manifest, "ids": native_ids, "supported_ids": supported_ids,
            "control_ids": in_scope_controls, "count": len(native_ids),
            "supported_count": len(supported_ids)}


def run_round(auth: str, container: str, recorder: scan.EvidenceRecorder, label: str,
              expected_candidates: int, expected_probes: int, expected_first_trust: int | None = None,
              timeout: int = MAX_TASK_TIMEOUT,
              expected_candidate_ids: list[str] | None = None, *,
              expected_probe_keys: list[tuple[str, str]] | None = None) -> dict[str, object]:
    started = scan.now_utc()
    execution = run_task(auth, recorder, timeout=timeout)
    scan.require_completed_execution(execution["task"], execution["start_time_previous"], label)
    progress = execution["progress"]
    require(all(0 <= value <= 100 for value in progress)
            and all(left <= right for left, right in zip(progress, progress[1:])),
            f"{label} has invalid or decreasing progress.")
    summary_line = latest_summary_since(container, started)
    fields = require_complete_summary(summary_line)
    validate_settlement(fields, expected_candidates, expected_probes, expected_first_trust)
    # The three deliberately unsupported in-scope controls are the only normal exclusions.
    require(fields["not_processed"] == 3 and fields["checked"] == expected_candidates - 3,
            f"{label} did not check exactly the supported fixtures and exclude the three controls.")
    probes = probe_starts_since(container, started)
    require(len(probes) == expected_probes, f"{label} raw probe starts disagree with its summary.")
    require(all(1 <= probe["running"] <= 2 for probe in probes),
            f"{label} exceeded the configured two-probe limit.")
    actual_keys = [(probe["item_id"], probe["source_key"]) for probe in probes]
    require(expected_probe_keys is not None or expected_probes == 0,
            f"{label} has no independent expected probe identities.")
    require(sorted(actual_keys) == sorted(expected_probe_keys or []),
            f"{label} probed unexpected, duplicate or missing sources.")
    events = batch_log_events(container, started)
    for event in events:
        if event["kind"] == "OBJECT_READ_RETURNED":
            requested = re.search(r"RequestedCount (\d+) ReturnedCount (\d+)", event["redacted_line"])
            require(requested is not None and 0 <= int(requested[2]) <= int(requested[1]) <= 128,
                    f"{label} has missing or oversized object-batch evidence.")
    logged_ids = [event["candidate_id"] for event in events if event.get("kind") == "CANDIDATE_ID"]
    identity_reconciliation = None
    if expected_candidate_ids is not None:
        identity_reconciliation = reconcile_candidate_identities(expected_candidate_ids, logged_ids)
    require(any(event["kind"] == "CANDIDATE_QUERY_STARTED" for event in events),
            f"{label} has no candidate-query phase marker.")
    require(any(event["kind"] == "CANDIDATE_QUERY_RETURNED" for event in events) or expected_candidates == 0,
            f"{label} has no candidate-query return marker.")
    require(any(event["kind"] == "CANDIDATE_SET_FIXED" for event in events) or execution["stopped"],
            f"{label} has no fixed candidate-set marker.")
    recorder.record("large_library_round", label=label, summary_line=summary_line, fields=fields,
                    task_execution=execution, phase_events=events, probe_starts=probes,
                    candidate_identity_reconciliation=identity_reconciliation)
    recorder.snapshot(f"round-{label}-{time.time_ns()}", {"fields": fields, "task_execution": execution,
                                                          "probe_starts": probes,
                                                          "phase_events": events,
                                                          "candidate_identity_reconciliation": identity_reconciliation})
    return {"summary": summary_line, "fields": fields, "execution": execution,
            "events": events, "started": started}


def native_items_by_id(auth: str) -> dict[str, dict]:
    """Read every current native item once through the paged query and index it by canonical item id."""
    result: dict[str, dict] = {}
    for item in paged_native_items(auth, {}):
        if not item.get("Id"):
            continue
        item_id = canonical_guid(item["Id"], "native item")
        require(item_id not in result, "The native paged query returned a duplicate item identity.")
        result[item_id] = item
    return result


def expected_all_rows(auth: str, fixture: dict[str, object], items: dict[str, dict]) -> dict[tuple[str, str], dict]:
    """Build the expected fingerprint set from the current native source identity for each fixture item.

    A native library scan can re-key a physical source id, so the expected source key is always resolved from
    the current native MediaSources (read once) instead of reusing a key captured before the scan.
    """
    current = native_items_by_id(auth)
    expected = {}
    for name in fixture["names"]:
        item_id = canonical_guid(items[name]["Id"], name)
        item = current.get(item_id)
        require(item is not None, f"Native item {name!r} disappeared while building the expected fingerprint set.")
        source_key = file_source_id(item, name)
        key = (item_id, canonical_guid(source_key, name))
        expected[key] = expected_row(item, source_key, fixture["paths"][name])
    return expected

def assert_native_sources(auth: str, fixture: dict[str, object], items: dict[str, dict]) -> None:
    current = native_items_by_id(auth)
    for name in fixture["names"]:
        item = current.get(canonical_guid(items[name]["Id"], name))
        require(item is not None, f"Native item {name!r} disappeared.")
        sources = item.get("MediaSources") or []
        require(len(sources) == 1, f"Native item {name!r} has {len(sources)} physical sources.")
        streams = sources[0].get("MediaStreams") or []
        require(any(stream.get("Type") in {"Video", "Audio"} for stream in streams),
                f"Native item {name!r} has no persisted main media stream.")
        path_hash = digest(str(sources[0].get("Path") or ""))
        manifest = scan.read_versioned_manifest(fixture["paths"][name])
        require(manifest is not None and path_hash == manifest["url_hash"],
                f"Native item {name!r} does not retain its expected current address.")


def capture_state(auth: str, fixture: dict, items: dict, expected: dict,
                  recorder: scan.EvidenceRecorder, label: str, native_expected: dict | None = None,
                  *, empty_fingerprints: bool = False) -> dict:
    """Save the key checkpoint as auditable rows and redacted native source signatures."""
    actual = fingerprint_map(allow_missing=True) if empty_fingerprints else fingerprint_map()
    recorder.snapshot(f"rows-{label}-{time.time_ns()}", {
        "expected_rows": [expected[key] for key in sorted(expected)],
        "actual_rows": [actual[key] for key in sorted(actual)]})
    current = native_items_by_id(auth)
    native = {}
    for name in fixture["names"]:
        item_id = canonical_guid(items[name]["Id"], name)
        item = current.get(item_id)
        require(item is not None, f"{label}: a supported item disappeared.")
        source_key = file_source_id(item, name)
        source = item["MediaSources"][0]
        streams = [stream for stream in (source.get("MediaStreams") or [])
                   if stream.get("Type") in {"Video", "Audio"}]
        require(bool(streams), f"{label}: a supported source lost its main stream.")
        # Only stable media properties: no delivery URLs, private paths, or serialization-order dependence.
        signature = [{key: stream.get(key) for key in ("Type", "Index", "Codec", "Profile",
                     "Width", "Height", "Channels", "SampleRate", "BitRate", "IsDefault")}
                     for stream in streams]
        native[(item_id, source_key)] = {"item_id": item_id, "source_key": source_key,
            "url_hash": digest(str(source.get("Path") or "")),
            "main_stream_sha256": digest(json.dumps(
                sorted(signature, key=lambda stream: (str(stream["Type"]), str(stream["Index"]))), sort_keys=True))}
    recorder.snapshot(f"state-{label}-{time.time_ns()}", {
        "expected_rows": [expected[key] for key in sorted(expected)],
        "actual_rows": [actual[key] for key in sorted(actual)],
        "native_sources": [native[key] for key in sorted(native)],
        "expected_native_sources": ([native_expected[key] for key in sorted(native_expected)]
                                    if native_expected is not None else None)})
    reconcile_rows({} if empty_fingerprints else expected, actual)
    require(set(native) == set(expected), f"{label}: native source identities changed unexpectedly.")
    require(all(native[key]["url_hash"] == expected[key]["url_hash"] for key in expected),
            f"{label}: a native address does not match the independently expected fingerprint.")
    if native_expected is not None:
        require(all(native[key] == value for key, value in native_expected.items()),
                f"{label}: native address or main-stream signature changed.")
    return native


def seed_controlled_contents(fixture: dict[str, object], items: dict[str, dict],
                             recorder: scan.EvidenceRecorder) -> list[dict[str, object]]:
    """Apply the pre-planned increment controls: four URL changes, four content changes, four Size changes,
    plus four newly indexed supported STRMs without a saved primary stream.

    The 12 controls were assigned by ``assign_increment_controls`` from four distinct real Guid batches and
    their baseline primary streams were prepared for their current route URL, so the same function serves the
    legacy fresh path and the retained-library reuse path without re-preparing the existing library.
    """
    url_group = list(fixture["url_group"])
    content_group = list(fixture["content_group"])
    size_group = list(fixture["size_group"])
    media_b = MEDIA_B_NAME
    sha_b, size_b = ensure_distinct_media_b()
    for name in url_group:
        url = create_source_route("u-change-" + uuid.uuid4().hex[:8], pe.MEDIA_MP4)
        fixture["urls"][name] = url
        fixture["paths"][name] = pe.write_strm(name, url, fixture["sha1"], fixture["size"])
        note_owned_edit(fixture["paths"][name])
    for name in content_group:
        replace_source_route(fixture["urls"][name], media_b)
        fixture["paths"][name] = pe.write_strm(name, fixture["urls"][name], sha_b, size_b)
        note_owned_edit(fixture["paths"][name])
    for name in size_group:
        # Same URL and still no comparable SHA-1; the route now serves B, so the changed Size is B's real size.
        replace_source_route(fixture["urls"][name], media_b)
        fixture["paths"][name] = pe.write_strm(name, fixture["urls"][name], None, size_b)
        note_owned_edit(fixture["paths"][name])
    # Add already-indexed supported STRMs without a saved primary stream. The batch must discover and probe
    # these four sources rather than trust them as first-trust rows.
    new_names = [f"Large missing-stream {uuid.uuid4().hex[:8]} {index}" for index in range(4)]
    for offset, name in enumerate(new_names):
        url = create_source_route("m" + uuid.uuid4().hex[:8], pe.MEDIA_MP4)
        fixture["urls"][name] = url
        fixture["paths"][name] = pe.write_strm(name, url, fixture["sha1"], fixture["size"])
        note_owned_edit(fixture["paths"][name])
    fixture["new_names"] = new_names
    changes = ([{"kind": "url", "name": name} for name in url_group]
               + [{"kind": "content", "name": name} for name in content_group]
               + [{"kind": "size", "name": name} for name in size_group]
               + [{"kind": "missing-main-stream", "name": name} for name in new_names])
    recorder.record("increment_controls_prepared", changes=changes, expected_sha1_b=sha_b,
                    expected_size_a=fixture["size"], expected_size_b=size_b, sha1_a=fixture["sha1"])
    return changes


class ScenarioState:
    """Mutable run-owned resources tracked across the scenario body and its required teardown."""

    def __init__(self) -> None:
        self.workspace = None
        self.before_state = None
        self.sampler: ResourceSampler | None = None
        self.instance_started = False
        self.budget: RunBudget | None = None
        self.previous_alarm_handler = None


def finalize_scenario(summary: dict[str, object], state: "ScenarioState", keep_workspace: bool) -> None:
    """Perform the required teardown and fail the overall status closed on any teardown failure.

    This function returns nothing: the caller derives the process result from ``summary['status']`` after it
    returns, so a sampler, reconciliation or cleanup failure can never leave the command reporting success
    even though the observed scenario body itself succeeded.
    """
    if state.sampler is not None:
        try:
            state.sampler.stop()
        except Exception as error:
            summary["status"] = "FAIL"
            summary["sampler_cleanup_error"] = type(error).__name__
    if state.before_state is not None:
        try:
            summary["instance_reconciliation"] = pe.reconcile_instance_state(state.before_state)
        except Exception as error:
            summary["status"] = "FAIL"
            summary["instance_reconciliation_error"] = type(error).__name__
    if state.workspace is not None and not keep_workspace:
        try:
            if summary.get("status") != "PASS" and state.instance_started:
                pe.compose("stop")
                summary["cleanup"] = {"status": "PRESERVED AFTER FAILURE",
                                      "container_states": pe.inspect_owned_container_states()}
            else:
                summary["cleanup"] = pe.cleanup_instance(
                    required_services=("jellyfin", "media") if state.instance_started else ())
        except Exception as error:
            summary["status"] = "FAIL"
            summary["cleanup_error"] = type(error).__name__


def run_scenario(package: Path, count: int, evidence_dir: Path, timeout: int, keep_workspace: bool) -> int:
    run_id = uuid.uuid4().hex[:12]
    recorder = scan.EvidenceRecorder(evidence_dir, run_id)
    summary: dict[str, object] = {"run_id": run_id, "count": count, "status": "FAIL"}
    state = ScenarioState()
    try:
        run_scenario_body(package, count, run_id, recorder, summary, state, timeout)
    except Exception as error:
        summary["status"] = "FAIL"
        summary["error"] = {"type": type(error).__name__, "message": scan._safe_exception(error)}
        recorder.record("failure", error=summary["error"])
    finally:
        if state.previous_alarm_handler is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, state.previous_alarm_handler)
        if summary.get("status") != "PASS" and state.instance_started:
            try:
                auth = scan.api_auth()
                for task in scan.task_list(auth):
                    if scan.task_state_name(task) in {"running", "cancelling", "1", "2"}:
                        status = scan.stop_task(auth, task["Id"])
                        recorder.record("failure_native_stop_requested", task_key=task.get("Key"), status=status)
                        wait_native_task_idle(auth, task["Key"], timeout=300)
            except Exception as error:
                summary["failure_drain_error"] = type(error).__name__
        if state.instance_started:
            for service in ("jellyfin", "media"):
                try:
                    recorder.write_raw(f"logs/{service}.log", "\n".join(
                        full_docker_log(pe.container_name(service))))
                except Exception as error:
                    summary["status"] = "FAIL"
                    summary[service + "_log_error"] = type(error).__name__
        finalize_scenario(summary, state, keep_workspace)
        recorder.set_metadata(exit_code=0 if summary.get("status") == "PASS" else 1,
                              final_status=summary.get("status", "FAIL"))
        recorder.finish(str(summary.get("status", "FAIL")), summary, {})
        print(json.dumps(scan._scrub(summary), ensure_ascii=False, indent=2, sort_keys=True))
    # Derive the exit code only after finalization so a failed reconciliation or cleanup is never command success.
    return 0 if summary.get("status") == "PASS" else 1


def run_scenario_body(package: Path, count: int, run_id: str, recorder: "scan.EvidenceRecorder",
                      summary: dict[str, object], state: "ScenarioState", timeout: int) -> None:
    package = package.resolve()
    verification = pp.verify_archive(package)
    summary["package_identity"] = {"archiveSha256": verification["archiveSha256"],
                                   "version": verification["version"], "guid": verification["guid"],
                                   "targetAbi": verification["targetAbi"], "runtime": verification["runtime"],
                                   "entries": verification["entries"]}
    state.workspace = pe.select_workspace()
    pe.PROJECT = pe.PROJECT + "-large-" + run_id
    state.before_state = pe.capture_instance_state()
    environment = system_profile()
    recorder.set_metadata(command=f"python3 scripts/run_isolated_large_library_integration.py --package <zip> --count {count} --scenario all",
                          runtime={"python": sys.version.split()[0], "dotnet_sdk": json.loads((ROOT / "global.json").read_text())["sdk"]["version"],
                                   "platform": platform.platform()},
                          inputs={"package_sha256": summary["package_identity"]["archiveSha256"],
                                  "count": count, "environment": environment})
    state.budget = RunBudget(environment, timeout)
    state.budget.check(environment)
    pe.SERVICE_RESOURCE_LIMITS = state.budget.limits
    recorder.record("host_and_budget", environment=environment,
                    limits={"level_timeout_seconds": timeout, "task_timeout_seconds": timeout,
                            "api_timeout_seconds": 180, "drain_timeout_seconds": 300,
                            "services": state.budget.limits, "host_floors": state.budget.floors,
                            "orchestrator_rss_limit_bytes": state.budget.orchestrator_limit,
                            "basis": "60% Jellyfin + 5% media + 10% orchestrator of initial MemAvailable; 20% host/storage reserve",
                            "native_prepare_workers": 2, "plugin_probe_default": 2,
                            "sample_seconds": 1, "progress_poll_seconds": POLL_SECONDS})
    require(signal.getitimer(signal.ITIMER_REAL)[0] == 0, "Another process alarm is already active.")
    state.previous_alarm_handler = signal.getsignal(signal.SIGALRM)
    def check_budget(signum, frame):
        state.budget.check()
    signal.signal(signal.SIGALRM, check_budget)
    signal.setitimer(signal.ITIMER_REAL, 1, 1)

    # Once startup is attempted, failures preserve the run-owned directory even if bootstrap only partly ran.
    state.instance_started = True
    pe.prepare_clean_instance()
    deploy = pe.deploy_archive(package)
    scan.restart()
    auth = scan.api_auth()
    require(scan.plugin_status(auth).lower() in {"active", "0"}, "The ZIP-installed plugin is not Active.")
    require(pkg.deployed_matches_archive(package).get("matched") is True,
            "The installed plugin payload does not match the tested ZIP.")
    # Use the existing sampler during indexing and native preparation too, not just batch execution.
    container = pe.container_name("jellyfin")
    state.sampler = ResourceSampler(container, recorder, state.budget)
    state.sampler.start()
    pe.add_library_authenticated(auth, "Package Local Fixtures", ["/media/local"])
    auth = scan.api_auth()
    fixture = build_fixture(count, run_id)
    items = prepare_indexed_fixture(auth, fixture, recorder)
    strm_library_id, local_library_id = selected_library_ids(auth)
    require(strm_library_id != local_library_id, "The in-scope and out-of-scope libraries are not distinct.")
    initial_candidates = capture_candidates(auth, strm_library_id, fixture, items, recorder, "control-selection")
    assign_increment_controls(fixture, items, initial_candidates["ids"], recorder)
    items = prepare_indexed_fixture(auth, fixture, recorder)
    require(scan.plugin_action(auth, False) == 204, "Could not disable the plugin before native preparation.")
    sampled_restart(state.sampler)
    auth = scan.api_auth()
    prepare_targets = [items[name] for name in fixture["names"]]
    prepare_native_streams(auth, prepare_targets, fixture["urls"], recorder, state.sampler)
    auth = scan.api_auth()
    items = wait_items_by_name(auth, list(items))
    assert_native_sources(auth, fixture, items)
    selected = capture_candidates(auth, strm_library_id, fixture, items, recorder, "before-first-trust")
    require(selected["supported_count"] == count, "The native library does not contain the requested supported count.")
    rows_before = fingerprint_map(allow_missing=True)
    require(not any(key[0] in set(selected["supported_ids"]) for key in rows_before),
            "The fresh package instance already contains fingerprints before first trust.")
    container = pe.container_name("jellyfin")
    identity = container_identity(container)
    recorder.set_container_identity(identity)
    run_full_behavior(auth, strm_library_id, container, fixture, items, selected,
                      recorder, state, summary, timeout, deploy, identity)


def run_full_behavior(auth: str, strm_library_id: str, container: str, fixture: dict,
                      items: dict, selected: dict, recorder: "scan.EvidenceRecorder",
                      state: "ScenarioState", summary: dict[str, object], timeout: int,
                      deploy: dict, identity: dict) -> None:
    """Execute the complete required RO-2 behavior on an already verified candidate set.

    Shared by the legacy ``--fresh`` path and the retained-library reuse path so both run the same
    required rounds (first trust, unchanged, controlled cross-batch increment, query-stage stop,
    in-flight stop/drain, recovery, two unchanged rounds, restart and explicit selected PlaybackInfo)
    instead of a second, weaker code path. The caller has already verified the native sources and the
    empty/reset first-trust store; this function mutates ``items`` and ``fixture`` in place.
    """
    run_timeout = min(timeout, MAX_TASK_TIMEOUT)
    round1 = run_round(auth, container, recorder, "first-trust", selected["count"], 0,
                       selected["supported_count"], run_timeout, selected["ids"])
    auth = scan.api_auth()
    expected = expected_all_rows(auth, fixture, items)
    first_rows = fingerprint_map()
    reconciliation = reconcile_rows(expected, first_rows)
    require(first_rows.keys() == expected.keys(), "First trust created rows outside the selected supported sources.")
    recorder.record("first_trust_reconciliation", rows=reconciliation)
    first_native = capture_state(auth, fixture, items, expected, recorder, "first-trust")
    round2 = run_round(auth, container, recorder, "unchanged", selected["count"], 0, 0,
                       run_timeout, selected["ids"])
    assert_native_sources(auth, fixture, items)
    capture_state(auth, fixture, items, expected, recorder, "unchanged", first_native)

    changes = seed_controlled_contents(fixture, items, recorder)
    auth = scan.api_auth()
    wait_native_task_idle(auth, scan.SCAN_TASK_KEY)
    task, interval = scan.run_native_scan_completed(auth, "large-library increment indexing", timeout=1800)
    recorder.record("fixture_scan_completed", task=task, interval=interval)
    new_items = poll_fixture_items(auth, list(fixture["new_names"]), recorder, deadline_seconds=1800)
    recorder.record("missing_stream_candidates_indexed", new_names=len(new_items))
    for name in fixture["new_names"]:
        item = scan.current_native_item_by_id(auth, new_items[name]["Id"])
        require(item is not None and not any(stream.get("Type") in {"Video", "Audio"}
                                              for source in item.get("MediaSources", [])
                                              for stream in (source.get("MediaStreams") or [])),
                f"The added source {name!r} unexpectedly has a main stream before batch checking.")
    items.update(new_items)
    fixture["names"].extend(fixture["new_names"])
    items = wait_items_by_name(auth, list(items))
    selected = capture_candidates(auth, strm_library_id, fixture, items, recorder, "before-increment")
    expected_increment_count = selected["count"]
    auth = scan.api_auth()
    changed_round = run_round(auth, container, recorder, "controlled-increment", expected_increment_count, 16, 0,
                              run_timeout, selected["ids"], expected_probe_keys=[
                                  (canonical_guid(items[change["name"]]["Id"], "changed item"),
                                   file_source_id(items[change["name"]], "changed source")) for change in changes])
    auth = scan.api_auth()
    increment_expected = expected_all_rows(auth, fixture, items)
    increment_rows = fingerprint_map()
    increment_reconciliation = reconcile_rows(increment_expected, increment_rows)
    recorder.record("increment_reconciliation", rows=increment_reconciliation, changes=changes)
    increment_native = capture_state(auth, fixture, items, increment_expected, recorder, "increment")
    followup = run_round(auth, container, recorder, "post-increment-unchanged", selected["count"], 0, 0,
                         run_timeout, selected["ids"])
    capture_state(auth, fixture, items, increment_expected, recorder, "post-increment", increment_native)

    # Preparation-stage stop: detect the real synchronous native-query window from phase logs and stop
    # during it. The window can be short at 1000 candidates, so the task allows up to three natural retries;
    # an unobserved window is reported NOT RUN rather than a fabricated in-query PASS and it fails the
    # overall acceptance result closed instead of exiting 0.
    auth = scan.api_auth()

    def perform_query_stop_attempt() -> tuple[dict, list[dict]]:
        nonlocal auth
        attempt_started = scan.now_utc()
        attempt_stop = run_query_stage_stop(auth, recorder, container, run_timeout)
        attempt_events = batch_log_events(container, attempt_started)
        if not query_stop_observed(attempt_stop, attempt_events):
            auth = scan.api_auth()
        return attempt_stop, attempt_events

    query_stage = run_query_stage_stop_attempts(perform_query_stop_attempt)
    candidate_start_seen = bool(query_stage["observed"])
    query_attempts = query_stage["attempts"]
    stage_stop = query_stage["stop"]
    stage_events = query_stage["events"]
    if candidate_start_seen:
        require(stage_stop is not None and stage_stop["stopped"],
                "The candidate-query stop was not sent after the query began.")
        require(not any(event["kind"] == "OBJECT_READ_STARTED" for event in stage_events),
                "Object reads began after stop during candidate acquisition.")
        recorder.record("query_stage_stop", status="PASS", attempts=query_attempts,
                        events=stage_events, execution=stage_stop)
    else:
        recorder.record("query_stage_stop", status="NOT RUN",
                        reason="The real query window was not observed in three natural attempts.",
                        attempts=query_attempts)

    # Stop after exactly two changed sources have actually entered the native probe. The delay route holds
    # those probes open; task diagnostics prove no later batch was read after the stop.
    sorted_candidates = sorted(selected["supported_ids"], key=scan.guid_sort_key)
    name_by_id = {canonical_guid(items[name]["Id"], name): name for name in fixture["names"]}
    all_candidate_ids = selected["ids"]
    supported_ids = {canonical_guid(item_id, "supported stop candidate") for item_id in sorted_candidates}
    first_batch_supported = [item_id for item_id in all_candidate_ids[:128]
                             if canonical_guid(item_id, "first batch candidate") in supported_ids]
    later_batch_supported = [item_id for item_id in all_candidate_ids[128:]
                             if canonical_guid(item_id, "later batch candidate") in supported_ids]
    require(len(first_batch_supported) >= 2 and len(later_batch_supported) >= 2,
            "The real native Guid order does not provide two supported sources in the first and later batches.")
    stop_target_ids = [*first_batch_supported[:2], *later_batch_supported[:2]]
    stop_names = [name_by_id[item_id] for item_id in stop_target_ids]
    stop_paths = [fixture["paths"][name] for name in stop_names]
    before_stop_expected = expected_all_rows(auth, fixture, items)
    before_stop_native = capture_state(auth, fixture, items, before_stop_expected, recorder, "before-stop")
    for index, (name, path) in enumerate(zip(stop_names, stop_paths, strict=True)):
        request_id = uuid.uuid4().hex
        url = f"http://media:8080/delay/20/{request_id}/{pe.MEDIA_MP4}"
        fixture["urls"][name] = url
        scan.rewrite_strm(path, url, fixture["sha1"], fixture["size"])
        note_owned_edit(path)
    auth = scan.api_auth()
    stop_started = scan.now_utc()
    targets = {canonical_guid(items[name]["Id"], name) for name in stop_names}
    probe_counts: dict[str, int] = {item_id: 0 for item_id in targets}
    stop_tail = LogTail(container, stop_started)
    def stop_after_two(task: dict, result: dict, log_tail: LogTail = stop_tail,
                       counts: dict[str, int] = probe_counts) -> bool:
        for line in log_tail.poll():
            event = parse_probe_start_line(line)
            if event is not None and event["item_id"] in counts:
                counts[event["item_id"]] = 1
        return sum(counts.values()) >= 2
    rerun_attempted = False

    def attempt_during_drain(task: dict) -> None:
        nonlocal rerun_attempted
        draining = current_task(auth)
        require(scan.task_state_name(draining) in {"cancelling", "2"},
                "The delayed probes did not leave an observable Cancelling window.")
        status = scan.start_task(auth, task["Id"])
        recorder.record("rerun_during_drain", request_status=status, task_before=draining)
        require(status in {204, 400, 409}, "Unexpected native rerun response during drain.")
        rerun_attempted = True

    stop_round = run_task(auth, recorder, timeout=run_timeout, stop_after=stop_after_two,
                          on_stop=attempt_during_drain)
    scan.wait_for_stable_idle(auth, stop_round["task"]["Id"])
    stop_events = batch_log_events(container, stop_started)
    started_ids = [key for key, value in probe_counts.items() if value]
    require(stop_round["stopped"] and len(started_ids) == 2,
            f"The stop did not catch exactly two started probes: {len(started_ids)}.")
    require(not any(event["kind"] == "OBJECT_READ_STARTED" and int(event.get("candidate_offset", -1)) >= 128
                    for event in stop_events), "A later object batch was read after the stop.")
    stopped_summary = require_complete_summary(latest_summary_since(container, stop_started))
    require(stopped_summary["actual_probe_calls"] == 2 and stopped_summary["reliable_success"] == 2,
            "The stopped round did not settle exactly the two actually started probes.")
    require(scan.task_status(stop_round["task"]) == "cancelled",
            f"The stopped native task did not finish Cancelled: {scan.task_status(stop_round['task'])}.")
    require(max(stop_round["progress"], default=0) < 100,
            "The stopped task reported 100% before cancellation settlement completed.")
    require(rerun_attempted and sum(event["kind"] == "CANDIDATE_QUERY_STARTED"
            and "LibraryCount" in event["redacted_line"] for event in stop_events) == 1,
            "A new batch execution entered during the old round's drain.")
    expected_started = {canonical_guid(items[name]["Id"], name) for name in stop_names[:2]}
    raw_starts = probe_starts_since(container, stop_started)
    expected_started_keys = {(canonical_guid(items[name]["Id"], name), file_source_id(items[name], name))
                             for name in stop_names[:2]}
    require(set(started_ids) == expected_started and len(raw_starts) == 2
            and {(probe["item_id"], probe["source_key"]) for probe in raw_starts} == expected_started_keys,
            "The stopped round did not probe exactly the two selected first-batch sources.")
    stopped_expected = dict(before_stop_expected)
    stopped_native_expected = {key: dict(value) for key, value in before_stop_native.items()}
    for name in stop_names[:2]:
        item = items[name]
        key = (canonical_guid(item["Id"], name), file_source_id(item, name))
        stopped_expected[key] = expected_row(item, key[1], fixture["paths"][name])
        # Started sources may legitimately acquire different stream properties; untouched ones may not.
        stopped_native_expected.pop(key)
    capture_state(auth, fixture, items, stopped_expected, recorder, "stopped-before-recovery",
                  stopped_native_expected)
    recorder.record("batch_stop_reconciliation", started_ids=started_ids, events=stop_events,
                    progress=stop_round["progress"], state=scan.task_state_name(stop_round["task"]))

    # Let the first round fully settle before starting a fresh candidate query; the new round must converge.
    auth = scan.api_auth()
    idle_task = current_task(auth)
    require(scan.task_state_name(idle_task) in {"idle", "0"}, "The old batch task did not return to native Idle.")
    recovery = run_round(auth, container, recorder, "post-stop-recovery", selected["count"], 2, 0,
                         run_timeout, selected["ids"], expected_probe_keys=[
                             (canonical_guid(items[name]["Id"], name), file_source_id(items[name], name))
                             for name in stop_names if canonical_guid(items[name]["Id"], name) not in started_ids])
    auth = scan.api_auth()
    post_stop_expected = expected_all_rows(auth, fixture, items)
    post_stop_rows = fingerprint_map()
    post_stop_reconciliation = reconcile_rows(post_stop_expected, post_stop_rows)
    recorder.record("idle_observation_started", label="before-unchanged-a", seconds=30)
    time.sleep(30)
    unchanged_a = run_round(auth, container, recorder, "post-stop-unchanged-a", selected["count"], 0, 0,
                            run_timeout, selected["ids"])
    recorder.record("idle_observation_started", label="after-a-before-b", seconds=30)
    time.sleep(30)
    unchanged_b = run_round(auth, container, recorder, "post-stop-unchanged-b", selected["count"], 0, 0,
                            run_timeout, selected["ids"])
    recorder.record("idle_observation_started", label="after-unchanged-b", seconds=30)
    time.sleep(30)

    # Restart state is checked before any PlaybackInfo call can construct a missing first-trust baseline.
    pre_restart_expected = expected_all_rows(auth, fixture, items)
    pre_restart_rows = fingerprint_map()
    pre_restart_reconciliation = reconcile_rows(pre_restart_expected, pre_restart_rows)
    pre_restart_native = capture_state(auth, fixture, items, pre_restart_expected, recorder, "pre-restart")
    require(pre_restart_rows.keys() == pre_restart_expected.keys(),
            "The pre-restart database has rows outside the fixed supported source set.")
    sampled_restart(state.sampler)
    auth = scan.api_auth()
    restarted_rows = fingerprint_map()
    restart_reconciliation = reconcile_rows(pre_restart_expected, restarted_rows)
    capture_state(auth, fixture, items, pre_restart_expected, recorder, "restart-before-playback",
                  pre_restart_native)
    assert_native_sources(auth, fixture, items)
    recorder.record("restart_read_only_reconciliation", rows=restart_reconciliation,
                    playback_before_snapshot=False)

    playback_started = scan.now_utc()
    playback_results = []
    for change in changes:
        name = change["name"]
        item = scan.current_native_item_by_id(auth, items[name]["Id"])
        require(item is not None, f"Changed source {name!r} disappeared after restart.")
        source_key = file_source_id(item, name)
        expected = pre_restart_expected[(canonical_guid(item["Id"], name), source_key)]
        status, response = scan.playback_info_selected(auth, item["Id"], source_key)
        require(status == 200, f"Explicit post-restart PlaybackInfo failed for {name!r} ({status}).")
        candidates = [source for source in response.get("MediaSources", [])
                      if source.get("Id") and canonical_guid(source["Id"], name) == source_key]
        require(len(candidates) == 1, f"PlaybackInfo selected the wrong physical source for {name!r}.")
        require(digest(str(candidates[0].get("Path") or "")) == expected["url_hash"],
                f"PlaybackInfo returned the wrong committed address for {name!r}.")
        require(any(stream.get("Type") in {"Video", "Audio"}
                    for stream in candidates[0].get("MediaStreams", [])),
                f"PlaybackInfo returned no primary stream for {name!r}.")
        playback_results.append({"name": name, "item_id": expected["item_id"],
                                 "source_key": source_key, "status": status,
                                 "url_hash": expected["url_hash"]})
    auth = scan.api_auth()
    extra_probes = plugin_probe_count(container, playback_started)
    require(extra_probes == 0, f"Post-restart PlaybackInfo caused {extra_probes} extra plugin probes.")
    after_playback_rows = fingerprint_map()
    playback_reconciliation = reconcile_rows(pre_restart_expected, after_playback_rows)
    capture_state(auth, fixture, items, pre_restart_expected, recorder, "after-playback", pre_restart_native)
    recorder.record("post_restart_explicit_playback", requests=playback_results,
                    extra_plugin_probes=extra_probes, rows=playback_reconciliation)

    state.sampler.stop()
    state.sampler = None
    required_stages = {"actual_query_stage_stop": candidate_start_seen}
    overall_status, _ = overall_acceptance_status(required_stages)
    summary.update({"status": overall_status, "deployment": deploy, "container_identity": identity,
                   "native_candidates": selected, "rounds": {
                       "first_trust": round1["fields"], "unchanged": round2["fields"],
                       "controlled_increment": changed_round["fields"],
                       "post_increment_unchanged": followup["fields"],
                       "query_stage_stop": stage_stop, "batch_stop": stop_round,
                       "post_stop_recovery": recovery["fields"],
                       "post_stop_unchanged_a": unchanged_a["fields"],
                       "post_stop_unchanged_b": unchanged_b["fields"]},
                   "reconciliations": {"first_trust": reconciliation,
                                       "increment": increment_reconciliation,
                                       "post_stop": post_stop_reconciliation,
                                       "pre_restart": pre_restart_reconciliation,
                                       "restart": restart_reconciliation},
                   "post_restart_playback": {"source_count": len(playback_results),
                                             "extra_plugin_probes": extra_probes,
                                             "reconciliation": playback_reconciliation},
                   "required_stages": {"actual_query_stage_stop": candidate_start_seen},
                   "remaining_gates": {"actual_query_stage_stop": "PASS" if candidate_start_seen else "NOT RUN"}})


REUSE_ENTRIES = ("config", "cache", "strm", "media", "media-server", "credentials.local.json", ".media-prepared")


def prepared_manifest(source: Path) -> dict[str, str]:
    """Hash offline inputs, rejecting links and unfinished SQLite transactions."""
    require(source.is_dir() and not source.is_symlink(), "Prepared source must be a real directory.")
    require((source / pe.RUN_MARKER).is_file() and
            re.fullmatch(r"[0-9a-f]{32}", (source / pe.RUN_MARKER).read_text().strip()) is not None,
            "Prepared source has no valid provenance marker.")
    for name in ("config/data/jellyfin.db", "strm", "media", "credentials.local.json"):
        require((source / name).exists(), "Prepared source is incomplete: " + name)
    hashes = {}
    for path in sorted(source.rglob("*")):
        require(not path.is_symlink(), "Prepared source contains a symbolic link.")
        require(path.is_dir() or path.is_file(), "Prepared source contains a special file.")
        require(not path.name.endswith(("-wal", "-shm", "-journal")),
                "Prepared source has SQLite transaction sidecars; stop and checkpoint it first.")
        if path.is_file():
            with path.open("rb") as stream:
                hashes[path.relative_to(source).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    return hashes


def require_source_stopped(source: Path) -> None:
    """Never copy a workspace that is mounted by any running Docker container."""
    listed = pe.run(*pe.DOCKER, "ps", "-q")
    require(listed.returncode == 0, "Cannot check running containers for prepared-source use.")
    if not listed.stdout.strip():
        return
    inspected = pe.run(*pe.DOCKER, "inspect", *listed.stdout.split())
    require(inspected.returncode == 0, "Cannot inspect prepared-source mount ownership.")
    for container in json.loads(inspected.stdout):
        for mount in container.get("Mounts", []):
            if mount.get("Type") == "bind":
                mounted = Path(mount["Source"]).resolve()
                require(not (source == mounted or source.is_relative_to(mounted)
                             or mounted.is_relative_to(source)),
                        "Prepared source overlaps a running container mount; refusing a live copy.")


def copy_prepared_workspace(source: Path) -> tuple[Path, dict[str, str]]:
    lexical = Path(os.path.abspath(source))
    require(not any(path.is_symlink() for path in (lexical, *lexical.parents)),
            "Prepared source path contains a symbolic link.")
    source = lexical.resolve(strict=True)
    require(source.is_relative_to((pe.BASE / "runs").resolve())
            and source != (pe.BASE / "runs").resolve(),
            "Prepared source must be a retained package run, not an arbitrary instance.")
    require_source_stopped(source)
    before = prepared_manifest(source)
    # Immutable read-only connections cannot create a journal in the prepared source.
    for name in before:
        if name.endswith(".db"):
            with closing(sqlite3.connect((source / name).as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
                require(connection.execute("PRAGMA quick_check").fetchall() == [("ok",)],
                        "Prepared SQLite integrity check failed.")
    target = pe.select_workspace()
    target.chmod(0o700)
    for name in REUSE_ENTRIES:
        original = source / name
        if original.is_dir():
            shutil.copytree(original, target / name, copy_function=shutil.copy2)
        elif original.is_file():
            shutil.copy2(original, target / name)
    require_source_stopped(source)
    require(prepared_manifest(source) == before, "Prepared source changed during copy.")
    for name, expected_hash in before.items():
        if name.split("/", 1)[0] not in REUSE_ENTRIES:
            continue
        copied = target / name
        with copied.open("rb") as stream:
            require(hashlib.file_digest(stream, "sha256").hexdigest() == expected_hash,
                    "Copied prepared input failed hash verification.")
        require(not os.path.samefile(source / name, copied), "Prepared copy shares a source inode.")
    return target, before


def reset_copied_fingerprints(recorder: scan.EvidenceRecorder) -> None:
    """Explicitly preserve then remove ONLY the fresh copy's first-trust store."""
    pe.workspace()
    database = pe.require_owned_path(pkg.fingerprint_database())
    if database.exists():
        saved = pe.require_owned_path(pe.WORK / "baseline-backup" / "strm-fingerprints.db")
        saved.parent.mkdir(parents=True, exist_ok=True)
        require(not saved.exists(), "Copied baseline backup already exists.")
        database.rename(saved)
        recorder.record("copied_fingerprint_reset", original_retained=True,
                        backup_sha256=hashlib.sha256(saved.read_bytes()).hexdigest())


def prepared_fixture(minimum: int) -> dict:
    fixture = {"names": [], "paths": {}, "controls": {}, "urls": {}}
    for path in sorted((pe.WORK / "strm").iterdir()):
        if path.suffix.lower() == ".strm":
            manifest = scan.read_versioned_manifest(path)
            if manifest is not None:
                fixture["names"].append(path.stem)
                fixture["paths"][path.stem] = path
            else:
                kind = "legacy" if path.read_text().splitlines()[0].startswith("http") else "unknown"
                require(kind not in fixture["controls"], "Prepared controls are ambiguous.")
                fixture["controls"][kind] = path.stem
        elif path.suffix.lower() == ".mp4":
            require("ordinary" not in fixture["controls"], "Prepared ordinary controls are ambiguous.")
            fixture["controls"]["ordinary"] = path.stem
    external = list((pe.WORK / "media").glob("*.strm"))
    require(len(external) == 1, "Expected one prepared out-of-scope control.")
    fixture["controls"]["out_of_scope"] = external[0].stem
    require(set(fixture["controls"]) == {"legacy", "unknown", "ordinary", "out_of_scope"},
            "Prepared library lacks required isolation controls.")
    require(len(fixture["names"]) >= minimum >= 1000,
            "Prepared supported source count is below the minimum; no rebuilding is attempted.")
    return fixture


def require_owned_reuse_containers() -> None:
    listed = pe.run(*pe.DOCKER, "ps", "-aq", "--filter", "label=com.docker.compose.project=" + pe.PROJECT)
    require(listed.returncode == 0, "Cannot query reuse project ownership.")
    if not listed.stdout.strip():
        return
    inspected = pe.run(*pe.DOCKER, "inspect", *listed.stdout.split())
    require(inspected.returncode == 0, "Cannot inspect reuse project ownership.")
    for container in json.loads(inspected.stdout):
        labels = container["Config"]["Labels"]
        require(labels.get("com.docker.compose.project.config_files") == str(pe.WORK / "compose.yaml"),
                "Existing project belongs to a different compose file.")
        mounts = container.get("Mounts", [])
        require(bool(mounts) and all(mount["Type"] == "bind" and
                Path(mount["Source"]).resolve().is_relative_to(pe.WORK.resolve()) for mount in mounts),
                "Existing project has foreign workspace mounts.")


def stop_and_retain_reuse() -> dict:
    pe.workspace()
    require_owned_reuse_containers()
    pe.compose("stop")
    states = pe.inspect_owned_container_states()
    require(sorted(state.get("service") for state in states) == ["jellyfin", "media"],
            "Reuse service exit evidence is incomplete.")
    require(all(state.get("status") == "exited" and type(state.get("exit_code")) is int
                and state["exit_code"] == 0 and state.get("oom_killed") is False
                and state.get("error") == "" and state.get("finished_at")
                and not str(state["finished_at"]).startswith("0001-") for state in states),
            "Reuse services did not exit cleanly; workspace retained for diagnosis.")
    return {"status": "STOPPED AND RETAINED", "container_states": states}


def run_prepared_checks(auth: str, scenario: str, minimum: int,
                        recorder: scan.EvidenceRecorder, state: ScenarioState, timeout: int) -> dict:
    fixture = prepared_fixture(minimum)
    items = resolve_prepared_items(auth, fixture)
    selected_id = prepared_selected_library(auth)
    candidates = capture_candidates(auth, selected_id, fixture, items, recorder, "prepared")
    required_ids = candidates["supported_ids"] + list(candidates["control_ids"].values())
    reconcile_candidate_identities(required_ids, candidates["ids"])
    require(canonical_guid(items[fixture["controls"]["out_of_scope"]]["Id"], "external control")
            not in candidates["ids"], "Out-of-scope control leaked into the selected library.")
    expected = expected_all_rows(auth, fixture, items)
    assert_native_sources(auth, fixture, items)
    baseline = fingerprint_map(allow_missing=True)
    if scenario == "baseline":
        require(not baseline, "First-trust needs an empty copied fingerprint store; use explicit --reset-copied-fingerprints.")
    else:
        reconcile_rows(expected, baseline)
    native_before = capture_state(auth, fixture, items, expected, recorder, "before-check",
                                  empty_fingerprints=scenario == "baseline")
    rounds = {}
    if scenario == "baseline":
        rounds["first_trust"] = run_round(auth, pe.container_name("jellyfin"), recorder, "first-trust",
            candidates["count"], 0, len(fixture["names"]), timeout, candidates["ids"], expected_probe_keys=[])["fields"]
    capture_state(auth, fixture, items, expected, recorder, "prepared-baseline", native_before)
    rounds["unchanged"] = run_round(auth, pe.container_name("jellyfin"), recorder, "unchanged",
        candidates["count"], 0, 0, timeout, candidates["ids"], expected_probe_keys=[])["fields"]
    capture_state(auth, fixture, items, expected, recorder, "unchanged", native_before)
    if scenario in {"baseline", "restart"}:
        started = scan.now_utc()
        sampled_restart(state.sampler)
        auth = scan.api_auth()
        # No PlaybackInfo before the complete persistence comparison.
        capture_state(auth, fixture, items, expected, recorder, "restart-before-playback", native_before)
        require(plugin_probe_count(pe.container_name("jellyfin"), started) == 0,
                "Restart unexpectedly started plugin probes.")
        rounds["restart"] = {"status": "PASS", "sources": len(expected), "playback_before_snapshot": False}
    return {"supported_count": len(expected), "candidate_count": candidates["count"], "rounds": rounds}


REUSE_PROTECTED_AREAS = ("configuration", "media", "strm", "libraries")


def reconcile_prepared_inputs(before: dict) -> dict:
    """Protect copied inputs; fingerprints and task execution results are intentional outputs.

    Fingerprint contents are independently reconciled at every checkpoint, while native
    task triggers are separately restored and read back. The bounded set of copied STRM/media files
    the controlled increment intentionally rewrites is tracked in ``_REUSE_EDIT_TRACKER`` so those
    planned edits are expected rather than treated as corruption; every other input must be unchanged.
    """
    expected = {area: dict(before[area]) for area in REUSE_PROTECTED_AREAS}
    edits = _REUSE_EDIT_TRACKER or {}
    for area, files in edits.items():
        for relative, sha256 in files.items():
            expected[area][relative] = sha256
    after = pe.capture_instance_state()
    for area in REUSE_PROTECTED_AREAS:
        require(expected[area] == after[area], "Prepared copy input changed: " + area)
    return {"status": "CLEAN", "protected_areas": list(REUSE_PROTECTED_AREAS),
            "controlled_edits": {area: sorted(files) for area, files in edits.items()},
            "intentional_outputs": ["fingerprint rows (checkpoint reconciled)",
                                    "task execution results (trigger restoration verified)",
                                    "bounded controlled increment files (independently hashed)"]}


def resolve_prepared_items(auth: str, fixture: dict) -> dict:
    """Resolve every prepared fixture name to its current native item, verifying the physical path."""
    names = fixture["names"] + list(fixture["controls"].values())
    native = native_items_by_id(auth)
    items = {}
    for item in native.values():
        name = item.get("Name")
        if name in names:
            require(name not in items, "Prepared native item names are ambiguous.")
            expected_path = ("/media/local/" if name == fixture["controls"]["out_of_scope"]
                             else "/media/strm/") + name
            require(str(item.get("Path") or "").rsplit(".", 1)[0] == expected_path,
                    "Prepared native item belongs to a different physical path.")
            items[name] = item
    require(set(items) == set(names), "Prepared files are not all independently indexed.")
    return items


def prepared_selected_library(auth: str) -> str:
    """Read the prepared configuration and return the single selected library id."""
    status, config = pe.request_json("GET", f"/Plugins/{pkg.PLUGIN_ID}/Configuration",
                                     headers={"Authorization": auth})
    require(status == 200, "Cannot read prepared plugin configuration.")
    require(config.get("Enabled") is True and config.get("DetailedLog") is True
            and config.get("BatchAllLibraries") is False and config.get("MaxConcurrentProbes") == 2,
            "Prepared configuration must enable detailed logging, one selected library and concurrency 2.")
    selected = config.get("BatchLibraryIds")
    selected = selected if isinstance(selected, list) else [selected]
    require(len(selected) == 1 and selected[0], "Prepared library selection is ambiguous.")
    return selected[0]


def prepare_reuse_increment_baselines(auth: str, items: dict[str, dict], names: list[str],
                                     urls: dict[str, str], recorder: scan.EvidenceRecorder,
                                     sampler: ResourceSampler) -> None:
    """Prepare only the 12 changed-URL increment controls' primary streams on the copied library.

    The retained library's other sources keep their already-saved streams; only the controls whose STRM URL
    changed need a fresh native primary stream before first trust. This is a bounded repair of the affected
    preparation, not a full-library re-preparation.
    """
    workers = min(2, len(names))
    failures: list[str] = []
    started = time.monotonic()

    def worker(offset: int) -> list[str]:
        errors = []
        for name in names[offset::workers]:
            if sampler.budget is not None and sampler.budget.failure:
                break
            try:
                if not scan.native_prepare_stream(auth, items[name], urls[name], timeout=180):
                    errors.append(canonical_guid(items[name]["Id"], "unprepared control"))
            except Exception as error:
                errors.append(f"{canonical_guid(items[name]['Id'], 'unprepared control')}:{type(error).__name__}")
        return errors

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="reuse-control-prepare") as pool:
        futures = [pool.submit(worker, offset) for offset in range(workers)]
        for future in as_completed(futures, timeout=MAX_TASK_TIMEOUT):
            failures.extend(future.result())
    require(not failures, f"Reuse increment-baseline preparation failed for {len(failures)} controls.")
    recorder.record("reuse_increment_baseline_prepared", count=len(names), workers=workers,
                    elapsed_seconds=time.monotonic() - started,
                    scope="only the 12 changed-URL controls; no full-library preparation")


def run_reuse_full_scenario(auth: str, fixture: dict, minimum: int, recorder: scan.EvidenceRecorder,
                            state: ScenarioState, summary: dict[str, object], timeout: int,
                            deploy: dict) -> None:
    """Run the complete required RO-2 behavior on a copied, verified 1004-item retained library.

    Unlike the focused scenarios, this never builds, rescans the whole library or re-prepares existing
    streams: it copies and verifies the retained sources, prepares only the 12 changed-URL increment
    controls whose baseline stream must be repaired, requires an explicitly reset empty copied fingerprint
    store for first trust, and then runs the shared ``run_full_behavior`` sequence (first trust, unchanged,
    cross-batch increment, query-stage stop, in-flight stop/drain, recovery, restart and explicit
    PlaybackInfo).
    """
    items = resolve_prepared_items(auth, fixture)
    library_id = prepared_selected_library(auth)
    fixture["sha1"], fixture["size"] = pe.media_sha1(pe.MEDIA_MP4)
    initial = capture_candidates(auth, library_id, fixture, items, recorder, "reuse-control-selection")
    assign_increment_controls(fixture, items, initial["ids"], recorder)
    control_names = fixture["url_group"] + fixture["content_group"] + fixture["size_group"]
    auth = scan.api_auth()
    wait_native_task_idle(auth, scan.SCAN_TASK_KEY)
    task, interval = scan.run_native_scan_completed(auth, "reuse increment control indexing", timeout=1800)
    recorder.record("reuse_control_scan_completed", task=task, interval=interval,
                    scope="reindex only the 12 rewritten control STRMs; library not rebuilt")
    poll_fixture_items(auth, control_names, recorder, deadline_seconds=1800)
    auth = scan.api_auth()
    items.update(resolve_prepared_items(auth, fixture))
    # Prepare only the 12 rewritten controls' baseline streams with the plugin disabled so the native
    # PlaybackInfo calls persist a primary stream without any plugin probe or fingerprint.
    require(scan.plugin_action(auth, False) == 204, "Could not disable the plugin for control preparation.")
    sampled_restart(state.sampler)
    auth = scan.api_auth()
    prepare_reuse_increment_baselines(auth, items, control_names, fixture["urls"], recorder, state.sampler)
    require(scan.plugin_action(scan.api_auth(), True) == 204, "Could not re-enable the plugin after preparation.")
    sampled_restart(state.sampler)
    auth = scan.api_auth()
    items = wait_items_by_name(auth, list(items))
    candidates = capture_candidates(auth, library_id, fixture, items, recorder, "reuse-all")
    required_ids = candidates["supported_ids"] + list(candidates["control_ids"].values())
    reconcile_candidate_identities(required_ids, candidates["ids"])
    require(canonical_guid(items[fixture["controls"]["out_of_scope"]]["Id"], "external control")
            not in candidates["ids"], "Out-of-scope control leaked into the selected library.")
    require(len(candidates["supported_ids"]) >= minimum,
            "The copied prepared library is below the required supported-source minimum.")
    expected = expected_all_rows(auth, fixture, items)
    assert_native_sources(auth, fixture, items)
    rows_before = fingerprint_map(allow_missing=True)
    require(not rows_before,
            "Reuse --scenario all needs an empty copied fingerprint store; pass --reset-copied-fingerprints.")
    capture_state(auth, fixture, items, expected, recorder, "before-first-trust", empty_fingerprints=True)
    container = pe.container_name("jellyfin")
    identity = container_identity(container)
    recorder.set_container_identity(identity)
    run_full_behavior(auth, library_id, container, fixture, items, candidates, recorder,
                      state, summary, timeout, deploy, identity)


def run_reuse_scenario(package: Path, source: Path, count: int, scenario: str,
                       evidence_dir: Path, timeout: int, reset_fingerprints: bool) -> int:
    run_id = uuid.uuid4().hex[:12]
    recorder = scan.EvidenceRecorder(evidence_dir, run_id)
    summary = {"run_id": run_id, "status": "FAIL", "focused_status": "FAIL",
               "scenario": scenario, "minimum_count": count,
               "full_task_acceptance": "NOT RUN",
               "not_run": ["increment", "query-stage-stop", "probe-stop-and-drain", "explicit-playback", "independent-B-review"]}
    require(scenario in {"baseline", "unchanged", "restart", "all"}, "Unknown focused reuse scenario.")
    require(not reset_fingerprints or scenario in {"baseline", "all"}, "Copied reset requires baseline or all scenario.")
    state = ScenarioState()
    source_before = None
    triggers = None
    previous_recorder = scan.ACTIVE_RECORDER
    previous_globals = (pe.WORK, pe.PROJECT, pe.PORT, pe.SERVICE_RESOURCE_LIMITS,
                        pe._OWNED_WORKSPACE, pe._RUN_TOKEN)
    # Distinct login device prevents shared tokens from other package tools being replaced.
    original_login = pe.login
    original_guard = pe.guard_containers
    def isolated_login(username, password):
        identity = f'MediaBrowser Client="Prepared library check", Device="isolated", DeviceId="{run_id}", Version="0.1.0"'
        status, payload = pe.request_json("POST", "/Users/AuthenticateByName",
            headers={"Authorization": identity}, body={"Username": username, "Pw": password})
        require(status == 200 and payload.get("AccessToken"), "Prepared instance login failed.")
        return identity + ', Token="' + payload["AccessToken"] + '"'
    try:
        scan.ACTIVE_RECORDER = recorder
        pe.login = isolated_login
        pe.guard_containers = require_owned_reuse_containers
        global _REUSE_EDIT_TRACKER
        _REUSE_EDIT_TRACKER = {}
        verification = pp.verify_archive(package.resolve())
        environment = system_profile()
        state.budget = RunBudget(environment, timeout)
        state.budget.check(environment)
        pe.SERVICE_RESOURCE_LIMITS = state.budget.limits
        recorder.set_metadata(command=" ".join(sys.argv), inputs={"package_sha256": verification["archiveSha256"],
                              "minimum_count": count, "scenario": scenario, "environment": environment})
        state.workspace, source_before = copy_prepared_workspace(source)
        summary["retained_workspace"] = str(state.workspace.relative_to(ROOT))
        summary["source_manifest_sha256"] = digest(json.dumps(source_before, sort_keys=True))
        pe.PROJECT += "-reuse-" + run_id
        require_owned_reuse_containers()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", pe.PORT))
        state.before_state = pe.capture_instance_state()
        if reset_fingerprints:
            reset_copied_fingerprints(recorder)
        summary["deployment"] = pe.deploy_archive(package.resolve())
        require(signal.getitimer(signal.ITIMER_REAL)[0] == 0, "Another process alarm is active.")
        state.previous_alarm_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, lambda signum, frame: state.budget.check())
        signal.setitimer(signal.ITIMER_REAL, 1, 1)
        state.instance_started = True
        startup_started = scan.now_utc()
        pe.compose("up")
        pe.wait_healthy()
        auth = scan.api_auth()
        require(scan.plugin_status(auth).lower() in {"active", "0"}, "Prepared plugin is not Active.")
        require(pkg.deployed_matches_archive(package).get("matched") is True, "Deployed package does not match ZIP.")
        state.sampler = ResourceSampler(pe.container_name("jellyfin"), recorder, state.budget)
        state.sampler.start()
        recorder.record("reuse_budget", environment=environment, limits=state.budget.limits,
                        floors=state.budget.floors, timeout_seconds=timeout)
        for service in ("jellyfin", "media"):
            recorder.set_container_identity(scan.docker_container_identity(pe.container_name(service)), component=service)
        for task in scan.task_list(auth):
            require(task.get("Key") != "RefreshLibrary" or not scan.last_start(task)
                    or dt.datetime.fromisoformat(scan.last_start(task).replace("Z", "+00:00")) < startup_started,
                    "Startup unexpectedly ran a library scan; prepared data must not be reindexed.")
            wait_native_task_idle(auth, task["Key"], timeout=min(timeout, 120))
        triggers = scan.snapshot_triggers(auth)
        for task_id in triggers:
            require(scan.set_triggers(auth, task_id, []) == 204, "Cannot suspend copied task triggers.")
        require(plugin_probe_count(pe.container_name("jellyfin"), startup_started) == 0,
                "Prepared startup unexpectedly triggered plugin probes.")
        if scenario == "all":
            run_reuse_full_scenario(auth, prepared_fixture(count), count, recorder, state, summary,
                                    timeout, summary["deployment"])
            if summary.get("status") != "PASS":
                raise RuntimeError("The retained-library full scenario did not satisfy every required stage.")
            summary.update(focused_status="PASS", full_task_acceptance="PASS", not_run=["independent-B-review"])
        else:
            summary.update(run_prepared_checks(auth, scenario, count, recorder, state, timeout))
            summary.update(status="PARTIAL", focused_status="PASS")
    except Exception as error:
        summary.update(status="FAIL", focused_status="FAIL",
                       error={"type": type(error).__name__, "message": scan._safe_exception(error)})
        recorder.record("reuse_failure", error=summary["error"])
    finally:
        if state.previous_alarm_handler is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, state.previous_alarm_handler)
        errors = []
        if state.instance_started:
            try:
                auth = scan.api_auth()
                for task in scan.task_list(auth):
                    if scan.task_state_name(task) not in {"idle", "0"}:
                        scan.stop_task(auth, task["Id"])
                        wait_native_task_idle(auth, task["Key"], timeout=300)
                if triggers is not None:
                    scan.restore_triggers(auth, triggers)
            except Exception as error:
                errors.append({"stage": "native task finalization", **scan._safe_exception(error)})
            if state.sampler is not None:
                try:
                    state.sampler.stop()
                except Exception as error:
                    errors.append({"stage": "sampling", **scan._safe_exception(error)})
            for service in ("jellyfin", "media"):
                try:
                    recorder.write_raw(f"logs/{service}.log", "\n".join(full_docker_log(pe.container_name(service))))
                except Exception as error:
                    errors.append({"stage": "logs", **scan._safe_exception(error)})
            try:
                summary["cleanup"] = stop_and_retain_reuse()
            except Exception as error:
                errors.append({"stage": "stop", **scan._safe_exception(error)})
        if state.workspace is None and pe._OWNED_WORKSPACE != previous_globals[4]:
            summary["retained_workspace"] = str(pe.WORK.relative_to(ROOT))
        if source_before is not None:
            try:
                require(prepared_manifest(source.resolve()) == source_before, "Original prepared source changed.")
                summary["source_unchanged"] = True
            except Exception as error:
                errors.append({"stage": "source integrity", **scan._safe_exception(error)})
        if state.before_state is not None:
            try:
                summary["instance_reconciliation"] = reconcile_prepared_inputs(state.before_state)
            except Exception as error:
                errors.append({"stage": "instance reconciliation", **scan._safe_exception(error)})
        if errors:
            summary.update(status="FAIL", focused_status="FAIL", finalization_errors=errors)
        pe.login = original_login
        pe.guard_containers = original_guard
        scan.ACTIVE_RECORDER = previous_recorder
        _REUSE_EDIT_TRACKER = None
        (pe.WORK, pe.PROJECT, pe.PORT, pe.SERVICE_RESOURCE_LIMITS,
         pe._OWNED_WORKSPACE, pe._RUN_TOKEN) = previous_globals
        exit_code = 0 if summary["focused_status"] == "PASS" else 1
        recorder.set_metadata(exit_code=exit_code, final_status=summary["status"])
        recorder.finish(summary["status"], summary, {})
        print(json.dumps(scan._scrub(summary), ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--reuse-workspace", type=Path, help="Stopped prepared package workspace; copied, never adopted.")
    mode.add_argument("--fresh", action="store_true", help="Explicit legacy full build; does not reuse prepared data.")
    parser.add_argument("--count", type=int, default=1000, help="Minimum supported sources; reuse keeps ALL actual sources.")
    parser.add_argument("--scenario", choices=("baseline", "unchanged", "restart", "all"))
    parser.add_argument("--reset-copied-fingerprints", action="store_true",
                        help="Explicitly archive/remove only the fresh copy fingerprint DB for baseline.")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=MAX_TASK_TIMEOUT)
    parser.add_argument("--keep-workspace", action="store_true",
                        help="Legacy --fresh option; reuse always stops and retains its copy.")
    args = parser.parse_args()
    if args.count < 1000:
        parser.error("--count must be at least 1000.")
    if args.fresh:
        if args.scenario not in (None, "all") or args.reset_copied_fingerprints:
            parser.error("--fresh only supports --scenario all and no copied-store reset.")
        args.scenario = "all"
    else:
        args.scenario = args.scenario or "unchanged"
        if args.reset_copied_fingerprints and args.scenario not in ("baseline", "all"):
            parser.error("Copied-store reset requires --scenario baseline or all.")
    if args.timeout_seconds <= 0 or args.timeout_seconds > MAX_TASK_TIMEOUT:
        parser.error(f"--timeout-seconds must be between 1 and {MAX_TASK_TIMEOUT}.")
    evidence_dir = args.evidence_dir.resolve()
    if evidence_dir.exists() and (not evidence_dir.is_dir() or any(evidence_dir.iterdir())):
        parser.error("--evidence-dir must be new or empty; prior evidence will not be overwritten.")
    if args.reuse_workspace:
        return run_reuse_scenario(args.package, args.reuse_workspace, args.count, args.scenario,
                                  evidence_dir, args.timeout_seconds, args.reset_copied_fingerprints)
    return run_scenario(args.package, args.count, evidence_dir, args.timeout_seconds, args.keep_workspace)


if __name__ == "__main__":
    raise SystemExit(main())
