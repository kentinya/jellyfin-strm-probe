#!/usr/bin/env python3
"""Run the real 1,000 or 3,000 item ZIP-installed batch acceptance scenario.

This entry owns a fresh package-environment workspace and an isolated Compose project.
It never mounts the source tree into Jellyfin, writes Jellyfin's database, or uses the
development deployment instance. Full evidence is written outside the instance.
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
import subprocess
import sys
import threading
import time
import uuid
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
    result = pe.run(*pe.DOCKER, "stats", "--no-stream", "--format",
                    "{{.MemUsage}}|{{.MemPerc}}|{{.CPUPerc}}|{{.PIDs}}", container_name, timeout=20)
    require(result.returncode == 0, "Could not sample the owned Jellyfin container resources.")
    fields = result.stdout.strip().split("|", 3)
    require(len(fields) == 4, "Docker returned an incomplete resource sample.")
    return {"memory": fields[0], "memory_percent": fields[1], "cpu_percent": fields[2], "processes": fields[3]}


class ResourceSampler:
    def __init__(self, container_name: str, recorder: scan.EvidenceRecorder) -> None:
        self.container_name = container_name
        self.recorder = recorder
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._sample, name="large-library-resource-sampler", daemon=True)
        self.failure: str | None = None

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stopped.set()
        self.thread.join(timeout=5)
        require(not self.thread.is_alive(), "Resource sampler did not stop cleanly.")
        require(self.failure is None, f"Resource sampling failed: {self.failure}.")

    def _sample(self) -> None:
        while not self.stopped.wait(1):
            try:
                self.recorder.record("resource_sample", docker_stats=docker_stats(self.container_name),
                                     host_memory=system_profile()["memory_available_bytes"])
            except Exception as error:  # Preserve sampler failure so it cannot be mistaken for a clean run.
                self.failure = type(error).__name__
                self.stopped.set()


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
    tail = LogTail(container_name, started)
    state: dict[str, object] = {"query_started_utc": None, "read_started": False,
                                "stop_status": None, "stop_requested_utc": None}
    lock = threading.Lock()
    stop_flag = threading.Event()

    def watcher() -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not stop_flag.is_set():
            try:
                lines = current_round_log_lines(tail.poll(), started)
            except Exception:
                time.sleep(0.01)
                continue
            if any("STRM_BATCH_OBJECT_READ_STARTED" in line for line in lines):
                state["read_started"] = True
            if not stop_flag.is_set() and any("STRM_BATCH_CANDIDATE_QUERY_STARTED" in line for line in lines):
                with lock:
                    if stop_flag.is_set():
                        continue
                    state["query_started_utc"] = scan.now_utc().isoformat()
                    try:
                        status = scan.stop_task(auth, task["Id"])
                    except Exception as error:  # noqa: BLE001 - recorded, never fatal
                        state["stop_status"] = f"error:{type(error).__name__}"
                    else:
                        state["stop_status"] = status
                        state["stop_requested_utc"] = scan.now_utc().isoformat()
                    stop_flag.set()
            time.sleep(0.01)

    watcher_thread = threading.Thread(target=watcher, name="query-stage-stop-watcher", daemon=True)
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
    stop_flag.set()
    watcher_thread.join(timeout=5)
    raise RuntimeError("The native batch task exceeded the fixed run timeout during the query-stage stop.")


def query_stop_observed(execution: dict, events: list[dict]) -> bool:
    """A preparation-stage stop only counts when the synchronous query actually started, the native stop was
    accepted, and no object read began; a stop that already read a batch is a late stop, not an in-query stop."""
    read_started = any(event["kind"] == "OBJECT_READ_STARTED" for event in events)
    return (execution.get("stopped") is True
            and execution.get("query_started_utc") is not None
            and execution.get("read_started") is not True
            and not read_started)


def run_task(auth: str, recorder: scan.EvidenceRecorder, timeout: int = MAX_TASK_TIMEOUT,
             *, stop_after: Callable[[dict, dict], bool] | None = None,
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
    # Choose twelve disjoint control names spread across the fixed range, then give each its own route and
    # initial metadata before any round runs. URL/content controls start with A's real SHA-1 and Size; the
    # Size control deliberately starts with no comparable SHA-1 and A's real Size.
    step = max(1, count // 13)
    indices: list[int] = []
    cursor = step
    while cursor < count and len(indices) < 12:
        if cursor not in indices:
            indices.append(cursor)
        cursor += step
    require(len(indices) == 12, "The candidate range is too small for twelve disjoint increment controls.")
    chosen = [names[index] for index in indices]
    url_group, content_group, size_group = chosen[:4], chosen[4:8], chosen[8:12]
    require(len(url_group) == 4 and len(content_group) == 4 and len(size_group) == 4,
            "The increment control groups are not the expected size.")
    for group, prefix in ((url_group, "u"), (content_group, "c"), (size_group, "s")):
        for index, name in enumerate(group):
            route = create_source_route(f"{prefix}{index}", pe.MEDIA_MP4)
            urls[name] = route
            if group is size_group:
                paths[name] = pe.write_strm(name, route, None, size)
            else:
                paths[name] = pe.write_strm(name, route, sha1, size)
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
            "url_group": url_group, "content_group": content_group, "size_group": size_group,
            "strm_dir": pe.WORK / "strm", "local_dir": pe.WORK / "media"}


def create_source_route(key: str, media_name: str) -> str:
    relative = Path("large-source") / f"{key}.mp4"
    source = pe.WORK / "media" / media_name
    target = pe.WORK / "media" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise RuntimeError("A per-source media route already exists.")
    os.link(source, target)
    return "http://media:8080/" + relative.as_posix()


def replace_source_route(url: str, media_name: str) -> None:
    from urllib.parse import urlsplit

    relative = Path(urlsplit(url).path.lstrip("/"))
    target = pe.require_owned_path(pe.WORK / "media" / relative, label="per-source media route")
    require(target.is_file() and not target.is_symlink(), "The per-source media route is not a regular owned file.")
    target.unlink()
    pe.copy_owned(pe.WORK / "media" / media_name, target, label="replace per-source media bytes")


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
    scan.refresh_library(auth)
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


def prepare_native_streams(auth: str, items: list[dict], urls: dict[str, str], recorder: scan.EvidenceRecorder) -> None:
    require(scan.plugin_action(auth, False) == 204, "Could not disable the plugin for native stream preparation.")
    scan.restart()
    auth = scan.api_auth()
    workers = min(2, len(items))
    failures: list[str] = []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="native-stream-prepare") as pool:
        futures = {pool.submit(scan.native_prepare_stream, auth, item, urls[item["Name"]], timeout=180): item for item in items}
        for future in as_completed(futures, timeout=MAX_TASK_TIMEOUT):
            item = futures[future]
            try:
                if not future.result():
                    failures.append(canonical_guid(item["Id"], "unprepared item"))
            except Exception as error:
                failures.append(f"{canonical_guid(item['Id'], 'unprepared item')}:{type(error).__name__}")
    require(not failures, f"Native stream preparation failed for {len(failures)} sources.")
    recorder.record("native_stream_preparation_completed", count=len(items), workers=workers,
                    elapsed_seconds=time.monotonic() - started)
    require(scan.plugin_action(scan.api_auth(), True) == 204, "Could not re-enable the plugin after preparation.")
    scan.restart()


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
              expected_candidate_ids: list[str] | None = None) -> dict[str, object]:
    started = scan.now_utc()
    execution = run_task(auth, recorder, timeout=timeout)
    summary_line = latest_summary_since(container, started)
    fields = require_complete_summary(summary_line)
    validate_settlement(fields, expected_candidates, expected_probes, expected_first_trust)
    events = batch_log_events(container, started)
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
                    task_execution=execution, phase_events=events,
                    candidate_identity_reconciliation=identity_reconciliation)
    recorder.snapshot(f"round-{label}-{time.time_ns()}", {"fields": fields, "task_execution": execution,
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


def seed_controlled_contents(fixture: dict[str, object], items: dict[str, dict],
                             recorder: scan.EvidenceRecorder) -> list[dict[str, object]]:
    """Apply the pre-planned increment controls: four URL changes, four content changes, four Size changes,
    plus four newly indexed supported STRMs without a saved primary stream."""
    url_group = list(fixture["url_group"])
    content_group = list(fixture["content_group"])
    size_group = list(fixture["size_group"])
    media_b = MEDIA_B_NAME
    sha_b, size_b = ensure_distinct_media_b()
    for name in url_group:
        url = create_source_route("u-change-" + uuid.uuid4().hex[:8], pe.MEDIA_MP4)
        fixture["urls"][name] = url
        pe.write_strm(name, url, fixture["sha1"], fixture["size"])
    for name in content_group:
        replace_source_route(fixture["urls"][name], media_b)
        pe.write_strm(name, fixture["urls"][name], sha_b, size_b)
    for name in size_group:
        # Same URL and still no comparable SHA-1; the route now serves B, so the changed Size is B's real size.
        replace_source_route(fixture["urls"][name], media_b)
        pe.write_strm(name, fixture["urls"][name], None, size_b)
    # Add already-indexed supported STRMs without a saved primary stream. The batch must discover and probe
    # these four sources rather than trust them as first-trust rows.
    new_names = [f"Large missing-stream {uuid.uuid4().hex[:8]} {index}" for index in range(4)]
    for offset, name in enumerate(new_names):
        url = create_source_route("m" + str(offset), pe.MEDIA_MP4)
        fixture["urls"][name] = url
        fixture["paths"][name] = pe.write_strm(name, url, fixture["sha1"], fixture["size"])
    fixture["new_names"] = new_names
    changes = ([{"kind": "url", "name": name} for name in url_group]
               + [{"kind": "content", "name": name} for name in content_group]
               + [{"kind": "size", "name": name} for name in size_group]
               + [{"kind": "missing-main-stream", "name": name} for name in new_names])
    recorder.record("increment_controls_prepared", changes=changes, expected_sha1_b=sha_b,
                    expected_size_a=fixture["size"], expected_size_b=size_b, sha1_a=fixture["sha1"])
    return changes


def run_scenario(package: Path, count: int, evidence_dir: Path, timeout: int, keep_workspace: bool) -> int:
    run_id = uuid.uuid4().hex[:12]
    recorder = scan.EvidenceRecorder(evidence_dir, run_id)
    summary: dict[str, object] = {"run_id": run_id, "count": count, "status": "FAIL"}
    workspace = None
    before_state = None
    sampler: ResourceSampler | None = None
    try:
        package = package.resolve()
        verification = pp.verify_archive(package)
        summary["package_identity"] = {"archiveSha256": verification["archiveSha256"],
                                       "version": verification["version"], "guid": verification["guid"],
                                       "targetAbi": verification["targetAbi"], "runtime": verification["runtime"],
                                       "entries": verification["entries"]}
        workspace = pe.select_workspace()
        pe.PROJECT = pe.PROJECT + "-large-" + run_id
        before_state = pe.capture_instance_state()
        environment = system_profile()
        recorder.set_metadata(command=f"python3 scripts/run_isolated_large_library_integration.py --package <zip> --count {count} --scenario all",
                              runtime={"python": sys.version.split()[0], "dotnet_sdk": json.loads((ROOT / "global.json").read_text())["sdk"]["version"],
                                       "platform": platform.platform()},
                              inputs={"package_sha256": summary["package_identity"]["archiveSha256"],
                                      "count": count, "environment": environment})
        recorder.record("host_and_budget", environment=environment,
                        limits={"task_timeout_seconds": timeout, "api_timeout_seconds": 180,
                                "native_prepare_workers": 2, "plugin_probe_default": 2,
                                "sample_seconds": 1, "progress_poll_seconds": POLL_SECONDS})

        pe.prepare_clean_instance()
        deploy = pe.deploy_archive(package)
        scan.restart()
        auth = scan.api_auth()
        require(scan.plugin_status(auth).lower() in {"active", "0"}, "The ZIP-installed plugin is not Active.")
        require(pkg.deployed_matches_archive(package).get("matched") is True,
                "The installed plugin payload does not match the tested ZIP.")
        pe.add_library_authenticated(auth, "Package Local Fixtures", ["/media/local"])
        auth = scan.api_auth()
        fixture = build_fixture(count, run_id)
        items = prepare_indexed_fixture(auth, fixture, recorder)
        strm_library_id, local_library_id = selected_library_ids(auth)
        require(strm_library_id != local_library_id, "The in-scope and out-of-scope libraries are not distinct.")
        require(scan.plugin_action(auth, False) == 204, "Could not disable the plugin before native preparation.")
        scan.restart()
        auth = scan.api_auth()
        prepare_targets = [items[name] for name in fixture["names"]]
        prepare_native_streams(auth, prepare_targets, fixture["urls"], recorder)
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
        sampler = ResourceSampler(container, recorder)
        sampler.start()
        run_timeout = min(timeout, MAX_TASK_TIMEOUT)
        round1 = run_round(auth, container, recorder, "first-trust", selected["count"], 0, count,
                           run_timeout, selected["ids"])
        auth = scan.api_auth()
        expected = expected_all_rows(auth, fixture, items)
        first_rows = fingerprint_map()
        reconciliation = reconcile_rows(expected, first_rows)
        require(first_rows.keys() == expected.keys(), "First trust created rows outside the selected supported sources.")
        recorder.record("first_trust_reconciliation", rows=reconciliation)
        round2 = run_round(auth, container, recorder, "unchanged", selected["count"], 0, 0,
                           run_timeout, selected["ids"])
        assert_native_sources(auth, fixture, items)

        changes = seed_controlled_contents(fixture, items, recorder)
        auth = scan.api_auth()
        wait_native_task_idle(auth, scan.SCAN_TASK_KEY)
        scan.refresh_library(auth)
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
        selected = capture_candidates(auth, strm_library_id, fixture, items, recorder, "before-increment")
        expected_increment_count = selected["count"]
        auth = scan.api_auth()
        changed_round = run_round(auth, container, recorder, "controlled-increment", expected_increment_count, 16, 0,
                                  run_timeout, selected["ids"])
        auth = scan.api_auth()
        increment_expected = expected_all_rows(auth, fixture, items)
        increment_rows = fingerprint_map()
        increment_reconciliation = reconcile_rows(increment_expected, increment_rows)
        recorder.record("increment_reconciliation", rows=increment_reconciliation, changes=changes)
        followup = run_round(auth, container, recorder, "post-increment-unchanged", selected["count"], 0, 0,
                             run_timeout, selected["ids"])

        # Preparation-stage stop: detect the real synchronous native-query window from phase logs and stop
        # during it. The window can be short at 1000 candidates, so the task allows up to three natural retries;
        # an unobserved window is reported NOT RUN rather than a fabricated in-query PASS.
        auth = scan.api_auth()
        query_attempts: list[dict[str, object]] = []
        candidate_start_seen = threading.Event()
        stage_stop: dict | None = None
        stage_events: list[dict[str, object]] = []
        for attempt in range(3):
            attempt_started = scan.now_utc()
            attempt_stop = run_query_stage_stop(auth, recorder, container, run_timeout)
            attempt_events = batch_log_events(container, attempt_started)
            observed = query_stop_observed(attempt_stop, attempt_events)
            query_attempts.append({"attempt": attempt + 1, "started_utc": attempt_started.isoformat(),
                                   "observed": observed,
                                   "query_started_utc": attempt_stop.get("query_started_utc"),
                                   "stop_requested_utc": attempt_stop.get("stop_requested_utc"),
                                   "stop_status": attempt_stop.get("stop_status"),
                                   "object_read_started": any(
                                       event["kind"] == "OBJECT_READ_STARTED" for event in attempt_events),
                                   "execution": attempt_stop, "events": attempt_events})
            if observed:
                candidate_start_seen.set()
                stage_stop = attempt_stop
                stage_events = attempt_events
                break
            auth = scan.api_auth()
        if candidate_start_seen.is_set():
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
        for index, (name, path) in enumerate(zip(stop_names, stop_paths, strict=True)):
            request_id = uuid.uuid4().hex
            url = f"http://media:8080/delay/20/{request_id}/{pe.MEDIA_MP4}"
            fixture["urls"][name] = url
            scan.rewrite_strm(path, url, fixture["sha1"], fixture["size"])
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
        stop_round = run_task(auth, recorder, timeout=run_timeout, stop_after=stop_after_two)
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
        recorder.record("batch_stop_reconciliation", started_ids=started_ids, events=stop_events,
                        progress=stop_round["progress"], state=scan.task_state_name(stop_round["task"]))

        # Let the first round fully settle before starting a fresh candidate query; the new round must converge.
        auth = scan.api_auth()
        idle_task = current_task(auth)
        require(scan.task_state_name(idle_task) in {"idle", "0"}, "The old batch task did not return to native Idle.")
        recovery = run_round(auth, container, recorder, "post-stop-recovery", selected["count"], 2, 0,
                             run_timeout, selected["ids"])
        auth = scan.api_auth()
        post_stop_expected = expected_all_rows(auth, fixture, items)
        post_stop_rows = fingerprint_map()
        post_stop_reconciliation = reconcile_rows(post_stop_expected, post_stop_rows)
        unchanged_a = run_round(auth, container, recorder, "post-stop-unchanged-a", selected["count"], 0, 0,
                                run_timeout, selected["ids"])
        unchanged_b = run_round(auth, container, recorder, "post-stop-unchanged-b", selected["count"], 0, 0,
                                run_timeout, selected["ids"])

        # Restart state is checked before any PlaybackInfo call can construct a missing first-trust baseline.
        pre_restart_expected = expected_all_rows(auth, fixture, items)
        pre_restart_rows = fingerprint_map()
        pre_restart_reconciliation = reconcile_rows(pre_restart_expected, pre_restart_rows)
        require(pre_restart_rows.keys() == pre_restart_expected.keys(),
                "The pre-restart database has rows outside the fixed supported source set.")
        scan.restart()
        auth = scan.api_auth()
        restarted_rows = fingerprint_map()
        restart_reconciliation = reconcile_rows(pre_restart_expected, restarted_rows)
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
        recorder.record("post_restart_explicit_playback", requests=playback_results,
                        extra_plugin_probes=extra_probes, rows=playback_reconciliation)

        sampler.stop()
        sampler = None
        summary.update({"status": "PASS", "deployment": deploy, "container_identity": identity,
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
                       "remaining_gates": {"actual_query_stage_stop": "PASS" if candidate_start_seen.is_set() else "NOT RUN"}})
        return 0
    except Exception as error:
        summary["status"] = "FAIL"
        summary["error"] = {"type": type(error).__name__, "message": scan._safe_exception(error)}
        recorder.record("failure", error=summary["error"])
        return 1
    finally:
        if sampler is not None:
            try:
                sampler.stop()
            except Exception as error:
                summary["status"] = "FAIL"
                summary["sampler_cleanup_error"] = type(error).__name__
        if before_state is not None:
            try:
                summary["instance_reconciliation"] = pe.reconcile_instance_state(before_state)
            except Exception as error:
                summary["status"] = "FAIL"
                summary["instance_reconciliation_error"] = type(error).__name__
        if workspace is not None and not keep_workspace:
            try:
                summary["cleanup"] = pe.cleanup_instance()
            except Exception as error:
                summary["status"] = "FAIL"
                summary["cleanup_error"] = type(error).__name__
        recorder.set_metadata(exit_code=0 if summary.get("status") == "PASS" else 1,
                              final_status=summary.get("status", "FAIL"))
        recorder.finish(str(summary.get("status", "FAIL")), summary, {})
        print(json.dumps(scan._scrub(summary), ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--count", type=int, choices=(1000, 3000), required=True)
    parser.add_argument("--scenario", choices=("all",), default="all")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=MAX_TASK_TIMEOUT)
    parser.add_argument("--keep-workspace", action="store_true")
    args = parser.parse_args()
    if args.timeout_seconds <= 0 or args.timeout_seconds > MAX_TASK_TIMEOUT:
        parser.error(f"--timeout-seconds must be between 1 and {MAX_TASK_TIMEOUT}.")
    evidence_dir = args.evidence_dir.resolve()
    if evidence_dir.exists() and (not evidence_dir.is_dir() or any(evidence_dir.iterdir())):
        parser.error("--evidence-dir must be new or empty; prior evidence will not be overwritten.")
    return run_scenario(args.package, args.count, evidence_dir, args.timeout_seconds, args.keep_workspace)


if __name__ == "__main__":
    raise SystemExit(main())
