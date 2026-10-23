#!/usr/bin/env python3
"""Slice 5 baseline: isolated ZIP install, self-prepared media, real native web playback.

This entry reuses the existing package environment (``package_environment``), the existing
browser driver (``package_playback_driver.mjs`` in strict mode) and the existing package
integration helpers instead of introducing a framework, environment manager, scenario DSL or
evidence system. It only adds the sequential orchestration the Slice 5 baseline needs:

  * generate the baseline fixtures with the pinned Jellyfin FFmpeg (24 s MP4/MKV H.264+AAC,
    A/B content plus byte-identical copies/aliases), record the real
    content SHA-1, byte size and ffprobe streams, and prepare limited/full/unspecified
    ColorRange videos whose actual ffprobe output is reported;
  * write version-1 video STRM files pointing at the local media server and let Jellyfin
    natively index them in its movie library;
  * with the plugin disabled, let Jellyfin itself probe and persist the necessary primary
    stream, then enable the plugin so no fingerprint exists yet;
  * per row (B01 MP4, B02 MKV) perform first trust, a second playback and a
    playback after restart, all started by a real Play click in the native web client, and
    refuse PASS unless the actual ffprobe count for the target source is zero inside each
    measurement window, both screenshots exist and are non-trivial, media time advanced by at
    least the required seconds, video reports decoded frames, the media request and the PlaybackInfo
    source/URL/primary stream match, and the
    five fingerprint fields match the fixture;
  * freeze the native URL/streams and the fingerprint before a restart and compare them
    read-only before any PlaybackInfo or playback.

Nothing here modifies plugin product code, the success predicate or the existing package
acceptance entry points.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import package_environment as pe  # noqa: E402
import package_plugin  # noqa: E402
import run_isolated_package_integration as pkg  # noqa: E402

ROOT = pe.ROOT
PLAYBACK_DRIVER = pkg.PLAYBACK_DRIVER
DOCKER = pe.DOCKER
MINIMUM_PROGRESS_SECONDS = 5.0
FIXTURE_SECONDS = 24
# F02 needs a controlled input that really cannot yield a native main stream. The first 512 bytes
# of the real A file are a strict truncation whose MP4 moov/MKV metadata is incomplete; the pinned
# image's own ffprobe rejects both containers at this length. Generation still proves the failure
# below, so a fixture that becomes probeable stops the run before any playback.
F02_CORRUPT_PREFIX_BYTES = 512
MOVIE_LIBRARY = pe.STRM_LIBRARY
FFPROBE_MARKER = 'Starting "/usr/lib/jellyfin-ffmpeg/ffprobe" with args'
FINGERPRINT_FIELDS = {"item_id", "source_key", "url_hash", "sha1", "file_size"}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MAX_WAIT = 180

# Video fixtures: testsrc2 (A) and smptebars (B) give a visibly different picture, and the drawn
# marker names the row so a screenshot can be checked against its own row.
VIDEO_FIXTURES: dict[str, dict[str, object]] = {
    "baseline-mp4-a.mp4": {"container": "mp4", "pattern": "testsrc2", "marker": "MP4 A", "tone": 440,
                           "color_range": "tv"},
    "baseline-mp4-b.mp4": {"container": "mp4", "pattern": "smptebars", "marker": "MP4 B", "tone": 880,
                           "color_range": "tv"},
    "baseline-mp4-limited.mp4": {"container": "mp4", "pattern": "testsrc2", "marker": "MP4 LIM", "tone": 440,
                                 "color_range": "tv"},
    "baseline-mp4-full.mp4": {"container": "mp4", "pattern": "testsrc2", "marker": "MP4 FULL", "tone": 440,
                              "color_range": "pc"},
    "baseline-mp4-unspecified.mp4": {"container": "mp4", "pattern": "testsrc2", "marker": "MP4 UNS", "tone": 440,
                                     "color_range": None},
    "baseline-mkv-a.mkv": {"container": "mkv", "pattern": "testsrc2", "marker": "MKV A", "tone": 440,
                           "color_range": "tv"},
    "baseline-mkv-b.mkv": {"container": "mkv", "pattern": "smptebars", "marker": "MKV B", "tone": 880,
                           "color_range": "tv"},
}
# Byte-identical copies/aliases of the A fixtures, written next to the originals.
COPY_ALIASES = {
    "baseline-mp4-a.mp4": "baseline-mp4-a-copy.mp4",
    "baseline-mkv-a.mkv": "baseline-mkv-a-copy.mkv",
}

ROWS = (
    {"id": "B01", "name": "Baseline MP4", "media_type": "video", "file": "baseline-mp4-a.mp4",
     "library": MOVIE_LIBRARY, "strm_name": "Baseline MP4"},
    {"id": "B02", "name": "Baseline MKV", "media_type": "video", "file": "baseline-mkv-a.mkv",
     "library": MOVIE_LIBRARY, "strm_name": "Baseline MKV"},
)
BASELINE_ROW_IDS = tuple(row["id"] for row in ROWS)


class BaselineError(RuntimeError):
    """A baseline precondition or acceptance check failed."""


class RowEvidenceError(BaselineError):
    """A row failed after it already reached recordable stages.

    The partial ``result`` (reached stages plus the recorded restore) is carried along so the matrix
    keeps the real HTTP statuses and read-backs of a failing row instead of replacing them with a
    bare message.
    """

    def __init__(self, message: str, result: dict) -> None:
        super().__init__(message)
        self.result = result


class ConfigurationRestoreError(RowEvidenceError):
    """A row changed server configuration and could not restore it.

    The row's own failure stays in ``result`` (with the failed restoration recorded next to it), and
    the matrix must not run later rows against a server whose configuration is still changed.
    """


class ConfigurationApplyError(BaselineError):
    """A configuration change was issued but its success could not be confirmed.

    The native write is sent before the confirming read-back, so an error here never proves the
    server kept its old value. The partially built record (the real POST status, any read-back and
    the error) travels with the exception so the row keeps that evidence and still restores the
    original value.
    """

    def __init__(self, message: str, record: dict) -> None:
        super().__init__(message)
        self.result = record


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BaselineError(message)


# ---------------------------------------------------------------------------------------------------------------------
# Pure validation helpers (unit-testable without Docker or Jellyfin)
# ---------------------------------------------------------------------------------------------------------------------


def fingerprint_fields_match(row: dict | None, *, expected_url: str, sha1: str | None, size: int | None,
                            expected_item_id: str | None = None,
                            expected_source_id: str | None = None) -> list[str]:
    """Return the reasons a fingerprint row does not match the fixture (empty means it matches).

    A ``None`` SHA-1 or size expectation means the fingerprint field must be empty/NULL (the
    manifest omitted or could not parse that optional field); a value means the parsed value must
    match, with the SHA-1 comparison case-insensitive on valid hex.
    """
    if row is None:
        return ["no fingerprint row was stored"]
    failures: list[str] = []
    if set(row) != FINGERPRINT_FIELDS:
        failures.append(f"fingerprint row fields are {sorted(row)} instead of {sorted(FINGERPRINT_FIELDS)}")
    if expected_item_id is not None and str(row.get("item_id")).lower() != _guid_hex(expected_item_id):
        failures.append("the fingerprint item id is not the item this playback belongs to")
    if expected_source_id is not None and str(row.get("source_key")).lower() != _guid_hex(expected_source_id):
        failures.append("the fingerprint source key is not the native media source of this row")
    if row.get("url_hash") != hashlib.sha256(expected_url.encode()).hexdigest():
        failures.append("the fingerprint URL hash does not match the STRM URL")
    if sha1 is None:
        if row.get("sha1"):
            failures.append(f"the fingerprint must not carry a SHA-1 for this row, saw {row.get('sha1')!r}")
    elif str(row.get("sha1") or "").lower() != sha1.lower():
        failures.append("the fingerprint SHA-1 does not match the fixture content")
    if size is None:
        if row.get("file_size") is not None:
            failures.append(f"the fingerprint must not carry a size for this row, saw {row.get('file_size')!r}")
    elif row.get("file_size") != size:
        failures.append("the fingerprint size does not match the fixture size")
    return failures


def _guid_hex(value: str) -> str:
    """Return the GUID in the 32-character form the fingerprint table stores."""
    normalized = normalize_source_id(value)
    try:
        return uuid.UUID(str(normalized)).hex
    except (ValueError, TypeError):
        return str(normalized or "").lower()


def picture_evidence_failures(entry: dict | None, media_type: str) -> list[str]:
    """Return the reasons the decoded-picture evidence is missing or degenerate.

    The screenshots themselves must still be opened and checked by a reviewer; this only proves
    that the driver decoded a real picture (a non-uniform luminance grid) at the progress point.
    """
    if media_type != "video":
        return []
    samples = [item for item in (entry or {}).get("strictObservations") or []
               if item.get("phase") == "progress"]
    if not samples:
        return ["no progress observation was recorded for the decoded picture"]
    picture = samples[-1].get("picture")
    if not isinstance(picture, dict) or picture.get("error"):
        return [f"the progress picture could not be sampled: {picture!r}"]
    grid = picture.get("grid") or []
    if len(grid) != 64:
        return [f"the progress picture grid has {len(grid)} cells instead of 64"]
    if len(set(grid)) < 3:
        return [f"the progress picture is uniform (only {len(set(grid))} distinct luminance values)"]
    if int(picture.get("distinctColors") or 0) < 4:
        return [f"the progress picture has only {picture.get('distinctColors')} distinct colours"]
    return []


def playback_request_failures(entry: dict | None, item_id: str) -> list[str]:
    """Return the reasons the real media requests cannot be attributed to this item.

    The native web client requests its media under the item identity (``/videos/<id>/...``,
    ``/audio/<id>/...``), so the recorded requests must carry this row's item id; otherwise the
    requests belong to another item and cannot be used as evidence for this playback.
    """
    normalized = normalize_source_id(item_id)
    if not normalized:
        return ["the item id needed to attribute the media requests was not recorded"]
    forms = {normalized, normalized.replace("-", "")}
    for request in (entry or {}).get("mediaRequests") or []:
        status = request.get("status")
        path = str(request.get("path") or "").lower()
        if isinstance(status, int) and status in (200, 206) and any(form in path for form in forms):
            return []
    return [f"no successful media request was attributable to item {normalized}"]


def playback_failures(entry: dict | None, *, expected_url: str, media_type: str,
                      expected_source_id: str | None = None,
                      minimum_seconds: float = MINIMUM_PROGRESS_SECONDS) -> list[str]:
    """Return the reasons a strict playback observation is not acceptable (empty means accepted)."""
    if not isinstance(entry, dict) or not entry:
        return ["no playback observation was produced"]
    failures: list[str] = []
    if entry.get("advanced") is not True:
        failures.append("the driver did not report advanced playback")
    # The contract requires the media clock to advance by at least ``minimum_seconds`` between the
    # start observation and the later one; an absolute position says nothing about how long the
    # playback actually played.
    advanced_seconds = entry.get("advancedSeconds")
    if not isinstance(advanced_seconds, (int, float)) or isinstance(advanced_seconds, bool):
        failures.append(f"media time advance {advanced_seconds!r} was not recorded")
    elif advanced_seconds < minimum_seconds:
        failures.append(f"media time advanced {advanced_seconds} s, less than {minimum_seconds} s")
    start_time = entry.get("startCurrentTime")
    if not isinstance(start_time, (int, float)) or isinstance(start_time, bool):
        failures.append(f"the start media time {start_time!r} was not recorded")
    current = entry.get("currentTime")
    if not isinstance(current, (int, float)) or isinstance(current, bool):
        failures.append(f"media time {current!r} was not recorded")
    elif isinstance(start_time, (int, float)) and not isinstance(start_time, bool) \
            and not isinstance(advanced_seconds, bool) \
            and abs((current - start_time) - (advanced_seconds if isinstance(advanced_seconds, (int, float)) else 0)) > 0.05:
        failures.append(f"media time {current!r} - start {start_time!r} does not equal the reported advance "
                        f"{advanced_seconds!r}")
    phases = {item.get("phase"): item for item in entry.get("strictObservations") or []}
    if "start" not in phases:
        failures.append("no start observation was recorded before the progress observation")
    if "progress" not in phases:
        failures.append("no progress observation was recorded")
    if entry.get("mediaErrorCode") is not None:
        failures.append(f"the media element reported error code {entry['mediaErrorCode']}")
    if entry.get("paused") is True:
        failures.append("the media element was paused at the observation point")
    if media_type == "video":
        if not entry.get("videoWidth"):
            failures.append("the video element has no decoded picture width")
        frames = entry.get("decodedFrames")
        if not isinstance(frames, int) or frames <= 0:
            failures.append(f"decoded video frames {frames!r} are not a positive count")
    elif media_type == "audio":
        # The native web client may render an audio-only stream in either element; what must not
        # happen is a decoded picture, which would mean the row played a video instead.
        if entry.get("element") not in ("audio", "video"):
            failures.append(f"audio playback used no native media element ({entry.get('element')!r})")
        if entry.get("videoWidth"):
            failures.append("audio playback decoded a video picture")
    else:
        failures.append(f"unknown media type {media_type!r}")
    for label, key in (("start", "startScreenshot"), ("progress", "progressScreenshot")):
        path = entry.get(key)
        if not path:
            failures.append(f"no {label} screenshot was captured")
            continue
        candidate = Path(path)
        if not candidate.is_file():
            failures.append(f"the {label} screenshot {candidate} does not exist")
        elif candidate.stat().st_size < 2000:
            failures.append(f"the {label} screenshot {candidate} is too small to show playback")
    requests = entry.get("mediaRequests") or []
    if not any(isinstance(item.get("status"), int) and item["status"] in (200, 206) for item in requests):
        failures.append("no successful media request was observed")
    elif entry.get("itemId"):
        failures += playback_request_failures(entry, entry["itemId"])
    failures += picture_evidence_failures(entry, media_type)
    required_stream = "Video" if media_type == "video" else "Audio"
    expected_hash = hashlib.sha256(expected_url.encode()).hexdigest()
    require_source_id = None if expected_source_id is None else normalize_source_id(expected_source_id)
    if expected_source_id is None:
        failures.append("the expected native media source id was not recorded")
    matched_source = False
    seen_source_ids: list[str] = []
    for info in entry.get("playbackInfo") or []:
        if info.get("status") != 200:
            continue
        for source in (info.get("body") or {}).get("mediaSources") or []:
            source_id = normalize_source_id(source.get("id"))
            if source_id:
                seen_source_ids.append(source_id)
            if require_source_id is not None and source_id != require_source_id:
                continue
            if source.get("pathHash") == expected_hash and required_stream in (source.get("streamTypes") or []):
                matched_source = True
    if not matched_source:
        if require_source_id is None:
            failures.append(
                f"no successful PlaybackInfo response carried the expected URL and a {required_stream} stream")
        else:
            failures.append(
                f"no successful PlaybackInfo response carried source id {require_source_id!r} with the "
                f"expected URL and a {required_stream} stream (seen source ids {sorted(set(seen_source_ids))})")
    return failures


def measurement_failures(*, phase: str, probes_before: int, probes_after: int,
                         counter_validated: bool, expected_delta: int | None = 0) -> list[str]:
    """Return the reasons the measurement window for one playback phase is not trustworthy.

    ``expected_delta`` is the ffprobe delta the contract expects inside the window (0 for skip
    rows, 1 for probe rows); ``None`` means record-only (native delegation rows report the real
    count without a zero-probe obligation).
    """
    failures: list[str] = []
    if expected_delta is None:
        return failures
    if not counter_validated:
        failures.append(f"{phase}: the ffprobe counter was never validated for this source")
    if probes_after < probes_before:
        failures.append(f"{phase}: the ffprobe counter went backwards")
    elif probes_after - probes_before != expected_delta:
        failures.append(f"{phase}: {probes_after - probes_before} ffprobe call(s) ran inside the window, "
                       f"expected {expected_delta}")
    return failures


def restart_readback_failures(frozen: dict, observed: dict) -> list[str]:
    """Return the reasons the read-only post-restart state does not match the frozen state."""
    failures: list[str] = []
    if not frozen:
        failures.append("the pre-restart state was not frozen")
        return failures
    if observed.get("fingerprint") != frozen.get("fingerprint"):
        failures.append("the stored fingerprint changed across the restart")
    if observed.get("fingerprint") is None:
        failures.append("no fingerprint was readable before or after the restart")
    # The saved media source must be compared in full: the address, the source id and every saved
    # stream field. Comparing only the set of stream types (e.g. ["Audio", "Video"]) accepted a
    # restart that changed the address, the codecs, the dimensions or the source identity.
    frozen_sources = frozen.get("nativeSources")
    observed_sources = observed.get("nativeSources")
    if not frozen_sources or not frozen_sources.get("sources"):
        failures.append("the pre-restart native media sources were not frozen")
    elif observed_sources != frozen_sources:
        failures.append("the natively saved media sources (id/address/streams) changed across the restart")
    if observed.get("strm_sha256") != frozen.get("strm_sha256"):
        failures.append("the STRM file changed across the restart")
    if observed.get("probe_count") != frozen.get("probe_count"):
        failures.append("the read-only post-restart read performed an ffprobe call")
    return failures


# ---------------------------------------------------------------------------------------------------------------------
# Environment, logging and server-side observations
# ---------------------------------------------------------------------------------------------------------------------


def run(*args: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return pe.run(*args, timeout=timeout)


# ---------------------------------------------------------------------------------------------------------------------
# Run-scoped environment adaptation: explicit Compose subnets
#
# The Docker daemon on this host has every predefined address pool fully subnetted by bridge
# networks left behind by earlier runs, so a plain ``docker compose up`` fails with "all
# predefined address pools have been fully subnetted". Per the documented development-server
# practice this run gives only its own two Compose networks explicit, non-overlapping /28
# subnets instead of pruning or deleting retained networks and instead of changing the shared
# environment tooling. ``acceptance`` stays internal.
# ---------------------------------------------------------------------------------------------------------------------

SUBNET_SPACE = "10.253.0.0/16"


def _ip_to_int(value: str) -> int:
    parts = [int(part) for part in value.split(".")]
    require(len(parts) == 4 and all(0 <= part <= 255 for part in parts), f"Invalid IPv4 address {value!r}.")
    return (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]


def _int_to_ip(value: int) -> str:
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def subnet_bounds(cidr: str) -> tuple[int, int]:
    """Return the inclusive [first, last] address range of an IPv4 CIDR block."""
    address, _, prefix = cidr.partition("/")
    require(prefix.isdigit() and 0 <= int(prefix) <= 32, f"Invalid CIDR {cidr!r}.")
    bits = int(prefix)
    size = 1 << (32 - bits)
    first = _ip_to_int(address) & ~(size - 1) & 0xFFFFFFFF
    return first, first + size - 1


def choose_free_subnets(used: list[str], count: int = 2, space: str = SUBNET_SPACE,
                        prefix: int = 28) -> list[str]:
    """Return ``count`` non-overlapping /prefix blocks inside ``space`` that touch no ``used`` range."""
    occupied = [subnet_bounds(cidr) for cidr in used if cidr]
    space_first, space_last = subnet_bounds(space)
    size = 1 << (32 - prefix)
    chosen: list[str] = []
    candidate = space_first
    while candidate + size - 1 <= space_last and len(chosen) < count:
        last = candidate + size - 1
        if not any(candidate <= used_last and used_first <= last for used_first, used_last in occupied):
            chosen.append(f"{_int_to_ip(candidate)}/{prefix}")
            occupied.append((candidate, last))
        candidate += size
    require(len(chosen) == count,
            f"Could not find {count} free /{prefix} subnets inside {space}; refusing to reuse an occupied range.")
    return chosen


def existing_subnets() -> list[str]:
    """Every IPv4 subnet known to Docker plus every host route, so a chosen range never overlaps."""
    found: list[str] = []
    listed = run(*DOCKER, "network", "ls", "-q", timeout=120)
    require(listed.returncode == 0, "Could not list the Docker networks for the subnet check.")
    ids = listed.stdout.split()
    if ids:
        inspected = run(*DOCKER, "network", "inspect", *ids, timeout=120)
        require(inspected.returncode == 0, "Could not inspect the Docker networks for the subnet check.")
        for network in json.loads(inspected.stdout):
            for config in (network.get("IPAM") or {}).get("Config") or []:
                if config.get("Subnet"):
                    found.append(str(config["Subnet"]))
    routes = run("ip", "-4", "route", timeout=60)
    if routes.returncode == 0:
        for line in routes.stdout.splitlines():
            for token in line.split():
                if "/" in token and token[0].isdigit():
                    found.append(token)
    return found


def inject_subnets(text: str, subnets: dict[str, str]) -> str:
    """Add an explicit ``ipam`` block to the named networks of a generated compose file."""
    lines = text.splitlines()
    try:
        index = lines.index("networks:")
    except ValueError:
        raise BaselineError("The generated compose file has no networks section.") from None
    rebuilt = list(lines[: index + 1])
    for line in lines[index + 1:]:
        stripped = line.strip()
        if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
            name = stripped[:-1]
            rebuilt.append(line)
            if name in subnets:
                rebuilt += ["    ipam:", "      config:", f'        - subnet: "{subnets[name]}"']
            continue
        rebuilt.append(line)
    return "\n".join(rebuilt) + "\n"


def install_explicit_subnets() -> dict:
    """Adapt only this run's Compose networks when the default Docker pools are exhausted."""
    used = existing_subnets()
    try:
        chosen = choose_free_subnets(used, 2)
    except BaselineError:
        return {"applied": False, "reason": "no free /28 block inside the adaptation space"}
    mapping = {"acceptance": chosen[0], "frontend": chosen[1]}
    original = pe.write_compose

    def patched() -> Path:
        path = original()
        text = path.read_text(encoding="utf-8")
        pe.write_owned_bytes(path, inject_subnets(text, mapping).encode("utf-8"),
                             label="compose file with explicit subnets")
        return path

    pe.write_compose = patched  # run-scoped adaptation of this process only
    return {"applied": True, "subnets": mapping, "usedRangesChecked": len(used),
            "reason": "the Docker daemon reported all predefined address pools fully subnetted"}


