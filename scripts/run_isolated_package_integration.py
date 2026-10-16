#!/usr/bin/env python3
"""Acceptance for the single-version plugin ZIP against a dedicated isolated instance.

Only the archive under test is installed: the package environment mounts no source tree,
SDK, NuGet cache or build output, and this script never calls the development deployment
helper. It covers a clean archive-only install, the Slice 3 baseline upgrade, uninstall /
native recovery, and the negative package validations.

Scenarios:
  all       clean + upgrade + recovery + invalid, in one session, with failures preserved
  clean     fresh instance, archive-only install, config page, native task, MP4/MKV playback,
            first-trust zero-probe, unchanged reuse, same-SHA-1 URL change, restart persistence
  upgrade   install the accepted Slice 3 baseline, prepare config/fingerprint/pending change,
            then replace it with the candidate archive and prove preservation
  recovery  disable, uninstall, native playback, reinstall and re-check
  invalid   corrupt / incomplete / unsafe archives are refused without disturbing a valid install

Evidence is printed as a single JSON document; pass --evidence-dir to persist it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import package_environment as pe  # noqa: E402
import package_plugin  # noqa: E402

ROOT = pe.ROOT
WORK = pe.WORK
FINGERPRINT_DATABASE = WORK / "config" / "data" / "plugins" / "b061643ed17d4c6e8ba26b57e286bd20" / "strm-fingerprints.db"
CONFIGURATION_FILE = WORK / "config" / "plugins" / "configurations" / "Jellyfin.Plugin.StrmProbeOptimizer.xml"
PLUGIN_ID = "b061643e-d17d-4c6e-8ba2-6b57e286bd20"
PAGE_NAME = "StrmProbeOptimizer"
TASK_NAME = "STRM 媒体信息检查"
PLUGIN_LOGGER = "Jellyfin.Plugin.StrmProbeOptimizer.Services.StrmPlaybackOptimizer"
CONFIG_DRIVER = ROOT / "scripts" / "configuration_page_driver.mjs"
PLAYBACK_DRIVER = ROOT / "scripts" / "package_playback_driver.mjs"
BROWSER_TOOLS = ROOT / "artifacts" / "dev-env" / "browser-tools"
MAX_WAIT = 120

PROBLEMS: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def record_problem(message: str) -> None:
    PROBLEMS.append(message)


def run(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return pe.run(*args, timeout=timeout)


def api_auth() -> str:
    credentials = json.loads(pe.CREDENTIALS.read_text(encoding="utf-8"))
    return pe.login(credentials["username"], credentials["password"])


def container() -> str:
    return pe.container_name("jellyfin")


def plugin_events() -> list[str]:
    logs = run("docker", "logs", "--tail", "2000", container())
    output = logs.stdout + logs.stderr
    return [line for line in output.splitlines() if PLUGIN_LOGGER in line]


def event_delta(before: list[str], after: list[str]) -> list[str]:
    from collections import Counter

    remaining = Counter(before)
    delta: list[str] = []
    for line in after:
        if remaining[line] > 0:
            remaining[line] -= 1
        else:
            delta.append(line)
    return delta


def safe_event(line: str) -> str:
    marker = PLUGIN_LOGGER + ": "
    return line.split(marker, 1)[-1]


def probe_calls(event: str) -> int | None:
    match = re.search(r"(?:plugin probe calls|calls)\s+(\d+)", event)
    return int(match.group(1)) if match else None


def item_by_name(auth: str, name: str) -> dict:
    status, payload = pe.request_json(
        "GET", "/Items?" + "Recursive=true&Limit=200&Fields=MediaSources,Path",
        headers={"Authorization": auth})
    require(status == 200, "The package-instance item listing failed.")
    matches = [item for item in payload.get("Items", []) if item.get("Name") == name]
    require(len(matches) == 1, f"Expected exactly one package-instance item named {name!r}, found {len(matches)}.")
    return matches[0]


def scan_and_wait(auth: str, name: str, timeout: int = MAX_WAIT) -> dict:
    pe.request_json("POST", "/Library/Refresh", headers={"Authorization": auth})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return item_by_name(auth, name)
        except RuntimeError:
            time.sleep(1)
    raise RuntimeError(f"The package instance did not scan the item {name!r}.")


def playback_info(auth: str, item_id: str, timeout: int = 90) -> tuple[int, dict]:
    return pe.request_json("GET", f"/Items/{item_id}/PlaybackInfo", headers={"Authorization": auth}, timeout=timeout)


def source_for_url(response: dict, expected_url: str) -> dict | None:
    expected = hashlib.sha256(expected_url.encode()).hexdigest()
    for source in response.get("MediaSources", []):
        path = source.get("Path") or ""
        if hashlib.sha256(path.encode()).hexdigest() == expected:
            types = {stream.get("Type") for stream in source.get("MediaStreams", [])}
            return {"path_matches": True, "has_video": "Video" in types, "has_audio": "Audio" in types,
                    "path_sha256": expected}
    return None


def saved_stream_types(auth: str, item_id: str) -> list[str]:
    status, payload = pe.request_json("GET", f"/Items/{item_id}?Fields=MediaStreams",
                                      headers={"Authorization": auth})
    require(status == 200, "The saved-stream read failed.")
    return sorted({stream.get("Type") for stream in payload.get("MediaStreams", [])})


def fingerprint_row(item_id: str, source_key: str) -> dict | None:
    import sqlite3

    require(FINGERPRINT_DATABASE.is_file(), "The plugin fingerprint database was not created.")
    uri = FINGERPRINT_DATABASE.as_posix() + "?mode=ro"
    with sqlite3.connect("file:" + uri, uri=True, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT item_id, source_key, url_hash, sha1, file_size FROM strm_fingerprint "
            "WHERE item_id = ? AND source_key = ?",
            (uuid.UUID(item_id).hex, uuid.UUID(source_key).hex),
        ).fetchone()
    return dict(row) if row is not None else None


def expected_url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def _normalized_id(value: str) -> str:
    return value.replace("-", "").lower()


def plugin_status(auth: str) -> str:
    status, plugins = pe.request_json("GET", "/Plugins", headers={"Authorization": auth})
    require(status == 200, "The plugin listing failed.")
    matches = [plugin for plugin in plugins if _normalized_id(str(plugin.get("Id", ""))) == _normalized_id(PLUGIN_ID)]
    require(len(matches) == 1, "The STRM Probe Optimizer plugin was not found exactly once.")
    return str(matches[0].get("Status"))


def plugin_action(auth: str, enabled: bool) -> int:
    version = "0.1.0.0"
    action = "Enable" if enabled else "Disable"
    status, _ = pe.request_json("POST", f"/Plugins/{PLUGIN_ID}/{version}/{action}",
                                headers={"Authorization": auth})
    return status


def restart() -> str:
    pe.compose("stop")
    pe.compose("up")
    return pe.wait_healthy()


def run_browser_driver(driver: Path, scenario: dict, evidence_dir: Path | None, timeout: int = 300) -> dict:
    node = shutil.which("node")
    require(node is not None, "Node.js is required for the browser drivers.")
    environment = os.environ.copy()
    environment["PLAYWRIGHT_BROWSERS_PATH"] = str(Path.home() / ".cache" / "ms-playwright")
    environment["STRM_CONFIG_PLAYWRIGHT_ROOT"] = str(BROWSER_TOOLS / "node")
    with tempfile.TemporaryDirectory(prefix="strm-package-browser-") as workspace:
        scenario_path = Path(workspace) / "scenario.json"
        scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
        completed = subprocess.run([node, str(driver), str(scenario_path)], cwd=str(BROWSER_TOOLS / "node"),
                                   capture_output=True, text=True, timeout=timeout, check=False, env=environment)
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "driver-stdout.txt").write_text(completed.stdout, encoding="utf-8")
        (evidence_dir / "driver-stderr.txt").write_text(completed.stderr, encoding="utf-8")
    parsed = None
    for line in reversed(completed.stdout.strip().splitlines()):
        try:
            parsed = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    require(parsed is not None, f"The browser driver {driver.name} produced no JSON result: {completed.stderr[-300:]}")
    return parsed


def deployed_matches_archive(archive: Path) -> dict:
    """Prove the loaded payload matches the archive byte-for-byte.

    Jellyfin rewrites ``meta.json`` as part of a normal install (it adds status/timestamp/autoUpdate),
    so that one file is compared field-wise rather than byte-for-byte; every code/native asset must
    match exactly.
    """
    with zipfile.ZipFile(archive) as bundle:
        expected = {
            name.split("/", 1)[1]: hashlib.sha256(bundle.read(name)).hexdigest()
            for name in bundle.namelist() if not name.endswith("/")
        }
    deployed = pe.deployed_payload()
    expected_payload = {name: digest for name, digest in expected.items() if name != "meta.json"}
    deployed_payload = {name: digest for name, digest in deployed.items() if name != "meta.json"}
    require(set(deployed_payload) == set(expected_payload),
            f"Deployed payload differs from the archive: {sorted(set(deployed_payload) ^ set(expected_payload))}.")
    for name, digest in expected_payload.items():
        require(deployed_payload[name] == digest, f"Deployed file {name!r} does not match the archive digest.")
    manifest = json.loads((pe.plugin_directory() / "meta.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(archive) as bundle:
        archived_manifest = json.loads(bundle.read(next(n for n in bundle.namelist() if n.endswith("meta.json"))))
    require(manifest["guid"] == archived_manifest["guid"] and manifest["version"] == archived_manifest["version"]
            and manifest["targetAbi"] == archived_manifest["targetAbi"]
            and manifest["assemblies"] == archived_manifest["assemblies"],
            "Jellyfin's installed manifest does not match the archive identity.")
    return {"payload_files": len(deployed_payload), "matched": True}


def ensure_native_task(auth: str) -> dict:
    status, tasks = pe.request_json("GET", "/ScheduledTasks", headers={"Authorization": auth})
    require(status == 200, "The scheduled-task listing failed.")
    matches = [task for task in tasks if task.get("Name") == TASK_NAME]
    require(len(matches) == 1, f"Expected exactly one native task {TASK_NAME!r}.")
    task = matches[0]
    triggers = task.get("Triggers", [])
    require(triggers == [], f"The native task must default to no trigger, found {triggers}.")
    start = pe.request_json("POST", "/ScheduledTasks/Running/" + task["Id"], headers={"Authorization": auth})
    require(start[0] in (200, 204), "The native task could not be started.")
    deadline = time.monotonic() + MAX_WAIT
    last = None
    while time.monotonic() < deadline:
        status, tasks = pe.request_json("GET", "/ScheduledTasks", headers={"Authorization": auth})
        last = next((entry for entry in tasks if entry["Id"] == task["Id"]), None)
        state = str((last or {}).get("State", "")).lower()
        if state in {"idle", "completed", "failed", "cancelled"} and (last or {}).get("LastExecutionResult"):
            break
        time.sleep(1)
    result = (last or {}).get("LastExecutionResult") or {}
    require(str(result.get("Status", "")).lower() in {"completed", "0"},
            f"The native task did not complete successfully: {result}.")
    return {"task_id": task["Id"], "default_triggers": triggers, "last_status": result.get("Status")}


def benign_console_entry(entry: dict) -> bool:
    """Classify Jellyfin's own web-client noise so a real error is never hidden.

    Each pattern is tied to a specific Jellyfin bundle or endpoint, never to this plugin's page.
    """
    text = str(entry.get("text", ""))
    url = str(entry.get("url", ""))
    if "WebSocket connection to 'ws://" in text and "jellyfin.sdk.bundle.js" in url:
        return True
    if "failed to get tab controller" in text and ("hometab" in text or "hometab" in url):
        return True
    if "CancelledError" in text and ("hometab" in url or "tanstack.query-core" in url):
        return True
    if "status of 404" in text and "/Packages/" in url:
        return True
    if text == "t.scrollHandler is not a function" and "49275." in url:
        return True
    # The native HLS.js player logs non-fatal internal/media/buffer warnings while switching or
    # buffering segments; only a non-fatal entry from Jellyfin's own bundle is benign.
    if "HLS Error" in text and "Fatal: false" in text and "main.jellyfin.bundle.js" in url:
        return True
    return False


def unexpected_console_errors(result: dict) -> list[dict]:
    return [entry for entry in result.get("consoleErrors", []) if not benign_console_entry(entry)]


def configuration_page_scenario(auth: str, evidence_dir: Path | None) -> dict:
    credentials = json.loads(pe.CREDENTIALS.read_text(encoding="utf-8"))
    scenario = {
        "scenario": "save_valid",
        "baseUrl": credentials["base_url"],
        "username": credentials["username"],
        "password": credentials["password"],
        "pluginId": PLUGIN_ID,
        "pageName": PAGE_NAME,
        "screenshotDir": str((evidence_dir or Path(tempfile.gettempdir())) / "config-page"),
        "edits": {"enabled": True, "playbackAutoCheck": True, "detailedLog": True, "maxConcurrentProbes": 4},
    }
    result = run_browser_driver(CONFIG_DRIVER, scenario, evidence_dir)
    require("error" not in result, f"The configuration page scenario failed: {result.get('error')}")
    errors = unexpected_console_errors(result)
    require(not errors, f"The configuration page produced unexpected console errors: {errors}")
    final = result["final"]
    require(final["saveState"] == "success" and final["loaded"], f"The configuration page did not save: {final}")
    require(int(final["maxConcurrentProbes"]) == 4 and final["detailedLog"] is True, f"The saved values were not reflected: {final}")
    require(len(result.get("postBodies") or []) == 1, "Exactly one configuration POST was expected.")
    # The saved values must be effective through the API and survive a restart.
    status, effective = pe.request_json("GET", f"/Plugins/{PLUGIN_ID}/Configuration", headers={"Authorization": auth})
    require(status == 200 and int(effective["MaxConcurrentProbes"]) == 4 and effective["DetailedLog"] is True,
            f"The saved configuration was not effective: {effective}")
    restart()
    new_auth = api_auth()
    status, after = pe.request_json("GET", f"/Plugins/{PLUGIN_ID}/Configuration", headers={"Authorization": new_auth})
    require(int(after["MaxConcurrentProbes"]) == 4 and after["DetailedLog"] is True,
            f"The saved configuration did not survive restart: {after}")
    # Restore the default concurrency so later scenarios start from a known state.
    pe.request_json("POST", f"/Plugins/{PLUGIN_ID}/Configuration",
                    headers={"Authorization": new_auth},
                    body={"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2,
                          "DetailedLog": False, "BatchAllLibraries": True, "BatchLibraryIds": ""})
    return {"final": final, "effective": effective, "after_restart": after}


def playback_scenario(auth: str, items: list[dict], evidence_dir: Path | None) -> dict:
    credentials = json.loads(pe.CREDENTIALS.read_text(encoding="utf-8"))
    scenario = {
        "baseUrl": credentials["base_url"],
        "username": credentials["username"],
        "password": credentials["password"],
        "items": items,
    }
    result = run_browser_driver(PLAYBACK_DRIVER, scenario, evidence_dir, timeout=420)
    require("error" not in result, f"The playback driver failed: {result.get('error')}")
    errors = unexpected_console_errors(result)
    require(not errors, f"Native web playback produced unexpected console errors: {errors}")
    for entry in result["results"]:
        require(entry["advanced"], f"Native web playback did not advance for {entry['name']!r}: {entry}")
    return result


def native_probe_and_save(auth: str, name: str, url: str, timeout: int = MAX_WAIT) -> dict:
    """Trigger native playback so Jellyfin itself probes and persists the primary stream.

    A library scan never probes STRM content, so the first-trust precondition (an existing
    necessary primary stream) requires one native playback while the plugin is disabled.
    """
    item = scan_and_wait(auth, name, timeout)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, response = playback_info(auth, item["Id"])
        if status == 200 and source_for_url(response, url) and "Video" in saved_stream_types(auth, item["Id"]):
            return item
        time.sleep(1)
    raise RuntimeError(f"Native playback never saved a primary stream for {name!r}.")


def write_versioned_strm(name: str, url: str, sha1: str | None, size: int | None) -> Path:
    return pe.write_strm(name, url, sha1, size)


def scenario_clean(package: Path, evidence_dir: Path | None) -> dict:
    summary: dict[str, object] = {}
    pe.prepare_clean_instance()
    summary["deployment"] = pe.deploy_archive(package)
    restart()
    auth = api_auth()
    require(pe.public_info().get("Version") == "12.2.0", "The package instance is not Jellyfin 12.2.0.")
    summary["plugin_status"] = plugin_status(auth)
    require(str(summary["plugin_status"]).lower() in {"active", "0"}, "The plugin is not Active after archive-only install.")
    summary["payload_matches_archive"] = deployed_matches_archive(package)

    mp4_url = "http://media:8080/" + pe.MEDIA_MP4
    mkv_url = "http://media:8080/" + pe.MEDIA_MKV
    mp4_sha, mp4_size = pe.media_sha1(pe.MEDIA_MP4)
    mkv_sha, mkv_size = pe.media_sha1(pe.MEDIA_MKV)
    write_versioned_strm("Package MP4", mp4_url, mp4_sha, mp4_size)
    write_versioned_strm("Package MKV", mkv_url, mkv_sha, mkv_size)

    # Establish the first-trust precondition natively: scan, disable the plugin, let Jellyfin
    # itself probe and save each primary stream, then re-enable the plugin.
    mp4_item = scan_and_wait(auth, "Package MP4")
    mkv_item = scan_and_wait(auth, "Package MKV")
    require(plugin_action(auth, False) == 204, "The package-instance plugin disable failed.")
    restart()
    auth = api_auth()
    require(str(plugin_status(auth)).lower() not in {"active", "0"}, "The plugin remained active after disable.")
    mp4_item = native_probe_and_save(auth, "Package MP4", mp4_url)
    mkv_item = native_probe_and_save(auth, "Package MKV", mkv_url)
    summary["native_streams_saved"] = {"mp4": saved_stream_types(auth, mp4_item["Id"]),
                                       "mkv": saved_stream_types(auth, mkv_item["Id"])}
    before = plugin_events()
    status, disabled_info = playback_info(auth, mp4_item["Id"])
    require(status == 200 and source_for_url(disabled_info, mp4_url), "Native playback failed while the plugin was disabled.")
    require(event_delta(before, plugin_events()) == [], "The plugin emitted events while disabled.")
    require(plugin_action(auth, True) == 204, "The package-instance plugin enable failed.")
    restart()
    auth = api_auth()

    before = plugin_events()
    status, trusted = playback_info(auth, mp4_item["Id"])
    events = [safe_event(line) for line in event_delta(before, plugin_events())]
    require(status == 200 and source_for_url(trusted, mp4_url),
            "The first-trust playback did not return the current address.")
    require(any("FirstTrust" in event for event in events), "The existing stream was not accepted through first trust.")
    require(all(probe_calls(event) in (0, None) for event in events), f"First trust performed a probe: {events}")
    row = fingerprint_row(mp4_item["Id"], mp4_item["Id"])
    require(row is not None and row["url_hash"] == expected_url_hash(mp4_url),
            "The first-trust fingerprint was not created.")
    require(set(row) == {"item_id", "source_key", "url_hash", "sha1", "file_size"}, "The fingerprint row has unexpected fields.")
    summary["first_trust"] = {"event": events[-1] if events else None, "fingerprint": row}

    # Unchanged re-check must not probe.
    before = plugin_events()
    status, reuse = playback_info(auth, mp4_item["Id"])
    reuse_events = [safe_event(line) for line in event_delta(before, plugin_events())]
    require(status == 200 and source_for_url(reuse, mp4_url), "The unchanged re-check failed.")
    require(all(probe_calls(event) in (0, None) for event in reuse_events), f"The unchanged re-check probed: {reuse_events}")
    summary["unchanged_reuse"] = reuse_events

    summary["configuration_page"] = configuration_page_scenario(auth, evidence_dir)
    auth = api_auth()
    summary["native_task"] = ensure_native_task(auth)
    auth = api_auth()

    # MP4 and MKV must actually play in the native web client.
    summary["playback"] = playback_scenario(auth, [
        {"name": "Package MP4", "id": mp4_item["Id"]},
        {"name": "Package MKV", "id": mkv_item["Id"]},
    ], evidence_dir)
    auth = api_auth()

    # A same-SHA-1/size URL change must probe, persist the new address and survive restart.
    alt_url = "http://media:8080/package-mp4-alt.mp4"
    write_versioned_strm("Package MP4", alt_url, mp4_sha, mp4_size)
    before = plugin_events()
    status, changed = playback_info(auth, mp4_item["Id"])
    changed_events = [safe_event(line) for line in event_delta(before, plugin_events())]
    require(status == 200 and source_for_url(changed, alt_url), "The changed URL was not returned after the probe.")
    require(any(probe_calls(event) == 1 for event in changed_events), f"The same-SHA URL change did not probe: {changed_events}")
    require(any("fingerprint committed" in event for event in changed_events), f"The changed URL was not committed: {changed_events}")
    changed_row = fingerprint_row(mp4_item["Id"], mp4_item["Id"])
    require(changed_row is not None and changed_row["url_hash"] == expected_url_hash(alt_url),
            "The changed URL was not persisted in the fingerprint.")
    restart()
    auth = api_auth()
    before = plugin_events()
    status, persisted = playback_info(auth, mp4_item["Id"])
    require(status == 200 and source_for_url(persisted, alt_url), "The changed URL was not restored after restart.")
    require(all(probe_calls(safe_event(line)) in (0, None) for line in event_delta(before, plugin_events())),
            "A persisted changed URL was re-probed after restart.")
    summary["same_sha_url_change"] = {"events": changed_events, "fingerprint": changed_row,
                                      "after_restart_reused": True}
    return summary


def build_baseline_archive(baseline_revision: str, destination_dir: Path) -> dict:
    """Build the accepted Slice 3 baseline publish in an isolated worktree; never touch main."""
    require(re.fullmatch(r"[0-9a-f]{40}", baseline_revision), "The baseline revision must be a full commit SHA.")
    worktree = Path(tempfile.mkdtemp(prefix="strm-baseline-wt-"))
    add = run("git", "worktree", "add", "--detach", str(worktree), baseline_revision, timeout=120)
    require(add.returncode == 0, f"Could not create the baseline worktree: {add.stderr.strip()}")
    try:
        publish_dir = Path(tempfile.mkdtemp(prefix="strm-baseline-pub-"))
        result = run("bash", str(ROOT / "scripts" / "dotnet-local"), "publish",
                     str(worktree / "src" / "Jellyfin.Plugin.StrmProbeOptimizer" / "Jellyfin.Plugin.StrmProbeOptimizer.csproj"),
                     "--configuration", "Release", "--runtime", "linux-x64", "--self-contained", "false",
                     "--output", str(publish_dir), "--nologo", timeout=900)
        require(result.returncode == 0, f"The baseline publish failed: {result.stderr.strip()[-400:]}")
        destination_dir.mkdir(parents=True, exist_ok=True)
        folder = destination_dir / "Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0"
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        for name in ("Jellyfin.Plugin.StrmProbeOptimizer.dll", "Jellyfin.Plugin.StrmProbeOptimizer.deps.json",
                     "Microsoft.Data.Sqlite.dll", "SQLitePCLRaw.batteries_v2.dll", "SQLitePCLRaw.core.dll",
                     "SQLitePCLRaw.provider.e_sqlite3.dll", "libe_sqlite3.so"):
            require((publish_dir / name).is_file(), f"The baseline publish is missing {name!r}.")
            shutil.copy2(publish_dir / name, folder / name)
        # The accepted baseline ships the prototype manifest.
        meta = {"category": "General", "description": "STRM playback interception prototype for Jellyfin 12.2.0.",
                "guid": PLUGIN_ID, "name": "STRM Probe Optimizer",
                "overview": "Validates native playback probe decisions and saved results for versioned STRM files.",
                "owner": "local-development", "targetAbi": "12.2.0.0", "version": "0.1.0.0",
                "assemblies": ["Jellyfin.Plugin.StrmProbeOptimizer.dll", "Microsoft.Data.Sqlite.dll",
                               "SQLitePCLRaw.batteries_v2.dll", "SQLitePCLRaw.core.dll",
                               "SQLitePCLRaw.provider.e_sqlite3.dll"]}
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        digests = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(folder.iterdir())}
        return {"revision": baseline_revision, "folder": str(folder), "files": digests}
    finally:
        run("git", "worktree", "remove", "--force", str(worktree), timeout=120)
        shutil.rmtree(worktree, ignore_errors=True)


def deploy_baseline(baseline_dir: Path) -> None:
    plugins = WORK / "config" / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    target = plugins / "Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(baseline_dir / "Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0", target)


def scenario_upgrade(package: Path, baseline_revision: str, evidence_dir: Path | None) -> dict:
    summary: dict[str, object] = {}
    pe.prepare_clean_instance()
    baseline_dir = WORK / "baseline"
    summary["baseline"] = build_baseline_archive(baseline_revision, baseline_dir)
    deploy_baseline(baseline_dir)
    restart()
    auth = api_auth()
    require(str(plugin_status(auth)).lower() in {"active", "0"}, "The baseline plugin is not Active.")

    mp4_sha, mp4_size = pe.media_sha1(pe.MEDIA_MP4)
    write_versioned_strm("Upgrade Item", "http://media:8080/" + pe.MEDIA_MP4, mp4_sha, mp4_size)
    item = native_probe_and_save(auth, "Upgrade Item", "http://media:8080/" + pe.MEDIA_MP4)
    # Establish a trusted fingerprint and a non-default configuration on the baseline.
    status, _ = playback_info(auth, item["Id"])
    require(status == 200, "The baseline could not establish its fingerprint.")
    require(plugin_action(auth, True) == 204, "The baseline plugin enable failed.")
    pe.request_json("POST", f"/Plugins/{PLUGIN_ID}/Configuration", headers={"Authorization": auth},
                    body={"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 3,
                          "DetailedLog": True, "BatchAllLibraries": True, "BatchLibraryIds": ""})
    baseline_fingerprint = fingerprint_row(item["Id"], item["Id"])
    require(baseline_fingerprint is not None, "The baseline fingerprint was not created.")
    configuration_before = CONFIGURATION_FILE.read_bytes()
    # Prepare a pending change (a new URL) so the upgrade must re-check it.
    pending_url = "http://media:8080/package-mp4-alt.mp4"
    write_versioned_strm("Upgrade Item", pending_url, mp4_sha, mp4_size)
    pe.compose("stop")
    time.sleep(1)
    summary["deployment"] = pe.deploy_archive(package)
    pe.compose("up")
    pe.wait_healthy()
    auth = api_auth()
    require(str(plugin_status(auth)).lower() in {"active", "0"}, "The candidate plugin is not Active after upgrade.")
    summary["payload_matches_archive"] = deployed_matches_archive(package)
    require(CONFIGURATION_FILE.read_bytes() == configuration_before, "The upgrade changed the persisted configuration file.")
    status, effective = pe.request_json("GET", f"/Plugins/{PLUGIN_ID}/Configuration", headers={"Authorization": auth})
    require(int(effective["MaxConcurrentProbes"]) == 3 and effective["DetailedLog"] is True,
            f"The upgrade did not preserve the effective configuration: {effective}")
    require(fingerprint_row(item["Id"], item["Id"]) == baseline_fingerprint,
            "The upgrade changed the trusted baseline before the pending change was re-checked.")
    summary["preserved_configuration"] = effective
    summary["preserved_fingerprint"] = baseline_fingerprint
    # The pending change must be re-checked and committed by the candidate.
    before = plugin_events()
    status, changed = playback_info(auth, item["Id"])
    events = [safe_event(line) for line in event_delta(before, plugin_events())]
    require(status == 200 and source_for_url(changed, pending_url), "The upgrade did not re-check the pending URL change.")
    require(any(probe_calls(event) == 1 for event in events), f"The pending change was not probed after upgrade: {events}")
    updated = fingerprint_row(item["Id"], item["Id"])
    require(updated is not None and updated["url_hash"] == expected_url_hash(pending_url),
            "The upgrade did not commit the pending change.")
    summary["pending_change_committed"] = updated
    # Backup and restore the configuration and fingerprint database, per the delivery instructions.
    backup_dir = WORK / "backup"
    backup_dir.mkdir(exist_ok=True)
    shutil.copy2(CONFIGURATION_FILE, backup_dir / "config.xml")
    shutil.copy2(FINGERPRINT_DATABASE, backup_dir / "strm-fingerprints.db")
    summary["backup_restore"] = {"configuration": str(backup_dir / "config.xml"), "fingerprint": str(backup_dir / "strm-fingerprints.db")}
    return summary


def scenario_recovery(package: Path, evidence_dir: Path | None) -> dict:
    summary: dict[str, object] = {}
    auth = api_auth()
    mp4_sha, mp4_size = pe.media_sha1(pe.MEDIA_MP4)
    write_versioned_strm("Recovery Item", "http://media:8080/" + pe.MEDIA_MP4, mp4_sha, mp4_size)
    item = native_probe_and_save(auth, "Recovery Item", "http://media:8080/" + pe.MEDIA_MP4)
    status, _ = playback_info(auth, item["Id"])
    require(status == 200, "The recovery scenario could not establish a fingerprint.")

    # Disable through Jellyfin: native playback must continue without plugin events.
    require(plugin_action(auth, False) == 204, "The recovery plugin disable failed.")
    restart()
    auth = api_auth()
    require(str(plugin_status(auth)).lower() not in {"active", "0"}, "The plugin remained active after disable.")
    before = plugin_events()
    status, disabled = playback_info(auth, item["Id"])
    require(status == 200 and source_for_url(disabled, "http://media:8080/" + pe.MEDIA_MP4),
            "Native playback failed after disabling the plugin.")
    require(event_delta(before, plugin_events()) == [], "The disabled plugin emitted events.")
    summary["disabled_native_playback"] = True

    # Remove the plugin payload entirely: native playback must still work.
    pe.remove_deployed_plugin()
    restart()
    auth = api_auth()
    before = plugin_events()
    status, removed = playback_info(auth, item["Id"])
    require(status == 200 and source_for_url(removed, "http://media:8080/" + pe.MEDIA_MP4),
            "Native playback failed after removing the plugin payload.")
    require(event_delta(before, plugin_events()) == [], "The removed plugin still emitted events.")
    summary["removed_native_playback"] = True

    # Reinstall the archive and re-check: the plugin must come back Active and re-evaluate.
    pe.deploy_archive(package)
    restart()
    auth = api_auth()
    require(str(plugin_status(auth)).lower() in {"active", "0"}, "The reinstalled plugin is not Active.")
    before = plugin_events()
    status, reinstalled = playback_info(auth, item["Id"])
    require(status == 200 and source_for_url(reinstalled, "http://media:8080/" + pe.MEDIA_MP4),
            "The reinstalled plugin did not return the current address.")
    require(any(PLUGIN_LOGGER in line for line in event_delta(before, plugin_events())),
            "The reinstalled plugin made no decision for the re-checked item.")
    summary["reinstalled_recheck"] = True
    return summary


def scenario_invalid(package: Path, evidence_dir: Path | None) -> dict:
    """Corrupt/unsafe archives must be refused; a valid install must survive a refused replacement."""
    import package_plugin as pp

    results: dict[str, object] = {}
    scratch = Path(tempfile.mkdtemp(prefix="strm-invalid-packages-"))
    try:
        original = package.read_bytes()
        cases: dict[str, Path] = {}

        truncated = scratch / "truncated.zip"
        truncated.write_bytes(original[: len(original) // 2])
        cases["truncated"] = truncated

        # Missing native asset.
        missing = scratch / "missing-native.zip"
        with zipfile.ZipFile(package) as source, zipfile.ZipFile(missing, "w") as target:
            for name in source.namelist():
                if name.endswith("libe_sqlite3.so"):
                    continue
                target.writestr(name, source.read(name))
        cases["missing_native"] = missing

        # GUID mismatch.
        guid = scratch / "guid.zip"
        with zipfile.ZipFile(package) as source, zipfile.ZipFile(guid, "w") as target:
            for name in source.namelist():
                data = source.read(name)
                if name.endswith("meta.json"):
                    manifest = json.loads(data)
                    manifest["guid"] = str(uuid.uuid4())
                    data = json.dumps(manifest).encode()
                target.writestr(name, data)
        cases["guid_mismatch"] = guid

        # targetAbi mismatch.
        abi = scratch / "abi.zip"
        with zipfile.ZipFile(package) as source, zipfile.ZipFile(abi, "w") as target:
            for name in source.namelist():
                data = source.read(name)
                if name.endswith("meta.json"):
                    manifest = json.loads(data)
                    manifest["targetAbi"] = "10.11.0.0"
                    data = json.dumps(manifest).encode()
                target.writestr(name, data)
        cases["target_abi_mismatch"] = abi

        # Path traversal.
        traversal = scratch / "traversal.zip"
        with zipfile.ZipFile(package) as source, zipfile.ZipFile(traversal, "w") as target:
            for name in source.namelist():
                target.writestr(name, source.read(name))
            target.writestr("Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0/../evil.dll", b"x")
        cases["path_traversal"] = traversal

        # Symbolic link.
        symlink = scratch / "symlink.zip"
        with zipfile.ZipFile(package) as source, zipfile.ZipFile(symlink, "w") as target:
            for name in source.namelist():
                target.writestr(name, source.read(name))
            info = zipfile.ZipInfo("Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0/link")
            info.external_attr = (0o120777 << 16)
            target.writestr(info, "meta.json")
        cases["symlink"] = symlink

        for name, path in cases.items():
            try:
                pp.verify_archive(path)
            except (pp.PackageError, zipfile.BadZipFile, OSError) as error:
                results[name] = {"rejected": True, "reason": str(error)[:160]}
            else:
                results[name] = {"rejected": False, "reason": "verify_archive accepted an invalid archive"}

        # A refused replacement must leave the currently deployed valid install untouched.
        pe.prepare_clean_instance()
        pe.deploy_archive(package)
        valid_payload = pe.deployed_payload()
        refused = False
        try:
            pe.deploy_archive(cases["missing_native"])
        except (pp.PackageError, pe.PackageEnvironmentError, zipfile.BadZipFile, OSError):
            refused = True
        require(refused, "The package environment accepted an invalid archive.")
        require(pe.deployed_payload() == valid_payload, "A refused archive disturbed the valid installation.")
        results["valid_install_preserved"] = True
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    for name, value in results.items():
        if name == "valid_install_preserved":
            continue
        require(value["rejected"], f"The invalid case {name!r} was not rejected.")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--baseline-revision")
    parser.add_argument("--scenario", default="all",
                        choices=["all", "clean", "upgrade", "recovery", "invalid"])
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()

    package = args.package.resolve()
    evidence_dir = args.evidence_dir.resolve() if args.evidence_dir else None
    summary: dict[str, object] = {"scenario": args.scenario, "package": str(package)}
    exit_code = 1
    try:
        verification = package_plugin.verify_archive(package)
        summary["package_identity"] = {
            "archiveSha256": verification["archiveSha256"],
            "version": verification["version"],
            "guid": verification["guid"],
            "targetAbi": verification["targetAbi"],
            "runtime": verification["runtime"],
            "entries": verification["entries"],
        }
        if args.scenario in {"all", "invalid"}:
            summary["invalid"] = scenario_invalid(package, evidence_dir)
        if args.scenario in {"all", "clean"}:
            summary["clean"] = scenario_clean(package, evidence_dir)
        if args.scenario in {"all", "upgrade"}:
            require(args.baseline_revision, "The upgrade scenario requires --baseline-revision.")
            summary["upgrade"] = scenario_upgrade(package, args.baseline_revision, evidence_dir)
        if args.scenario in {"all", "recovery"}:
            if args.scenario == "recovery":
                # A standalone recovery run needs a clean instance with the candidate installed.
                pe.prepare_clean_instance()
                pe.deploy_archive(package)
                restart()
            summary["recovery"] = scenario_recovery(package, evidence_dir)
        if PROBLEMS:
            summary["status"] = "FAIL"
            summary["problems"] = list(PROBLEMS)
            exit_code = 1
        else:
            summary["status"] = "PASS"
            exit_code = 0
    except (RuntimeError, OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError,
            zipfile.BadZipFile, package_plugin.PackageError, pe.PackageEnvironmentError) as error:
        summary["status"] = "FAIL"
        summary["error"] = f"{type(error).__name__}: {error}"
        exit_code = 1
    finally:
        if evidence_dir is not None:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / "package-integration-result.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
