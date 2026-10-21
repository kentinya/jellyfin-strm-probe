#!/usr/bin/env python3
"""Slice 5 baseline: isolated ZIP install, self-prepared media, real native web playback.

This entry reuses the existing package environment (``package_environment``), the existing
browser driver (``package_playback_driver.mjs`` in strict mode) and the existing package
integration helpers instead of introducing a framework, environment manager, scenario DSL or
evidence system. It only adds the sequential orchestration the Slice 5 baseline needs:

  * generate the baseline fixtures with the pinned Jellyfin FFmpeg (24 s MP4/MKV H.264+AAC and
    a real AAC/M4A audio file, A/B content plus byte-identical copies/aliases), record the real
    content SHA-1, byte size and ffprobe streams, and prepare limited/full/unspecified
    ColorRange videos whose actual ffprobe output is reported;
  * write version-1 STRM files pointing at the local media server and let Jellyfin natively
    index them as Video (movies library) and Audio (music library) items;
  * with the plugin disabled, let Jellyfin itself probe and persist the necessary primary
    stream, then enable the plugin so no fingerprint exists yet;
  * per row (B01 MP4, B02 MKV, B03 Audio) perform first trust, a second playback and a
    playback after restart, all started by a real Play click in the native web client, and
    refuse PASS unless the actual ffprobe count for the target source is zero inside each
    measurement window, both screenshots exist and are non-trivial, media time advanced by at
    least the required seconds, video reports decoded frames (audio reports native audio
    progress), the media request and the PlaybackInfo source/URL/primary stream match, and the
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
MOVIE_LIBRARY = pe.STRM_LIBRARY
MUSIC_LIBRARY = "Package Audio Fixtures"
MUSIC_LIBRARY_PATH = "/media/local/music"
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
AUDIO_FIXTURES: dict[str, dict[str, object]] = {
    "audio/audio-a.m4a": {"tone": 440, "title": "Audio A"},
    "audio/audio-b.m4a": {"tone": 880, "title": "Audio B"},
}
# Byte-identical copies/aliases of the A fixtures, written next to the originals.
COPY_ALIASES = {
    "baseline-mp4-a.mp4": "baseline-mp4-a-copy.mp4",
    "baseline-mkv-a.mkv": "baseline-mkv-a-copy.mkv",
    "audio/audio-a.m4a": "audio/audio-a-copy.m4a",
}

ROWS = (
    {"id": "B01", "name": "Baseline MP4", "media_type": "video", "file": "baseline-mp4-a.mp4",
     "library": MOVIE_LIBRARY, "strm_name": "Baseline MP4"},
    {"id": "B02", "name": "Baseline MKV", "media_type": "video", "file": "baseline-mkv-a.mkv",
     "library": MOVIE_LIBRARY, "strm_name": "Baseline MKV"},
    {"id": "B03", "name": "Baseline Audio", "media_type": "audio", "file": "audio/audio-a.m4a",
     "library": MUSIC_LIBRARY, "strm_name": "Baseline Audio"},
)


class BaselineError(RuntimeError):
    """A baseline precondition or acceptance check failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BaselineError(message)


# ---------------------------------------------------------------------------------------------------------------------
# Pure validation helpers (unit-testable without Docker or Jellyfin)
# ---------------------------------------------------------------------------------------------------------------------


def fingerprint_fields_match(row: dict | None, *, expected_url: str, sha1: str, size: int) -> list[str]:
    """Return the reasons a fingerprint row does not match the fixture (empty means it matches)."""
    if row is None:
        return ["no fingerprint row was stored"]
    failures: list[str] = []
    if set(row) != FINGERPRINT_FIELDS:
        failures.append(f"fingerprint row fields are {sorted(row)} instead of {sorted(FINGERPRINT_FIELDS)}")
    if row.get("url_hash") != hashlib.sha256(expected_url.encode()).hexdigest():
        failures.append("the fingerprint URL hash does not match the STRM URL")
    if str(row.get("sha1") or "").lower() != sha1.lower():
        failures.append("the fingerprint SHA-1 does not match the fixture content")
    if row.get("file_size") != size:
        failures.append("the fingerprint size does not match the fixture size")
    return failures