def enable_probe_logging() -> dict:
    """Enable the pinned server's own ffprobe debug lines so probe counts come from real processes.

    This is logging configuration only: it does not change probing, persistence or playback.
    """
    target = pe.WORK / "config" / "config" / "logging.json"
    body = {
        "Serilog": {
            "MinimumLevel": {
                "Default": "Information",
                "Override": {"Microsoft": "Warning", "System": "Warning",
                             "MediaBrowser.MediaEncoding": "Debug",
                             "MediaBrowser.Providers": "Debug"},
            }
        }
    }
    pe.write_owned_bytes(target, (json.dumps(body, indent=2) + "\n").encode("utf-8"), label="logging override")
    return {"path": str(target), "override": body["Serilog"]["MinimumLevel"]["Override"]}


def server_log_lines() -> list[str]:
    log_dir = pe.WORK / "config" / "log"
    lines: list[str] = []
    for path in sorted(log_dir.glob("log_*.log")):
        lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return lines


def archive_evidence(evidence_dir: Path, name: str, content: str) -> str:
    """Write one original run artifact next to the other evidence (never inside the workspace).

    The evidence directory is run-independent: the workspace cleanup cannot remove it, so a first
    failure stays available even when the instance is stopped afterwards. Paths are absolute.
    """
    target = evidence_dir / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)


def archive_server_logs(evidence_dir: Path) -> list[str]:
    """Copy this run's complete original Jellyfin server logs next to the other evidence."""
    log_dir = pe.WORK / "config" / "log"
    written: list[str] = []
    for path in sorted(log_dir.glob("log_*.log")):
        target = evidence_dir / "server-logs" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        written.append(str(target))
    return written


def archive_media_logs() -> list[dict]:
    """Return this run's original media-container request/range log lines with their counts."""
    logs = run(*DOCKER, "logs", pe.container_name("media"), timeout=120)
    lines = (logs.stdout + logs.stderr).splitlines()
    counts: dict[str, int] = {}
    for line in lines:
        match = re.search(r"MEDIA_REQUEST (\w+) (\S+)", line)
        if match:
            key = f"{match.group(1)} {match.group(2)}"
            counts[key] = counts.get(key, 0) + 1
    return {"lineCount": len(lines), "requestCounts": counts, "lines": lines}


def probe_count(url: str) -> int:
    """Count the pinned server's real ffprobe process starts for exactly this media URL.

    The pinned server logs ``Starting "<ffprobe>" with args "... -i \\"<url>\\" ..."``, so the URL
    appears wrapped in escaped quotes inside the argument string. Requiring the closing quote (or
    the end of the operand) means a longer path that has this URL as a prefix is never counted, and
    only ffprobe starts are counted (never ffmpeg media reads or the ffmpeg capability probe).
    """
    quoted = '-i \\"' + url + '\\"'
    candidates = (quoted + " ", quoted, " -i " + url + " ", " -i " + url + '\\"')
    return sum(1 for line in server_log_lines()
               if FFPROBE_MARKER in line and any(candidate in line for candidate in candidates))


def plugin_event_lines() -> list[str]:
    return [line for line in server_log_lines() if pkg.PLUGIN_LOGGER in line]


def plugin_event_delta(before: list[str]) -> list[str]:
    return [pkg.safe_event(line) for line in pkg.event_delta(before, plugin_event_lines())]


def media_server_requests() -> dict[str, int]:
    """Return {filename: GET count} from this run's own media container log."""
    logs = run(*DOCKER, "logs", pe.container_name("media"), timeout=120)
    counts: dict[str, int] = {}
    for line in (logs.stdout + logs.stderr).splitlines():
        match = re.search(r"MEDIA_REQUEST (\w+) (\S+)", line)
        if match:
            key = f"{match.group(1)} {match.group(2)}"
            counts[key] = counts.get(key, 0) + 1
    return counts


def media_request_delta(before: dict[str, int], after: dict[str, int], filename: str) -> int:
    key = "GET " + filename
    return after.get(key, 0) - before.get(key, 0)


def fingerprint_row_for_item(auth: str, item_id: str, source_id: str | None = None) -> dict | None:
    """Read the stored fingerprint for this item and its currently saved native source key.

    The physical source id can change (a native scan re-keys it), so the source key is resolved
    from the current native source set and the row is read for that exact (item, source) pair;
    the item id is never reused as a stand-in source id.
    """
    key = source_id or current_source_key(auth, item_id)
    if key is None:
        return None
    return fingerprint_row_or_none(item_id, key)


def fingerprint_row_or_none(item_id: str, source_id: str) -> dict | None:
    if not pkg.fingerprint_database().is_file():
        return None
    return pkg.fingerprint_row(item_id, source_id)


def normalize_source_id(value: object) -> str | None:
    """Normalize a native MediaSource id to the dashed GUID form the plugin stores."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return str(uuid.UUID(text))
    except ValueError:
        return text.lower()


# The complete native stream objects are kept in the snapshot (see native_source_snapshot); this
# tuple remains only as the documented field of interest for the C-row ColorRange comparison.
COLOR_FIELDS = ("Type", "Index", "Codec", "Width", "Height", "SampleRate", "Channels",
                "BitRate", "ColorRange", "ColorSpace", "ColorTransfer", "ColorPrimaries",
                "IsDefault", "Language", "Profile", "Level", "BitDepth", "RefFrames")
# Only this run's own synthetic fixture locations are echoed into the evidence; every other path is
# kept only as a hash so no private library path can leak into a log or an index file.
SAFE_PATH_PREFIXES = ("http://media:", "/media/strm/", "/media/local/")


def safe_path(value: object) -> str | None:
    text = str(value or "")
    return text if text.startswith(SAFE_PATH_PREFIXES) else None


def native_source_snapshot(auth: str, item_id: str) -> dict:
    """Read the saved native sources and the item address through a read-only native query.

    ``GET /Items/{id}?Fields=MediaSources,MediaStreams,Path`` is the same read-only item query the
    accepted scan/large tooling already uses; it performs no probing and no refresh. The complete
    per-source identity, address and stream fields are kept so a restart comparison is not limited
    to the set of stream types.
    """
    status, payload = pe.request_json(
        "GET", f"/Items/{item_id}?Fields=MediaSources,MediaStreams,Path",
        headers={"Authorization": auth})
    require(status == 200, "The read-only native media-source query failed.")
    sources = []
    for source in payload.get("MediaSources") or []:
        path = str(source.get("Path") or "")
        # The complete native stream objects are kept verbatim (no field projection): a restart
        # comparison must catch a change in any saved stream field, and the C-row three-stage
        # evidence needs the full PrimaryStreamIdentity round trip, not an 11-field subset.
        streams = [{"Type": stream.get("Type"), "fields": dict(stream)}
                   for stream in (source.get("MediaStreams") or [])]
        sources.append({
            "id": normalize_source_id(source.get("Id")),
            "pathHash": hashlib.sha256(path.encode()).hexdigest(),
            "path": safe_path(path),
            "protocol": source.get("Protocol"),
            "container": source.get("Container"),
            "runTimeTicks": source.get("RunTimeTicks"),
            "size": source.get("Size"),
            "streams": sorted(streams, key=lambda item: (str(item.get("Type")), item["fields"].get("Index") or 0)),
        })
    sources.sort(key=lambda source: str(source.get("id")))
    return {"itemId": normalize_source_id(payload.get("Id")), "itemPath": safe_path(payload.get("Path")),
            "itemPathHash": hashlib.sha256(str(payload.get("Path") or "").encode()).hexdigest(),
            "sources": sources}


def current_source_key(auth: str, item_id: str) -> str | None:
    """Return the single stored native source id of an item (resolved without any PlaybackInfo)."""
    status, payload = pe.request_json(
        "GET", f"/Items/{item_id}?Fields=MediaSources",
        headers={"Authorization": auth})
    require(status == 200, "The read-only native source-id query failed.")
    ids = [normalize_source_id(source.get("Id")) for source in payload.get("MediaSources") or []]
    ids = [value for value in ids if value]
    require(len(ids) == 1, f"Expected exactly one native media source, found {ids}.")
    return ids[0]


def saved_stream_types(auth: str, item_id: str) -> list[str]:
    status, payload = pe.request_json("GET", f"/Items/{item_id}?Fields=MediaStreams",
                                      headers={"Authorization": auth})
    require(status == 200, "The saved-stream read failed.")
    return sorted({stream.get("Type") for stream in payload.get("MediaStreams", [])})


def item_media_type(auth: str, item_id: str) -> dict:
    status, payload = pe.request_json("GET", f"/Items/{item_id}", headers={"Authorization": auth})
    require(status == 200, "The item read failed.")
    return {"MediaType": payload.get("MediaType"), "Type": payload.get("Type"), "Path": payload.get("Path"),
            "Name": payload.get("Name")}


def raw_item_query(auth: str, name: str, item_path: str | None = None) -> dict:
    """Return the raw native item-search evidence without collapsing the failure into a timeout.

    The row is located by its unique STRM path; ``name`` is the row's STRM file name (without
    extension). Every query answer — status, the listing, the match and its native server log tail
    — is recorded and raised with the actual evidence attached, never collapsed into a timeout.
    """
    started = time.monotonic()
    attempts: list[dict] = []
    deadline = started + MAX_WAIT
    strm_path = item_path or ("/media/strm/" + name + ".strm")
    while time.monotonic() < deadline:
        stamp = round(time.monotonic() - started, 1)
        # The row is identified by its STRM path, never by the item name: the native library naming
        # strips suffix words ("... limited" became "Matrix MP4 C02") so a name-based lookup cannot
        # address every row. The path is unique per row and survives every naming rule.
        status, payload = pe.request_json(
            "GET", "/Items?" + urllib.parse.urlencode(
                {"Recursive": "true", "Limit": "200", "Fields": "MediaSources,Path"}),
            headers={"Authorization": auth})
        if status == 200:
            items = payload.get("Items", [])
            matches = [item for item in items if item.get("Path") == strm_path]
            attempt: dict = {"at": stamp, "status": status,
                             "listedItems": [{"id": item.get("Id"), "name": item.get("Name"),
                                              "type": item.get("Type"),
                                              "path": safe_path(item.get("Path"))} for item in items][:20],
                             "matchingIds": [item.get("Id") for item in matches]}
            if len(matches) == 1:
                attempts.append(attempt)
                return {"status": "FOUND", "elapsedSeconds": round(time.monotonic() - started, 1),
                        "attempts": attempts, "item": matches[0]}
            if len(matches) > 1:
                attempts.append(attempt)
                raise BaselineError(
                    f"The native library returned {len(matches)} items for {strm_path!r} "
                    f"(ids {[item.get('Id') for item in matches]}); refusing to guess the row's item. "
                    f"Raw query attempts {json.dumps(attempts, ensure_ascii=False)}")
            attempts.append(attempt)
        else:
            attempts.append({"at": stamp, "status": status, "body": payload})
        time.sleep(2)
    log_tail = server_log_lines()[-80:]
    raise BaselineError(
        f"The package instance did not scan the row STRM {strm_path!r} within {MAX_WAIT}s; "
        f"raw query attempts {json.dumps(attempts, ensure_ascii=False)}; "
        f"server log tail {json.dumps(log_tail, ensure_ascii=False)}")


def add_library(auth_header: str, name: str, collection_type: str, paths: list[str]) -> None:
    """Create a library through the same native endpoint the package environment uses."""
    body = {"LibraryOptions": {"EnableInternetProviders": False, "EnableRealtimeMonitor": False,
                               "SaveLocalMetadata": False, "PathInfos": [{"Path": p} for p in paths]}}
    query = f"name={urllib.parse.quote(name)}&collectionType={collection_type}&refreshLibrary=true"
    query += "".join(f"&paths={urllib.parse.quote(p)}" for p in paths)
    status, _ = pe.request_json("POST", "/Library/VirtualFolders?" + query, body=body,
                                headers={"Authorization": auth_header})
    require(status in (200, 204), f"Adding the library {name!r} failed with HTTP {status}.")


# ---------------------------------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------------------------------


def ffmpeg(command: list[str], timeout: int = 240) -> subprocess.CompletedProcess[str]:
    result = run(*DOCKER, "run", "--rm", "--entrypoint", "/usr/lib/jellyfin-ffmpeg/ffmpeg",
                 "-v", f"{pe.WORK / 'media'}:/out", pe.load_image_lock()["server"], *command, timeout=timeout)
    return result


def ffprobe(path_in_container: str) -> dict:
    result = run(*DOCKER, "run", "--rm", "--entrypoint", "/usr/lib/jellyfin-ffmpeg/ffprobe",
                 "-v", f"{pe.WORK / 'media'}:/out", pe.load_image_lock()["server"],
                 "-v", "error", "-print_format", "json", "-show_streams", "-show_format",
                 path_in_container, timeout=120)
    require(result.returncode == 0, f"ffprobe failed for {path_in_container}: {result.stderr.strip()[-300:]}")
    return json.loads(result.stdout)


def fixture_ffmpeg_args(spec: dict[str, object], name: str) -> list[str]:
    """The real encode arguments for one fixture, chosen for the actual ffprobe color_range output.

    The measured behaviour of the pinned FFmpeg decides the plan, never the generation parameter:
    a bare MP4 encode drops the h264 VUI range flags (ffprobe color_range None even with
    ``-color_range tv``), so the limited input needs the full bt709 triple; an MKV muxer labels an
    unmarked stream "tv" on its own, so an unspecified MKV must be remuxed from a VUI-less MP4
    encode; "pc" carries through directly in both containers.
    """
    duration = int(spec.get("seconds", FIXTURE_SECONDS))
    args = ["-y", "-f", "lavfi", "-i",
            f"{spec['pattern']}=duration={duration}:size=320x180:rate=15",
            "-f", "lavfi", "-i", f"sine=frequency={spec['tone']}:duration={duration}"]
    chain: list[str] = []
    if spec.get("noise"):
        # The P06 "up" partner must be a genuinely longer file, not merely a longer duration: a
        # static smptebars source encodes to fewer bytes than the shorter A clip. Real per-frame
        # noise raises the encoded size at the same resolution/duration, and stays decodable.
        chain.append(str(spec["noise"]))
    chain.append(f"drawtext=fontfile={FONT}:text='{spec['marker']}':fontsize=48:fontcolor=white:"
                 "x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.5")
    filters = ",".join(chain)
    args += ["-vf", filters, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if spec["color_range"] == "pc":
        args += ["-color_range", "pc"]
    elif spec["color_range"] == "tv":
        args += ["-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709",
                 "-color_trc", "bt709"]
    args += ["-c:a", "aac", "-b:a", "96k", "-shortest", "-t", str(duration)]
    if spec["container"] == "mp4":
        # Put moov at the front so the real browser can start decoding without downloading the
        # rest of the file before its first media request.
        args += ["-movflags", "+faststart"]
    args += ["/out/" + name]
    return args


def encode_fixture(spec: dict[str, object], name: str) -> list[list[str]]:
    """Generate one fixture with the pinned FFmpeg, remuxing when the container cannot stay unmarked."""
    if spec["container"] == "mkv" and spec["color_range"] is None:
        # MKV muxing itself marks an unmarked h264 stream "tv"; only a remux from a VUI-less MP4
        # encode keeps the color_range genuinely absent from the actual output.
        intermediate = "__enc-" + name + ".mp4"
        encode = dict(spec, container="mp4")
        first = fixture_ffmpeg_args(encode, intermediate)
        result = ffmpeg(first)
        require(result.returncode == 0, f"Could not generate {intermediate}: {result.stderr.strip()[-300:]}")
        remux = ["-y", "-i", "/out/" + intermediate, "-c", "copy", "/out/" + name]
        result = ffmpeg(remux)
        require(result.returncode == 0, f"Could not remux {name}: {result.stderr.strip()[-300:]}")
        return [first, remux]
    args = fixture_ffmpeg_args(spec, name)
    result = ffmpeg(args)
    require(result.returncode == 0, f"Could not generate {name}: {result.stderr.strip()[-300:]}")
    return [args]


def require_actual_color_range(name: str, spec: dict[str, object], streams: list[dict]) -> None:
    """Refuse a fixture whose actual ffprobe color_range does not match the scenario it names.

    The generation parameters prove nothing: an input generated with ``-color_range tv`` can
    still probe as unspecified, and an MKV muxer can label an unmarked stream "tv". The real
    output must carry tv/pc/nothing exactly as the C-row contract requires, or the fixture set is
    wrong and the run stops before any playback is claimed.
    """
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    require(videos, f"{name}: no video stream was probeable; the ColorRange input is unusable.")
    actual = videos[0].get("color_range")
    expected = {"tv": "tv", "pc": "pc", None: None}[spec["color_range"]]
    require(actual == expected,
            f"{name}: the actual ffprobe video color_range is {actual!r}, not the required {expected!r}; "
            f"the fixture does not match its scenario and no C-row may use it.")


def generate_fixtures() -> dict:
    """Generate the baseline media with the pinned Jellyfin FFmpeg and record real identities."""
    pe.workspace()
    commands: dict[str, list[str]] = {}
    for name, spec in VIDEO_FIXTURES.items():
        commands[name] = encode_fixture(spec, name)
    aliases: dict[str, str] = {}
    for source, alias in COPY_ALIASES.items():
        target = pe.WORK / "media" / alias
        target.parent.mkdir(parents=True, exist_ok=True)
        pe.copy_owned(pe.WORK / "media" / source, target, label=f"byte-identical copy {alias}")
        aliases[alias] = source
    fixture_names = [*VIDEO_FIXTURES, *aliases]
    fixtures: dict[str, dict] = {}
    for name in fixture_names:
        path = pe.WORK / "media" / name
        data = path.read_bytes()
        info = ffprobe("/out/" + name)
        streams = [{key: stream.get(key) for key in
                    ("index", "codec_type", "codec_name", "width", "height", "pix_fmt", "color_range",
                     "sample_rate", "channels", "duration", "disposition")}
                   for stream in info.get("streams", [])]
        # The scenario a fixture names is only acceptable when the real output matches it; a
        # mislabelled ColorRange input must stop the run before any C-row can claim evidence.
        # Byte-identical aliases keep the source fixture's spec; they have no entry of their own.
        require_actual_color_range(name, VIDEO_FIXTURES.get(name, VIDEO_FIXTURES[aliases.get(name, name)]),
                                   streams)
        fixtures[name] = {
            "sha1": hashlib.sha1(data).hexdigest(),
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "ffprobe": {"format": info.get("format", {}).get("format_name"),
                        "duration": info.get("format", {}).get("duration"),
                        "size": info.get("format", {}).get("size"),
                        "streams": streams},
        }
    for alias, source in aliases.items():
        require(fixtures[alias]["sha256"] == fixtures[source]["sha256"],
                f"The copy {alias} is not byte-identical to {source}.")
    return {"commands": commands, "fixtures": fixtures, "aliases": aliases,
            "durationSeconds": FIXTURE_SECONDS}


def write_row_strm(row: dict, fixture: dict) -> dict:
    """Write the version-1 STRM for one row and return its identity."""
    require(row["media_type"] == "video", "Audio STRM rows are outside the current Slice 5 contract.")
    url = f"http://media:8080/{row['file']}"
    target = pe.WORK / "strm" / (row["strm_name"] + ".strm")
    lines = ["# strm-probe-version:1", f"# strm-probe-sha1:{fixture['sha1']}",
             f"# strm-probe-size:{fixture['size']}", url]
    pe.write_owned_bytes(target, ("\n".join(lines) + "\n").encode("utf-8"), label=f"STRM {row['id']}")
    return {"path": str(target), "url": url, "sha1": fixture["sha1"], "size": fixture["size"],
            "contentSha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "content": "\n".join(lines)}


# ---------------------------------------------------------------------------------------------------------------------
# Playback measurement
# ---------------------------------------------------------------------------------------------------------------------


def credentials() -> dict:
    return json.loads(pe.credentials_path().read_text(encoding="utf-8"))


def play_once(auth: str, row: dict, phase: str, evidence_dir: Path, relax_console: bool = False) -> dict:
    """Start one real native web playback and capture every measurement for the phase.

    ``relax_console`` is used only for the intentionally-failing F rows, where a failed media
    request is the expected state and its console noise must not abort the capture.
    """
    phase_dir = evidence_dir / row["id"] / phase
    phase_dir.mkdir(parents=True, exist_ok=True)
    item = row["item"]
    url = row["url"]
    # The media-request counter must watch the file the phase's own URL serves: a URL-change row
    # reads its old file during trust and its new file after the manifest switched, so the phase
    # URL (query stripped) is the only correct per-phase key.
    filename = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
    before_probes = probe_count(url)
    before_events = plugin_event_lines()
    before_media = media_server_requests()
    scenario = {
        "baseUrl": credentials()["base_url"],
        "username": credentials()["username"],
        "password": credentials()["password"],
        "strict": {"minimumSeconds": MINIMUM_PROGRESS_SECONDS,
                   "screenshotDir": str(phase_dir / "screenshots")},
        "items": [{"name": row["name"], "id": item["Id"], "mediaType": row["media_type"]}],
    }
    result = pkg.run_browser_driver(PLAYBACK_DRIVER, scenario, phase_dir, timeout=420)
    console_errors = [] if relax_console else pkg.unexpected_console_errors(result)
    entries = result.get("results") or []
    entry = entries[0] if len(entries) == 1 else {}
    # Let the server's asynchronous log sink and the media container flush before counting.
    time.sleep(2)
    # The driver's own login invalidates the API token this run handed out before the playback
    # (a fresh AuthenticateByName revokes the previous access token), so the read-only observation
    # queries authenticate again instead of failing with an unrelated HTTP 500/401.
    auth = refresh_auth()
    after_probes = probe_count(url)
    after_media = media_server_requests()
    events = plugin_event_delta(before_events)
    read_errors: dict[str, str] = {}
    def read_state(name, operation, missing):
        try:
            return operation()
        except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            read_errors[name] = type(error).__name__
            return missing

    fingerprint = read_state("fingerprint", lambda: fingerprint_row_for_item(auth, item["Id"], row["sourceKey"]), None)
    native_sources = read_state("nativeSources", lambda: native_source_snapshot(auth, item["Id"]), {})
    # The driver's own record of the client playback stop: the pinned web client reports
    # ``Sessions/Playing/Stopped`` from the OSD page's viewbeforehide handler and the app-close
    # handler, and the server turns that report into KillTranscodingJobs. Without it the owned
    # transcode job outlived the window and the owned instance's stop hit the compose grace period.
    playback_stop = entry.get("playbackStop") if isinstance(entry, dict) else None
    observation = {
        "row": row["id"], "phase": phase, "itemId": item["Id"], "expectedSourceId": row["sourceKey"],
        "url": url,
        "playback": entry, "consoleErrors": console_errors,
        "playbackStop": playback_stop,
        "pluginEvents": events,
        "pluginProbeCalls": [pkg.probe_calls(event) for event in events],
        "ffprobe": {"before": before_probes, "after": after_probes, "delta": after_probes - before_probes},
        "mediaServerRequests": {"before": before_media.get("GET " + filename, 0),
                                "after": after_media.get("GET " + filename, 0),
                                "delta": media_request_delta(before_media, after_media, filename)},
        "fingerprint": fingerprint,
        "nativeSources": native_sources,
        "readErrors": read_errors,
    }
    (phase_dir / "observation.json").write_text(json.dumps(observation, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    require("error" not in result, f"{row['id']} {phase}: the browser driver failed: {result.get('error')}")
    require(result.get("strict") is True, f"{row['id']} {phase}: the driver did not run in strict mode.")
    require(not console_errors, f"{row['id']} {phase}: unexpected console errors {console_errors}")
    require(len(entries) == 1, f"{row['id']} {phase}: expected exactly one playback result.")
    require(not read_errors, f"{row['id']} {phase}: read-only state unavailable: {read_errors}")
    return observation


def playback_stop_failures(entry: dict | None, playback_stop: dict | None) -> list[str]:
    """Return the reasons the client playback stop was not completed by the client itself.

    The contract's playback evidence does not change: a window is judged on its measurement. This
    check only refuses a window whose playback was left running, because the owned instance would
    then be stopped with a live transcode job and the owned shutdown would be killed by the compose
    grace period instead of completing natively.
    """
    if not isinstance(entry, dict) or entry.get("advanced") is not True:
        # A window that never started a playback has nothing to stop; its own failure stands.
        return []
    if not isinstance(playback_stop, dict) or not playback_stop:
        return ["the client playback stop was not recorded"]
    if playback_stop.get("stopReported") is not True:
        return [f"the client never reported its playback stop (attempts {playback_stop.get('attempts')!r})"]
    statuses = playback_stop.get("stopStatuses") or []
    if not any(status == 204 for status in statuses):
        return [f"the client playback stop was not accepted natively (statuses {statuses!r})"]
    return []


def assert_playback(row: dict, observation: dict, *, counter_validated: bool,
                    expected_delta: int | None = 0, allow_missing_media_fetch: bool = False,
                    url_for_source: str | None = None,
                    expected_source_url: str | None = None) -> None:
    """Accept one successful strict playback window.

    ``expected_delta`` is the contract ffprobe expectation for the window; ``url_for_source`` is
    the URL the saved source must carry after a probe window moved the address (P02 rows);
    ``expected_source_url`` overrides the PlaybackInfo URL identity check (D04 local media).
    """
    phase = observation["phase"]
    source_url = expected_source_url or url_for_source or observation["url"]
    failures = playback_failures(observation["playback"], expected_url=source_url,
                                 media_type=row["media_type"],
                                 expected_source_id=observation.get("expectedSourceId"))
    failures += measurement_failures(phase=f"{row['id']} {phase}",
                                     probes_before=observation["ffprobe"]["before"],
                                     probes_after=observation["ffprobe"]["after"],
                                     counter_validated=counter_validated,
                                     expected_delta=expected_delta)
    if not allow_missing_media_fetch and observation["mediaServerRequests"]["delta"] < 1:
        failures.append(f"{row['id']} {phase}: the server never fetched the fixture from the media service")
    failures += playback_stop_failures(observation["playback"], observation.get("playbackStop"))
    # The saved source set after the playback must still carry the expected source id, the expected
    # address and the required stream; a playback that silently resolved another source is refused.
    sources = (observation.get("nativeSources") or {}).get("sources") or []
    expected_id = normalize_source_id(observation.get("expectedSourceId"))
    expected_hash = hashlib.sha256(source_url.encode()).hexdigest()
    required = "Video" if row["media_type"] == "video" else "Audio"
    matched = [source for source in sources if source.get("id") == expected_id]
    if expected_id is None:
        failures.append(f"{row['id']} {phase}: the expected native source id was not recorded")
    elif not matched:
        failures.append(f"{row['id']} {phase}: the saved native sources {[s.get('id') for s in sources]} "
                        f"do not contain the expected source {expected_id}")
    else:
        source = matched[0]
        if source.get("pathHash") != expected_hash:
            failures.append(f"{row['id']} {phase}: the saved source address is not the expected URL")
        stream_types = {stream.get("Type") for stream in source.get("streams") or []}
        if required not in stream_types:
            failures.append(f"{row['id']} {phase}: the saved source has no {required} stream ({sorted(stream_types)})")
    require(not failures, "; ".join(failures))


def _strm_sha256(row: dict):
    path = row.get("path")
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None


def freeze_state(auth: str, row: dict) -> dict:
    # Web Play logs in independently and revokes the journey's older API token. Freeze
    # through a fresh login, as play_once already does for its read-only observations.
    auth = refresh_auth()
    item = row["item"]
    return {
        "fingerprint": fingerprint_row_for_item(auth, item["Id"], row.get("sourceKey")),
        "nativeSources": native_source_snapshot(auth, item["Id"]),
        "strm_sha256": _strm_sha256(row),
        "probe_count": probe_count(row["url"]),
    }


def refresh_auth() -> str:
    """Re-authenticate for the next native request boundary and return the token locally.

    The browser driver logs in with its own session and revokes the API token the run handed out
    before the playback, so every native request that follows a real Web Play must authenticate
    again instead of reusing the revoked token. The token stays a local value: it is never placed
    into an evidence or result object, and a request that still fails keeps failing.
    """
    return pkg.api_auth()


def read_only_state(auth: str, row: dict) -> dict:
    item = row["item"]
    return {
        "fingerprint": fingerprint_row_for_item(auth, item["Id"], row.get("sourceKey")),
        "nativeSources": native_source_snapshot(auth, item["Id"]),
        "strm_sha256": _strm_sha256(row),
        "probe_count": probe_count(row["url"]),
    }


# ---------------------------------------------------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------------------------------------------------


# Jellyfin derives concrete entity types from the library collection type: a movie library yields
# ``Movie`` (a Video), a music library yields ``Audio``. Both are still the native Video/Audio
# entities the plugin treats as required-primary-stream owners, so the check accepts the concrete
# class names rather than only the abstract base names.
VIDEO_ENTITY_SUFFIXES = ("Movie", "Episode", "MusicVideo", "Video", "Trailer")
AUDIO_ENTITY_SUFFIXES = ("Audio", "AudioBook")


def entity_class_failures(info: dict, media_type: str) -> list[str]:
    """Return the reasons the native item is not the expected Video/Audio entity."""
    failures: list[str] = []
    reported_media_type = str(info.get("MediaType") or "").lower()
    if reported_media_type != media_type:
        failures.append(f"native media type is {info.get('MediaType')!r}, expected {media_type!r}")
    entity = str(info.get("Type") or "").rsplit(".", 1)[-1]
    allowed = VIDEO_ENTITY_SUFFIXES if media_type == "video" else AUDIO_ENTITY_SUFFIXES
    if entity not in allowed:
        failures.append(f"native entity {info.get('Type')!r} is not one of {list(allowed)}")
    if media_type == "audio" and entity in VIDEO_ENTITY_SUFFIXES:
        failures.append("an audio row must not be indexed as a video entity")
    return failures


def prepare_instance(package: Path) -> dict:
    summary: dict[str, object] = {}
    summary["networkAdaptation"] = install_explicit_subnets()
    pe.prepare_clean_instance()
    summary["logging"] = enable_probe_logging()
    pe.compose("stop")
    pe.compose("up")
    pe.wait_healthy()
    auth = refresh_auth()
    # The wizard already registered the movie STRM library; adding it again would index the same
    # files twice and break the exactly-one-item scan lookups.
    summary["libraries"] = {"movies": MOVIE_LIBRARY}
    summary["deployment"] = pe.deploy_archive(package)
    pkg.restart()
    auth = refresh_auth()
    require(pe.public_info().get("Version") == "12.2.0", "The package instance is not Jellyfin 12.2.0.")
    summary["pluginStatus"] = pkg.plugin_status(auth)
    require(str(summary["pluginStatus"]).lower() in {"active", "0"},
            "The plugin is not Active after archive-only install.")
    summary["payloadMatchesArchive"] = pkg.deployed_matches_archive(package)
    status, tasks = pe.request_json("GET", "/ScheduledTasks", headers={"Authorization": auth})
    require(status == 200, "The scheduled-task listing failed.")
    native = [task for task in tasks if task.get("Name") == pkg.TASK_NAME]
    require(len(native) == 1 and native[0].get("Triggers") == [],
            "The native task must exist exactly once with no default trigger.")
    summary["nativeTask"] = {"id": native[0]["Id"], "triggers": native[0].get("Triggers")}
    return summary


def prepare_rows(auth: str, rows: list[dict]) -> dict:
    """Scan the STRM rows, then let Jellyfin probe/persist the primary stream with the plugin off."""
    summary: dict[str, object] = {}
    pe.request_json("POST", "/Library/Refresh", headers={"Authorization": auth})
    for row in rows:
        require(row["media_type"] == "video", "Audio STRM rows are outside the current Slice 5 contract.")
        row["item"] = pkg.scan_and_wait(auth, row["strm_name"], MAX_WAIT)
        info = item_media_type(auth, row["item"]["Id"])
        summary[row["id"] + ".item"] = info
        entity_failures = entity_class_failures(info, row["media_type"])
        require(not entity_failures, f"{row['id']}: " + "; ".join(entity_failures))
        summary[row["id"] + ".entity"] = str(info.get("Type")).rsplit(".", 1)[-1]
    require(pkg.plugin_action(auth, False) == 204, "The package-instance plugin disable failed.")
    pkg.restart()
    auth = refresh_auth()
    require(str(pkg.plugin_status(auth)).lower() not in {"active", "0"}, "The plugin remained active after disable.")
    for row in rows:
        required = "Video"
        deadline = time.monotonic() + MAX_WAIT
        saved: list[str] = []
        while time.monotonic() < deadline:
            status, response = pkg.playback_info(auth, row["item"]["Id"])
            if status == 200 and response.get("MediaSources"):
                saved = saved_stream_types(auth, row["item"]["Id"])
                if required in saved:
                    break
            time.sleep(1)
        require(required in saved,
                f"{row['id']}: Jellyfin never persisted a native {required} primary stream (saved {saved}).")
        summary[row["id"] + ".preparedStreams"] = saved
        summary[row["id"] + ".preparationProbeCount"] = probe_count(row["url"])
        require(probe_count(row["url"]) >= 1,
                f"{row['id']}: no ffprobe line was observed for the preparation probe; the counter is not usable.")
        # Fix the expected native source identity and the prepared address/streams for this row, so
        # every later phase is compared against the source this row really owns.
        snapshot = native_source_snapshot(auth, row["item"]["Id"])
        source_ids = [source["id"] for source in snapshot["sources"] if source.get("id")]
        require(len(source_ids) == 1,
                f"{row['id']}: expected exactly one native media source during preparation, found {source_ids}.")
        row["sourceKey"] = source_ids[0]
        row["preparedSource"] = snapshot
        row["preparedAddressMatchesUrl"] = (
            snapshot["sources"][0].get("pathHash") == hashlib.sha256(row["url"].encode()).hexdigest())
        summary[row["id"] + ".preparedSource"] = snapshot
        summary[row["id"] + ".preparedAddressMatchesStrmUrl"] = row["preparedAddressMatchesUrl"]
    require(pkg.plugin_action(auth, True) == 204, "The package-instance plugin enable failed.")
    pkg.restart()
    return summary


def scenario_baseline(package: Path, evidence_dir: Path, selected: list[str],
                      summary: dict[str, object]) -> None:
    """Run the baseline, recording every reached stage into ``summary`` even when a stage fails."""
    summary["fixtures"] = generate_fixtures()
    summary["instance"] = prepare_instance(package)
    auth = refresh_auth()
    rows = []
    for row in ROWS:
        if row["id"] not in selected:
            continue
        fixture = summary["fixtures"]["fixtures"][row["file"]]
        entry = dict(row)
        entry.update(write_row_strm(row, fixture))
        entry["fixture"] = {"sha1": fixture["sha1"], "size": fixture["size"],
                            "ffprobe": fixture["ffprobe"]}
        rows.append(entry)
    summary["rows"] = [{"id": row["id"], "name": row["name"], "mediaType": row["media_type"],
                        "url": row["url"], "strm": row["path"], "strmContentSha256": row["contentSha256"]}
                       for row in rows]
    summary["preparation"] = prepare_rows(auth, rows)
    auth = refresh_auth()
    for row in rows:
        require(fingerprint_row_for_item(auth, row["item"]["Id"], row["sourceKey"]) is None,
                f"{row['id']}: a fingerprint already existed before the first trust playback.")

    results: dict[str, object] = {}
    failures: list[str] = []
    for row in rows:
        row_result: dict[str, object] = {}
        try:
            require(row.get("preparedAddressMatchesUrl") is True,
                    f"{row['id']}: the prepared native source address is not the STRM URL.")
            # 1) first trust
            first = play_once(auth, row, "first-trust", evidence_dir)
            assert_playback(row, first, counter_validated=True)
            row_failures = fingerprint_fields_match(first["fingerprint"], expected_url=row["url"],
                                                    sha1=row["fixture"]["sha1"], size=row["fixture"]["size"],
                                                    expected_item_id=row["item"]["Id"],
                                                    expected_source_id=row["sourceKey"])
            if first["fingerprint"] is not None:
                require(any("FirstTrust" in event for event in first["pluginEvents"]),
                        f"{row['id']}: the existing stream was not accepted through first trust "
                        f"({first['pluginEvents']}).")
                require(all(call in (0, None) for call in first["pluginProbeCalls"]),
                        f"{row['id']}: first trust reported a plugin probe {first['pluginEvents']}.")
            require(not row_failures, f"{row['id']}: " + "; ".join(row_failures))
            row_result["firstTrust"] = {"fingerprint": first["fingerprint"], "events": first["pluginEvents"],
                                        "ffprobe": first["ffprobe"],
                                        "startTime": first["playback"].get("startCurrentTime"),
                                        "advancedSeconds": first["playback"].get("advancedSeconds"),
                                        "mediaRequests": first["mediaServerRequests"]}
            # 2) second playback reuses the trusted baseline
            second = play_once(auth, row, "second-play", evidence_dir)
            assert_playback(row, second, counter_validated=True)
            require(second["fingerprint"] == first["fingerprint"],
                    f"{row['id']}: the second playback changed the trusted fingerprint.")
            require(all(call in (0, None) for call in second["pluginProbeCalls"]),
                    f"{row['id']}: the second playback reported a plugin probe {second['pluginEvents']}.")
            row_result["secondPlay"] = {"ffprobe": second["ffprobe"], "events": second["pluginEvents"],
                                        "startTime": second["playback"].get("startCurrentTime"),
                                        "advancedSeconds": second["playback"].get("advancedSeconds")}
            # 3) restart: freeze, restart, compare read-only before any PlaybackInfo or playback
            frozen = freeze_state(auth, row)
            row_result["frozenBeforeRestart"] = frozen
            pkg.restart()
            auth = refresh_auth()
            observed = read_only_state(auth, row)
            row_result["readOnlyAfterRestart"] = observed
            restart_failures = restart_readback_failures(frozen, observed)
            require(not restart_failures, f"{row['id']}: " + "; ".join(restart_failures))
            after = play_once(auth, row, "after-restart", evidence_dir)
            assert_playback(row, after, counter_validated=True)
            require(after["fingerprint"] == frozen["fingerprint"],
                    f"{row['id']}: the post-restart playback changed the trusted fingerprint.")
            row_result["afterRestart"] = {"ffprobe": after["ffprobe"], "events": after["pluginEvents"],
                                          "startTime": after["playback"].get("startCurrentTime"),
                                          "advancedSeconds": after["playback"].get("advancedSeconds")}
            row_result["status"] = "PASS"
        except (BaselineError, RuntimeError, OSError, subprocess.SubprocessError) as error:
            # A row failure never stops the remaining rows: every row keeps its own evidence so B can
            # see the real per-row result instead of a single aborted run.
            row_result["status"] = "FAIL"
            row_result["error"] = f"{type(error).__name__}: {error}"
            failures.append(f"{row['id']}: {row_result['error']}")
        results[row["id"]] = row_result
    summary["rowsResult"] = results
    if failures:
        raise BaselineError("Baseline rows failed: " + " | ".join(failures))
    summary["status"] = "PASS"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--scenario", default="baseline", choices=["baseline", "matrix"])
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--rows", default=",".join(BASELINE_ROW_IDS),
                        help="Comma-separated row ids to run (default: both video baseline rows; "
                             "matrix ids are MP4.P02.01, MKV.C02.limited, MP4.F01, MKV.D06, ...).")
    parser.add_argument("--workspace", type=Path,
                        help="Fresh run-owned workspace under artifacts/package-env (default: auto-created).")
    parser.add_argument("--keep-workspace", action="store_true",
                        help="Leave this run's workspace and instance in place for inspection.")
    args = parser.parse_args()

    selected = [part.strip() for part in args.rows.split(",") if part.strip()]
    if args.scenario == "matrix":
        known = matrix_row_ids()
        require(set(selected) <= known, f"Unknown matrix row ids {sorted(set(selected) - known)}.")
    else:
        known = set(BASELINE_ROW_IDS)
        require(set(selected) <= known, f"Unknown row ids {sorted(set(selected) - known)}; known rows are {sorted(known)}.")
    package = args.package.resolve()
    evidence_dir = args.evidence_dir.resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {"scenario": args.scenario, "package": str(package), "rows": selected}
    exit_code = 1
    before_state = None
    workspace = None
    started = time.time()
    try:
        verification = package_plugin.verify_archive(package)
        summary["packageIdentity"] = {
            "archiveSha256": verification["archiveSha256"], "version": verification["version"],
            "guid": verification["guid"], "targetAbi": verification["targetAbi"],
            "runtime": verification["runtime"], "entries": verification["entries"],
        }
        workspace = pe.select_workspace(args.workspace)
        summary["workspace"] = str(workspace)
        before_state = pe.capture_instance_state()
        baseline: dict[str, object] = {}
        summary["baseline"] = baseline
        if args.scenario == "matrix":
            scenario_matrix(package, evidence_dir, selected, baseline)
        else:
            scenario_baseline(package, evidence_dir, selected, baseline)
        summary["status"] = "PASS"
        exit_code = 0
    except (BaselineError, RuntimeError, OSError, ValueError, KeyError, json.JSONDecodeError,
            subprocess.SubprocessError, package_plugin.PackageError, pe.PackageEnvironmentError) as error:
        summary["status"] = "FAIL"
        summary["error"] = f"{type(error).__name__}: {error}"
        exit_code = 1
    finally:
        # The original Jellyfin and media-service logs are archived before any reconciliation or
        # cleanup so the real ffprobe lines and the first failure stay independently countable even
        # when a later teardown step itself fails. The archive lives under the evidence directory,
        # which cleanup never removes.
        archived: dict[str, object] = {}
        try:
            probe_lines = [line for line in server_log_lines() if FFPROBE_MARKER in line]
            archived["serverProbeLog"] = archive_evidence(
                evidence_dir, "server-ffprobe-lines.log", "\n".join(probe_lines) + "\n")
            archived["serverProbeLineCount"] = len(probe_lines)
            # The complete original server log is archived as well: the ffprobe lines alone cannot
            # explain a native 500 or a first failure that never reached a probe.
            archived["serverLogFiles"] = archive_server_logs(evidence_dir)
        except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError) as archive_error:
            archived["serverLogArchiveError"] = f"{type(archive_error).__name__}: {archive_error}"
        try:
            archived["mediaLogs"] = archive_media_logs()
        except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError, RuntimeError) as archive_error:
            archived["mediaLogArchiveError"] = f"{type(archive_error).__name__}: {archive_error}"
        summary["evidenceArchive"] = archived
        summary["elapsedSeconds"] = round(time.time() - started, 1)
        if before_state is not None:
            try:
                summary["instanceReconciliation"] = pe.reconcile_instance_state(before_state)
            except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError) as teardown_error:
                summary["teardownError"] = f"{type(teardown_error).__name__}: {teardown_error}"
                summary["status"] = "FAIL"
                exit_code = 1
        if workspace is not None and not args.keep_workspace:
            try:
                summary["cleanup"] = pe.cleanup_instance()
            except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError) as cleanup_error:
                summary["cleanupError"] = f"{type(cleanup_error).__name__}: {cleanup_error}"
                summary["status"] = "FAIL"
                exit_code = 1
        (evidence_dir / f"{args.scenario}-result.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (evidence_dir / "INDEX.md").write_text(
            render_matrix_index(summary) if args.scenario == "matrix" else render_index(summary),
            encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


def render_index(summary: dict) -> str:
    lines = ["# Slice 5 baseline evidence index", "",
             f"- Status: **{summary.get('status')}**",
             f"- Scenario: {summary.get('scenario')}",
             f"- Rows: {', '.join(summary.get('rows') or [])}",
             f"- Package: `{summary.get('package')}`",
             f"- Package SHA-256: `{(summary.get('packageIdentity') or {}).get('archiveSha256')}`",
             f"- Workspace: `{summary.get('workspace')}`",
             f"- Elapsed seconds: {summary.get('elapsedSeconds')}",
             ""]
    if summary.get("error"):
        lines += ["## Failure", "", f"```\n{summary['error']}\n```", ""]
    fixtures = (summary.get("baseline") or {}).get("fixtures", {}).get("fixtures", {})
    if fixtures:
        lines += ["## Fixtures", "", "| file | SHA-1 | size | streams |", "|---|---|---|---|"]
        for name, fixture in fixtures.items():
            streams = ", ".join(f"{stream.get('codec_type')}:{stream.get('codec_name')}"
                                + (f"/{stream.get('color_range')}" if stream.get("color_range") else "")
                                for stream in fixture["ffprobe"]["streams"])
            lines.append(f"| `{name}` | `{fixture['sha1']}` | {fixture['size']} | {streams} |")
        lines.append("")
    rows = (summary.get("baseline") or {}).get("rowsResult", {})
    if rows:
        lines += ["## Baseline rows", "",
                  "| row | status | ffprobe (first/second/restart) | advanced seconds (first/second/restart) "
                  "| source id |", "|---|---|---|---|---|"]
        for row_id, result in rows.items():
            prepared = ((summary.get("baseline") or {}).get("preparation") or {}).get(row_id + ".preparedSource") or {}
            source_ids = [source.get("id") for source in prepared.get("sources") or []]
            if result.get("status") != "PASS":
                lines.append(f"| {row_id} | {result.get('status')} | - | - | {', '.join(str(s) for s in source_ids)} |")
                continue
            probes = "/".join(str(result[key]["ffprobe"]["delta"])
                              for key in ("firstTrust", "secondPlay", "afterRestart"))
            advances = "/".join(str(result[key].get("advancedSeconds"))
                                 for key in ("firstTrust", "secondPlay", "afterRestart"))
            lines.append(f"| {row_id} | PASS | {probes} | {advances} | {', '.join(str(s) for s in source_ids)} |")
        lines.append("")
        for row_id, result in rows.items():
            if result.get("status") not in ("PASS", "BLOCKED"):
                lines += [f"### {row_id} failure", "", f"```\n{result.get('error')}\n```", ""]
        for row_id, result in rows.items():
            if result.get("status") != "PASS":
                continue
            frozen = result.get("frozenBeforeRestart") or {}
            lines += [f"### {row_id} restart read-back (read-only, before any playback)", "",
                      f"- fingerprint: `{json.dumps(frozen.get('fingerprint'), sort_keys=True)}`",
                      f"- fingerprint matched after restart: "
                      f"{frozen.get('fingerprint') == (result.get('readOnlyAfterRestart') or {}).get('fingerprint')}",
                      f"- native sources matched after restart: "
                      f"{frozen.get('nativeSources') == (result.get('readOnlyAfterRestart') or {}).get('nativeSources')}",
                      f"- probe count before/after: {frozen.get('probe_count')}/"
                      f"{(result.get('readOnlyAfterRestart') or {}).get('probe_count')}", ""]
            for source in (frozen.get("nativeSources") or {}).get("sources") or []:
                streams = ", ".join(f"{stream.get('Type')}#{stream['fields'].get('Index')}"
                                    f":{stream['fields'].get('Codec')}"
                                    for stream in source.get("streams") or [])
                lines.append(f"  - source `{source.get('id')}` address `{source.get('path')}` "
                             f"pathHash `{source.get('pathHash')}` streams {streams}")
            lines.append("")
    blocked = (summary.get("baseline") or {}).get("blocked") or []
    if blocked:
        lines += ["## Blocked rows (not passed)", ""]
        for row_id in blocked:
            lines += [f"### {row_id}", "",
                      f"```\n{(rows.get(row_id) or {}).get('error')}\n```",
                      "", f"native response: `{json.dumps((rows.get(row_id) or {}).get('nativeAudioResponse'))}`",
                      ""]
    lines += ["## Evidence files", "",
              "- `baseline-result.json`: complete machine-readable result (fixtures, per-row observations).",
              "- `<row>/<phase>/observation.json`: ffprobe window, plugin events, media requests, fingerprint.",
              "- `<row>/<phase>/screenshots/*.png`: start and 5 s progress screenshots.",
              "- `<row>/<phase>/driver-stdout.txt`, `driver-stderr.txt`: raw browser driver output.",
              ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------------------------
# Matrix scenario: the eight-decision video matrix with fixed row ids (Task 5.3)
#
# The row registry is the contract's fixed expansion: per format 44 P rows, 6 C rows, 2 F rows and
# 6 D rows. The entry only reuses the existing sequential preparation, the strict web driver and the
# media service; it adds no scenario configuration, DSL or scheduler. Rows keep every input frozen
# before the measurement window (os.replace / write_owned_bytes only, nothing mutates mid-playback).
# ---------------------------------------------------------------------------------------------------------------------

MEDIA_PREFIX = "http://media:8080/"
INT64_MAX = 9223372036854775807
# Explicit "remove this manifest token in the rewrite" instruction; a token absent from the
# apply dict means "keep the old-side value", so removal can never silently degrade to keep.
DELETE = object()


def matrix_row_ids() -> set[str]:
    """The fixed id set of the contract expansion (unit-testable without fixtures)."""
    ids: set[str] = set()
    for fmt in ("MP4", "MKV"):
        ids.update(f"{fmt}.P01.{t}" for t in ("01", "02", "03", "04"))
        ids.update(f"{fmt}.P02.{t}" for t in ("01", "02", "03", "04", "05", "06", "07", "08"))
        ids.update(f"{fmt}.P03.{t}" for t in ("01", "02", "03", "04", "05"))
        ids.update(f"{fmt}.P04.{t}" for t in ("01", "02", "03"))
        ids.update(f"{fmt}.P05.{t}" for t in ("01", "02", "03", "04", "05"))
        ids.update(f"{fmt}.P06.{t}.{d}" for t in ("01", "02", "03", "04", "05") for d in ("up", "down"))
        ids.update(f"{fmt}.P07.{t}" for t in ("01", "02", "03", "04", "05", "06"))
        ids.update(f"{fmt}.P08.{t}" for t in ("01", "02", "03"))
        ids.update(f"{fmt}.C02.{t}" for t in ("limited", "full", "unspecified"))
        ids.update(f"{fmt}.C06.{t}" for t in ("limited", "full", "unspecified"))
        ids.update([f"{fmt}.F01", f"{fmt}.F02"])
        ids.update(f"{fmt}.{group}" for group in ("D01", "D02", "D03", "D04", "D05", "D06"))
    return ids


def matrix_extra_specs(fmt: str) -> dict[str, dict[str, object]]:
    """The controlled extra media the matrix needs beyond the baseline fixtures.

    ``p4b`` is a short (16 s) smptebars B-side: the guaranteed-shorter partner and the
    equal-length-after-legal-padding partner. ``p06up`` is the guaranteed-longer side; a longer
    duration alone does not make it longer in bytes (a static pattern encodes far smaller), so it
    also carries real per-frame noise. The ``short-*`` and plain ColorRange names are the C-row
    controlled targets; the evidence records the actual ffprobe fields, never the generation
    parameters.
    """
    ext = "mp4" if fmt == "MP4" else "mkv"
    prefix = f"matrix-{ext}-"
    specs: dict[str, dict[str, object]] = {
        prefix + f"p4b.{ext}": {"container": ext, "pattern": "smptebars", "marker": fmt + " P4B", "tone": 660,
                               "color_range": "tv", "seconds": 16},
        prefix + f"p06up.{ext}": {"container": ext, "pattern": "smptebars", "marker": fmt + " P06UP", "tone": 660,
                                  "color_range": "tv", "seconds": 28,
                                  "noise": "noise=alls=40:allf=t+u"},
    }
    for tail, marker, color_range in (("limited", "C06LIM", "tv"), ("full", "C06FULL", "pc"),
                                      ("unspecified", "C06UNS", None)):
        specs[prefix + f"short-{tail}.{ext}"] = {"container": ext, "pattern": "testsrc2",
                                                 "marker": fmt + " " + marker, "tone": 440,
                                                 "color_range": color_range, "seconds": 20}
    if fmt == "MKV":
        # The MP4 C02 targets reuse the baseline fixtures; MKV needs its own 24 s ColorRange targets.
        for tail, marker, color_range in (("limited", "LIM", "tv"), ("full", "FULL", "pc"),
                                          ("unspecified", "UNS", None)):
            specs[f"matrix-mkv-{tail}.mkv"] = {"container": "mkv", "pattern": "testsrc2", "marker": "MKV " + marker,
                                               "tone": 440, "color_range": color_range, "seconds": 24}
    return specs


def pad_mkv_to(data: bytes, target: int) -> bytes:
    """Grow an MKV to exactly ``target`` bytes with a legal trailing Empty Element.

    The original document stays byte-for-byte at the front; a matroska Empty Element
    (id 0x1549) with the unknown-size marker (0xFF, which consumes to end of file) plus zero
    padding bytes is appended so readers skip the padding entirely. The caller must still
    verify the result is natively probeable/decodable.
    """
    require(len(data) < target, "Legal padding can only grow a file, not shrink it.")
    require(len(data) > 4 and data[:4] == b"\x1a\x45\xdf\xa3", "Not an EBML Matroska document.")
    need = target - len(data)
    require(need >= 4, "The target size leaves no room for the Empty Element header.")
    result = data + b"\x15\x49\xff" + b"\x00" * (need - 3)
    require(len(result) == target, f"MKV padding produced {len(result)} bytes instead of {target}.")
    return result


def pad_mp4_to(data: bytes, target: int) -> bytes:
    """Grow an MP4 to exactly ``target`` bytes by appending one legal ``free`` atom.

    The original bytes stay byte-for-byte at the front, so the moov/mdat chunk offsets stay
    valid; readers skip a trailing free atom. The caller must still verify that the padded
    file remains natively probeable and decodable.
    """
    require(len(data) < target, "Legal padding can only grow a file, not shrink it.")
    require(len(data) > 8 and data[4:8] == b"ftyp", "Not an MP4 (missing ftyp box).")
    free_size = target - len(data)
    require(free_size >= 8, "The target size leaves no room for a free atom header.")
    free_box = free_size.to_bytes(4, "big") + b"free" + b"\x00" * (free_size - 8)
    result = data + free_box
    require(len(result) == target, f"MP4 padding produced {len(result)} bytes instead of {target}.")
    return result


def f02_truncated_bytes(data: bytes) -> bytes:
    """Return a real truncated copy of the A file for the F02 failure window.

    F02 is not a successful-media scenario: the fixed URL must hold bytes that the native probe
    really cannot turn into the necessary main stream. The container metadata of both fixed
    fixtures lives in their first few hundred bytes, so cutting at 512 leaves a strict prefix with
    no usable moov/Matroska stream description. The generated file is probed below before any row
    is built; this helper only makes the cut deterministic and testable.
    """
    require(len(data) > F02_CORRUPT_PREFIX_BYTES,
            f"The F02 source is only {len(data)} bytes; it cannot be truncated to a 512-byte prefix.")
    prefix = data[:F02_CORRUPT_PREFIX_BYTES]
    require(0 < len(prefix) < len(data), "The F02 corrupt partner is not a strict truncation of A.")
    return prefix


def require_f02_unprobeable(name: str, streams: list[dict], probe_error: str | None) -> None:
    """Refuse an F02 partner that the pinned native probe could still accept.

    The manifest for the failing window records the real SHA-1/Size of this controlled input, so
    the input itself must be genuinely unusable. A truncated file that already exposes a video
    stream would make the expected failure window playable again (the previous first-third cut did
    exactly that even though its byte count was smaller). Generation therefore requires the pinned
    ffprobe to fail and the result to contain no video stream.
    """
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    require(not videos,
            f"{name}: the F02 corrupt input still exposes video streams {videos!r}; "
            f"the failure window would not prove a native probe failure.")
    require(probe_error is not None,
            f"{name}: the F02 corrupt input still probes successfully with streams {streams!r}; "
            f"the failure window would not prove a native probe failure.")


def require_p06_directions(label: str, a_size: int, up_size: int, down_size: int) -> None:
    """Refuse a P06 partner set whose real byte sizes contradict the fixed up/down direction.

    The contract's ten P06 rows per format are half ``up`` (the new media really has more bytes)
    and half ``down`` (fewer). A longer duration does not imply more bytes, so the generated files
    are measured and the run stops before any playback if a direction is wrong; a mislabelled
    partner must never be reported as the other direction.
    """
    require(down_size < a_size,
            f"{label}: the P06 down partner is {down_size} bytes, not fewer than A's {a_size}; "
            f"the down direction would really be an up case.")
    require(up_size > a_size,
            f"{label}: the P06 up partner is {up_size} bytes, not more than A's {a_size}; "
            f"the up direction would really be a down case.")


def generate_matrix_fixtures() -> dict:
    """Generate the matrix media with the pinned FFmpeg and derive the padded/truncated partners."""
    base = generate_fixtures()
    specs: dict[str, dict[str, object]] = {}
    specs.update(matrix_extra_specs("MP4"))
    specs.update(matrix_extra_specs("MKV"))
    commands = dict(base["commands"])
    for name, spec in specs.items():
        commands[name] = encode_fixture(spec, name)
    derived: dict[str, dict] = {}
    for ext in ("mp4", "mkv"):
        a_bytes = (pe.WORK / "media" / f"baseline-{ext}-a.{ext}").read_bytes()
        p4b_bytes = (pe.WORK / "media" / f"matrix-{ext}-p4b.{ext}").read_bytes()
        p06up_bytes = (pe.WORK / "media" / f"matrix-{ext}-p06up.{ext}").read_bytes()
        require_p06_directions(ext.upper(), len(a_bytes), len(p06up_bytes), len(p4b_bytes))
        padded = pad_mp4_to(p4b_bytes, len(a_bytes)) if ext == "mp4" else pad_mkv_to(p4b_bytes, len(a_bytes))
        pe.write_owned_bytes(pe.WORK / "media" / f"matrix-{ext}-b-padded.{ext}", padded,
                             label=f"padded partner matrix-{ext}-b-padded")
        truncated = f02_truncated_bytes(a_bytes)
        pe.write_owned_bytes(pe.WORK / "media" / f"matrix-{ext}-a-trunc.{ext}", truncated,
                             label=f"truncated partner matrix-{ext}-a-trunc")
        info = ffprobe(f"/out/matrix-{ext}-b-padded.{ext}")
        require(info.get("streams"), f"The padded partner matrix-{ext}-b-padded is not natively probeable.")
        derived[ext] = {"padded": f"matrix-{ext}-b-padded.{ext}", "truncated": f"matrix-{ext}-a-trunc.{ext}"}
    corrupt_names = {item["truncated"] for item in derived.values()}
    fixtures = dict(base["fixtures"])
    for name in [*specs, *derived["mp4"].values(), *derived["mkv"].values()]:
        data = (pe.WORK / "media" / name).read_bytes()
        streams: list[dict] = []
        probe_error: str | None = None
        try:
            info = ffprobe("/out/" + name)
            streams = [{key: stream.get(key) for key in
                        ("index", "codec_type", "codec_name", "width", "height", "pix_fmt", "color_range",
                         "sample_rate", "channels", "duration", "disposition")}
                       for stream in info.get("streams", [])]
        except BaselineError as error:
            probe_error = str(error)[-300:]
        if name in corrupt_names:
            # The F02 corrupt input must fail before measurement; recording its real bytes is not
            # enough, because a still-probeable truncation would make the expected failure window
            # playable and silently change the scenario.
            require_f02_unprobeable(name, streams, probe_error)
        if name in specs:
            # Extra ColorRange inputs prove their actual output the same way the baseline set does.
            require_actual_color_range(name, specs[name], streams)
        fixture = {"sha1": hashlib.sha1(data).hexdigest(), "size": len(data),
                   "sha256": hashlib.sha256(data).hexdigest(),
                   "ffprobe": {"streams": streams, "probeable": bool(streams)}}
        if probe_error is not None:
            fixture["ffprobe"]["error"] = probe_error
        fixtures[name] = fixture
    return {"commands": commands, "fixtures": fixtures, "aliases": base["aliases"],
            "derived": derived, "durationSeconds": FIXTURE_SECONDS}


def _valid_sha1(token: object) -> bool:
    text = str(token or "")
    return len(text) == 40 and all(char in "0123456789abcdefABCDEF" for char in text)


def parsed_tokens(sha1_token: object, size_token: object) -> tuple[str | None, int | None]:
    """The fingerprint fields the plugin can derive from these manifest tokens (None = not stored).

    Invalid lengths, non-hex characters, negative/non-numeric sizes and the Int64 overflow value all
    parse to ``None`` exactly as the manifest reader rejects them; a legal 0 stays 0.
    """
    sha1 = str(sha1_token).lower() if _valid_sha1(sha1_token) else None
    size = None
    if size_token is not None:
        text = str(size_token)
        if re.fullmatch(r"\d+", text) and int(text) <= INT64_MAX:
            size = int(text)
    return sha1, size


def build_matrix_rows(fixture_table: dict) -> list[dict]:
    """The contract's fixed row expansion: 44 P rows + 6 C rows + F/D rows per format.

    Tokens: a valid 40-hex string is real content SHA-1; ``None`` is absent; the 39-char and
    40-char-non-hex strings are the contract's invalid L/X forms. Sizes are literal manifest
    strings so the negative, non-numeric and Int64-overflow rows keep their real text.
    """
    rows: list[dict] = []
    for fmt in ("MP4", "MKV"):
        ext = "mp4" if fmt == "MP4" else "mkv"

        def fx(name: str) -> dict:
            return fixture_table[name]

        a = fx(f"baseline-{ext}-a.{ext}")
        b = fx(f"baseline-{ext}-b.{ext}")
        p4b = fx(f"matrix-{ext}-p4b.{ext}")
        p06up = fx(f"matrix-{ext}-p06up.{ext}")
        # The P06 rows are fixed as five "up" and five "down" directions per format; the real
        # fixture byte counts must agree before any row is built, so a wrong-direction partner can
        # never be labelled with the other direction.
        require_p06_directions(fmt, int(a["size"]), int(p06up["size"]), int(p4b["size"]))
        bpad = fx(f"matrix-{ext}-b-padded.{ext}")
        trunc = fx(f"matrix-{ext}-a-trunc.{ext}")
        c02_targets = ({"limited": f"baseline-{ext}-limited.{ext}", "full": f"baseline-{ext}-full.{ext}",
                        "unspecified": f"baseline-{ext}-unspecified.{ext}"} if ext == "mp4" else
                       {"limited": "matrix-mkv-limited.mkv", "full": "matrix-mkv-full.mkv",
                        "unspecified": "matrix-mkv-unspecified.mkv"})
        va, na = a["sha1"], str(a["size"])
        vb, nb = b["sha1"], str(b["size"])
        v4, n4 = p4b["sha1"], str(p4b["size"])
        vu, nu = p06up["sha1"], str(p06up["size"])
        vp = bpad["sha1"]
        vt, nt = trunc["sha1"], str(trunc["size"])
        l39, x40 = va[:39], va[:39] + "z"
        base_url = MEDIA_PREFIX + f"baseline-{ext}-a.{ext}"
        copy_url = MEDIA_PREFIX + f"switch-copy-{ext}.{ext}"
        base_media = f"baseline-{ext}-a.{ext}"

        def add(group: str, tail: str, *, media: str, old_sha: object, old_size: object,
                apply_kind: str, apply: dict | None = None, expect: int = 0,
                fp_kind: str = "same", fp_tokens: tuple[object, object] | None = None,
                fp_url: str | None = None, journey: str = "normal", trust: bool = True,
                watch_media: str | None = None, item_name: str | None = None) -> None:
            # Jellyfin derives the item name from the STRM file name's first extension boundary:
            # a dot in the name makes "... C02.limited" become the item "... C02", so every row
            # item name spells its tail with spaces and never contains a dot.
            item = item_name or (f"Matrix {fmt} {group} " + tail.replace(".", " ")).strip()
            item = item.replace(".", " ").strip()
            # The STRM file name is a stable row property: ``row["item"]`` is replaced by the native
            # item dictionary once the row has been scanned, so it must never key the STRM path.
            strm_name = item
            # Fixed-URL families (P04/P06/C/F02) keep the URL constant while the file bytes on it
            # change, so the manifest address is the switch file itself, not the baseline media.
            url = MEDIA_PREFIX + media if media.startswith("switch-") else base_url
            # The media-request counter keys off the file name behind the requested URL, so the
            # watched file defaults to the row's own media file; static-path rows watch their
            # partner file explicitly.
            row = {"id": f"{fmt}.{group}" + (f".{tail}" if tail else ""), "fmt": fmt, "name": item,
                   "item": item, "strm_name": strm_name, "media_type": "video", "media": media, "url": url,
                   "old": {"sha1": old_sha, "size": old_size}, "apply": apply or {},
                   "apply_kind": apply_kind, "expect_probes": expect, "fp_kind": fp_kind,
                   "fp_tokens": fp_tokens, "fp_url": fp_url or url, "journey": journey,
                   "trust": trust, "watch_media": watch_media or media}
            rows.append(row)

        # --- P01: missing necessary video stream, bounded removal in this run's owned copy ---------
        for tail, drop, prime in (("01", "all", False), ("02", "all", True),
                                  ("03", "video", False), ("04", "video", True)):
            add("P01", tail, media=base_media, old_sha=va, old_size=na, apply_kind="remove-streams",
                apply={"drop": drop, "prime": prime}, expect=1, fp_kind="new", fp_tokens=(va, na),
                journey="p01", trust=False)

        # --- P02: URL changed (old manifest tokens -> new manifest tokens / watch media) ----------
        p02 = [
            ("01", copy_url, va, na, va, na, f"switch-copy-{ext}.{ext}"),
            ("02", MEDIA_PREFIX + f"media-p02b-{ext}.{ext}", va, na, vb, nb, f"media-p02b-{ext}.{ext}"),
            ("03", copy_url, None, na, None, na, f"switch-copy-{ext}.{ext}"),
            ("04", MEDIA_PREFIX + f"media-p04b-{ext}.{ext}", None, na, None, n4, f"media-p04b-{ext}.{ext}"),
            ("05", copy_url, None, None, None, None, f"switch-copy-{ext}.{ext}"),
            ("06", copy_url, va, na, None, na, f"switch-copy-{ext}.{ext}"),
            ("07", copy_url, None, na, va, na, f"switch-copy-{ext}.{ext}"),
            ("08", base_url + "?alias=1", va, na, va, na, base_media),
        ]
        for tail, new_url, old_sha, old_size, new_sha, new_size, watch in p02:
            add("P02", tail, media=base_media, old_sha=old_sha, old_size=old_size,
                apply_kind="manifest-url", apply={"url": new_url, "sha1": new_sha, "size": new_size},
                expect=1, fp_kind="new", fp_tokens=(new_sha, new_size), fp_url=new_url, watch_media=watch)

        # --- P03: URL unchanged, same valid SHA-1 (Size/case/missing variants) --------------------
        # None keeps the manifest token absent; the special value DELETE marks an existing token for
        # removal so a manifest rewrite cannot silently keep the old value behind.
        for tail, new_sha, new_size in (("01", None, None), ("02", va, str(int(na) + 1)),
                                        ("03", va.upper(), na), ("04", va, DELETE),
                                        ("05", va, "-1")):
            apply = {k: v for k, v in (("sha1", new_sha), ("size", new_size)) if v is not None}
            add("P03", tail, media=base_media, old_sha=va, old_size=na, apply_kind="manifest",
                apply=apply, expect=0, fp_kind="same")

        # --- P04: URL unchanged, different valid SHA-1, atomic A -> partner on the fixed URL ------
        for tail, new_sha, new_size, partner in (
                ("01", vp, na, f"matrix-{ext}-b-padded.{ext}"),
                ("02", v4, n4, f"matrix-{ext}-p4b.{ext}"),
                ("03", v4, DELETE, f"matrix-{ext}-p4b.{ext}")):
            add("P04", tail, media=f"switch-p04-{ext}.{ext}", old_sha=va, old_size=na, apply_kind="switch",
                apply={"to": partner, "sha1": new_sha, "size": new_size}, expect=1, fp_kind="new",
                fp_tokens=(new_sha, new_size), fp_url=MEDIA_PREFIX + f"switch-p04-{ext}.{ext}")

        # --- P05: URL unchanged, incomparable SHA-1, valid equal sizes ---------------------------
        # The direction is literal: 01 removes the old SHA-1, 02 writes the old-side value on the
        # new side, 04/05 swap the valid old hash for the invalid L/X form. Sizes stay equal at N.
        for tail, old_sha, new_sha in (("01", va, DELETE), ("02", None, va), ("03", None, None),
                                       ("04", va, l39), ("05", x40, va)):
            apply = {"size": na}
            if new_sha is not None:
                apply["sha1"] = new_sha
            add("P05", tail, media=base_media, old_sha=old_sha, old_size=na, apply_kind="manifest",
                apply=apply, expect=0, fp_kind="same")

        # --- P06: URL unchanged, incomparable SHA-1, valid different sizes ------------------------
        # old SHA-1 per P05 direction; the new valid hash always belongs to the bytes the row's
        # own direction really serves (up serves p06up, down serves p4b), never the other file's.
        p06 = {"01": (va, None, None), "02": (None, vu, v4), "03": (None, None, None),
               "04": (va, l39, l39), "05": (x40, vu, v4)}
        for tail, (old_sha, sha_up, sha_down) in p06.items():
            for direction, new_sha in (("up", sha_up), ("down", sha_down)):
                media = f"switch-p06{direction}-{ext}.{ext}"
                new_size = nu if direction == "up" else n4
                partner = f"matrix-{ext}-{'p06up' if direction == 'up' else 'p4b'}.{ext}"
                add("P06", f"{tail}.{direction}", media=media, old_sha=old_sha, old_size=na,
                    apply_kind="switch",
                    apply={"to": partner, "sha1": new_sha, "size": new_size}, expect=1, fp_kind="new",
                    fp_tokens=(new_sha, new_size), fp_url=MEDIA_PREFIX + media)

        # --- P07: URL unchanged, SHA-1 and Size both incomparable ---------------------------------
        # Both sides are missing/invalid in the direction the contract fixes: 01 loses the old
        # SHA-1 (V->none) with no old size and a valid new size; 02 has no old SHA-1, gains a new
        # valid one and loses the old size; 03 has neither side and keeps neither size;
        # 04 turns the old hash invalid and the old size into the negative text -1;
        # 05 starts from the invalid hash/size pair and gains a valid hash and size;
        # 06 has neither side and moves the old size to the Int64 overflow text.
        p07 = [("01", va, DELETE, None, na), ("02", None, va, na, DELETE),
               ("03", None, None, None, None), ("04", va, x40, na, "-1"),
               ("05", x40, va, "not-a-size", na), ("06", None, None, na, "9223372036854775808")]
        for tail, old_sha, new_sha, old_size, new_size in p07:
            apply: dict = {}
            if new_sha is not None:
                apply["sha1"] = new_sha
            if new_size is not None:
                apply["size"] = new_size
            add("P07", tail, media=base_media, old_sha=old_sha, old_size=old_size, apply_kind="manifest",
                apply=apply, expect=0, fp_kind="same")

        # --- P08: only Modified / mtime / rewrite -------------------------------------------------
        add("P08", "01", media=base_media, old_sha=va, old_size=na, apply_kind="mtime", expect=0,
            fp_kind="same")
        add("P08", "02", media=base_media, old_sha=va, old_size=na, apply_kind="comment",
            apply={"extra": "# Modified: 2026-10-21T00:00:00Z"}, expect=0, fp_kind="same")
        add("P08", "03", media=base_media, old_sha=va, old_size=na, apply_kind="rewrite", expect=0,
            fp_kind="same")

        # --- C: ColorRange three-stage regression -------------------------------------------------
        # C02 is a URL A→B change (new path to the real B bytes); C06 keeps the URL and switches
        # the bytes to a genuinely shorter side with the new SHA-1 absent.
        for tail in ("limited", "full", "unspecified"):
            target = c02_targets[tail]
            t = fx(target)
            c02_url = MEDIA_PREFIX + target
            add("C02", tail, media=base_media, old_sha=va, old_size=na, apply_kind="manifest-url",
                apply={"url": c02_url, "sha1": t["sha1"], "size": str(t["size"])},
                expect=1, fp_kind="new", fp_tokens=(t["sha1"], str(t["size"])), fp_url=c02_url,
                watch_media=target)
            short = fx(f"matrix-{ext}-short-{tail}.{ext}")
            add("C06", tail, media=f"switch-c06-{tail}-{ext}.{ext}", old_sha=va, old_size=na,
                apply_kind="switch", apply={"to": f"matrix-{ext}-short-{tail}.{ext}", "sha1": None,
                                            "size": str(short["size"])}, expect=1, fp_kind="new",
                fp_tokens=(None, str(short["size"])), fp_url=MEDIA_PREFIX + f"switch-c06-{tail}-{ext}.{ext}")

        # --- F: failure, old-baseline protection and same-target recovery -------------------------
        add("F01", "", media=base_media, old_sha=va, old_size=na, apply_kind="f01",
            apply={"url": MEDIA_PREFIX + f"missing-f01-{ext}.{ext}", "sha1": v4, "size": n4,
                   "recovery_file": f"matrix-{ext}-p4b.{ext}"},
            expect=1, fp_kind="new", fp_tokens=(v4, n4),
            fp_url=MEDIA_PREFIX + f"missing-f01-{ext}.{ext}", journey="f01", trust=True)
        add("F02", "", media=f"switch-f02-{ext}.{ext}", old_sha=va, old_size=na, apply_kind="f02",
            apply={"corrupt_to": f"matrix-{ext}-a-trunc.{ext}", "corrupt_sha1": vt, "corrupt_size": nt,
                   "recovery_file": f"matrix-{ext}-p4b.{ext}"},
            expect=1, fp_kind="new", fp_tokens=(v4, n4),
            fp_url=MEDIA_PREFIX + f"switch-f02-{ext}.{ext}", journey="f02", trust=True)

        # --- D: permissions and native delegation --------------------------------------------------
        add("D01", "", media=base_media, old_sha=va, old_size=na, apply_kind="none", expect=0, fp_kind="same")
        add("D02", "", media=base_media, old_sha=va, old_size=na, apply_kind="d02", expect=-1, fp_kind="same",
            journey="d02")
        add("D03", "", media=base_media, old_sha=va, old_size=na, apply_kind="d03", expect=-1, fp_kind="same",
            journey="d03")
        add("D04", "", media=f"regular-{ext}/Matrix Regular {fmt}.{ext}", old_sha=va, old_size=na,
            apply_kind="d04", expect=-1, fp_kind="none", journey="d04", trust=False,
            item_name=f"Matrix Regular {fmt}")
        add("D05", "", media=base_media, old_sha=None, old_size=None, apply_kind="d05", expect=-1,
            fp_kind="none", journey="d05", trust=False, item_name=f"Matrix {fmt} D05")
        add("D06", "", media=base_media, old_sha=va, old_size=na, apply_kind="d06",
            apply={"url": copy_url, "sha1": va, "size": na}, expect=1, fp_kind="new", fp_tokens=(va, na),
            fp_url=copy_url, watch_media=f"switch-copy-{ext}.{ext}", journey="d06")
    return rows


def matrix_media_dir() -> Path:
    return pe.WORK / "media"


def reset_row_media(row: dict) -> dict:
    """Re-establish this row's own A bytes on its media files before the journey starts.

    Switch rows share a fixed URL per family but must never inherit or consume a previous row's
    partner bytes: the row's switch target is reset to a byte-identical copy of the row's A
    fixture, and a failing row's recovery target gets a fresh copy of its recovery bytes. Rows
    whose media is the shared fixture itself (never mutated) and the 404 target (never created
    until its recovery stage) are left untouched. The partner files stay in place so later rows
    still find their own sources.
    """
    ext = "mp4" if row["fmt"] == "MP4" else "mkv"
    media = matrix_media_dir()
    a_source = media / f"baseline-{ext}-a.{ext}"
    reset: dict[str, object] = {}
    row_media = row["media"]
    if row_media.startswith("switch-"):
        require("/" not in row_media, f"{row['id']}: unexpected nested media path {row_media!r}")
        target = media / row_media
        require(not target.is_symlink() and target.resolve().is_relative_to(media.resolve()),
                f"{row['id']}: the switch target must stay inside this run's media directory.")
        pe.copy_owned(a_source, target, label=f"row A baseline reset {row['id']}")
        reset[row_media] = "reset to A content"
    if row["apply_kind"] == "f01":
        # The 404 target stays missing until its recovery stage; a previous row's recovery bytes
        # (or a leftover from an earlier batch) must not leak into this row's failure window.
        missing = matrix_media_dir() / row["apply"]["url"].rsplit("/", 1)[-1]
        if missing.is_file():
            require(not missing.is_symlink(), f"{row['id']}: the 404 target must not be a symbolic link.")
            missing.unlink()
            reset[missing.name] = "removed (404 target must stay missing)"
    if row["apply_kind"] == "f01":
        recovery = media / row["apply"]["recovery_file"].rsplit("/", 1)[-1]
        if not recovery.is_file():
            pe.copy_owned(media / f"matrix-{ext}-p4b.{ext}", recovery,
                          label=f"recovery source restore {row['id']}")
            reset[recovery.name] = "restored recovery source"
    return reset


def setup_matrix_media(rows: list[dict]) -> dict:
    """Create the run-owned media files every selected row touches, with A content on the switch URLs.

    Every source byte comes from this run's fixtures; the switch URL files start as byte-identical
    A content so the pre-switch state is verifiable, and ``missing-f01`` is deliberately never
    created. Nothing here is a control API: rows switch content later through a single atomic
    ``os.replace``.
    """
    media = matrix_media_dir()
    created: dict[str, str] = {}
    needed: set[str] = set()
    for row in rows:
        needed.add(row["media"])
        apply = row["apply"]
        for key in ("to", "recovery_file", "corrupt_to"):
            if apply.get(key):
                needed.add(apply[key])
        if apply.get("url"):
            target_name = apply["url"][len(MEDIA_PREFIX):].split("?", 1)[0]
            if target_name.startswith("missing-"):
                pass  # the F01 404 target must stay missing until the recovery stage
            else:
                # A URL-change row's new address must really serve its bytes from this run's files;
                # the file behind it is created here from the row's fixture content.
                needed.add(target_name)
    source_map: dict[str, str] = {}
    for ext in ("mp4", "mkv"):
        source_map[f"switch-copy-{ext}.{ext}"] = f"baseline-{ext}-a.{ext}"
        source_map[f"media-p02b-{ext}.{ext}"] = f"baseline-{ext}-b.{ext}"
        source_map[f"media-p04b-{ext}.{ext}"] = f"matrix-{ext}-p4b.{ext}"
    for name in sorted(needed):
        if name in source_map:
            source = source_map[name]
            pe.copy_owned(media / source, media / name, label=f"matrix media {name}")
            created[name] = "copy of " + source
        elif name.startswith("switch-"):
            ext = "mp4" if name.endswith(".mp4") else "mkv"
            source = f"baseline-{ext}-a.{ext}"
            pe.copy_owned(media / source, media / name, label=f"switch start {name}")
            created[name] = "A content start"
        elif "/" in name and name.startswith("regular-"):
            # The D04 regular-media files are ordinary (non-STRM) items under their own library path.
            ext = "mp4" if name.endswith(".mp4") else "mkv"
            target = media / name
            target.parent.mkdir(parents=True, exist_ok=True)
            pe.write_owned_bytes(target, (media / f"baseline-{ext}-a.{ext}").read_bytes(),
                                 label=f"regular media {target.name}")
            created[name] = "regular media written from baseline A"
        elif name.startswith("matrix-"):
            created[name] = "generated fixture"  # already present from generate_matrix_fixtures
    return {"created": created, "missingF01": "never created"}


def write_matrix_strm(row: dict, tokens: dict | None = None, url: str | None = None,
                      extra: str | None = None, unversioned: bool = False) -> dict:
    """Write (or rewrite) the run-owned STRM for the row and return its content identity."""
    media = "mp4" if row["fmt"] == "MP4" else "mkv"
    base_url = url or row["url"]
    if unversioned:
        lines = ["# legacy unversioned stream file", base_url]
    else:
        value = tokens if tokens is not None else row["old"]
        lines = ["# strm-probe-version:1"]
        if value.get("sha1") is not None:
            lines.append(f"# strm-probe-sha1:{value['sha1']}")
        if value.get("size") is not None:
            lines.append(f"# strm-probe-size:{value['size']}")
        if extra:
            lines.append(extra)
        lines.append(base_url)
    target = pe.WORK / "strm" / (row["strm_name"] + ".strm")
    pe.write_owned_bytes(target, ("\n".join(lines) + "\n").encode("utf-8"), label=f"STRM {row['id']}")
    return {"path": str(target), "url": base_url, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "lines": lines, "mediaExtension": media}


def apply_matrix_change(row: dict) -> dict:
    """Apply the row's frozen pre-window mutation exactly once, atomically, before the playback."""
    media = matrix_media_dir()
    ext = "mp4" if row["fmt"] == "MP4" else "mkv"
    apply = row["apply"]
    kind = row["apply_kind"]
    record: dict[str, object] = {"kind": kind}
    if kind in ("manifest", "manifest-url", "comment", "d06"):
        if kind in ("manifest-url", "d06"):
            tokens = {"sha1": apply.get("sha1"), "size": apply.get("size")}
        elif kind == "comment":
            tokens = dict(row["old"])
        else:
            # A token named in the rewrite is written (DELETE removes it); a token absent from the
            # rewrite keeps the old-side value, so a kept value is always an explicit decision.
            tokens = {}
            for field in ("sha1", "size"):
                if field in apply:
                    if apply[field] is not DELETE:
                        tokens[field] = apply[field]
                else:
                    tokens[field] = row["old"][field]
        if kind in ("manifest-url", "d06"):
            record["strm"] = write_matrix_strm(row, tokens=tokens, url=apply["url"])
        elif kind == "comment":
            record["strm"] = write_matrix_strm(row, tokens=tokens, extra=apply["extra"])
        else:
            record["strm"] = write_matrix_strm(row, tokens=tokens)
    elif kind == "mtime":
        target = pe.WORK / "strm" / (row["strm_name"] + ".strm")
        stamp = time.time() + 3600
        os.utime(target, (stamp, stamp))
        record["newMtime"] = stamp
        record["strm"] = {"path": str(target), "url": row["url"],
                          "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    elif kind == "rewrite":
        # The row's STRM identity is its stable ``strm_name``: ``row["item"]`` is replaced by the
        # native item dictionary once the row has been scanned, so it can never key a path.
        target = pe.WORK / "strm" / (row["strm_name"] + ".strm")
        current = target.read_bytes()
        before = hashlib.sha256(current).hexdigest()
        staging = pe.WORK / "strm" / ("." + row["strm_name"] + ".rewritten.strm")
        pe.write_owned_bytes(staging, current, label=f"rewritten STRM bytes {row['id']}")
        os.replace(staging, target)  # same bytes, same path, new inode/mtime
        after = hashlib.sha256(target.read_bytes()).hexdigest()
        require(before == after, f"{row['id']}: the byte-identical STRM rewrite changed the content.")
        record["contentSha256Unchanged"] = True
        record["strm"] = {"path": str(target), "url": row["url"], "sha256": after}
        return record
    elif kind == "switch":
        source = media / apply["to"]
        destination = media / row["media"]
        require(source.is_file(), f"The switch source {source.name} for {row['id']} does not exist.")
        # Shared partners must survive for the following rows in the same batch, so the fixed URL
        # is moved to the partner bytes through a row-owned staging copy; the partner file itself
        # is never consumed. The destination file exists (created by setup_matrix_media) and stays
        # owned by this run, so an atomic replace on it never recreates a run path.
        require(destination.is_file(), f"The switch destination {destination.name} for {row['id']} is missing.")
        staging = media / (".staging-" + uuid.uuid4().hex[:12] + "-" + destination.name)
        pe.copy_owned(source, staging, label=f"staging switch copy for {row['id']}")
        os.replace(staging, destination)  # atomic: the fixed URL serves new bytes only after this
        record["switchedFrom"] = row["media"]
        record["switchedTo"] = apply["to"]
        record["switchSha256"] = hashlib.sha256(destination.read_bytes()).hexdigest()
        tokens = {}
        for field in ("sha1", "size"):
            value = apply.get(field, row["old"][field])
            if value is not DELETE:
                tokens[field] = value
        record["strm"] = write_matrix_strm(row, tokens=tokens)
    elif kind == "f01":
        # The failing window's manifest documents the real prepared B identity behind the missing
        # URL; it must not wipe the identity fields.
        record["strm"] = write_matrix_strm(row, tokens={"sha1": apply.get("sha1"), "size": apply.get("size")},
                                           url=apply["url"])
        record["missingUrl"] = apply["url"]
    elif kind == "f02":
        source = media / apply["corrupt_to"]
        destination = media / row["media"]
        require(destination.is_file(), f"The corrupt destination {destination.name} for {row['id']} is missing.")
        staging = media / (".staging-" + uuid.uuid4().hex[:12] + "-" + destination.name)
        pe.copy_owned(source, staging, label=f"staging corrupt copy for {row['id']}")
        os.replace(staging, destination)
        record["switchedTo"] = apply["corrupt_to"]
        record["switchSha256"] = hashlib.sha256(destination.read_bytes()).hexdigest()
        record["strm"] = write_matrix_strm(row, tokens={"sha1": apply["corrupt_sha1"],
                                                          "size": apply["corrupt_size"]})
    else:
        require(kind in ("none", "d02", "d03", "d04", "d05"), f"Unhandled apply kind {kind!r}.")
    return record


def recovery_stage(row: dict) -> dict:
    """Place the recovered B bytes on the same target URL and update the manifest to its real identity."""
    apply = row["apply"]
    media = matrix_media_dir()
    record: dict[str, object] = {"recoveredTo": apply["recovery_file"]}
    if row["apply_kind"] == "f01":
        target = media / apply["recovery_file"].rsplit("/", 1)[-1]
        # The 404 target file now exists on the same URL with the real recovered bytes.
        missing_name = apply["url"].rsplit("/", 1)[-1]
        source = media / apply["recovery_file"]
        pe.write_owned_bytes(media / missing_name, source.read_bytes(),
                             label=f"recovered media {missing_name}")
        target = media / missing_name
        record["target"] = missing_name
        record["strm"] = write_matrix_strm(row, tokens={"sha1": row["fp_tokens"][0],
                                                          "size": row["fp_tokens"][1]},
                                           url=apply["url"])
    else:  # f02: the fixed URL already holds the corrupted bytes; replace them atomically.
        source = media / apply["recovery_file"]
        destination = media / row["media"]
        require(destination.is_file(), f"The recovery destination {destination.name} for {row['id']} is missing.")
        staging = media / (".staging-" + uuid.uuid4().hex[:12] + "-" + destination.name)
        pe.copy_owned(source, staging, label=f"staging recovery copy for {row['id']}")
        os.replace(staging, destination)
        target = destination
        record["target"] = destination.name
        record["strm"] = write_matrix_strm(row, tokens={"sha1": row["fp_tokens"][0],
                                                          "size": row["fp_tokens"][1]})
    record["recoveredSha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    return record


def plugin_configuration(auth: str) -> dict:
    # The existing verified entry (package/scan/configuration tooling) addresses the plugin
    # configuration without a version segment; a guessed /0.1.0.0/ route is not part of that contract.
    status, body = pe.request_json("GET", f"/Plugins/{pkg.PLUGIN_ID}/Configuration",
                                  headers={"Authorization": auth})
    require(status == 200, "The plugin configuration read failed.")
    return body


def set_plugin_configuration(auth: str, changes: dict) -> int:
    body = plugin_configuration(auth)
    body.update(changes)
    status, _ = pe.request_json("POST", f"/Plugins/{pkg.PLUGIN_ID}/Configuration", body=body,
                                headers={"Authorization": auth})
    return status


# The pinned server answers the plugin configuration POST with 204 No Content; the accepted
# complete configuration gate records exactly ``serverStatus: 204`` for the same route. 200 with a
# body is the other documented success, so both are accepted and the real status is recorded.
CONFIGURATION_ACCEPTED_STATUSES = (200, 204)


def apply_plugin_configuration(auth: str, changes: dict) -> dict:
    """Apply one configuration change, accept only a native success, and verify the read-back.

    The returned record carries the actual HTTP status and the read-back of every changed field, so
    a status-only assertion can never stand in for a change the server did not really apply.

    The write is issued before that confirming read-back, so from the moment this helper is entered
    the server may already hold the new value. A failure therefore raises ``ConfigurationApplyError``
    with the record built so far — the real POST status and the read-back error stay auditable, and
    the caller still has to restore the original value instead of assuming nothing changed.
    """
    record: dict[str, object] = {"changes": dict(changes), "status": None, "observed": None}
    try:
        status = set_plugin_configuration(auth, changes)
        record["status"] = status
        require(status in CONFIGURATION_ACCEPTED_STATUSES,
                f"The plugin configuration change {changes} failed with HTTP {status}.")
        observed = plugin_configuration(auth)
        readback = {name: observed.get(name) for name in changes}
        record["observed"] = readback
        mismatched = {name: readback[name] for name, value in changes.items() if readback[name] != value}
        require(not mismatched,
                f"The plugin configuration change {changes} was not applied ({mismatched}).")
    except (BaselineError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        record["error"] = f"{type(error).__name__}: {error}"
        raise ConfigurationApplyError(str(error), record) from error
    return record


def restore_plugin_configuration(changes: dict) -> dict:
    """Restore changed configuration after a failed row and verify it really took effect.

    A real Web Play revokes the API token the journey held, so every attempt authenticates again;
    a failure is reported instead of being turned into a passing row.
    """
    attempts: list[dict] = []
    last_error = None
    for attempt in (1, 2):
        try:
            auth = refresh_auth()
            status = set_plugin_configuration(auth, changes)
            observed = plugin_configuration(auth)
            readback = {name: observed.get(name) for name in changes}
            attempts.append({"attempt": attempt, "status": status, "observed": readback})
            if status in CONFIGURATION_ACCEPTED_STATUSES and readback == {k: v for k, v in changes.items()}:
                return {"status": "restored", "attempts": attempts, "observed": readback}
            last_error = f"HTTP {status} with read-back {readback}"
        except (BaselineError, RuntimeError, OSError, subprocess.SubprocessError) as error:
            last_error = f"{type(error).__name__}: {error}"
            attempts.append({"attempt": attempt, "error": last_error})
    return {"status": "FAILED", "attempts": attempts, "error": last_error}


def restore_plugin_enabled() -> dict:
    """Re-enable the whole plugin after a failed D02 and verify the real plugin status."""
    attempts: list[dict] = []
    last_error = None
    for attempt in (1, 2):
        try:
            auth = refresh_auth()
            status = pkg.plugin_action(auth, True)
            observed = str(pkg.plugin_status(auth))
            attempts.append({"attempt": attempt, "status": status, "pluginStatus": observed})
            if status in CONFIGURATION_ACCEPTED_STATUSES and observed.lower() not in {"disabled"}:
                return {"status": "restored", "attempts": attempts, "pluginStatus": observed}
            last_error = f"HTTP {status} with plugin status {observed!r}"
        except (BaselineError, RuntimeError, OSError, subprocess.SubprocessError) as error:
            last_error = f"{type(error).__name__}: {error}"
            attempts.append({"attempt": attempt, "error": last_error})
    return {"status": "FAILED", "attempts": attempts, "error": last_error}


def native_static_stream_read(auth: str, item_id: str, head_bytes: int = 256 * 1024) -> dict:
    """The existing native read-only entry with no probe permission: static stream transfer."""
    base = credentials()["base_url"]
    request = pe.urllib.request.Request(f"{base}/Videos/{item_id}/stream?static=true",
                                        headers={"Authorization": auth})
    try:
        with pe.urllib.request.urlopen(request, timeout=120) as response:
            head = response.read(head_bytes)
            status = response.status
            contentType = response.headers.get("Content-Type")
    except pe.urllib.error.HTTPError as error:
        head = error.read(head_bytes)
        status = error.code
        contentType = error.headers.get("Content-Type") if error.headers else None
    return {"status": status, "contentType": contentType, "headSha256": hashlib.sha256(head).hexdigest(),
            "headLength": len(head)}


# The pinned server's own database file name. Older Jellyfin layouts used ``db.sqlite3``; the
# fixed 12.2 startup log names ``/config/data/jellyfin.db``, so both are recognised and exactly one
# real file must exist. The name is discovered, never assumed: replacing the file name alone is not
# enough because the stream table's columns and value representations differ as well.
NATIVE_DATABASE_NAMES = ("jellyfin.db", "db.sqlite3")
# The native stream table is recognised by the column pair carrying the owning item and the stream
# type, plus the codec column the attachment table also has. Nothing is guessed from a table name.
NATIVE_ITEM_COLUMNS = ("itemid", "item_id")
NATIVE_STREAM_TYPE_COLUMNS = ("streamtype", "type")
NATIVE_CODEC_COLUMNS = ("codec",)
# ``MediaStreamType`` in the pinned server: 0 = Audio, 1 = Video.
NATIVE_STREAM_TYPE_VALUES = {"Video": 1, "Audio": 0}


def native_database_path(config_root: Path | None = None) -> Path:
    """Return this run's own Jellyfin database file, or refuse when it is not there."""
    data_directory = (config_root or (pe.WORK / "config")) / "data"
    found = [data_directory / name for name in NATIVE_DATABASE_NAMES if (data_directory / name).is_file()]
    require(found, f"No Jellyfin database ({', '.join(NATIVE_DATABASE_NAMES)}) was found under the owned config/data.")
    require(len(found) == 1, f"Ambiguous native database location: {[path.name for path in found]}.")
    return found[0]


def native_stream_table(connection: sqlite3.Connection) -> dict:
    """Locate the native stream table with its real column names and value representation.

    The pinned database stores ``MediaStreamInfos(ItemId TEXT, StreamType INTEGER, Codec TEXT)``;
    the lookup therefore accepts the documented column-name variants by their real position and
    reports the representation so the delete never writes a string where an integer belongs.
    """
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    matches: list[dict] = []
    for table in tables:
        columns = {str(row[1]).lower(): str(row[1])
                   for row in connection.execute(f"PRAGMA table_info(\"{table}\")")}
        item_column = next((columns[name] for name in NATIVE_ITEM_COLUMNS if name in columns), None)
        type_column = next((columns[name] for name in NATIVE_STREAM_TYPE_COLUMNS if name in columns), None)
        codec_column = next((columns[name] for name in NATIVE_CODEC_COLUMNS if name in columns), None)
        if item_column and type_column and codec_column:
            declaration = {str(row[1]).lower(): str(row[2]).upper()
                           for row in connection.execute(f"PRAGMA table_info(\"{table}\")")}
            matches.append({"table": table, "itemColumn": item_column, "typeColumn": type_column,
                            "codecColumn": codec_column,
                            "typeAffinity": declaration.get(str(type_column).lower(), "")})
    require(len(matches) == 1, f"Expected exactly one native stream table, found {matches} in {tables}.")
    return matches[0]


def native_item_identity(value: object) -> str | None:
    """Normalise one stored item identity to the 32-character GUID hex form.

    The pinned database stores the item id as TEXT (``00269FE5-4AF7-30BB-...``); an older layout
    stored the raw binary GUID, whose first three blocks are little-endian. Both are normalised so
    the comparison is exact and never a prefix/substring match.
    """
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        require(len(raw) == 16, f"A stored binary item id must be a 16-byte GUID, found {len(raw)} bytes.")
        return uuid.UUID(bytes_le=raw).hex
    if isinstance(value, str):
        text = value.strip().strip("{}").replace("-", "").lower()
        require(re.fullmatch(r"[0-9a-f]{32}", text),
                "A stored item id must be a GUID string or 16 raw bytes.")
        return text
    return None


def native_stream_type_values(type_affinity: str, observed: list[object], kinds: list[str]) -> list[object]:
    """Map the requested stream kinds onto the table's real stored representation."""
    text_affinity = "CHAR" in type_affinity or "TEXT" in type_affinity
    if text_affinity or any(isinstance(value, str) for value in observed):
        return list(kinds)
    require(not any(isinstance(value, (bytes, bytearray)) for value in observed),
            "The native stream type column must be stored as an integer or text, not a blob.")
    return [NATIVE_STREAM_TYPE_VALUES[kind] for kind in kinds]


def p01_stream_surgery(rows: list[dict], drop_spec: dict, evidence_dir: Path, stage: str) -> dict:
    """Bounded stream removal in this run's stopped owned copy, then read-only verification.

    The service is stopped first, the real database file and its WAL sidecars are backed up, the
    schema is inspected so the stream table is never guessed, the item rows are matched by their
    real stored identity, and the delete is parameterized to the target item plus the allowed
    stream types in their real representation. After the service is back up, the saved stream set
    is verified read-only before any playback in this stage.
    """
    record: dict[str, object] = {"stage": stage, "targets": []}
    run(*DOCKER, "stop", "-t", "30", pe.container_name("jellyfin"), timeout=300)
    database = native_database_path()
    record["databaseName"] = database.name
    backup_dir = evidence_dir / "db-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:8]
    # The evidence directory sits outside the owned workspace (so cleanup keeps it); the backup is
    # therefore written with plain file IO under the same non-symlink guarantees, not through the
    # workspace-scoped pe.copy_owned guard, which must keep refusing foreign destinations.
    sidecar_names = (database.name + "-wal", database.name + "-shm")
    backups: dict[str, str] = {}
    for name in (database.name, *sidecar_names):
        source = database.parent / name
        target = backup_dir / f"p01-{stage}-{token}-{name}"
        require(not target.is_symlink(), "The P01 backup path must not be a symbolic link.")
        if not source.is_file():
            continue
        shutil.copy2(source, target)
        backups[name] = str(target)
    record["backup"] = backups.get(database.name)
    record["sidecarBackups"] = {name: backups.get(name) for name in sidecar_names if name in backups}
    record["walSideFiles"] = {name: (database.parent / name).is_file() for name in sidecar_names}
    connection = sqlite3.connect(database)
    try:
        if connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal":
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            connection.commit()
        stream = native_stream_table(connection)
        record["streamTable"] = stream["table"]
        record["streamTableColumns"] = {"item": stream["itemColumn"], "type": stream["typeColumn"],
                                        "typeAffinity": stream["typeAffinity"]}
        item_column, type_column, table = stream["itemColumn"], stream["typeColumn"], stream["table"]
        raw_ids = [row[0] for row in connection.execute(f'SELECT DISTINCT "{item_column}" FROM "{table}"')]
        identities = [(raw, native_item_identity(raw)) for raw in raw_ids]
        require(all(identity is not None for _, identity in identities),
                "Every stored native item id must be a GUID string or 16 raw bytes.")
        observed_types = [row[0] for row in connection.execute(f'SELECT DISTINCT "{type_column}" FROM "{table}"')]
        record["storedStreamTypes"] = sorted({str(value) for value in observed_types})

        for row in rows:
            item_guid = uuid.UUID(row["item"]["Id"])
            matches = [raw for raw, identity in identities if identity == item_guid.hex]
            require(len(matches) == 1,
                    f"P01 {row['id']}: expected exactly one stream row owner for the item, found {len(matches)}.")
            kinds = ["Video", "Audio"] if drop_spec[row["id"]] == "all" else ["Video"]
            values = native_stream_type_values(stream["typeAffinity"], observed_types, kinds)
            placeholders = ",".join("?" for _ in values)
            item_ref = '"' + item_column + '"'
            type_ref = '"' + type_column + '"'
            table_ref = '"' + table + '"'
            present = connection.execute(
                "SELECT DISTINCT " + type_ref + " FROM " + table_ref + " WHERE " + item_ref +
                " = ? AND " + type_ref + " IN (" + placeholders + ") ORDER BY " + type_ref,
                [matches[0], *values]).fetchall()
            require(len(present) == len(values),
                    f"P01 {row['id']}: the target item does not carry every requested stream type; "
                    f"the surgery would remove {present} instead of {values}.")
            cursor = connection.execute(
                "DELETE FROM " + table_ref + " WHERE " + item_ref + " = ? AND " + type_ref +
                " IN (" + placeholders + ")", [matches[0], *values])
            require(cursor.rowcount > 0,
                    f"P01 {row['id']}: the parameterized delete matched no stream row.")
            record["targets"].append({"row": row["id"], "removedRows": cursor.rowcount, "kinds": kinds,
                                      "storedValues": values})
        connection.commit()
    finally:
        connection.close()
    record["walSideFilesAfter"] = {name: (database.parent / name).is_file() for name in sidecar_names}
    pe.compose("up")
    pe.wait_healthy()
    auth = refresh_auth()
    for row in rows:
        saved = saved_stream_types(auth, row["item"]["Id"])
        expected = [] if drop_spec[row["id"]] == "all" else ["Audio"]
        record[f"{row['id']}.savedAfter"] = saved
        require(sorted(saved) == sorted(expected),
                f"P01 {row['id']}: the read-only verification after the restart saw {saved}, "
                f"expected {expected}.")
    return record


def fp_expected_failures(auth: str, row: dict, *, url: str, sha1_token: object, size_token: object) -> list[str]:
    """Check the stored five-field fingerprint against the row's parsed manifest expectation."""
    sha1, size = parsed_tokens(sha1_token, size_token)
    key = row.get("sourceKey") or current_source_key(auth, row["item"]["Id"])
    observed = fingerprint_row_or_none(row["item"]["Id"], key) if key else None
    return fingerprint_fields_match(observed, expected_url=url, sha1=sha1, size=size,
                                    expected_item_id=row["item"]["Id"], expected_source_id=key)


def fp_snapshot(auth: str, row: dict) -> dict | None:
    key = row.get("sourceKey") or current_source_key(auth, row["item"]["Id"])
    return fingerprint_row_or_none(row["item"]["Id"], key) if key else None


def trust_play(auth: str, row: dict, evidence_dir: Path) -> dict:
    """The first-trust journey: accept the prepared native stream and establish the fingerprint.

    First trust is never a probe: the expected window delta is zero and the plugin must report no
    probe call. The row then remembers the frozen trust fingerprint for every later comparison.
    """
    obs = play_once(auth, row, "first-trust", evidence_dir)
    assert_playback(row, obs, counter_validated=True, expected_delta=0)
    require(any("FirstTrust" in event for event in obs["pluginEvents"]),
            f"{row['id']}: the existing stream was not accepted through first trust ({obs['pluginEvents']}).")
    require(all(call in (0, None) for call in obs["pluginProbeCalls"]),
            f"{row['id']}: first trust reported a plugin probe {obs['pluginEvents']}.")
    # The Web Play revoked the token the playback was started with; every read-only request after
    # it authenticates again.
    auth = refresh_auth()
    failures = fp_expected_failures(auth, row, url=row["url"], sha1_token=row["old"]["sha1"],
                                    size_token=row["old"]["size"])
    require(not failures, f"{row['id']} first-trust: " + "; ".join(failures))
    row["trust_fp"] = fp_snapshot(auth, row)
    return obs


def post_window_fp_failures(auth: str, row: dict) -> list[str]:
    """The fingerprint check after a measurement window, per the row's expectation."""
    if row["fp_kind"] == "new":
        return fp_expected_failures(auth, row, url=row["fp_url"], sha1_token=row["fp_tokens"][0],
                                    size_token=row["fp_tokens"][1])
    if row["fp_kind"] == "none":
        key = row.get("sourceKey") or current_source_key(auth, row["item"]["Id"])
        observed = fingerprint_row_or_none(row["item"]["Id"], key) if key else None
        return [f"{row['id']}: a fingerprint row must not exist for {row['id']}"] if observed else []
    frozen = row.get("trust_fp")
    observed = fp_snapshot(auth, row)
    if frozen is None or observed is None:
        return [f"{row['id']}: the trusted baseline fingerprint is missing before or after the window"]
    return ([f"{row['id']}: the trusted fingerprint changed across the window: {frozen} -> {observed}"]
            if observed != frozen else [])


def restart_then_play(auth: str, row: dict, evidence_dir: Path, result: dict,
                      url_for_source: str | None, record_only: bool = False) -> None:
    """Freeze the state, restart, verify read-only, then replay without duplicate probing.

    ``record_only`` is the D-row mode: native delegation rows report the real ffprobe count
    instead of requiring zero probes, and the frozen/read-only comparison covers the sources,
    the address, the probe count and the fingerprint presence/absence.
    """
    frozen = freeze_state(auth, row)
    result["frozenBeforeRestart"] = frozen
    pkg.restart()
    auth = refresh_auth()
    observed_state = read_only_state(auth, row)
    if record_only:
        if observed_state["nativeSources"] != frozen["nativeSources"]:
            failures = [f"{row['id']}: the natively saved media sources changed across the restart"]
        else:
            failures = []
        if row["fp_kind"] == "none":
            if observed_state["fingerprint"] is not None:
                failures.append(f"{row['id']}: a fingerprint appeared across the restart")
        elif observed_state["fingerprint"] != frozen["fingerprint"]:
            failures.append(f"{row['id']}: the fingerprint changed across the restart")
        require(not failures, "; ".join(failures))
        expected_delta = None
    else:
        restart_failures = restart_readback_failures(frozen, observed_state)
        require(not restart_failures, f"{row['id']}: " + "; ".join(restart_failures))
        expected_delta = 0
    after = play_once(auth, row, "after-restart", evidence_dir)
    assert_playback(row, after, counter_validated=not record_only,
                    expected_delta=expected_delta, url_for_source=url_for_source,
                    allow_missing_media_fetch=row["apply_kind"] == "d04")
    # The post-restart playback revoked the token it was started with; the follow-up fingerprint
    # read authenticates again instead of reusing it.
    auth = refresh_auth()
    fp_final = fp_snapshot(auth, row)
    if not record_only:
        require(fp_final == observed_state["fingerprint"],
                f"{row['id']}: the fingerprint changed across the restart read-back.")
    result["readOnlyAfterRestart"] = observed_state
    result["afterRestart"] = {"ffprobe": after["ffprobe"], "events": after["pluginEvents"],
                              "advancedSeconds": after["playback"].get("advancedSeconds")}


def d_row_restart(auth: str, row: dict, evidence_dir: Path, result: dict) -> None:
    """The D-row restart: freeze, restart, read-only compare, replay with the native probe count
    reported but not required to be zero (contract: no native probe-count obligation)."""
    restart_then_play(auth, row, evidence_dir, result, None, record_only=True)


def journey_normal(auth: str, row: dict, evidence_dir: Path) -> dict:
    result: dict[str, object] = {}
    if row["trust"]:
        result["firstTrust"] = trust_play(auth, row, evidence_dir)
        auth = refresh_auth()
    result["apply"] = apply_matrix_change(row) if row["apply_kind"] != "none" else {"kind": "none"}
    if row["apply_kind"] == "manifest-url":
        # From here on the measurement windows, the probes and the saved source all belong to the
        # new address; the old URL stays only in the evidence record.
        row["url"] = row["apply"]["url"]
    obs = play_once(auth, row, "window", evidence_dir)
    url_for_source = row["fp_url"] if row["expect_probes"] else None
    assert_playback(row, obs, counter_validated=True, expected_delta=row["expect_probes"],
                    url_for_source=url_for_source)
    if row["expect_probes"]:
        require(any(call == 1 for call in obs["pluginProbeCalls"]),
                f"{row['id']}: the plugin reported no successful probe call ({obs['pluginEvents']}).")
    auth = refresh_auth()
    fp_failures = post_window_fp_failures(auth, row)
    require(not fp_failures, "; ".join(fp_failures))
    result["window"] = {"ffprobe": obs["ffprobe"], "events": obs["pluginEvents"],
                        "advancedSeconds": obs["playback"].get("advancedSeconds"),
                        "screenshots": [obs["playback"].get("startScreenshot"),
                                         obs["playback"].get("progressScreenshot")]}
    second = play_once(auth, row, "second-play", evidence_dir)
    assert_playback(row, second, counter_validated=True, expected_delta=0, url_for_source=url_for_source)
    result["secondPlay"] = {"ffprobe": second["ffprobe"], "events": second["pluginEvents"]}
    restart_then_play(auth, row, evidence_dir, result, url_for_source)
    result["status"] = "PASS"
    return result


def p01_precondition(auth: str, row: dict) -> dict:
    """Read-only check that this row really starts without its necessary video stream.

    The bounded removal itself is the stopped-copy surgery recorded once for all selected P01 rows
    in the preparation summary (backup, schema-inspected, parameterized delete, read-only verified).
    Repeating it here would delete rows that are already gone, so the journey only verifies the
    frozen precondition: no Video stream, and Audio still present when only Video was dropped.
    """
    saved = saved_stream_types(auth, row["item"]["Id"])
    expected = [] if row["apply"]["drop"] == "all" else ["Audio"]
    require(sorted(saved) == sorted(expected),
            f"{row['id']}: the prepared missing-stream precondition is {saved}, expected {expected}.")
    return {"stage": "precondition", "savedStreams": saved, "expected": expected}


def journey_p01(auth: str, row: dict, evidence_dir: Path) -> dict:
    drop = row["apply"]["drop"]
    prime = row["apply"]["prime"]
    result: dict[str, object] = {"journey": "p01", "drop": drop, "prime": prime}
    drop_spec = {row["id"]: drop}
    result["precondition"] = p01_precondition(auth, row)
    require(fp_snapshot(auth, row) is None, f"{row['id']}: a fingerprint existed before the window.")
    if prime:
        # The "with fingerprint" P01 rows prime once: the probe succeeds and commits the fingerprint,
        # then the streams are removed again so the window starts with a fingerprint but no streams.
        obs = play_once(auth, row, "prime", evidence_dir, relax_console=True)
        assert_playback(row, obs, counter_validated=True, expected_delta=1)
        require(any(call == 1 for call in obs["pluginProbeCalls"]),
                f"{row['id']}: the prime probe was not reported {obs['pluginEvents']}.")
        auth = refresh_auth()
        failures = fp_expected_failures(auth, row, url=row["url"], sha1_token=row["fp_tokens"][0],
                                        size_token=row["fp_tokens"][1])
        require(not failures, f"{row['id']} prime: " + "; ".join(failures))
        row["trust_fp"] = fp_snapshot(auth, row)
        result["prime"] = {"ffprobe": obs["ffprobe"], "fingerprint": row["trust_fp"]}
        result["surgery2"] = p01_stream_surgery([row], drop_spec, evidence_dir, "prime-after")
        auth = refresh_auth()
    obs = play_once(auth, row, "window", evidence_dir)
    assert_playback(row, obs, counter_validated=True, expected_delta=1)
    require(any(call == 1 for call in obs["pluginProbeCalls"]),
            f"{row['id']}: the window probe was not reported {obs['pluginEvents']}.")
    auth = refresh_auth()
    failures = fp_expected_failures(auth, row, url=row["url"], sha1_token=row["fp_tokens"][0],
                                    size_token=row["fp_tokens"][1])
    require(not failures, f"{row['id']} window: " + "; ".join(failures))
    result["window"] = {"ffprobe": obs["ffprobe"], "events": obs["pluginEvents"],
                        "advancedSeconds": obs["playback"].get("advancedSeconds")}
    second = play_once(auth, row, "second-play", evidence_dir)
    assert_playback(row, second, counter_validated=True, expected_delta=0)
    result["secondPlay"] = {"ffprobe": second["ffprobe"], "events": second["pluginEvents"]}
    restart_then_play(auth, row, evidence_dir, result, None)
    result["status"] = "PASS"
    return result


def journey_f01(auth: str, row: dict, evidence_dir: Path) -> dict:
    result: dict[str, object] = {"journey": "f01"}
    result["firstTrust"] = trust_play(auth, row, evidence_dir)
    auth = refresh_auth()
    result["apply"] = apply_matrix_change(row)  # manifest now points at the real 404 target
    row["url"] = row["apply"]["url"]
    # From here the requested (and recovered) media is served from the missing target's own file
    # name, so the media-request counter must watch that name, not the baseline A it trusted.
    row["watch_media"] = row["apply"]["url"].rsplit("/", 1)[-1]
    failed = play_once(auth, row, "fail-window", evidence_dir, relax_console=True)
    require(failed["playback"].get("advanced") is not True,
            f"{row['id']}: the 404 target must not produce an advancing playback.")
    require(failed["ffprobe"]["delta"] == 1,
            f"{row['id']}: the failed probe was not attempted {failed['ffprobe']}.")
    require(failed["fingerprint"] == row["trust_fp"],
            f"{row['id']}: the failed probe overwrote the trusted baseline {failed['fingerprint']}.")
    require(failed["playback"].get("incompleteScreenshot") or failed["playback"].get("requestErrorScreenshot"),
            f"{row['id']}: no failure screenshot was captured for the 404 window.")
    result["failWindow"] = {"ffprobe": failed["ffprobe"], "events": failed["pluginEvents"],
                            "screenshots": [failed["playback"].get("incompleteScreenshot"),
                                             failed["playback"].get("requestErrorScreenshot")]}
    retry = play_once(auth, row, "fail-retry", evidence_dir, relax_console=True)
    require(retry["ffprobe"]["delta"] == 1, f"{row['id']}: the failed target still must be probed.")
    require(retry["fingerprint"] == row["trust_fp"],
            f"{row['id']}: the retry committed a fingerprint for a failed target.")
    result["failRetry"] = {"ffprobe": retry["ffprobe"], "events": retry["pluginEvents"]}
    frozen = freeze_state(auth, row)
    result["frozenBeforeRestart"] = frozen
    pkg.restart()
    auth = refresh_auth()
    observed_state = read_only_state(auth, row)
    restart_failures = restart_readback_failures(frozen, observed_state)
    require(not restart_failures, f"{row['id']}: " + "; ".join(restart_failures))
    require(observed_state["fingerprint"] == row["trust_fp"],
            f"{row['id']}: the restart changed the protected baseline.")
    result["recovery"] = recovery_stage(row)
    recovered = play_once(auth, row, "recovery-play", evidence_dir)
    url_for_source = row["fp_url"]
    assert_playback(row, recovered, counter_validated=True, expected_delta=1, url_for_source=url_for_source)
    auth = refresh_auth()
    failures = fp_expected_failures(auth, row, url=row["fp_url"], sha1_token=row["fp_tokens"][0],
                                    size_token=row["fp_tokens"][1])
    require(not failures, f"{row['id']} recovery: " + "; ".join(failures))
    result["recoveryPlay"] = {"ffprobe": recovered["ffprobe"],
                              "advancedSeconds": recovered["playback"].get("advancedSeconds")}
    second = play_once(auth, row, "second-play", evidence_dir)
    assert_playback(row, second, counter_validated=True, expected_delta=0, url_for_source=url_for_source)
    result["secondPlay"] = {"ffprobe": second["ffprobe"], "events": second["pluginEvents"]}
    restart_then_play(auth, row, evidence_dir, result, url_for_source)
    result["status"] = "PASS"
    return result


def journey_f02(auth: str, row: dict, evidence_dir: Path) -> dict:
    result: dict[str, object] = {"journey": "f02"}
    result["firstTrust"] = trust_play(auth, row, evidence_dir)
    auth = refresh_auth()
    result["apply"] = apply_matrix_change(row)  # the fixed URL now serves the corrupted bytes
    failed = play_once(auth, row, "fail-window", evidence_dir, relax_console=True)
    require(failed["playback"].get("advanced") is not True,
            f"{row['id']}: the corrupted target must not produce an advancing playback.")
    require(failed["ffprobe"]["delta"] == 1,
            f"{row['id']}: the failed probe was not attempted {failed['ffprobe']}.")
    require(failed["fingerprint"] == row["trust_fp"],
            f"{row['id']}: the failed probe overwrote the trusted baseline {failed['fingerprint']}.")
    result["failWindow"] = {"ffprobe": failed["ffprobe"], "events": failed["pluginEvents"],
                            "screenshots": [failed["playback"].get("incompleteScreenshot"),
                                             failed["playback"].get("requestErrorScreenshot")]}
    frozen = freeze_state(auth, row)
    result["frozenBeforeRestart"] = frozen
    pkg.restart()
    auth = refresh_auth()
    observed_state = read_only_state(auth, row)
    restart_failures = restart_readback_failures(frozen, observed_state)
    require(not restart_failures, f"{row['id']}: " + "; ".join(restart_failures))
    result["recovery"] = recovery_stage(row)
    recovered = play_once(auth, row, "recovery-play", evidence_dir)
    url_for_source = row["fp_url"]
    assert_playback(row, recovered, counter_validated=True, expected_delta=1, url_for_source=url_for_source)
    auth = refresh_auth()
    failures = fp_expected_failures(auth, row, url=row["fp_url"], sha1_token=row["fp_tokens"][0],
                                    size_token=row["fp_tokens"][1])
    require(not failures, f"{row['id']} recovery: " + "; ".join(failures))
    result["recoveryPlay"] = {"ffprobe": recovered["ffprobe"],
                              "advancedSeconds": recovered["playback"].get("advancedSeconds")}
    second = play_once(auth, row, "second-play", evidence_dir)
    assert_playback(row, second, counter_validated=True, expected_delta=0, url_for_source=url_for_source)
    result["secondPlay"] = {"ffprobe": second["ffprobe"], "events": second["pluginEvents"]}
    restart_then_play(auth, row, evidence_dir, result, url_for_source)
    result["status"] = "PASS"
    return result


def journey_d02(auth: str, row: dict, evidence_dir: Path) -> dict:
    """Whole plugin disabled: native playback of the versioned STRM, fingerprint preserved.

    The whole required journey — first native play, second play, freeze, restart, read-only
    comparison and the post-restart play — runs with the plugin still disabled. The plugin is
    re-enabled (and its real status verified) only after that journey, in a ``finally`` so a failed
    window inside the disabled phase still restores the server for later rows.
    """
    result: dict[str, object] = {"journey": "d02"}
    # A write is treated as applied from the moment it is sent: the native call can commit before its
    # status/read-back is observed, so the restore below must run for a sent-but-failed disable.
    disable_sent = False
    try:
        result["firstTrust"] = trust_play(auth, row, evidence_dir)
        auth = refresh_auth()
        result["configBefore"] = plugin_configuration(auth)
        disable_sent = True
        disable_status = pkg.plugin_action(auth, False)
        result["disableStatus"] = disable_status
        require(disable_status in CONFIGURATION_ACCEPTED_STATUSES,
                f"{row['id']}: the plugin disable failed with HTTP {disable_status}.")
        pkg.restart()
        auth = refresh_auth()
        status = str(pkg.plugin_status(auth)).lower()
        require(status not in {"active", "0"}, f"{row['id']}: the plugin remained active after disable.")
        obs = play_once(auth, row, "native-play", evidence_dir, relax_console=True)
        assert_playback(row, obs, counter_validated=True, expected_delta=None)
        require(obs["fingerprint"] == row["trust_fp"],
                f"{row['id']}: native playback with the plugin disabled changed the fingerprint.")
        result["nativePlay"] = {"ffprobe": obs["ffprobe"], "events": obs["pluginEvents"],
                                "advancedSeconds": obs["playback"].get("advancedSeconds"),
                                "note": "the native probe count is the real value; zero is not required"}
        auth = refresh_auth()
        second = play_once(auth, row, "native-play-second", evidence_dir, relax_console=True)
        assert_playback(row, second, counter_validated=True, expected_delta=None)
        require(second["fingerprint"] == row["trust_fp"],
                f"{row['id']}: the second native playback with the plugin disabled changed the fingerprint.")
        result["nativePlaySecond"] = {"ffprobe": second["ffprobe"], "events": second["pluginEvents"],
                                      "advancedSeconds": second["playback"].get("advancedSeconds")}
        auth = refresh_auth()
        d_row_restart(auth, row, evidence_dir, result)
        auth = refresh_auth()
        status = str(pkg.plugin_status(auth)).lower()
        require(status not in {"active", "0"},
                f"{row['id']}: the plugin was active before the restart playback finished.")
    finally:
        # The disabled phase must never leak into the next row, even when a window inside it failed.
        failure = sys.exc_info()[1]
        if disable_sent:
            restored = restore_plugin_enabled()
            result["restore"] = restored
            if failure is not None:
                result["failure"] = f"{type(failure).__name__}: {failure}"
            if restored.get("status") != "restored":
                raise ConfigurationRestoreError(
                    f"{row['id']}: the plugin could not be re-enabled after the disabled journey "
                    f"({restored.get('error')})" + (f"; the row itself failed with {result['failure']}"
                                                     if failure is not None else "") + ".", result)
            pkg.restart()
            restored["pluginStatusAfterRestart"] = str(pkg.plugin_status(refresh_auth()))
            if restored["pluginStatusAfterRestart"].lower() in {"disabled"}:
                raise ConfigurationRestoreError(
                    f"{row['id']}: the plugin was disabled again after the restore restart.", result)
            if failure is not None:
                # The switch was restored, but this row still failed: keep its reached stages and the
                # restore record, and never report it as passing.
                raise RowEvidenceError(f"{row['id']}: {result['failure']}", result) from failure
        elif failure is not None:
            # The disable write was never issued, so this row cannot have left the plugin disabled.
            result["failure"] = f"{type(failure).__name__}: {failure}"
            raise RowEvidenceError(f"{row['id']}: {result['failure']}", result) from failure
    result["configAfter"] = plugin_configuration(refresh_auth())
    result["status"] = "PASS"
    return result


def journey_d03(auth: str, row: dict, evidence_dir: Path) -> dict:
    """Only the playback auto-check is off: native playback, no optimization commit.

    As with D02 the second play, the freeze, the restart, the read-only comparison and the
    post-restart play all run while the auto-check is still off; the auto-check is restored to the
    value the row started with afterwards, in a ``finally`` so a failed window cannot leave the
    next row running against a changed switch.
    """
    result: dict[str, object] = {"journey": "d03"}
    auth = refresh_auth()
    before = plugin_configuration(auth)
    original = before.get("PlaybackAutoCheck")
    require(isinstance(original, bool),
            f"{row['id']}: the playback auto-check value was not readable ({original!r}).")
    result["configBefore"] = before
    result["firstTrust"] = trust_play(auth, row, evidence_dir)
    # The disable write is issued before its confirming read-back, so from the first statement in
    # the ``try`` the server may already hold the new value.  The restore therefore always runs from
    # ``finally`` — even when the change helper failed before it could return — and a row that fails
    # here is never reported as passing.
    try:
        result["disable"] = apply_plugin_configuration(refresh_auth(), {"PlaybackAutoCheck": False})
        pkg.restart()
        auth = refresh_auth()
        require(plugin_configuration(auth).get("PlaybackAutoCheck") is False,
                f"{row['id']}: the playback auto-check was not off after the restart.")
        before_events = plugin_event_lines()
        obs = play_once(auth, row, "native-play", evidence_dir, relax_console=True)
        assert_playback(row, obs, counter_validated=True, expected_delta=None)
        require(plugin_event_delta(before_events) == [],
                f"{row['id']}: plugin events were emitted while the auto-check was off.")
        require(obs["fingerprint"] == row["trust_fp"],
                f"{row['id']}: the disabled auto-check changed the fingerprint.")
        result["nativePlay"] = {"ffprobe": obs["ffprobe"],
                                "advancedSeconds": obs["playback"].get("advancedSeconds")}
        auth = refresh_auth()
        before_events = plugin_event_lines()
        second = play_once(auth, row, "native-play-second", evidence_dir, relax_console=True)
        assert_playback(row, second, counter_validated=True, expected_delta=None)
        require(plugin_event_delta(before_events) == [],
                f"{row['id']}: plugin events were emitted on the second play while the auto-check was off.")
        require(second["fingerprint"] == row["trust_fp"],
                f"{row['id']}: the second native playback changed the fingerprint.")
        result["nativePlaySecond"] = {"ffprobe": second["ffprobe"],
                                      "advancedSeconds": second["playback"].get("advancedSeconds")}
        auth = refresh_auth()
        d_row_restart(auth, row, evidence_dir, result)
        auth = refresh_auth()
        require(plugin_configuration(auth).get("PlaybackAutoCheck") is False,
                f"{row['id']}: the auto-check was restored before the restart playback finished.")
    except ConfigurationApplyError as error:
        # The write may already have been applied even though the helper never returned: keep the
        # real POST status and read-back error, then let the finally block restore the original.
        result["disable"] = dict(error.result)
        raise
    finally:
        failure = sys.exc_info()[1]
        restored = restore_plugin_configuration({"PlaybackAutoCheck": original})
        result["restore"] = restored
        if failure is not None:
            result["failure"] = f"{type(failure).__name__}: {failure}"
        if restored.get("status") != "restored":
            raise ConfigurationRestoreError(
                f"{row['id']}: the playback auto-check could not be restored to {original!r} "
                f"({restored.get('error')})" + (f"; the row itself failed with {result['failure']}"
                                                 if failure is not None else "") + ".", result)
        pkg.restart()
        observed = plugin_configuration(refresh_auth()).get("PlaybackAutoCheck")
        restored["observedAfterRestart"] = observed
        if observed is not original:
            raise ConfigurationRestoreError(
                f"{row['id']}: the playback auto-check read back {observed!r} after the restore "
                f"restart instead of {original!r}.", result)
        if failure is not None:
            raise RowEvidenceError(f"{row['id']}: {result['failure']}", result) from failure
    result["configAfter"] = plugin_configuration(refresh_auth())
    result["status"] = "PASS"
    return result


def journey_d04(auth: str, row: dict, evidence_dir: Path) -> dict:
    """Ordinary (non-STRM) media: native playback, no fingerprint, no versioned commit."""
    result: dict[str, object] = {"journey": "d04"}
    item_id = row["item"]["Id"]
    media_path = item_media_type(auth, item_id)["Path"]
    obs = play_once(auth, row, "native-play", evidence_dir, relax_console=True)
    assert_playback(row, obs, counter_validated=True, expected_delta=None,
                    allow_missing_media_fetch=True, expected_source_url=media_path)
    # The browser login revoked the pre-playback token; the follow-up read authenticates again.
    auth = refresh_auth()
    key = current_source_key(auth, item_id)
    observed_fp = fingerprint_row_or_none(item_id, key) if key else None
    require(observed_fp is None, f"{row['id']}: an ordinary media item carries a fingerprint row.")
    result["nativePlay"] = {"ffprobe": obs["ffprobe"], "events": obs["pluginEvents"],
                            "advancedSeconds": obs["playback"].get("advancedSeconds")}
    second = play_once(auth, row, "second-play", evidence_dir, relax_console=True)
    assert_playback(row, second, counter_validated=True, expected_delta=None,
                    allow_missing_media_fetch=True, expected_source_url=media_path)
    result["secondPlay"] = {"ffprobe": second["ffprobe"], "events": second["pluginEvents"]}
    auth = refresh_auth()
    d_row_restart(auth, row, evidence_dir, result)
    result["status"] = "PASS"
    return result


def journey_d05(auth: str, row: dict, evidence_dir: Path) -> dict:
    """Unversioned legacy STRM: native playback, no supported-version optimization commit."""
    result: dict[str, object] = {"journey": "d05"}
    item_id = row["item"]["Id"]
    obs = play_once(auth, row, "native-play", evidence_dir, relax_console=True)
    assert_playback(row, obs, counter_validated=True, expected_delta=None)
    auth = refresh_auth()
    key = current_source_key(auth, item_id)
    observed_fp = fingerprint_row_or_none(item_id, key) if key else None
    require(observed_fp is None, f"{row['id']}: an unversioned STRM carries a fingerprint row.")
    result["nativePlay"] = {"ffprobe": obs["ffprobe"], "events": obs["pluginEvents"],
                            "advancedSeconds": obs["playback"].get("advancedSeconds")}
    second = play_once(auth, row, "second-play", evidence_dir, relax_console=True)
    assert_playback(row, second, counter_validated=True, expected_delta=None)
    result["secondPlay"] = {"ffprobe": second["ffprobe"], "events": second["pluginEvents"]}
    auth = refresh_auth()
    d_row_restart(auth, row, evidence_dir, result)
    result["status"] = "PASS"
    return result


def journey_d06(auth: str, row: dict, evidence_dir: Path) -> dict:
    """The allowMediaProbe=false native read, then the first Web Play that probes and commits."""
    result: dict[str, object] = {"journey": "d06"}
    result["firstTrust"] = trust_play(auth, row, evidence_dir)
    auth = refresh_auth()
    result["apply"] = apply_matrix_change(row)
    row["url"] = row["apply"]["url"]
    probes_before = probe_count(row["url"])
    static_read = native_static_stream_read(auth, row["item"]["Id"])
    result["staticRead"] = static_read
    require(static_read["status"] in (200, 302), f"{row['id']}: the static native read failed ({static_read}).")
    require(probe_count(row["url"]) == probes_before,
            f"{row['id']}: the static native read ran an ffprobe call.")
    require(fp_snapshot(auth, row) == row["trust_fp"],
            f"{row['id']}: the static native read changed the fingerprint.")
    obs = play_once(auth, row, "window", evidence_dir)
    assert_playback(row, obs, counter_validated=True, expected_delta=1, url_for_source=row["fp_url"])
    auth = refresh_auth()
    failures = fp_expected_failures(auth, row, url=row["fp_url"], sha1_token=row["fp_tokens"][0],
                                    size_token=row["fp_tokens"][1])
    require(not failures, f"{row['id']} window: " + "; ".join(failures))
    result["window"] = {"ffprobe": obs["ffprobe"], "advancedSeconds": obs["playback"].get("advancedSeconds")}
    second = play_once(auth, row, "second-play", evidence_dir)
    assert_playback(row, second, counter_validated=True, expected_delta=0, url_for_source=row["fp_url"])
    result["secondPlay"] = {"ffprobe": second["ffprobe"], "events": second["pluginEvents"]}
    restart_then_play(auth, row, evidence_dir, result, row["fp_url"])
    result["status"] = "PASS"
    return result


def native_item_path(row: dict) -> str | None:
    """The native path the row's item must be located by, or ``None`` for a STRM row.

    D04 is the ordinary-media control: its item is a real file under the regular-media library, so
    the lookup must address that path. Every other row is a versioned STRM item addressed by its
    STRM file, which ``raw_item_query`` derives from the row's stable name.
    """
    if row["apply_kind"] == "d04":
        return "/media/local/" + row["media"]
    return None


def prepare_matrix_rows(auth: str, rows: list[dict], evidence_dir: Path) -> dict:
    """Native preparation with the plugin disabled, bounded P01 surgery, then re-enable.

    Scan everything once, disable the plugin, let Jellyfin itself probe and persist each row's
    prepared address/stream (the row's own prepared media URL), run the P01 stream removals in the
    stopped owned copy, and only then re-enable the plugin and hand out a fresh token.
    """
    summary: dict[str, object] = {}
    # The same explicit refresh the baseline preparation uses: the wizard's add-library scan is not
    # a guaranteed completed scan, so a row's item may not exist yet; one native refresh before the
    # item lookups makes the per-row waits start from a real scan trigger.
    pe.request_json("POST", "/Library/Refresh", headers={"Authorization": auth})
    for row in rows:
        item_path = native_item_path(row)
        item = raw_item_query(auth, row["strm_name"], item_path)
        summary[row["id"] + ".scan"] = {"status": item["status"],
                                        "elapsedSeconds": item["elapsedSeconds"],
                                        "attempts": item["attempts"]}
        row["item"] = item["item"]
        info = item_media_type(auth, row["item"]["Id"])
        entity_failures = entity_class_failures(info, row["media_type"])
        require(not entity_failures, f"{row['id']}: " + "; ".join(entity_failures))
        summary[row["id"] + ".entity"] = str(info.get("Type")).rsplit(".", 1)[-1]
    require(pkg.plugin_action(auth, False) == 204, "The package-instance plugin disable failed.")
    pkg.restart()
    auth = refresh_auth()
    for row in rows:
        if row["apply_kind"] == "d04":
            deadline = time.monotonic() + MAX_WAIT
            saved: list[str] = []
            while time.monotonic() < deadline:
                saved = saved_stream_types(auth, row["item"]["Id"])
                if "Video" in saved:
                    break
                time.sleep(1)
            require("Video" in saved, f"{row['id']}: no native Video stream was prepared.")
            summary[row["id"] + ".preparedStreams"] = saved
            row["url"] = "/media/local/" + row["media"]
            snapshot = native_source_snapshot(auth, row["item"]["Id"])
            ids = [source["id"] for source in snapshot["sources"] if source.get("id")]
            require(len(ids) == 1, f"{row['id']}: expected exactly one native source, found {ids}.")
            row["sourceKey"] = ids[0]
            summary[row["id"] + ".preparedSource"] = snapshot
            continue
        # Every STRM-backed row is prepared on the URL that currently serves its prepared media,
        # so the counter, the saved address and the snapshot all belong to the same real input.
        prep_url = MEDIA_PREFIX + row["media"]
        deadline = time.monotonic() + MAX_WAIT
        saved = []
        while time.monotonic() < deadline:
            status, _ = pkg.playback_info(auth, row["item"]["Id"])
            saved = saved_stream_types(auth, row["item"]["Id"])
            if status == 200 and "Video" in saved:
                break
            time.sleep(1)
        require("Video" in saved, f"{row['id']}: no native Video stream was prepared ({saved}).")
        count = probe_count(prep_url)
        summary[row["id"] + ".preparationProbeCount"] = count
        require(count >= 1, f"{row['id']}: the preparation probe was never observed; counter unusable.")
        snapshot = native_source_snapshot(auth, row["item"]["Id"])
        ids = [source["id"] for source in snapshot["sources"] if source.get("id")]
        require(len(ids) == 1, f"{row['id']}: expected exactly one native source, found {ids}.")
        row["sourceKey"] = ids[0]
        summary[row["id"] + ".preparedSource"] = snapshot
    p01_rows = [row for row in rows if row["journey"] == "p01"]
    if p01_rows:
        drop_spec = {row["id"]: row["apply"]["drop"] for row in p01_rows}
        summary["p01Surgery"] = p01_stream_surgery(p01_rows, drop_spec, evidence_dir, "pre")
        auth = refresh_auth()
    require(pkg.plugin_action(auth, True) == 204, "The package-instance plugin enable failed.")
    pkg.restart()
    auth = refresh_auth()
    require(set_plugin_configuration(auth, {"DetailedLog": True}) in (200, 204),
            "The diagnostic logging configuration could not be saved.")
    return summary


def scenario_matrix(package: Path, evidence_dir: Path, selected: list[str],
                    summary: dict[str, object]) -> None:
    """Run the fixed video matrix rows in batches, recording every reached stage per row."""
    matrix = generate_matrix_fixtures()
    summary["fixtures"] = {"commands": matrix["commands"], "fixtures": matrix["fixtures"],
                          "derived": matrix["derived"], "aliases": matrix["aliases"],
                          "durationSeconds": matrix["durationSeconds"]}
    all_rows = build_matrix_rows(matrix["fixtures"])
    known = {row["id"] for row in all_rows}
    rows = [row for row in all_rows if row["id"] in selected]
    require(len(rows) == len(selected), f"Unknown matrix row ids {sorted(set(selected) - known)}.")
    summary["rows"] = [{"id": row["id"], "item": row["item"], "url": row["url"], "journey": row["journey"],
                       "expectProbes": row["expect_probes"], "oldManifest": row["old"],
                       "applyKind": row["apply_kind"], "fpKind": row["fp_kind"],
                       "fpUrl": row["fp_url"]} for row in rows]
    summary["mediaSetup"] = setup_matrix_media(rows)
    strm_identities = []
    for row in rows:
        if row["apply_kind"] == "d04":
            strm_identities.append({"path": "/media/local/" + row["media"], "ordinaryMedia": True})
            continue
        identity = write_matrix_strm(row, unversioned=row["apply_kind"] == "d05")
        row["path"] = identity["path"]
        strm_identities.append(identity)
    summary["strm"] = [{"id": row["id"], **identity} for row, identity in zip(rows, strm_identities)]
    summary["instance"] = prepare_instance(package)
    auth = refresh_auth()
    for row in rows:
        if row["apply_kind"] == "d04":
            ext = "mp4" if row["fmt"] == "MP4" else "mkv"
            add_library(auth, f"Matrix {row['fmt']} Regular Media", "movies", [f"/media/local/regular-{ext}"])
    summary["preparation"] = prepare_matrix_rows(auth, rows, evidence_dir)
    auth = refresh_auth()
    results: dict[str, object] = {}
    dispatch = {"normal": journey_normal, "p01": journey_p01, "f01": journey_f01,
                "f02": journey_f02, "d02": journey_d02, "d03": journey_d03, "d04": journey_d04,
                "d05": journey_d05, "d06": journey_d06}
    for row in rows:
        # Every row starts from live credentials: a real Web Play in the previous row revoked the
        # token that journey held, so reusing it for this row's first native read would fail with an
        # unrelated error and hide the row's real behaviour.
        auth = refresh_auth()
        try:
            # The intentionally-disabled D02/D03 windows restore their own switch; every other row
            # needs the plugin enabled with its playback auto-check on, so a leaked change cannot be
            # mistaken for a passing native-delegation result.
            if row["journey"] not in ("d02", "d03"):
                precondition = plugin_configuration(auth)
                require(precondition.get("Enabled") is True,
                        f"{row['id']}: the plugin was not enabled before the row (Enabled="
                        f"{precondition.get('Enabled')!r}).")
                require(precondition.get("PlaybackAutoCheck") is True,
                        f"{row['id']}: the playback auto-check was not enabled before the row "
                        f"(PlaybackAutoCheck={precondition.get('PlaybackAutoCheck')!r}).")
            # The switch URL belongs to this row: a shared partner file must survive the previous
            # row in the batch, so every fixed-URL row re-establishes its own A baseline bytes
            # before its journey starts and the window switches them to the partner through a
            # row-owned staging copy.
            reset = reset_row_media(row)
            results[row["id"]] = {"mediaReset": reset}
            journey_result = dispatch[row["journey"]](auth, row, evidence_dir)
            journey_result["mediaReset"] = reset
            results[row["id"]] = journey_result
            auth = refresh_auth()
        except ConfigurationRestoreError as error:
            # The row failed and its configuration could not be restored: record both and stop the
            # batch instead of reporting later rows that ran against a changed server.
            failed_result = dict(error.result)
            failed_result.setdefault("status", "FAIL")
            failed_result["status"] = "FAIL"
            failed_result["error"] = f"{type(error).__name__}: {error}"
            failed_result["configurationRestored"] = False
            results[row["id"]] = failed_result
            summary["rowsResult"] = results
            summary["abortedAfter"] = row["id"]
            raise BaselineError(
                f"Matrix stopped after {row['id']}: the server configuration could not be restored "
                f"({error}).") from error
        except RowEvidenceError as error:
            # A failing row whose configuration was restored keeps its reached stages and statuses.
            failed_result = dict(error.result)
            failed_result["status"] = "FAIL"
            failed_result["error"] = f"{type(error).__name__}: {error}"
            results[row["id"]] = failed_result
            auth = refresh_auth()
        except (BaselineError, RuntimeError, OSError, subprocess.SubprocessError) as error:
            results[row["id"]] = {"status": "FAIL", "error": f"{type(error).__name__}: {error}"}
            auth = refresh_auth()
    summary["rowsResult"] = results
    failed = [row_id for row_id, result in results.items() if result.get("status") != "PASS"]
    if failed:
        raise BaselineError("Matrix rows failed: " + " | ".join(failed))


def render_matrix_index(summary: dict) -> str:
    lines = ["# Slice 5 matrix evidence index", "",
             f"- Status: **{summary.get('status')}**",
             f"- Scenario: {summary.get('scenario')}",
             f"- Rows: {', '.join(summary.get('rows') or [])}",
             f"- Package: `{summary.get('package')}`",
             f"- Package SHA-256: `{(summary.get('packageIdentity') or {}).get('archiveSha256')}`",
             f"- Workspace: `{summary.get('workspace')}`",
             f"- Elapsed seconds: {summary.get('elapsedSeconds')}", ""]
    if summary.get("error"):
        lines += ["## Failure", "", f"```\n{summary['error']}\n```", ""]
    fixtures = ((summary.get("fixtures") or {}).get("fixtures") or {})
    if fixtures:
        lines += ["## Fixtures", "", "| file | SHA-1 | size | probeable |", "|---|---|---|---|"]
        for name, fixture in fixtures.items():
            lines.append(f"| `{name}` | `{fixture['sha1']}` | {fixture['size']} | "
                         f"{fixture['ffprobe'].get('probeable', True)} |")
        lines.append("")
    setup = (summary.get("mediaSetup") or {})
    if setup.get("created"):
        lines += ["## Media setup", ""]
        for name, origin in setup["created"].items():
            lines.append(f"- `{name}`: {origin}")
        lines += [f"- F01 404 target: {setup.get('missingF01')}", ""]
    rows = ((summary.get("rowsResult") or {}))
    if rows:
        lines += ["## Matrix rows", "", "| row | journey | status | ffprobe deltas | advanced s |",
                  "|---|---|---|---|---|"]
        for row_id, result in rows.items():
            journey = str(result.get("journey", "normal"))
            status = str(result.get("status", "FAIL"))
            probes: list[str] = []
            advanced: list[str] = []
            for key in ("firstTrust", "prime", "window", "failWindow", "failRetry", "recoveryPlay",
                        "nativePlay", "secondPlay", "afterRestart"):
                block = result.get(key)
                if isinstance(block, dict) and isinstance(block.get("ffprobe"), dict):
                    probes.append(str(block["ffprobe"].get("delta")))
                if isinstance(block, dict) and block.get("advancedSeconds") is not None:
                    advanced.append(str(block["advancedSeconds"]))
            lines.append(f"| {row_id} | {journey} | {status} | {'/'.join(probes) or '-'} | "
                         f"{'/'.join(advanced) or '-'} |")
        lines.append("")
        for row_id, result in rows.items():
            if result.get("status") != "PASS":
                lines += [f"### {row_id} failure", "", f"```\n{result.get('error')}\n```", ""]
    lines += ["## Evidence files", "",
              "- `<row-id>/<phase>/observation.json`: ffprobe window, plugin events, media requests, fingerprint, native sources.",
              "- `<row-id>/<phase>/screenshots/*.png`: start / 5 s progress / failure screenshots; `-playbackinfo-*.json` raw responses.",
              "- `<row-id>/<phase>/driver-stdout.txt`, `driver-stderr.txt`: raw browser driver output.",
              "- `db-backups/p01-*`: P01 owned-copy database backups.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BaselineError, RuntimeError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