def playback_failures(entry: dict | None, *, expected_url: str, media_type: str,
                      minimum_seconds: float = MINIMUM_PROGRESS_SECONDS) -> list[str]:
    """Return the reasons a strict playback observation is not acceptable (empty means accepted)."""
    if not isinstance(entry, dict) or not entry:
        return ["no playback observation was produced"]
    failures: list[str] = []
    if entry.get("advanced") is not True:
        failures.append("the driver did not report advanced playback")
    current = entry.get("currentTime")
    if not isinstance(current, (int, float)) or current < minimum_seconds:
        failures.append(f"media time {current!r} did not advance by {minimum_seconds} s")
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
    required_stream = "Video" if media_type == "video" else "Audio"
    expected_hash = hashlib.sha256(expected_url.encode()).hexdigest()
    matched_source = False
    for info in entry.get("playbackInfo") or []:
        if info.get("status") != 200:
            continue
        for source in (info.get("body") or {}).get("mediaSources") or []:
            if source.get("pathHash") == expected_hash and required_stream in (source.get("streamTypes") or []):
                matched_source = True
    if not matched_source:
        failures.append(
            f"no successful PlaybackInfo response carried the expected URL and a {required_stream} stream")
    return failures


def measurement_failures(*, phase: str, probes_before: int, probes_after: int,
                         counter_validated: bool) -> list[str]:
    """Return the reasons the measurement window for one playback phase is not trustworthy."""
    failures: list[str] = []
    if not counter_validated:
        failures.append(f"{phase}: the ffprobe counter was never validated for this source")
    if probes_after < probes_before:
        failures.append(f"{phase}: the ffprobe counter went backwards")
    elif probes_after != probes_before:
        failures.append(f"{phase}: {probes_after - probes_before} ffprobe call(s) ran inside the window")
    return failures


def restart_readback_failures(frozen: dict, observed: dict) -> list[str]:
    """Return the reasons the read-only post-restart state does not match the frozen state."""
    failures: list[str] = []
    if not frozen:
        failures.append("the pre-restart state was not frozen")
        return failures
    if observed.get("fingerprint") != frozen.get("fingerprint"):
        failures.append("the stored fingerprint changed across the restart")
    if observed.get("streams") != frozen.get("streams"):
        failures.append("the natively saved media streams changed across the restart")
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


def fingerprint_row_or_none(item_id: str, source_id: str) -> dict | None:
    if not pkg.fingerprint_database().is_file():
        return None
    return pkg.fingerprint_row(item_id, source_id)


def read_fingerprint_snapshot(item_id: str, source_id: str) -> dict | None:
    database = pkg.fingerprint_database()
    if not database.is_file():
        return None
    uri = database.as_posix() + "?mode=ro"
    with sqlite3.connect("file:" + uri, uri=True, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT item_id, source_key, url_hash, sha1, file_size FROM strm_fingerprint "
            "WHERE item_id = ? AND source_key = ?",
            (uuid.UUID(item_id).hex, uuid.UUID(source_id).hex),
        ).fetchone()
    return dict(row) if row is not None else None


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


def generate_fixtures() -> dict:
    """Generate the baseline media with the pinned Jellyfin FFmpeg and record real identities."""
    pe.workspace()
    # The FFmpeg container writes into the mounted media directory, so the audio subdirectory must
    # exist before the first render. The music library holds only the audio STRM; the audio fixture
    # itself stays outside every library path so no regular (non-STRM) audio item is indexed.
    for name in ("audio", "music"):
        (pe.WORK / "media" / name).mkdir(parents=True, exist_ok=True)
    commands: dict[str, list[str]] = {}
    for name, spec in VIDEO_FIXTURES.items():
        args = ["-y", "-f", "lavfi", "-i",
                f"{spec['pattern']}=duration={FIXTURE_SECONDS}:size=320x180:rate=15",
                "-f", "lavfi", "-i", f"sine=frequency={spec['tone']}:duration={FIXTURE_SECONDS}"]
        filters = (f"drawtext=fontfile={FONT}:text='{spec['marker']}':fontsize=48:fontcolor=white:"
                   "x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.5")
        args += ["-vf", filters, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
        if spec["color_range"]:
            args += ["-color_range", str(spec["color_range"])]
        args += ["-c:a", "aac", "-b:a", "96k", "-shortest", "-t", str(FIXTURE_SECONDS),
                 "/out/" + name]
        commands[name] = args
        result = ffmpeg(args)
        require(result.returncode == 0, f"Could not generate {name}: {result.stderr.strip()[-300:]}")
    for name, spec in AUDIO_FIXTURES.items():
        args = ["-y", "-f", "lavfi", "-i", f"sine=frequency={spec['tone']}:duration={FIXTURE_SECONDS}",
                "-c:a", "aac", "-b:a", "128k", "-metadata", f"title={spec['title']}",
                "-t", str(FIXTURE_SECONDS), "/out/" + name]
        commands[name] = args
        result = ffmpeg(args)
        require(result.returncode == 0, f"Could not generate {name}: {result.stderr.strip()[-300:]}")
    # The music library holds only the audio STRM; the audio fixture itself stays outside every
    # library path so no regular (non-STRM) audio item is indexed alongside it.
    aliases: dict[str, str] = {}
    for source, alias in COPY_ALIASES.items():
        target = pe.WORK / "media" / alias
        target.parent.mkdir(parents=True, exist_ok=True)
        pe.copy_owned(pe.WORK / "media" / source, target, label=f"byte-identical copy {alias}")
        aliases[alias] = source

    fixtures: dict[str, dict] = {}
    for name in [*VIDEO_FIXTURES, *AUDIO_FIXTURES, *aliases]:
        path = pe.WORK / "media" / name
        data = path.read_bytes()
        info = ffprobe("/out/" + name)
        streams = [{key: stream.get(key) for key in
                    ("index", "codec_type", "codec_name", "width", "height", "pix_fmt", "color_range",
                     "sample_rate", "channels", "duration", "disposition")}
                   for stream in info.get("streams", [])]
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
    url = f"http://media:8080/{row['file']}"
    if row["media_type"] == "audio":
        target = pe.WORK / "media" / "music" / (row["strm_name"] + ".strm")
    else:
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


def play_once(auth: str, row: dict, phase: str, evidence_dir: Path) -> dict:
    """Start one real native web playback and capture every measurement for the phase."""
    phase_dir = evidence_dir / row["id"] / phase
    phase_dir.mkdir(parents=True, exist_ok=True)
    item = row["item"]
    url = row["url"]
    filename = row["file"]
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
    require("error" not in result, f"{row['id']} {phase}: the browser driver failed: {result.get('error')}")
    require(result.get("strict") is True, f"{row['id']} {phase}: the driver did not run in strict mode.")
    console_errors = pkg.unexpected_console_errors(result)
    require(not console_errors, f"{row['id']} {phase}: unexpected console errors {console_errors}")
    require(len(result.get("results") or []) == 1, f"{row['id']} {phase}: expected exactly one playback result.")
    entry = result["results"][0]
    # Let the server's asynchronous log sink and the media container flush before counting.
    time.sleep(2)
    after_probes = probe_count(url)
    after_media = media_server_requests()
    events = plugin_event_delta(before_events)
    observation = {
        "row": row["id"], "phase": phase, "itemId": item["Id"], "url": url,
        "playback": entry, "consoleErrors": console_errors,
        "pluginEvents": events,
        "pluginProbeCalls": [pkg.probe_calls(event) for event in events],
        "ffprobe": {"before": before_probes, "after": after_probes, "delta": after_probes - before_probes},
        "mediaServerRequests": {"before": before_media.get("GET " + filename, 0),
                                "after": after_media.get("GET " + filename, 0),
                                "delta": media_request_delta(before_media, after_media, filename)},
        "fingerprint": fingerprint_row_or_none(item["Id"], item["Id"]),
        "savedStreams": saved_stream_types(auth, item["Id"]),
    }
    (phase_dir / "observation.json").write_text(json.dumps(observation, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    return observation


def assert_playback(row: dict, observation: dict, *, counter_validated: bool) -> None:
    phase = observation["phase"]
    failures = playback_failures(observation["playback"], expected_url=observation["url"],
                                 media_type=row["media_type"])
    failures += measurement_failures(phase=f"{row['id']} {phase}",
                                     probes_before=observation["ffprobe"]["before"],
                                     probes_after=observation["ffprobe"]["after"],
                                     counter_validated=counter_validated)
    if observation["mediaServerRequests"]["delta"] < 1:
        failures.append(f"{row['id']} {phase}: the server never fetched the fixture from the media service")
    require(not failures, "; ".join(failures))


def freeze_state(auth: str, row: dict) -> dict:
    item = row["item"]
    return {
        "fingerprint": read_fingerprint_snapshot(item["Id"], item["Id"]),
        "streams": saved_stream_types(auth, item["Id"]),
        "strm_sha256": hashlib.sha256(Path(row["strm_path"]).read_bytes()).hexdigest(),
        "probe_count": probe_count(row["url"]),
    }


def read_only_state(auth: str, row: dict) -> dict:
    item = row["item"]
    return {
        "fingerprint": read_fingerprint_snapshot(item["Id"], item["Id"]),
        "streams": saved_stream_types(auth, item["Id"]),
        "strm_sha256": hashlib.sha256(Path(row["strm_path"]).read_bytes()).hexdigest(),
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
    auth = pkg.api_auth()
    add_library(auth, MUSIC_LIBRARY, "music", [MUSIC_LIBRARY_PATH])
    summary["libraries"] = {"movies": MOVIE_LIBRARY, "music": MUSIC_LIBRARY}
    summary["deployment"] = pe.deploy_archive(package)
    pkg.restart()
    auth = pkg.api_auth()
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
        row["item"] = pkg.scan_and_wait(auth, row["strm_name"], MAX_WAIT)
        info = item_media_type(auth, row["item"]["Id"])
        summary[row["id"] + ".item"] = info
        entity_failures = entity_class_failures(info, row["media_type"])
        require(not entity_failures, f"{row['id']}: " + "; ".join(entity_failures))
        summary[row["id"] + ".entity"] = str(info.get("Type")).rsplit(".", 1)[-1]
    require(pkg.plugin_action(auth, False) == 204, "The package-instance plugin disable failed.")
    pkg.restart()
    auth = pkg.api_auth()
    require(str(pkg.plugin_status(auth)).lower() not in {"active", "0"}, "The plugin remained active after disable.")
    for row in rows:
        required = "Video" if row["media_type"] == "video" else "Audio"
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
    require(pkg.plugin_action(auth, True) == 204, "The package-instance plugin enable failed.")
    pkg.restart()
    return summary


def scenario_baseline(package: Path, evidence_dir: Path, selected: list[str]) -> dict:
    summary: dict[str, object] = {}
    summary["fixtures"] = generate_fixtures()
    summary["instance"] = prepare_instance(package)
    auth = pkg.api_auth()
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
    auth = pkg.api_auth()
    require(fingerprint_row_or_none(rows[0]["item"]["Id"], rows[0]["item"]["Id"]) is None,
            "A fingerprint already existed before the first trust playback.")

    results: dict[str, object] = {}
    failures: list[str] = []
    for row in rows:
        row_result: dict[str, object] = {}
        try:
            # 1) first trust
            first = play_once(auth, row, "first-trust", evidence_dir)
            assert_playback(row, first, counter_validated=True)
            row_failures = fingerprint_fields_match(first["fingerprint"], expected_url=row["url"],
                                                    sha1=row["fixture"]["sha1"], size=row["fixture"]["size"])
            if first["fingerprint"] is not None:
                require(any("FirstTrust" in event for event in first["pluginEvents"]),
                        f"{row['id']}: the existing stream was not accepted through first trust "
                        f"({first['pluginEvents']}).")
                require(all(call in (0, None) for call in first["pluginProbeCalls"]),
                        f"{row['id']}: first trust reported a plugin probe {first['pluginEvents']}.")
            require(not row_failures, f"{row['id']}: " + "; ".join(row_failures))
            row_result["firstTrust"] = {"fingerprint": first["fingerprint"], "events": first["pluginEvents"],
                                        "ffprobe": first["ffprobe"], "playbackTime": first["playback"]["currentTime"],
                                        "mediaRequests": first["mediaServerRequests"]}
            # 2) second playback reuses the trusted baseline
            second = play_once(auth, row, "second-play", evidence_dir)
            assert_playback(row, second, counter_validated=True)
            require(second["fingerprint"] == first["fingerprint"],
                    f"{row['id']}: the second playback changed the trusted fingerprint.")
            require(all(call in (0, None) for call in second["pluginProbeCalls"]),
                    f"{row['id']}: the second playback reported a plugin probe {second['pluginEvents']}.")
            row_result["secondPlay"] = {"ffprobe": second["ffprobe"], "events": second["pluginEvents"],
                                        "playbackTime": second["playback"]["currentTime"]}
            # 3) restart: freeze, restart, compare read-only before any PlaybackInfo or playback
            frozen = freeze_state(auth, row)
            row_result["frozenBeforeRestart"] = frozen
            pkg.restart()
            auth = pkg.api_auth()
            observed = read_only_state(auth, row)
            row_result["readOnlyAfterRestart"] = observed
            restart_failures = restart_readback_failures(frozen, observed)
            require(not restart_failures, f"{row['id']}: " + "; ".join(restart_failures))
            after = play_once(auth, row, "after-restart", evidence_dir)
            assert_playback(row, after, counter_validated=True)
            require(after["fingerprint"] == frozen["fingerprint"],
                    f"{row['id']}: the post-restart playback changed the trusted fingerprint.")
            row_result["afterRestart"] = {"ffprobe": after["ffprobe"], "events": after["pluginEvents"],
                                          "playbackTime": after["playback"]["currentTime"]}
            row_result["status"] = "PASS"
        except BaselineError as error:
            row_result["status"] = "FAIL"
            row_result["error"] = str(error)
            failures.append(f"{row['id']}: {error}")
        results[row["id"]] = row_result
    summary["rowsResult"] = results
    if failures:
        raise BaselineError("Baseline rows failed: " + " | ".join(failures))
    summary["status"] = "PASS"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--scenario", default="baseline", choices=["baseline"])
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--rows", default="B01,B02,B03",
                        help="Comma-separated row ids to run (default: all baseline rows).")
    parser.add_argument("--workspace", type=Path,
                        help="Fresh run-owned workspace under artifacts/package-env (default: auto-created).")
    parser.add_argument("--keep-workspace", action="store_true",
                        help="Leave this run's workspace and instance in place for inspection.")
    args = parser.parse_args()

    selected = [part.strip() for part in args.rows.split(",") if part.strip()]
    known = {row["id"] for row in ROWS}
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
        summary["baseline"] = scenario_baseline(package, evidence_dir, selected)
        summary["status"] = "PASS"
        exit_code = 0
    except (BaselineError, RuntimeError, OSError, ValueError, KeyError, json.JSONDecodeError,
            subprocess.SubprocessError, package_plugin.PackageError, pe.PackageEnvironmentError) as error:
        summary["status"] = "FAIL"
        summary["error"] = f"{type(error).__name__}: {error}"
        exit_code = 1
    finally:
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
        (evidence_dir / "baseline-result.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (evidence_dir / "INDEX.md").write_text(render_index(summary), encoding="utf-8")
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
                  "| row | status | ffprobe (first/second/restart) | playback seconds |", "|---|---|---|---|"]
        for row_id, result in rows.items():
            if result.get("status") != "PASS":
                lines.append(f"| {row_id} | FAIL | - | - |")
                continue
            probes = "/".join(str(result[key]["ffprobe"]["delta"])
                              for key in ("firstTrust", "secondPlay", "afterRestart"))
            times = "/".join(str(result[key]["playbackTime"])
                             for key in ("firstTrust", "secondPlay", "afterRestart"))
            lines.append(f"| {row_id} | PASS | {probes} | {times} |")
        lines.append("")
        for row_id, result in rows.items():
            if result.get("status") != "PASS":
                lines += [f"### {row_id} failure", "", f"```\n{result.get('error')}\n```", ""]
    lines += ["## Evidence files", "",
              "- `baseline-result.json`: complete machine-readable result (fixtures, per-row observations).",
              "- `<row>/<phase>/observation.json`: ffprobe window, plugin events, media requests, fingerprint.",
              "- `<row>/<phase>/screenshots/*.png`: start and 5 s progress screenshots.",
              "- `<row>/<phase>/driver-stdout.txt`, `driver-stderr.txt`: raw browser driver output.",
              ""]
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BaselineError, RuntimeError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
