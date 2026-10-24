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
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import package_environment as pe  # noqa: E402
import package_plugin  # noqa: E402

ROOT = pe.ROOT
PLUGIN_ID = "b061643e-d17d-4c6e-8ba2-6b57e286bd20"
PAGE_NAME = "StrmProbeOptimizer"
TASK_NAME = "STRM 媒体信息检查"
PLUGIN_LOGGER = "Jellyfin.Plugin.StrmProbeOptimizer.Services.StrmPlaybackOptimizer"
CONFIG_DRIVER = ROOT / "scripts" / "configuration_page_driver.mjs"
PLAYBACK_DRIVER = ROOT / "scripts" / "package_playback_driver.mjs"
BROWSER_TOOLS = ROOT / "artifacts" / "dev-env" / "browser-tools"
MAX_WAIT = 120


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return pe.run(*args, timeout=timeout)


def api_auth() -> str:
    credentials = json.loads(pe.credentials_path().read_text(encoding="utf-8"))
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


def fingerprint_database() -> Path:
    return pe.WORK / "config" / "data" / "plugins" / "b061643ed17d4c6e8ba26b57e286bd20" / "strm-fingerprints.db"


def configuration_file() -> Path:
    return pe.WORK / "config" / "plugins" / "configurations" / "Jellyfin.Plugin.StrmProbeOptimizer.xml"


def fingerprint_row(item_id: str, source_key: str) -> dict | None:
    import sqlite3

    database = fingerprint_database()
    require(database.is_file(), "The plugin fingerprint database was not created.")
    uri = database.as_posix() + "?mode=ro"
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


def native_task_definition(auth: str | None = None) -> dict:
    """Read the native task's identity and triggers without starting it.

    The accepted ``ensure_native_task`` both finds the task and runs it; a compatibility round that
    must measure its own changes needs the read-only half only. The request authenticates for
    itself, because a previous native login already revoked an earlier token.
    """
    status, tasks = pe.request_json("GET", "/ScheduledTasks",
                                    headers={"Authorization": api_auth()})
    require(status == 200, "The scheduled-task listing failed.")
    matches = [task for task in tasks if task.get("Name") == TASK_NAME]
    require(len(matches) == 1, f"Expected exactly one native task {TASK_NAME!r}.")
    task = matches[0]
    triggers = task.get("Triggers", [])
    require(triggers == [], f"The native task must default to no trigger, found {triggers}.")
    return {"task_id": task["Id"], "default_triggers": triggers}


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
    credentials = json.loads(pe.credentials_path().read_text(encoding="utf-8"))
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
    credentials = json.loads(pe.credentials_path().read_text(encoding="utf-8"))
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


def installed_plugin_payload() -> tuple[dict[str, str], Path]:
    """Return the payload Jellyfin's own installer created, plus the folder it lives in.

    The native installer extracts the archive into ``<PluginsPath>/<PackageName>_<Version>/``, so the
    archive's own top-level folder ends up one level below that. The payload is therefore read from
    the archive's folder wherever the native install put it, instead of from the manually deployed
    layout ``deploy_archive`` produces.
    """
    root = pe.require_owned_path(pe.WORK / "config" / "plugins", label="package plugins directory")
    require(root.is_dir(), "The instance has no plugins directory after the native installation.")
    candidates = sorted(path for path in root.rglob("Jellyfin.Plugin.StrmProbeOptimizer.deps.json")
                        if path.is_file())
    require(len(candidates) == 1,
            f"Expected exactly one natively installed plugin payload, found {[str(p) for p in candidates]}")
    folder = candidates[0].parent
    require(folder.is_dir() and not folder.is_symlink(),
            "The natively installed plugin folder is not a real directory.")
    payload = {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in sorted(folder.rglob("*")) if path.is_file()}
    return payload, folder


def installed_matches_archive(archive: Path) -> dict:
    """Prove the natively installed payload matches the archive byte-for-byte.

    Jellyfin rewrites ``meta.json`` during ``PopulateManifest``, so that single file is compared
    field-wise; every code and native asset must match the archive exactly.
    """
    with zipfile.ZipFile(archive) as bundle:
        top = {name.split("/", 1)[0] for name in bundle.namelist() if "/" in name}
        require(len(top) == 1, f"The archive must have exactly one top-level folder, found {sorted(top)}.")
        expected = {name.split("/", 1)[1]: hashlib.sha256(bundle.read(name)).hexdigest()
                    for name in bundle.namelist() if not name.endswith("/")}
    deployed, folder = installed_plugin_payload()
    expected_payload = {name: digest for name, digest in expected.items() if name != "meta.json"}
    deployed_payload = {name: digest for name, digest in deployed.items() if name != "meta.json"}
    require(set(deployed_payload) == set(expected_payload),
            f"The natively installed payload differs from the archive: "
            f"{sorted(set(deployed_payload) ^ set(expected_payload))}.")
    for name, digest in expected_payload.items():
        require(deployed_payload[name] == digest,
                f"The natively installed file {name!r} does not match the archive digest.")
    manifest = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(archive) as bundle:
        archived = json.loads(bundle.read(next(n for n in bundle.namelist() if n.endswith("meta.json"))))
    for field in ("guid", "version", "targetAbi", "assemblies"):
        require(manifest[field] == archived[field],
                f"Jellyfin's installed manifest field {field!r} does not match the archive identity.")
    return {"payloadFiles": len(deployed_payload), "matched": True, "folder": str(folder),
            "installedManifest": {key: manifest.get(key) for key in
                                  ("guid", "version", "targetAbi", "status", "autoUpdate")}}


def plugin_folders() -> dict[str, Path]:
    """Every folder directly under this instance's plugins directory."""
    root = pe.WORK / "config" / "plugins"
    if not root.is_dir():
        return {}
    return {path.name: path for path in root.iterdir()}


def deploy_baseline(baseline_dir: Path) -> None:
    owned_plugins = pe.require_owned_path(pe.WORK / "config" / "plugins", label="package plugins directory")
    owned_plugins.mkdir(parents=True, exist_ok=True)
    target = pe.require_owned_path(owned_plugins / "Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0", label="baseline folder")
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(baseline_dir / "Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0", target)


def scenario_upgrade(package: Path, baseline_revision: str, evidence_dir: Path | None) -> dict:
    summary: dict[str, object] = {}
    pe.prepare_clean_instance()
    baseline_dir = pe.WORK / "baseline"
    summary["baseline"] = build_baseline_archive(baseline_revision, baseline_dir)
    deploy_baseline(baseline_dir)
    restart()
    auth = api_auth()
    require(str(plugin_status(auth)).lower() in {"active", "0"}, "The baseline plugin is not Active.")

    mp4_sha, mp4_size = pe.media_sha1(pe.MEDIA_MP4)
    unchanged_url = "http://media:8080/" + pe.MEDIA_MP4
    pending_url = "http://media:8080/package-mp4-alt.mp4"
    # Two items: one stays unchanged across the upgrade, one has a pending URL change.
    write_versioned_strm("Upgrade Unchanged", unchanged_url, mp4_sha, mp4_size)
    write_versioned_strm("Upgrade Item", unchanged_url, mp4_sha, mp4_size)
    unchanged_item = native_probe_and_save(auth, "Upgrade Unchanged", unchanged_url)
    item = native_probe_and_save(auth, "Upgrade Item", unchanged_url)
    # Establish trusted fingerprints and a non-default configuration on the baseline.
    status, _ = playback_info(auth, unchanged_item["Id"])
    require(status == 200, "The baseline could not establish the unchanged item's fingerprint.")
    status, _ = playback_info(auth, item["Id"])
    require(status == 200, "The baseline could not establish its fingerprint.")
    require(plugin_action(auth, True) == 204, "The baseline plugin enable failed.")
    pe.request_json("POST", f"/Plugins/{PLUGIN_ID}/Configuration", headers={"Authorization": auth},
                    body={"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 3,
                          "DetailedLog": True, "BatchAllLibraries": True, "BatchLibraryIds": ""})
    unchanged_fingerprint = fingerprint_row(unchanged_item["Id"], unchanged_item["Id"])
    baseline_fingerprint = fingerprint_row(item["Id"], item["Id"])
    require(unchanged_fingerprint is not None and baseline_fingerprint is not None,
            "The baseline fingerprints were not created.")
    configuration_before = configuration_file().read_bytes()
    # Prepare a pending change (a new URL) so the upgrade must re-check it.
    write_versioned_strm("Upgrade Item", pending_url, mp4_sha, mp4_size)
    pe.compose("stop")
    time.sleep(1)
    summary["deployment"] = pe.deploy_archive(package)
    pe.compose("up")
    pe.wait_healthy()
    auth = api_auth()
    require(str(plugin_status(auth)).lower() in {"active", "0"}, "The candidate plugin is not Active after upgrade.")
    summary["payload_matches_archive"] = deployed_matches_archive(package)
    require(configuration_file().read_bytes() == configuration_before, "The upgrade changed the persisted configuration file.")
    status, effective = pe.request_json("GET", f"/Plugins/{PLUGIN_ID}/Configuration", headers={"Authorization": auth})
    require(int(effective["MaxConcurrentProbes"]) == 3 and effective["DetailedLog"] is True,
            f"The upgrade did not preserve the effective configuration: {effective}")
    require(fingerprint_row(unchanged_item["Id"], unchanged_item["Id"]) == unchanged_fingerprint,
            "The upgrade changed the unchanged item's trusted baseline.")
    require(fingerprint_row(item["Id"], item["Id"]) == baseline_fingerprint,
            "The upgrade changed the trusted baseline before the pending change was re-checked.")
    summary["preserved_configuration"] = effective
    summary["preserved_fingerprint"] = baseline_fingerprint

    # The unchanged item must reuse its fingerprint with zero plugin probes after replacement.
    before = plugin_events()
    status, reused = playback_info(auth, unchanged_item["Id"])
    reuse_events = [safe_event(line) for line in event_delta(before, plugin_events())]
    require(status == 200 and source_for_url(reused, unchanged_url),
            "The upgrade did not return the unchanged item's current address.")
    require(all(probe_calls(event) in (0, None) for event in reuse_events),
            f"The unchanged item was probed after upgrade: {reuse_events}")
    summary["unchanged_reuse"] = reuse_events

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

    # Real backup and restore: stop the server, back up config + fingerprint, mutate the
    # live values through the normal API, then stop, restore the backup, restart and read back.
    backup_dir = pe.WORK / "backup"
    pe.compose("stop")
    time.sleep(1)
    summary["backup"] = pe.backup_state(backup_dir)
    pe.compose("up")
    pe.wait_healthy()
    auth = api_auth()
    # Mutate the live configuration so the restore is meaningful and observable.
    pe.request_json("POST", f"/Plugins/{PLUGIN_ID}/Configuration", headers={"Authorization": auth},
                    body={"Enabled": True, "PlaybackAutoCheck": False, "MaxConcurrentProbes": 7,
                          "DetailedLog": False, "BatchAllLibraries": True, "BatchLibraryIds": ""})
    pe.compose("stop")
    time.sleep(1)
    restored = pe.restore_state(backup_dir)
    pe.compose("up")
    pe.wait_healthy()
    auth = api_auth()
    status, after_restore = pe.request_json("GET", f"/Plugins/{PLUGIN_ID}/Configuration", headers={"Authorization": auth})
    require(int(after_restore["MaxConcurrentProbes"]) == 3 and after_restore["DetailedLog"] is True
            and after_restore["PlaybackAutoCheck"] is True,
            f"The restored configuration does not match the backup: {after_restore}")
    require(restored["configuration"]["sha256"] == summary["backup"]["configuration"]["sha256"],
            "The restored configuration file does not match the backup bytes.")
    require(fingerprint_row(item["Id"], item["Id"])["url_hash"] == expected_url_hash(pending_url),
            "The restored fingerprint does not match the backed-up committed change.")
    status, restored_playback = playback_info(auth, item["Id"])
    require(status == 200 and source_for_url(restored_playback, pending_url),
            "The restored instance did not play the committed address.")
    summary["restore"] = {"restored": restored, "effective": after_restore, "playback_reused": True}

    # Negative control: a restore from a directory that does not exist must be refused.
    refused = False
    try:
        pe.restore_state(backup_dir / "missing-backup")
    except (pe.PackageEnvironmentError, OSError):
        refused = True
    require(refused, "The restore accepted a missing backup directory.")
    summary["restore_failure_refused"] = True
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
        published_sha, published_entries = pp.expected_from_sidecar(package)
        cases: dict[str, Path] = {}

        def rewrite(name: str, mutate) -> None:
            target = scratch / (name + ".zip")
            with zipfile.ZipFile(package) as source, zipfile.ZipFile(target, "w") as output:
                for entry in source.namelist():
                    data = source.read(entry)
                    replacement = mutate(entry, data)
                    if replacement is None:
                        continue
                    output.writestr(entry, replacement)
            cases[name] = target

        truncated = scratch / "truncated.zip"
        truncated.write_bytes(original[: len(original) // 2])
        cases["truncated"] = truncated

        # Missing native asset.
        rewrite("missing_native", lambda entry, data: None if entry.endswith("libe_sqlite3.so") else data)

        # Changed native payload (content differs but the old sidecar digest is preserved).
        def change_native(entry: str, data: bytes) -> bytes:
            return b"not a native SQLite library" if entry.endswith("libe_sqlite3.so") else data

        rewrite("changed_native_payload", change_native)

        # A managed dependency removed from the ZIP and the meta whitelist while deps still needs it.
        def drop_managed(entry: str, data: bytes) -> bytes | None:
            if entry.endswith("/Microsoft.Data.Sqlite.dll"):
                return None
            if entry.endswith("meta.json"):
                manifest = json.loads(data)
                manifest["assemblies"].remove("Microsoft.Data.Sqlite.dll")
                return json.dumps(manifest).encode()
            return data

        rewrite("missing_managed_with_stale_deps", drop_managed)

        # Manifest version conflict.
        def conflict_version(entry: str, data: bytes) -> bytes:
            if entry.endswith("meta.json"):
                manifest = json.loads(data)
                manifest["version"] = "9.9.9.9"
                return json.dumps(manifest).encode()
            return data

        rewrite("version_conflict", conflict_version)

        # An extra Jellyfin core assembly that must never ship.
        core = scratch / "extra_core_assembly.zip"
        with zipfile.ZipFile(package) as source, zipfile.ZipFile(core, "w") as target:
            root = source.namelist()[0].split("/")[0]
            for entry in source.namelist():
                target.writestr(entry, source.read(entry))
            target.writestr(root + "/Jellyfin.Controller.dll", b"unexpected core assembly")
        cases["extra_core_assembly"] = core

        # GUID mismatch.
        rewrite("guid_mismatch", lambda entry, data: (
            json.dumps({**json.loads(data), "guid": str(uuid.uuid4())}).encode()
            if entry.endswith("meta.json") else data))

        # targetAbi mismatch.
        rewrite("target_abi_mismatch", lambda entry, data: (
            json.dumps({**json.loads(data), "targetAbi": "10.11.0.0"}).encode()
            if entry.endswith("meta.json") else data))

        # Path traversal.
        traversal = scratch / "path_traversal.zip"
        with zipfile.ZipFile(package) as source, zipfile.ZipFile(traversal, "w") as target:
            for entry in source.namelist():
                target.writestr(entry, source.read(entry))
            target.writestr("Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0/../evil.dll", b"x")
        cases["path_traversal"] = traversal

        # Symbolic link.
        symlink = scratch / "symlink.zip"
        with zipfile.ZipFile(package) as source, zipfile.ZipFile(symlink, "w") as target:
            for entry in source.namelist():
                target.writestr(entry, source.read(entry))
            info = zipfile.ZipInfo("Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0/link")
            info.external_attr = 0o120777 << 16
            target.writestr(info, "meta.json")
        cases["symlink"] = symlink

        for name, path in cases.items():
            # Publish the original sidecar next to every mutation so the digest comparison is
            # genuinely exercised (a missing sidecar would otherwise mask the digest check).
            source_sidecar = pp.sidecar_manifest_path(package)
            if source_sidecar.is_file():
                shutil.copy2(source_sidecar, pp.sidecar_manifest_path(path))
            # Each mutation must fail on its own structural merit where possible, independent
            # of the sidecar digest, so no single digest mismatch makes every case pass by
            # accident.
            structural_rejected = False
            reason = "published sidecar digest mismatch"
            try:
                pp.verify_archive(path)
            except (pp.PackageError, zipfile.BadZipFile, OSError) as error:
                structural_rejected = True
                reason = str(error)[:160]
            # The published sidecar (unchanged) must also refuse every mutation of the original.
            sidecar_rejected = False
            if published_sha is not None:
                try:
                    pp.verify_archive(path, expected_sha256=published_sha, expected_entries=published_entries)
                except (pp.PackageError, zipfile.BadZipFile, OSError):
                    sidecar_rejected = True
            results[name] = {
                "rejected": structural_rejected or sidecar_rejected,
                "structural_rejected": structural_rejected,
                "sidecar_rejected": sidecar_rejected,
                "reason": reason,
            }

        # A package without a sidecar must still be refused by the deployment consumer.
        sidecar_missing = False
        if published_sha is not None:
            import shutil as _shutil
            isolated = scratch / "no-sidecar"
            isolated.mkdir()
            copy = isolated / package.name
            _shutil.copy2(package, copy)
            try:
                pp.verify_archive(copy, expected_sha256=published_sha, expected_entries=published_entries)
            except pp.PackageError:
                sidecar_missing = False
            else:
                sidecar_missing = True  # digest still matches; the consumer supplies it from the sidecar
            # The real protection is that deploy refuses when it cannot find a sidecar: exercise that.
            try:
                pe.deploy_archive(copy)
            except (pp.PackageError, pe.PackageEnvironmentError, zipfile.BadZipFile, OSError):
                results["missing_sidecar"] = {"rejected": True, "reason": "deployment refused an archive without its sidecar"}
            else:
                results["missing_sidecar"] = {"rejected": False, "reason": "deployment accepted an archive without its sidecar"}
            results["missing_sidecar"]["sidecar_digest_still_matched"] = sidecar_missing

        # A refused replacement must leave the currently deployed valid install untouched.
        pe.prepare_clean_instance()
        pe.deploy_archive(package)
        valid_payload = pe.deployed_payload()
        for name in ("changed_native_payload", "missing_managed_with_stale_deps", "version_conflict",
                     "extra_core_assembly", "missing_native"):
            refused = False
            try:
                pe.deploy_archive(cases[name])
            except (pp.PackageError, pe.PackageEnvironmentError, zipfile.BadZipFile, OSError):
                refused = True
            require(refused, f"The package environment accepted the invalid archive {name!r}.")
            require(pe.deployed_payload() == valid_payload,
                    f"The refused archive {name!r} disturbed the valid installation.")
        results["valid_install_preserved"] = True
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    for name, value in results.items():
        if name == "valid_install_preserved":
            continue
        require(value["rejected"], f"The invalid case {name!r} was not rejected.")
    return results



# ---------------------------------------------------------------------------------------------------------------------
# Slice 6 / Task 6.1 compatibility scenario: the released archive on Jellyfin 12.3
#
# Only sequencing lives here. Every step reuses an existing helper: the package-environment
# workspace/instance, the native API reads above, the strict playback driver, and the native batch
# scenarios in ``run_isolated_batch_integration``. Nothing relaxes a success condition of the plugin.
# ---------------------------------------------------------------------------------------------------------------------

# The playback entry is imported for its read-only native helpers only (source-id normalization,
# probe counting, the freeze/read-only comparison and the strict driver path). No playback scenario,
# journey or matrix row is reused: this Task's playback obligations belong to the 14-row matrix run.
import run_isolated_playback_integration as playback  # noqa: E402

CONTENT_LIBRARY = pe.STRM_LIBRARY
OTHER_LIBRARY = pe.LOCAL_LIBRARY
FLAT_PLUGIN_ID = PLUGIN_ID.replace("-", "").lower()
COMPAT_MAX_WAIT = 180


def require_compat(condition: bool, message: str) -> None:
    require(condition, message)


def compat_record(evidence_dir: Path | None, name: str, payload: object) -> None:
    if evidence_dir is None:
        return
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                                     encoding="utf-8")


def compat_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint_store_path() -> Path:
    return pe.WORK / "config" / "data" / "plugins" / FLAT_PLUGIN_ID / "strm-fingerprints.db"


def plugin_configuration() -> dict:
    status, body = pe.request_json("GET", f"/Plugins/{PLUGIN_ID}/Configuration",
                                   headers={"Authorization": api_auth()})
    require(status == 200, "The plugin configuration could not be read.")
    return body


def fingerprint_store_report() -> dict:
    """Read the released five-field fingerprint store without writing to it."""
    database = fingerprint_store_path()
    require(database.is_file(), "The plugin fingerprint store was not created on this instance.")
    # Read a copy: a WAL-mode store must not gain side files merely because it was inspected.
    with tempfile.TemporaryDirectory(prefix="strm-fingerprint-schema-") as temporary:
        copy = Path(temporary) / "strm-fingerprints.db"
        shutil.copy2(database, copy)
        with sqlite3.connect(copy) as connection:
            tables = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            columns = [row[1] for row in connection.execute("PRAGMA table_info(strm_fingerprint)")]
            rows = int(connection.execute("SELECT COUNT(*) FROM strm_fingerprint").fetchone()[0])
    require("strm_fingerprint" in tables, "The plugin fingerprint store has no strm_fingerprint table.")
    require(columns == ["item_id", "source_key", "url_hash", "sha1", "file_size"],
            f"The fingerprint schema is not the released five-field schema: {columns}")
    return {"path": str(database), "table": "strm_fingerprint", "columns": columns, "rows": rows,
            "sha256": compat_sha256(database.read_bytes())}


def fingerprint_row_by_item(item_id: str) -> dict | None:
    database = fingerprint_store_path()
    if not database.is_file():
        return None
    rows = read_fingerprint_rows_copy(database)
    wanted = uuid.UUID(item_id).hex
    return next((row for row in rows if row["item_id"] == wanted), None)


# --- Stage 1: native web repository install -------------------------------------------------------------

# The publicly served plugin repository this Task's Required Surface names. The native installer
# must download the released archive from this index; a locally served copy is not the contract's
# surface and cannot stand in for it.
PUBLIC_REPOSITORY_URL = (
    "https://raw.githubusercontent.com/kentinya/jellyfin-strm-probe/main/manifest.json"
)
PUBLIC_RELEASE_URL = (
    "https://github.com/kentinya/jellyfin-strm-probe/releases/download/v0.1.0/"
    "Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip"
)


def fetch_public_catalog(expected_archive: Path) -> dict:
    """Read the public index and prove it serves exactly the archive under test.

    This is the read-only half of the surface: the same document the native installer consumes is
    fetched here first, so the version, ABI, download address and MD5 the browser will see are
    recorded before the install and can be compared with the archive's own identity.
    """
    with urllib.request.urlopen(PUBLIC_REPOSITORY_URL, timeout=30) as response:
        require(response.status == 200, f"The public repository index answered {response.status}.")
        raw = response.read()
    catalog = json.loads(raw)
    require(isinstance(catalog, list) and len(catalog) == 1,
            "The public repository index must contain exactly one plugin entry.")
    plugin = catalog[0]
    require(_normalized_id(str(plugin.get("guid", ""))) == _normalized_id(PLUGIN_ID),
            f"The public index lists another plugin guid: {plugin.get('guid')!r}")
    versions = plugin.get("versions") or []
    require(len(versions) == 1, f"The public index must list exactly one version, found {len(versions)}.")
    version = versions[0]
    archive_md5 = hashlib.md5(expected_archive.read_bytes(), usedforsecurity=False).hexdigest()
    require(version.get("sourceUrl") == PUBLIC_RELEASE_URL,
            f"The public index download address is {version.get('sourceUrl')!r}, not the released asset.")
    require(version.get("checksum") == archive_md5,
            "The public index checksum does not match the archive under test.")
    return {"repositoryUrl": PUBLIC_REPOSITORY_URL, "indexSha256": compat_sha256(raw),
            "indexBytes": len(raw),
            "catalog": {"guid": plugin.get("guid"), "name": plugin.get("name"),
                        "versions": [{"version": version.get("version"),
                                      "targetAbi": version.get("targetAbi"),
                                      "sourceUrl": version.get("sourceUrl"),
                                      "checksum": version.get("checksum")}]},
            "archiveSha256": compat_sha256(expected_archive.read_bytes()),
            "archiveMd5": archive_md5}


def stage_web_install(package: Path, evidence_dir: Path | None, summary: dict) -> dict:
    # The public index is read before the instance exists, so a wrong or unavailable public surface
    # fails before any install attempt instead of being confused with an install problem.
    summary["publicRepository"] = fetch_public_catalog(package)
    pe.prepare_clean_instance()
    pe.compose("stop")
    pe.compose("up")
    pe.wait_healthy()
    credentials = json.loads(pe.credentials_path().read_text(encoding="utf-8"))
    # A fresh instance ships Jellyfin's own bundled providers, so only this plugin's absence is required.
    installed_before = sorted(name for name in plugin_folders()
                              if name.startswith("Jellyfin.Plugin.StrmProbeOptimizer"))
    require(not installed_before,
            f"A fresh instance must not contain this plugin before the native installation: {installed_before}")
    summary["preInstallBundledPlugins"] = sorted(plugin_folders())
    summary["preInstallPayloadAbsent"] = True
    driver = run_browser_driver(CONFIG_DRIVER, {
        "scenario": "web_install",
        "baseUrl": credentials["base_url"],
        "username": credentials["username"],
        "password": credentials["password"],
        "pluginId": PLUGIN_ID,
        "pluginName": "STRM Probe Optimizer",
        "pageName": PAGE_NAME,
        "repositoryName": "STRM Probe Optimizer — Linux x64",
        "repositoryUrl": summary["publicRepository"]["repositoryUrl"],
        # The native labels this scenario must click are the shipped English ones; the browser's UI
        # language is pinned for this scenario only (every other scenario keeps its accepted locale).
        "locale": "en-US",
        "screenshotDir": str((evidence_dir or Path(tempfile.gettempdir())) / "web-install"),
    }, evidence_dir, timeout=600)
    require("error" not in driver, f"The native repository/install driver failed: {driver.get('error')}")
    require(driver["repository"]["repositoryAdded"] is True,
            f"The native repository could not be added: {driver['repository']}")
    require(driver["install"]["installConfirmed"] is True,
            f"The native installation was not confirmed: {driver['install']}")
    summary["nativeInstall"] = {"repository": driver["repository"], "install": driver["install"],
                               "screenshots": driver.get("screenshots"),
                               "repositoryUrl": summary["publicRepository"]["repositoryUrl"],
                               "catalogDownload": summary["publicRepository"]["catalog"]["versions"][0]}
    before_restart = installed_matches_archive(package)
    summary["payloadBeforeRestart"] = {"payloadFiles": before_restart["payloadFiles"],
                                       "folder": before_restart["folder"]}
    restart()
    auth = api_auth()
    public = pe.public_info()
    summary["publicVersion"] = public.get("Version")
    require(public.get("Version") == pe.server_public_version(),
            f"The instance is {public.get('Version')!r}, not {pe.server_public_version()}.")
    summary["pluginStatus"] = plugin_status(auth)
    require(str(summary["pluginStatus"]).lower() in {"active", "0"},
            f"The natively installed plugin is not Active ({summary['pluginStatus']}).")
    summary["payloadMatchesArchive"] = installed_matches_archive(package)
    status, plugins = pe.request_json("GET", "/Plugins", headers={"Authorization": auth})
    installed = [plugin for plugin in plugins
                 if str(plugin.get("Id", "")).replace("-", "").lower() == FLAT_PLUGIN_ID]
    require(status == 200 and len(installed) == 1, "The natively installed plugin was not listed exactly once.")
    summary["installed"] = {key: installed[0].get(key) for key in
                            ("Id", "Name", "Version", "Status", "CanUninstall")}
    require(str(installed[0].get("Version")) == "0.1.0.0",
            f"The natively installed version is {installed[0].get('Version')!r}, not 0.1.0.0.")
    summary["configurationPage"] = configuration_page_scenario(auth, evidence_dir)
    auth = api_auth()
    # The store is created on the plugin's first real optimization, so the "core integration and
    # SQLite work" evidence is taken after one real first-trust playback (the same accepted
    # sequence the clean scenario uses): native probe with the plugin off, then the plugin's own
    # first trust creates the schema.
    summary["firstTrust"] = first_trust_after_install(package, evidence_dir)
    summary["fingerprintStore"] = fingerprint_store_report()
    summary["configurationAfterRestore"] = plugin_configuration()
    return summary


def first_trust_after_install(package: Path, evidence_dir: Path | None) -> dict:
    """Prove the natively installed plugin really takes part in a playback and creates its store.

    Jellyfin itself persists the main stream while the plugin is disabled (no first-trust claim can
    come from an unprobed item), then the plugin's own first-trust path accepts the existing stream
    with zero plugin probes and writes its minimal fingerprint. Only the accepted package helpers are
    used, on this run's own instance and synthetic media.
    """
    summary: dict[str, object] = {}
    sha1, size = pe.media_sha1(pe.MEDIA_MP4)
    url = "http://media:8080/" + pe.MEDIA_MP4
    pe.write_strm("Compatibility First Trust", url, sha1, size)
    auth = api_auth()
    item = scan_and_wait(auth, "Compatibility First Trust")
    require(plugin_action(auth, False) == 204, "The plugin disable before the native preparation failed.")
    restart()
    auth = api_auth()
    prepared = native_probe_and_save(auth, "Compatibility First Trust", url)
    summary["nativePreparedStreams"] = saved_stream_types(auth, prepared["Id"])
    require(plugin_action(auth, True) == 204, "The plugin enable after the native preparation failed.")
    restart()
    auth = api_auth()
    before = plugin_events()
    status, trusted = playback_info(auth, prepared["Id"])
    events = [safe_event(line) for line in event_delta(before, plugin_events())]
    require(status == 200 and source_for_url(trusted, url),
            "The first-trust playback did not return the current address.")
    require(any("FirstTrust" in event for event in events),
            f"The existing stream was not accepted through first trust: {events}")
    require(all(probe_calls(event) in (0, None) for event in events),
            f"First trust performed a probe: {events}")
    row = fingerprint_row(prepared["Id"], prepared["Id"])
    require(row is not None and set(row) == {"item_id", "source_key", "url_hash", "sha1", "file_size"},
            f"The first-trust fingerprint is missing or not the five-field row: {row}")
    summary.update({"itemId": prepared["Id"], "events": events, "fingerprint": row,
                    "nativeProbeSaved": True, "pluginProbeCalls": [
                        probe_calls(event) for event in events]})
    return summary


# --- Stage 2: non-empty 12.2 prepared workspace upgraded to 12.3 -----------------------------------------

UPGRADE_COPY_AREAS = ("config", "strm", "media", "media-server")


def workspace_digest(root: Path) -> str:
    """A stable read-only digest over a workspace's configuration, STRM and media bytes."""
    digest = hashlib.sha256()
    for area in UPGRADE_COPY_AREAS:
        base_dir = root / area
        if not base_dir.is_dir():
            continue
        for path in sorted(base_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def read_fingerprint_rows_copy(database: Path) -> list[dict]:
    """Read a fingerprint store's five-field rows without touching the file in place."""
    with tempfile.TemporaryDirectory(prefix="strm-fingerprint-read-") as temporary:
        copy = Path(temporary) / "strm-fingerprints.db"
        shutil.copy2(database, copy)
        with sqlite3.connect(copy) as connection:
            connection.row_factory = sqlite3.Row
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='strm_fingerprint'").fetchone()
            require(table is not None, "The copied fingerprint store has no strm_fingerprint table.")
            return [dict(row) for row in connection.execute(
                "SELECT item_id, source_key, url_hash, sha1, file_size FROM strm_fingerprint")]


def verify_upgrade_source(source: Path) -> dict:
    """Verify an existing prepared 12.2 workspace is owned, quiescent and internally consistent.

    Nothing in the source is modified: this only proves the source is a real non-empty prepared copy
    (run marker, no symbolic links, no SQLite transaction side files, a five-field fingerprint store
    with rows, the versioned STRM files and the media bytes those rows address).
    """
    require(source.is_dir(), f"The upgrade source workspace {source} does not exist.")
    resolved = source.resolve()
    require(resolved.is_relative_to(pe.BASE.resolve()),
            "The upgrade source must be an existing package-environment run workspace.")
    require((resolved / pe.RUN_MARKER).is_file(),
            "The upgrade source has no run marker; it is not an owned run workspace.")
    symlinks = [path for path in resolved.rglob("*") if path.is_symlink()]
    require(not symlinks, f"The upgrade source contains symbolic links: {[str(p) for p in symlinks[:5]]}")
    side_files = [path for path in resolved.rglob("*") if path.name.endswith(("-wal", "-shm", "-journal"))]
    require(not side_files,
            f"The upgrade source has SQLite transaction side files: {[str(p) for p in side_files[:5]]}")
    database = resolved / "config" / "data" / "plugins" / FLAT_PLUGIN_ID / "strm-fingerprints.db"
    require(database.is_file(), "The upgrade source has no plugin fingerprint store.")
    # The source is only ever read through a temporary copy: opening a WAL-mode database in place
    # can create -wal/-shm side files, which would itself disturb the prepared source.
    rows = read_fingerprint_rows_copy(database)
    require(rows, "The upgrade source holds no trusted fingerprint; it is not a non-empty prepared copy.")
    configuration = resolved / "config" / "plugins" / "configurations" / "Jellyfin.Plugin.StrmProbeOptimizer.xml"
    require(configuration.is_file(), "The upgrade source has no persisted plugin configuration.")
    strm_files = sorted((resolved / "strm").glob("*.strm"))
    require(strm_files, "The upgrade source has no versioned STRM files.")
    url_hashes = {row["url_hash"] for row in rows}
    strm_records = []
    for path in strm_files:
        data = path.read_bytes()
        text = data.decode("utf-8-sig")
        urls = [line.strip() for line in text.splitlines()
                if line.strip() and not line.strip().startswith("#")]
        require(urls, f"The upgrade source STRM {path.name} has no URL.")
        sha1_match = re.search(r"^# strm-probe-sha1:([0-9a-fA-F]{40})$", text, re.MULTILINE)
        size_match = re.search(r"^# strm-probe-size:(\d+)$", text, re.MULTILINE)
        leaf = urllib.parse.urlsplit(urls[0]).path.rsplit("/", 1)[-1]
        media = resolved / "media" / leaf
        require(media.is_file(), f"The upgrade source media {leaf} behind {path.name} is missing.")
        media_bytes = media.read_bytes()
        strm_records.append({
            "name": path.name, "url": urls[0], "sha256": compat_sha256(data),
            "urlHash": compat_sha256(urls[0].encode()),
            "sha1": sha1_match.group(1) if sha1_match else None,
            "size": int(size_match.group(1)) if size_match else None,
            "mediaSha1": hashlib.sha1(media_bytes).hexdigest(), "mediaSize": len(media_bytes),
        })
    require(any(record["urlHash"] in url_hashes for record in strm_records),
            "No trusted fingerprint matches one of the source's own STRM addresses.")
    return {"source": str(resolved), "runMarker": (resolved / pe.RUN_MARKER).read_text(encoding="utf-8").strip(),
            "fingerprints": rows, "strm": strm_records,
            "configurationSha256": compat_sha256(configuration.read_bytes()),
            "configuration": configuration.read_text(encoding="utf-8"),
            "digest": workspace_digest(resolved), "symlinks": 0, "sideFiles": 0}


def adopt_upgrade_source(source: Path) -> dict:
    """Copy the verified prepared state into this run's own fresh workspace.

    The source's own credentials file is copied as well (mode 0600): the adopted instance keeps the
    source's admin account, and without it no native read could be authenticated. Nothing in the
    source is modified.
    """
    credentials = source / pe.credentials_path().name
    require(credentials.is_file(), "The upgrade source has no credentials file for its own admin user.")
    target_credentials = pe.write_owned_bytes(pe.credentials_path(), credentials.read_bytes(),
                                              label="adopted credentials")
    target_credentials.chmod(0o600)
    for area in UPGRADE_COPY_AREAS:
        origin = source / area
        if not origin.is_dir():
            continue
        target = pe.require_owned_path(pe.WORK / area, label=f"adopted {area}")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(origin, target)
    require((pe.WORK / pe.RUN_MARKER).is_file(),
            "This run's workspace marker disappeared during the adoption.")
    return {"areas": list(UPGRADE_COPY_AREAS), "digest": workspace_digest(pe.WORK)}


def read_only_instance_state(auth: str) -> dict:
    """Read-only state of every adopted STRM item: configuration, address, streams and fingerprint.

    Only the read-only ``GET /Items`` query is issued. No PlaybackInfo and no playback: this is the
    state a restart/upgrade comparison must be able to read before any measurement.
    """
    require(str(plugin_status(auth)).lower() in {"active", "0"},
            "The adopted instance's plugin is not Active.")
    status, payload = pe.request_json(
        "GET", "/Items?Recursive=true&Limit=200&Fields=MediaSources,MediaStreams,Path",
        headers={"Authorization": auth})
    require(status == 200, "The adopted instance's item listing failed.")
    items: dict[str, object] = {}
    for item in payload.get("Items", []):
        path = str(item.get("Path") or "")
        if not path.endswith(".strm"):
            continue
        item_id = str(item.get("Id"))
        sources = [{
            "id": playback.normalize_source_id(source.get("Id")),
            "pathHash": compat_sha256(str(source.get("Path") or "").encode()),
            "path": playback.safe_path(source.get("Path")),
            "streamTypes": sorted({stream.get("Type") for stream in source.get("MediaStreams") or []}),
            "streamFields": sorted(json.dumps(stream, sort_keys=True)
                                   for stream in source.get("MediaStreams") or []),
        } for source in item.get("MediaSources") or []]
        items[str(item.get("Name") or item_id)] = {
            "itemId": item_id, "sources": sources,
            "fingerprint": fingerprint_row_by_item(item_id),
            "itemPathHash": compat_sha256(path.encode()),
        }
    require(items, "The adopted instance has no STRM item; an upgrade could not prove preservation.")
    require(any(entry["fingerprint"] is not None for entry in items.values()),
            "The adopted instance has no trusted fingerprint; it is not a non-empty prepared copy.")
    return {"configuration": plugin_configuration(),
            "configurationFileSha256": compat_sha256(
                (pe.WORK / "config" / "plugins" / "configurations"
                 / "Jellyfin.Plugin.StrmProbeOptimizer.xml").read_bytes()),
            "items": items}


def upgrade_preservation_failures(before: dict, after: dict) -> list[str]:
    failures: list[str] = []
    if after.get("configuration") != before.get("configuration"):
        failures.append("the effective plugin configuration changed across the upgrade")
    if after.get("configurationFileSha256") != before.get("configurationFileSha256"):
        failures.append("the persisted configuration bytes changed across the upgrade")
    before_items = before.get("items") or {}
    after_items = after.get("items") or {}
    if set(before_items) != set(after_items):
        failures.append(f"the STRM item set changed across the upgrade: "
                        f"{sorted(set(before_items) ^ set(after_items))}")
    for name, entry in before_items.items():
        observed = after_items.get(name)
        if observed is None:
            continue
        if observed.get("itemId") != entry.get("itemId"):
            failures.append(f"{name}: the native item id changed across the upgrade")
        if observed.get("sources") != entry.get("sources"):
            failures.append(f"{name}: the saved native address/streams changed across the upgrade")
        if observed.get("fingerprint") != entry.get("fingerprint"):
            failures.append(f"{name}: the trusted fingerprint changed across the upgrade")
        if entry.get("fingerprint") is not None and observed.get("fingerprint") is None:
            failures.append(f"{name}: the trusted fingerprint was lost by the upgrade")
        if observed.get("itemPathHash") != entry.get("itemPathHash"):
            failures.append(f"{name}: the item's own path changed across the upgrade")
    return failures


def stage_upgrade(package: Path, upgrade_source: Path, evidence_dir: Path | None, summary: dict) -> dict:
    # The upgrade needs its own clean instance inside this run's workspace: the previous stage's
    # fresh 12.3 instance is cleared, never reused, and the run marker is preserved.
    summary["reset"] = reset_owned_instance()
    summary["source"] = verify_upgrade_source(upgrade_source)
    summary["adopted"] = adopt_upgrade_source(upgrade_source)
    require(workspace_digest(upgrade_source) == summary["source"]["digest"],
            "The upgrade source changed while it was being copied; refusing to continue.")
    summary["sourceUnchangedAfterCopy"] = True
    summary["adoptedCredentials"] = {"path": str(pe.credentials_path()),
                                     "mode": oct(pe.credentials_path().stat().st_mode & 0o777)}
    # The adopted copy carries the prepared 12.2 *state* (configuration, native library, address,
    # streams and trusted fingerprints); the plugin payload is the released archive under test, so the
    # upgraded instance runs exactly the package this Task is about.
    summary["deployment"] = pe.deploy_archive(package)
    summary["payloadMatchesArchive"] = installed_matches_archive(package)
    summary["sourcePluginPayloadReplaced"] = True
    # Freeze the adopted state under the fixed 12.2 identity, then upgrade it in place.
    pe.select_server_version("12.2")
    summary["before"] = {"server": pe.verify_server_image()}
    pe.compose("up")
    pe.wait_healthy()
    auth = api_auth()
    summary["before"]["publicVersion"] = pe.public_info().get("Version")
    require(summary["before"]["publicVersion"] == "12.2.0",
            f"The adopted copy did not boot as Jellyfin 12.2.0 ({summary['before']['publicVersion']}).")
    summary["before"]["state"] = read_only_instance_state(auth)
    pe.compose("stop")
    pe.select_server_version("12.3")
    summary["after"] = {"serverSelection": pe.server_identity()}
    pe.compose("up")
    pe.wait_healthy()
    auth = api_auth()
    summary["after"]["publicVersion"] = pe.public_info().get("Version")
    require(summary["after"]["publicVersion"] == pe.server_public_version(),
            f"The upgraded instance is {summary['after']['publicVersion']!r}, "
            f"not {pe.server_public_version()}.")
    summary["after"]["pluginStatus"] = plugin_status(auth)
    require(str(summary["after"]["pluginStatus"]).lower() in {"active", "0"},
            "The plugin is not Active after the server upgrade.")
    # Read-only first: no PlaybackInfo and no playback before this comparison.
    summary["after"]["state"] = read_only_instance_state(auth)
    compat_record(evidence_dir, "upgrade-before.json", summary["before"])
    compat_record(evidence_dir, "upgrade-after.json", summary["after"])
    problems = upgrade_preservation_failures(summary["before"]["state"], summary["after"]["state"])
    require(not problems, "The upgrade did not preserve the 12.2 state: " + "; ".join(problems))
    summary["preserved"] = True
    return summary


def reset_owned_instance() -> dict:
    """Clear this run's own instance areas so the next stage starts from a fresh instance.

    Only this process's marker-verified workspace is touched; the run marker stays so the workspace
    is still recognised as this run's own data.
    """
    pe.workspace()
    pe.compose("stop")
    cleared = []
    for name in ("config", "cache", "strm", "media", "media-server"):
        target = pe.require_owned_path(pe.WORK / name, label=f"reset {name}")
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
            cleared.append(name)
        target.mkdir(parents=True, exist_ok=True)
    pe.workspace()
    return {"cleared": cleared, "marker": (pe.WORK / pe.RUN_MARKER).read_text(encoding="utf-8").strip()}


# --- Stage 3: six sources in two native libraries --------------------------------------------------------


# The small library uses the accepted 24-second synthetic fixtures (the same pinned-FFmpeg
# generation the playback entry already provides), so a real Web playback can advance the contract's
# five seconds. The 2-second package fixtures are too short for a playback window.
SMALL_LIBRARY_A = "baseline-mp4-a.mp4"
SMALL_LIBRARY_A_ALT = "baseline-mp4-a-copy.mp4"
SMALL_LIBRARY_B = "baseline-mkv-a.mkv"
SMALL_LIBRARY_B_ALT = "baseline-mkv-a-copy.mkv"


def small_library_plan() -> dict[str, dict]:
    return {
        "S1": {"library": CONTENT_LIBRARY, "media": SMALL_LIBRARY_A},
        "S2": {"library": CONTENT_LIBRARY, "media": SMALL_LIBRARY_A},
        "S3": {"library": CONTENT_LIBRARY, "media": SMALL_LIBRARY_A},
        "S4": {"library": CONTENT_LIBRARY, "media": SMALL_LIBRARY_A},
        "S5": {"library": CONTENT_LIBRARY, "media": SMALL_LIBRARY_B},
        "O1": {"library": OTHER_LIBRARY, "media": SMALL_LIBRARY_B},
    }


def small_library_path(name: str) -> Path:
    plan = small_library_plan()[name]
    directory = pe.WORK / ("strm" if plan["library"] == CONTENT_LIBRARY else "media")
    return directory / f"Compat {name}.strm"


def small_library_url(name: str) -> str:
    return "http://media:8080/" + small_library_plan()[name]["media"]


def write_small_library_strm(name: str, url: str, sha1: str | None, size: int | None) -> dict:
    path = small_library_path(name)
    lines = ["# strm-probe-version:1"]
    if sha1 is not None:
        lines.append(f"# strm-probe-sha1:{sha1}")
    if size is not None:
        lines.append(f"# strm-probe-size:{size}")
    lines.append(url)
    pe.write_owned_bytes(path, ("\n".join(lines) + "\n").encode("utf-8"), label=f"small library {name}")
    return {"name": name, "url": url, "sha256": compat_sha256(path.read_bytes())}


def wait_for_compat_item(auth: str | None, name: str, timeout: int = COMPAT_MAX_WAIT) -> dict:
    """Find one indexed item, authenticating for the request that is actually being made.

    A fresh native login revokes the previous token, so a long sequence of native reads must not
    reuse an ``auth`` value an intervening login already invalidated.
    """
    pe.request_json("POST", "/Library/Refresh", headers={"Authorization": api_auth()})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return item_by_name(api_auth(), name)
        except RuntimeError:
            time.sleep(1)
    raise RuntimeError(f"The instance did not index the compatibility item {name!r}.")


def wait_for_saved_video(auth: str, item_id: str, timeout: int = COMPAT_MAX_WAIT) -> list[str]:
    deadline = time.monotonic() + timeout
    saved: list[str] = []
    while time.monotonic() < deadline:
        status, _ = playback_info(auth, item_id)
        saved = saved_stream_types(auth, item_id)
        if status == 200 and "Video" in saved:
            return saved
        time.sleep(1)
    return saved


def library_names(auth: str | None = None) -> list[str]:
    status, folders = pe.request_json("GET", "/Library/VirtualFolders",
                                      headers={"Authorization": api_auth()})
    require(status == 200, "The native library listing failed.")
    return [str(folder.get("Name")) for folder in folders]


def library_ids(auth: str | None = None) -> dict[str, str]:
    status, folders = pe.request_json("GET", "/Library/VirtualFolders",
                                      headers={"Authorization": api_auth()})
    require(status == 200, "The native library listing failed.")
    by_path: dict[str, str] = {}
    for folder in folders:
        for info in folder.get("LibraryOptions", {}).get("PathInfos", []):
            by_path[str(info.get("Path", "")).rstrip("/")] = folder["ItemId"]
    content = by_path.get("/media/strm")
    other = by_path.get(pe.LOCAL_LIBRARY_PATH)
    require(content and other and content != other,
            f"The two required native libraries were not found: {by_path}")
    return {"content": content, "other": other}


def prepare_small_library(auth: str) -> dict:
    """Create the six real sources and let Jellyfin itself persist each main stream."""
    pe.ensure_media()
    # The accepted fixture generator writes the 24-second A/B media into this run's media directory.
    pe.workspace()
    if not (pe.WORK / "media" / SMALL_LIBRARY_B).is_file():
        playback.generate_fixtures()
    summary: dict[str, object] = {}
    for name in small_library_plan():
        path = small_library_path(name)
        if path.exists():
            path.unlink()
        url = small_library_url(name)
        sha1, size = pe.media_sha1(url.rsplit("/", 1)[-1])
        summary[name + ".strm"] = write_small_library_strm(name, url, sha1, size)
    # The second library is created by ``prepare_clean_instance`` when this stage asks for it; only a
    # stage that did not get it needs it added here.
    if OTHER_LIBRARY not in library_names(auth):
        pe.add_library_authenticated(auth, OTHER_LIBRARY, [pe.LOCAL_LIBRARY_PATH])
    require(plugin_action(api_auth(), False) == 204, "The plugin disable before the baseline failed.")
    restart()
    require(str(plugin_status(api_auth())).lower() not in {"active", "0"},
            "The plugin remained active during the small-library baseline.")
    for name in small_library_plan():
        item = wait_for_compat_item(None, f"Compat {name}")
        saved = wait_for_saved_video(api_auth(), item["Id"])
        require("Video" in saved, f"{name}: Jellyfin never persisted a Video main stream ({saved}).")
        summary[name + ".preparedStreams"] = saved
    require(plugin_action(api_auth(), True) == 204, "The plugin enable after the baseline failed.")
    restart()
    for name in small_library_plan():
        item = wait_for_compat_item(None, f"Compat {name}")
        status, response = playback_info(api_auth(), item["Id"])
        require(status == 200, f"{name}: the first-trust PlaybackInfo failed ({status}).")
        sources = [{"id": playback.normalize_source_id(source.get("Id")),
                    "path": playback.safe_path(source.get("Path")),
                    "pathHash": compat_sha256(str(source.get("Path") or "").encode())}
                   for source in response.get("MediaSources") or []]
        require(sources, f"{name}: the first-trust PlaybackInfo returned no media source.")
        row = fingerprint_row_by_item(item["Id"])
        require(row is not None, f"{name}: first trust did not persist a trusted fingerprint.")
        summary[name] = {"itemId": item["Id"], "sources": sources, "firstTrust": row}
    return summary


def small_library_configuration(changes: dict) -> dict:
    """Save one effective configuration change and return the read-back configuration.

    A fresh native login revokes the previous access token, so the read, the write and the
    verification each authenticate for their own request instead of reusing a token a previous
    native call already invalidated.
    """
    payload = {**plugin_configuration(), **changes}
    status, _ = pe.request_json("POST", f"/Plugins/{PLUGIN_ID}/Configuration",
                                headers={"Authorization": api_auth()}, body=payload)
    require(status == 204, f"The compatibility configuration save failed ({status}).")
    return plugin_configuration()


def stage_small_library_mixed() -> dict:
    """Mixed round: S1/S3/S4/S5 unchanged, S2 changes, O1 changes inside the unselected library."""
    libraries = library_ids()
    small_library_configuration({"Enabled": True, "PlaybackAutoCheck": True,
                                 "MaxConcurrentProbes": 2, "DetailedLog": True,
                                 "BatchAllLibraries": False,
                                 "BatchLibraryIds": libraries["content"]})
    before = {name: fingerprint_row_by_item(wait_for_compat_item(None, f"Compat {name}")["Id"])
              for name in small_library_plan()}
    require(all(row is not None for row in before.values()),
            f"Every compatibility source needs a trusted baseline before the mixed round: {before}")
    sha1, size = pe.media_sha1(SMALL_LIBRARY_A)
    s2 = write_small_library_strm("S2", "http://media:8080/" + SMALL_LIBRARY_A_ALT, sha1, size)
    o1_sha1, o1_size = pe.media_sha1(SMALL_LIBRARY_B)
    o1 = write_small_library_strm("O1", "http://media:8080/" + SMALL_LIBRARY_B_ALT, o1_sha1, o1_size)
    task = native_task_definition()
    summary: dict[str, object] = {"libraries": libraries, "nativeTask": task, "s2": s2, "o1": o1,
                                  "baseline": before}
    # The pre-measurement inputs are recorded before the round so a wrong scope or a STRM that did not
    # really change is visible in the evidence instead of only in a summary counter.
    summary["preRoundConfiguration"] = plugin_configuration()
    summary["preRoundStrm"] = {name: small_library_path(name).read_text(encoding="utf-8")
                               for name in ("S2", "O1")}
    run = compat_batch().run_task(pkg_api())
    summary["run"] = compat_batch().task_summary(run)
    line = compat_batch().latest_batch_summary(container())["line"]
    fields = compat_batch().summary_fields(line)
    compat_batch().assert_summary_equations(fields)
    summary["summary"] = line
    require((fields.get("candidates") or 0) >= 5,
            f"The mixed round did not consider the five in-scope sources: {line}")
    require(fields.get("need_probe") == 1,
            f"Exactly one in-scope source changed, so exactly one probe was needed: {line}")
    require(fields.get("actual_probe_calls") == 1,
            f"The mixed round did not perform exactly one real probe: {line}")
    require(fields.get("reliable_success") == 1,
            f"The changed source was not settled as one reliable success: {line}")
    s2_row = fingerprint_row_by_item(wait_for_compat_item(None, "Compat S2")["Id"])
    require(s2_row is not None and s2_row["url_hash"] == compat_sha256(s2["url"].encode()),
            f"S2's new address was not committed: {s2_row}")
    require(fingerprint_row_by_item(wait_for_compat_item(None, "Compat O1")["Id"]) == before["O1"],
            "An out-of-scope library source was committed by the selected-library round.")
    summary["s2Committed"] = s2_row
    summary["o1Unchanged"] = True
    repeat = compat_batch().run_task(pkg_api())
    repeat_line = compat_batch().latest_batch_summary(container())["line"]
    repeat_fields = compat_batch().summary_fields(repeat_line)
    compat_batch().assert_summary_equations(repeat_fields)
    require(repeat_fields.get("actual_probe_calls") == 0,
            f"The unchanged repeat round performed a probe: {repeat_line}")
    require(fingerprint_row_by_item(wait_for_compat_item(None, "Compat S2")["Id"]) == s2_row,
            "The unchanged repeat round changed the committed fingerprint.")
    summary["repeat"] = {"run": compat_batch().task_summary(repeat), "summary": repeat_line}
    return summary


def pkg_api():
    """The native API client of this run's own package instance."""
    import run_isolated_plugin_integration as native

    return native.JellyfinApi(credentials_path=pe.credentials_path())


def compat_batch():
    import run_isolated_batch_integration as batch
    return batch


def stage_small_library_native_rounds() -> dict:
    """Reuse the existing native stop and concurrency rounds on this instance.

    The batch/playback sharing round is *not* taken from the API-level scenario: its "playback" is a
    PlaybackInfo HTTP call, which cannot stand in for a real Web Play. The one required direction --
    a native task that really started, then a real Web Play on the same source -- is measured by
    ``stage_web_sharing`` instead, and the API-level fact is kept only as what it is.
    """
    import run_isolated_batch_integration as batch

    instance = batch.PackageInstance(pe)
    batch.configure_instance(instance)
    template = pe.WORK / "strm" / batch.PackageInstance.template_name
    if not template.is_file():
        sha1, size = pe.media_sha1(SMALL_LIBRARY_A)
        pe.write_strm(batch.PackageInstance.template_name[:-len(".strm")],
                      "http://media:8080/" + SMALL_LIBRARY_A, sha1, size)
    summary: dict[str, object] = {}
    summary["stop"] = batch.scenario_stop(pkg_api(), container(), pe.container_name("media"))
    api_sharing = batch.scenario_sharing(pkg_api(), container(), pe.container_name("media"))
    # Recorded as an API-level sharing observation only; it is never evidence of a Web playback.
    summary["apiSharing"] = {
        "kind": "PlaybackInfo HTTP call, not a Web Play",
        "batch_first": {key: (api_sharing.get("batch_first") or {}).get(key)
                        for key in ("slow_probe_requests", "actual_probe_calls", "reliable_success")},
        "playback_first": {key: (api_sharing.get("playback_first") or {}).get(key)
                           for key in ("slow_probe_requests", "actual_probe_calls", "reliable_success")},
    }
    summary["mixed"] = batch.scenario_mixed(pkg_api(), container(), pe.container_name("media"))
    summary["cleanupProblems"] = list(batch.CLEANUP_PROBLEMS)
    require(not batch.CLEANUP_PROBLEMS,
            f"The reused native rounds left cleanup problems: {batch.CLEANUP_PROBLEMS}")
    return summary


def stage_web_sharing(evidence_dir: Path | None) -> dict:
    """One direction only: the native task starts, then a real Web Play joins the same source.

    The source is a controlled delayed route, so the batch's probe is genuinely still running when
    the browser starts. Exactly one physical media request may be started for it, the changed
    address must be committed once, and the Web Play must really decode and advance at least five
    seconds. The independent changed source in the second round keeps the default concurrency of two
    exercised (peak reaches two, never three).
    """
    import run_isolated_batch_integration as batch

    instance = batch.PackageInstance(pe)
    batch.configure_instance(instance)
    media_container = pe.container_name("media")
    libraries = library_ids()
    small_library_configuration({"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2,
                                 "DetailedLog": True, "BatchAllLibraries": False,
                                 "BatchLibraryIds": libraries["content"]})
    api = pkg_api()
    item = wait_for_compat_item(None, "Compat S2")
    sha1, size = pe.media_sha1(SMALL_LIBRARY_A)
    plain_url = small_library_url("S2")
    before_row = fingerprint_row_by_item(item["Id"])
    require(before_row is not None, "The sharing source needs a trusted baseline before the round.")
    request_id = uuid.uuid4().hex
    target_url = batch.delay_url(plain_url, 12, request_id)
    changed = write_small_library_strm("S2", target_url, sha1, size)
    summary: dict[str, object] = {"itemId": item["Id"], "address": changed["url"],
                                  "before": before_row, "delayRequestId": request_id}
    before = batch.slow_request_counts(media_container)
    # Only this round's own plugin events are evidence: earlier small-library stages also probe,
    # so the start/join counters are the delta since this round began.
    before_events = playback.plugin_event_lines()
    task_id = batch.task_id_for(api)
    status, _ = api.request_response("/ScheduledTasks/Running/" + task_id, method="POST")
    require(status == 204, "Jellyfin did not accept the sharing round's native task start.")
    summary["taskStartStatus"] = status
    # The batch's own delayed probe must really be running before the browser starts.
    batch.wait_for_request_id_start(media_container, request_id, before.get(request_id, 0), timeout=90)
    started_at = time.time()
    summary["probeStartedBeforePlayback"] = True
    credentials = json.loads(pe.credentials_path().read_text(encoding="utf-8"))
    phase_dir = (evidence_dir or Path(tempfile.gettempdir())) / "web-sharing"
    result = run_browser_driver(PLAYBACK_DRIVER, {
        "baseUrl": credentials["base_url"], "username": credentials["username"],
        "password": credentials["password"],
        "strict": {"minimumSeconds": playback.MINIMUM_PROGRESS_SECONDS,
                   "screenshotDir": str(phase_dir / "screenshots")},
        "items": [{"name": "Compat S2", "id": item["Id"], "mediaType": "video"}],
    }, phase_dir, timeout=420)
    require("error" not in result, f"The same-source Web Play failed: {result.get('error')}")
    entry = (result.get("results") or [{}])[0]
    require(entry.get("advanced") is True, f"The same-source Web Play did not advance: {entry}")
    require(isinstance(entry.get("advancedSeconds"), (int, float))
            and entry["advancedSeconds"] >= playback.MINIMUM_PROGRESS_SECONDS,
            f"The same-source Web Play advanced {entry.get('advancedSeconds')} s.")
    final = batch.wait_for_idle(api, timeout=batch.MAX_WAIT_SECONDS)
    require(batch.task_state_name(final) in {"idle", "0"}, "The sharing native round did not settle.")
    after = batch.slow_request_counts(media_container)
    slow_hits = after.get(request_id, 0) - before.get(request_id, 0)
    summary["webPlay"] = {"advancedSeconds": entry.get("advancedSeconds"),
                          "screenshots": [entry.get("startScreenshot"), entry.get("progressScreenshot")],
                          "elapsedSeconds": round(time.time() - started_at, 1)}
    # The physical probe count comes from the plugin's own start/join lines: the probe route is
    # also read by the transcode job the Web Play starts, so a raw media-request counter would
    # count playback reads as extra probes.
    delta = playback.plugin_event_delta(before_events)
    started_events = [event for event in delta if "Native STRM probe started" in event]
    joined_events = [event for event in delta if "joined a running native probe" in event.lower()]
    summary["physicalProbes"] = {"started": len(started_events), "joined": len(joined_events),
                                 "slowRouteHits": slow_hits, "startedLines": started_events[-3:],
                                 "joinedLines": joined_events[-3:]}
    require(len(started_events) == 1,
            f"The shared source must have exactly one physical probe start, observed {started_events}.")
    require(joined_events,
            "The real Web Play never joined the running probe; no same-source sharing happened.")
    summary_line = batch.latest_batch_summary(container())["line"]
    fields = batch.summary_fields(summary_line)
    batch.assert_summary_equations(fields)
    summary["summary"] = summary_line
    require(fields.get("reliable_success") == 1,
            f"The shared source must settle as one reliable success: {summary_line}")
    # The Web Play revoked the token the batch used; re-authenticate before the read-only check.
    auth = api_auth()
    committed = fingerprint_row_by_item(item["Id"])
    require(committed is not None and committed["url_hash"] == compat_sha256(target_url.encode()),
            f"The shared probe did not commit the changed address: {committed}")
    summary["committed"] = committed
    summary["concurrency"] = stage_sharing_concurrency()
    return summary


def stage_sharing_concurrency() -> dict:
    """An independent changed source alongside a still-running probe keeps the peak at two.

    The two independently changed sources are started through the native task and their delayed
    probes are observed through the plugin's own start lines, so the peak is the plugin's real
    running-probe counter rather than an assumption.
    """
    import run_isolated_batch_integration as batch

    media_container = pe.container_name("media")
    api = pkg_api()
    sha1, size = pe.media_sha1(SMALL_LIBRARY_A)
    ids = {"S1": uuid.uuid4().hex, "S3": uuid.uuid4().hex}
    urls = {name: batch.delay_url(small_library_url(name), 12 if name == "S1" else 8, ids[name])
            for name in ids}
    for name, url in urls.items():
        write_small_library_strm(name, url, sha1, size)
    before = batch.slow_request_counts(media_container)
    started_epoch = time.time()
    task = batch.run_task(api, timeout=batch.MAX_WAIT_SECONDS)
    entries = batch.probe_start_entries_absolute(container(), started_epoch)
    peak = max((entry["running"] for entry in entries), default=0)
    after = batch.slow_request_counts(media_container)
    started = {name: after.get(ids[name], 0) - before.get(ids[name], 0) for name in ids}
    result = {"task": batch.task_summary(task), "peakRunningProbes": peak,
              "configuredConcurrency": 2, "started": started,
              "probeStartLines": entries[-6:]}
    require(peak >= 1, f"No plugin probe start was observed for the concurrency round: {result}")
    require(peak <= 2, f"The plugin exceeded its default concurrency of 2: peak {peak}")
    require(all(count == 1 for count in started.values()),
            f"Each independently changed source must be probed exactly once: {started}")
    return result


def stage_permissions(evidence_dir: Path | None) -> dict:
    """Real disabled-plugin delegation and the real static-stream (``allowMediaProbe=false``) window.

    Both are driven through the entries the fixed server really exposes: disabling the plugin through
    the native API and restarting, and a genuine ``/Videos/{id}/stream?static=true`` request. Neither is
    synthesised, and the native delegation is reported with its real probe count instead of a
    zero-probe claim.
    """
    summary: dict[str, object] = {}
    libraries = library_ids()
    small_library_configuration({"Enabled": True, "PlaybackAutoCheck": True, "MaxConcurrentProbes": 2,
                                 "DetailedLog": True, "BatchAllLibraries": False,
                                 "BatchLibraryIds": libraries["content"]})
    s1 = wait_for_compat_item(None, "Compat S1")
    baseline = fingerprint_row_by_item(s1["Id"])
    require(baseline is not None, "The disabled-delegation source needs a trusted baseline.")
    credentials = json.loads(pe.credentials_path().read_text(encoding="utf-8"))
    # 1) Whole plugin disabled: native playback must still work and the fingerprint must not change.
    require(plugin_action(api_auth(), False) == 204, "The plugin disable failed.")
    restart()
    require(str(plugin_status(api_auth())).lower() not in {"active", "0"},
            "The plugin remained active after the disable.")
    before_events = playback.plugin_event_lines()
    before_probes = playback.probe_count(small_library_url("S1"))
    phase_dir = (evidence_dir or Path(tempfile.gettempdir())) / "disabled-native-play"
    result = run_browser_driver(PLAYBACK_DRIVER, {
        "baseUrl": credentials["base_url"], "username": credentials["username"],
        "password": credentials["password"],
        "strict": {"minimumSeconds": playback.MINIMUM_PROGRESS_SECONDS,
                   "screenshotDir": str(phase_dir / "screenshots")},
        "items": [{"name": "Compat S1", "id": s1["Id"], "mediaType": "video"}],
    }, phase_dir, timeout=420)
    require("error" not in result, f"The disabled-plugin native playback failed: {result.get('error')}")
    entry = (result.get("results") or [{}])[0]
    require(entry.get("advanced") is True, f"The disabled-plugin playback did not advance: {entry}")
    time.sleep(2)
    after_probes = playback.probe_count(small_library_url("S1"))
    events = playback.plugin_event_delta(before_events)
    summary["disabledDelegation"] = {
        "advancedSeconds": entry.get("advancedSeconds"),
        "screenshots": [entry.get("startScreenshot"), entry.get("progressScreenshot")],
        "nativeProbeDelta": after_probes - before_probes,
        "pluginEvents": events,
        "fingerprintUnchanged": fingerprint_row_by_item(s1["Id"]) == baseline,
        "note": "the native probe count is the real value; zero is not required for this delegation",
    }
    require(not events, f"The disabled plugin still emitted events: {events}")
    require(fingerprint_row_by_item(s1["Id"]) == baseline,
            "Native playback with the plugin disabled changed the fingerprint.")
    require(plugin_action(api_auth(), True) == 204, "The plugin enable after the delegation failed.")
    restart()
    summary["restoredPluginStatus"] = plugin_status(api_auth())
    require(str(summary["restoredPluginStatus"]).lower() in {"active", "0"},
            "The plugin is not Active again after the delegation restore.")
    # 2) The real static-stream window: the server itself passes allowMediaProbe=false, so the plugin
    #    must not probe and must not commit a changed fingerprint; a later Web Play then does.
    sha1, size = pe.media_sha1(SMALL_LIBRARY_A)
    changed = write_small_library_strm("S3", "http://media:8080/" + SMALL_LIBRARY_A_ALT, sha1, size)
    s3 = wait_for_compat_item(None, "Compat S3")
    s3_baseline = fingerprint_row_by_item(s3["Id"])
    require(s3_baseline is not None, "The static-window source needs a trusted baseline.")
    before_probes = playback.probe_count(changed["url"])
    static = playback.native_static_stream_read(api_auth(), s3["Id"])
    time.sleep(2)
    after_probes = playback.probe_count(changed["url"])
    summary["staticWindow"] = {
        "httpStatus": static["status"], "bytesRead": static["headLength"],
        "contentType": static["contentType"],
        "nativeProbeDelta": after_probes - before_probes,
        "fingerprintChanged": fingerprint_row_by_item(s3["Id"]) != s3_baseline,
        "address": changed["url"],
    }
    require(static["status"] == 200 and static["headLength"] > 0,
            f"The real static stream request failed: {static}")
    require(after_probes - before_probes == 0,
            f"The static (allowMediaProbe=false) window still probed ({after_probes - before_probes}).")
    require(fingerprint_row_by_item(s3["Id"]) == s3_baseline,
            "The static (allowMediaProbe=false) window committed a changed fingerprint.")
    phase_dir = (evidence_dir or Path(tempfile.gettempdir())) / "static-window-play"
    result = run_browser_driver(PLAYBACK_DRIVER, {
        "baseUrl": credentials["base_url"], "username": credentials["username"],
        "password": credentials["password"],
        "strict": {"minimumSeconds": playback.MINIMUM_PROGRESS_SECONDS,
                   "screenshotDir": str(phase_dir / "screenshots")},
        "items": [{"name": "Compat S3", "id": s3["Id"], "mediaType": "video"}],
    }, phase_dir, timeout=420)
    require("error" not in result, f"The playback after the static window failed: {result.get('error')}")
    entry = (result.get("results") or [{}])[0]
    require(entry.get("advanced") is True, "The playback after the static window did not advance.")
    time.sleep(2)
    committed = fingerprint_row_by_item(s3["Id"])
    summary["afterStaticWebPlay"] = {
        "advancedSeconds": entry.get("advancedSeconds"),
        "screenshots": [entry.get("startScreenshot"), entry.get("progressScreenshot")],
        "committedUrlHash": (committed or {}).get("url_hash"),
        "expectedUrlHash": compat_sha256(changed["url"].encode()),
        "nativeProbeDelta": playback.probe_count(changed["url"]) - after_probes,
    }
    require((committed or {}).get("url_hash") == compat_sha256(changed["url"].encode()),
            f"The allowed Web Play did not commit the changed address: {committed}")
    return summary


def stage_multi_source(evidence_dir: Path | None) -> dict:
    """Merge S4/S5 into one visible project, select B explicitly, play, freeze, restart, read, play."""
    s4 = wait_for_compat_item(None, "Compat S4")
    s5 = wait_for_compat_item(None, "Compat S5")
    status, _ = pe.request_json("POST", "/Videos/MergeVersions?" + urllib.parse.urlencode(
        {"ids": ",".join([s4["Id"], s5["Id"]])}), headers={"Authorization": api_auth()})
    require(status == 204, f"Jellyfin refused the native version merge ({status}).")
    merged = wait_for_compat_item(None, "Compat S4")
    status, payload = pe.request_json(
        "GET", f"/Items/{merged['Id']}?Fields=MediaSources,MediaStreams,Path",
        headers={"Authorization": api_auth()})
    require(status == 200, "The merged project's read-only query failed.")
    sources = payload.get("MediaSources") or []
    require(len(sources) == 2, f"The merged project must expose two native sources, found {len(sources)}.")
    by_path = {playback.safe_path(source.get("Path")): playback.normalize_source_id(source.get("Id"))
               for source in sources}
    b_path = small_library_url("S5")
    require(b_path in by_path, f"The B version is not addressable by its own path: {sorted(by_path)}")
    selected = by_path[b_path]
    credentials = json.loads(pe.credentials_path().read_text(encoding="utf-8"))
    summary: dict[str, object] = {"mergedItemId": merged["Id"], "sourceIds": by_path,
                                  "selected": selected, "bPath": b_path}
    before_probes = playback.probe_count(b_path)
    before_events = playback.plugin_event_lines()
    phase_dir = (evidence_dir or Path(tempfile.gettempdir())) / "multi-source-play"
    result = run_browser_driver(PLAYBACK_DRIVER, {
        "baseUrl": credentials["base_url"],
        "username": credentials["username"],
        "password": credentials["password"],
        "strict": {"minimumSeconds": playback.MINIMUM_PROGRESS_SECONDS,
                   "screenshotDir": str(phase_dir / "screenshots")},
        "items": [{"name": "Compat S4", "id": merged["Id"], "mediaType": "video",
                   "selectedSourceId": selected, "selectedSourceIdProgressMarker": "Compat S5"}],
    }, phase_dir, timeout=420)
    require("error" not in result, f"The explicit multi-source playback failed: {result.get('error')}")
    entry = (result.get("results") or [{}])[0]
    require(entry.get("advanced") is True, f"The selected-version playback did not advance: {entry}")
    selection = entry.get("sourceSelection") or {}
    require(selection.get("selected")
            and playback.normalize_source_id(selection["selected"]) == selected,
            f"The client did not keep the explicitly selected version: {selection}")
    require(selection.get("alternateVersionLoaded") is True,
            f"The client never loaded the explicitly selected version: {selection}")
    time.sleep(2)
    after_probes = playback.probe_count(b_path)
    summary["playback"] = {"advancedSeconds": entry.get("advancedSeconds"),
                           "sourceSelection": selection,
                           "screenshots": [entry.get("startScreenshot"), entry.get("progressScreenshot")],
                           "pluginEvents": playback.plugin_event_delta(before_events),
                           "probeDelta": after_probes - before_probes}
    require(after_probes - before_probes == 0,
            f"The already trusted selected version was probed again ({after_probes - before_probes}).")
    row = {"id": "COMPAT.S4S5", "fmt": "MKV", "name": "Compat S4", "item": merged,
           "strm_name": "Compat S4", "media_type": "video", "media": SMALL_LIBRARY_B, "url": b_path,
           "old": {"sha1": None, "size": None}, "apply": {}, "apply_kind": "none",
           "expect_probes": 0, "fp_kind": "same", "fp_tokens": (None, None), "fp_url": b_path,
           "journey": "normal", "trust": False, "watch_media": SMALL_LIBRARY_B,
           "sourceKey": selected, "path": str(small_library_path("S4"))}
    frozen = playback.freeze_state(api_auth(), row)
    summary["frozen"] = {"fingerprint": frozen["fingerprint"],
                         "sources": [{"id": source["id"], "path": source["path"],
                                      "pathHash": source["pathHash"],
                                      "streamTypes": [stream["Type"] for stream in source["streams"]]}
                                     for source in frozen["nativeSources"]["sources"]],
                         "probeCount": frozen["probe_count"]}
    restart()
    observed = playback.read_only_state(api_auth(), row)
    problems = playback.restart_readback_failures(frozen, observed)
    require(not problems, "The multi-source restart read-back failed: " + "; ".join(problems))
    summary["readOnlyAfterRestart"] = {"fingerprint": observed["fingerprint"],
                                       "probeCount": observed["probe_count"]}
    after_dir = (evidence_dir or Path(tempfile.gettempdir())) / "multi-source-play-restart"
    result = run_browser_driver(PLAYBACK_DRIVER, {
        "baseUrl": credentials["base_url"],
        "username": credentials["username"],
        "password": credentials["password"],
        "strict": {"minimumSeconds": playback.MINIMUM_PROGRESS_SECONDS,
                   "screenshotDir": str(after_dir / "screenshots")},
        "items": [{"name": "Compat S4", "id": merged["Id"], "mediaType": "video",
                   "selectedSourceId": selected, "selectedSourceIdProgressMarker": "Compat S5"}],
    }, after_dir, timeout=420)
    require("error" not in result, f"The post-restart multi-source playback failed: {result.get('error')}")
    entry = (result.get("results") or [{}])[0]
    require(entry.get("advanced") is True, "The post-restart selected-version playback did not advance.")
    time.sleep(2)
    summary["afterRestartPlayback"] = {
        "advancedSeconds": entry.get("advancedSeconds"),
        "sourceSelection": entry.get("sourceSelection"),
        "screenshots": [entry.get("startScreenshot"), entry.get("progressScreenshot")],
        "probeDelta": playback.probe_count(b_path) - observed["probe_count"]}
    require(summary["afterRestartPlayback"]["probeDelta"] == 0,
            "The post-restart playback probed an already trusted source again.")
    return summary


def stage_small_library(package: Path, evidence_dir: Path | None, summary: dict) -> dict:
    # The stage starts from this run's own empty workspace: a previous stage's STRM/media files would
    # otherwise be indexed as extra candidates and change the measured candidate set.
    summary["reset"] = reset_owned_instance()
    # A freshly bootstrapped instance with both native libraries, so no other stage's configuration,
    # credentials, libraries or items can leak into this measurement.
    summary["instance"] = pe.prepare_clean_instance(
        [(CONTENT_LIBRARY, ["/media/strm"]), (OTHER_LIBRARY, [pe.LOCAL_LIBRARY_PATH])])
    summary["serverIdentity"] = pe.verify_server_image()
    summary["deployment"] = pe.deploy_archive(package)
    restart()
    summary["publicVersion"] = pe.public_info().get("Version")
    require(summary["publicVersion"] == pe.server_public_version(),
            f"The small-library instance is {summary['publicVersion']!r}.")
    summary["pluginStatus"] = plugin_status(api_auth())
    require(str(summary["pluginStatus"]).lower() in {"active", "0"},
            "The plugin is not Active on the small-library instance.")
    summary["preparation"] = prepare_small_library(api_auth())
    summary["fixtures"] = {"a": {"name": SMALL_LIBRARY_A, "sha1": pe.media_sha1(SMALL_LIBRARY_A)[0],
                                 "size": pe.media_sha1(SMALL_LIBRARY_A)[1]},
                           "b": {"name": SMALL_LIBRARY_B, "sha1": pe.media_sha1(SMALL_LIBRARY_B)[0],
                                 "size": pe.media_sha1(SMALL_LIBRARY_B)[1]}}
    summary["mixed"] = stage_small_library_mixed()
    summary["nativeRounds"] = stage_small_library_native_rounds()
    summary["webSharing"] = stage_web_sharing(evidence_dir)
    summary["permissions"] = stage_permissions(evidence_dir)
    summary["multiSource"] = stage_multi_source(evidence_dir)
    summary["unifiedRestart"] = small_library_unified_restart(summary["multiSource"], evidence_dir)
    small_library_configuration({"Enabled": True, "PlaybackAutoCheck": True,
                                 "MaxConcurrentProbes": 2, "DetailedLog": False,
                                 "BatchAllLibraries": True, "BatchLibraryIds": ""})
    summary["restoredConfiguration"] = plugin_configuration()
    require(summary["restoredConfiguration"].get("BatchAllLibraries") is True,
            "The small-library stage did not restore the all-library default scope.")
    summary["fingerprintStore"] = fingerprint_store_report()
    return summary


def small_library_unified_restart(multi_source: dict, evidence_dir: Path | None) -> dict:
    """Freeze every accepted small-library item/source, restart once, read all, then play.

    The multi-source stage already proves the selected version; this restart covers the whole stage:
    all six prepared sources (including both sources of the merged project) and the configuration are
    frozen, the server restarts once, and every address, complete primary stream set and five-field
    fingerprint is compared read-only before any PlaybackInfo or playback. Only then does the
    explicitly selected version play again, through the real Web client, without a new probe.
    """
    api = pkg_api()
    prepared = {name: wait_for_compat_item(None, f"Compat {name}")
                for name in ("S1", "S2", "S3", "S4", "O1")}
    merged = {"Id": multi_source["mergedItemId"]}
    selected = multi_source["selected"]
    schedule = [("S1", prepared["S1"]), ("S2", prepared["S2"]), ("S3", prepared["S3"]),
                ("S4", merged), ("O1", prepared["O1"])]

    def snapshot() -> dict:
        state: dict[str, object] = {}
        auth = api_auth()
        state["configuration"] = plugin_configuration()
        items: dict[str, object] = {}
        for name, item in schedule:
            auth = api_auth()
            items[name] = {
                "itemId": item["Id"],
                "sources": [{"id": playback.normalize_source_id(source.get("Id")),
                             "pathHash": compat_sha256(str(source.get("Path") or "").encode()),
                             "path": playback.safe_path(source.get("Path"))}
                            for source in (read_sources(item["Id"]) or [])],
                "streams": native_stream_snapshot(item["Id"]),
            }
        state["items"] = items
        state["fingerprints"] = {name: fingerprint_rows(item["Id"]) for name, item in schedule}
        return state

    frozen = snapshot()
    require(len((frozen["items"].get("S4") or {}).get("sources") or []) == 2,
            "The merged project must expose both native sources when frozen.")
    require(all(rows for rows in frozen["fingerprints"].values()),
            f"Every accepted source needs a trusted fingerprint before the unified restart: "
            f"{ {name: len(rows) for name, rows in frozen['fingerprints'].items()} }")
    restart()
    observed = snapshot()
    problems: list[str] = []
    if observed["configuration"] != frozen["configuration"]:
        problems.append("the plugin configuration changed across the restart")
    for name, _item in schedule:
        before = frozen["items"][name]
        after = observed["items"][name]
        if after["itemId"] != before["itemId"]:
            problems.append(f"{name}: the native item id changed across the restart")
        if after["sources"] != before["sources"]:
            problems.append(f"{name}: the saved native address changed across the restart")
        if after["streams"] != before["streams"]:
            problems.append(f"{name}: the saved native streams changed across the restart")
        if observed["fingerprints"][name] != frozen["fingerprints"][name]:
            problems.append(f"{name}: a trusted fingerprint changed across the restart")
    require(not problems, "The small-library unified restart read-back failed: " + "; ".join(problems))
    # The CONFIGURATION is read before any playback; only the explicitly selected version is played
    # again, and it must not probe an already trusted source.
    before_probes = playback.probe_count(multi_source["bPath"])
    credentials = json.loads(pe.credentials_path().read_text(encoding="utf-8"))
    after_dir = (evidence_dir or Path(tempfile.gettempdir())) / "multi-source-play-unified-restart"
    result = run_browser_driver(PLAYBACK_DRIVER, {
        "baseUrl": credentials["base_url"], "username": credentials["username"],
        "password": credentials["password"],
        "strict": {"minimumSeconds": playback.MINIMUM_PROGRESS_SECONDS,
                   "screenshotDir": str(after_dir / "screenshots")},
        "items": [{"name": "Compat S4", "id": merged["Id"], "mediaType": "video",
                   "selectedSourceId": selected, "selectedSourceIdProgressMarker": "Compat S5"}],
    }, after_dir, timeout=420)
    require("error" not in result, f"The unified-restart multi-source playback failed: {result.get('error')}")
    entry = (result.get("results") or [{}])[0]
    require(entry.get("advanced") is True, "The unified-restart selected-version playback did not advance.")
    time.sleep(2)
    delta = playback.probe_count(multi_source["bPath"]) - before_probes
    require(delta == 0, f"The unified-restart playback probed an already trusted source ({delta}).")
    return {"frozen": {"items": frozen["items"], "fingerprints": frozen["fingerprints"],
                       "configuration": frozen["configuration"]},
            "readOnlyAfterRestart": {"items": observed["items"],
                                     "fingerprints": observed["fingerprints"],
                                     "configuration": observed["configuration"]},
            "readOnlyBeforeAnyPlayback": True,
            "playback": {"advancedSeconds": entry.get("advancedSeconds"),
                         "sourceSelection": entry.get("sourceSelection"),
                         "screenshots": [entry.get("startScreenshot"), entry.get("progressScreenshot")],
                         "probeDelta": delta}}


def read_sources(item_id: str) -> list[dict]:
    status, payload = pe.request_json("GET", f"/Items/{item_id}?Fields=MediaSources,MediaStreams,Path",
                                      headers={"Authorization": api_auth()})
    require(status == 200, "The read-only native media-source query failed.")
    return payload.get("MediaSources") or []


def native_stream_snapshot(item_id: str) -> list[dict]:
    """Every saved stream of every source, compared in full rather than by stream type set."""
    snapshot = []
    for source in read_sources(item_id):
        snapshot.append({"id": playback.normalize_source_id(source.get("Id")),
                         "streams": sorted(json.dumps(stream, sort_keys=True)
                                           for stream in source.get("MediaStreams") or [])})
    return sorted(snapshot, key=lambda entry: str(entry["id"]))


def fingerprint_rows(item_id: str) -> list[dict]:
    database = fingerprint_store_path()
    if not database.is_file():
        return []
    wanted = uuid.UUID(item_id).hex
    return sorted((row for row in read_fingerprint_rows_copy(database) if row["item_id"] == wanted),
                  key=lambda row: row["source_key"])


def scenario_compatibility(package: Path, upgrade_source: Path | None,
                           evidence_dir: Path | None) -> dict:
    """The Slice 6 compatibility sequence on one freshly owned workspace.

    Each stage's own record is kept in the shared summary as soon as it exists, so a failure in a
    later stage never discards the earlier stages' real observations.
    """
    summary: dict[str, object] = {"serverIdentity": pe.server_identity()}
    summary["webInstall"] = run_compat_stage("webInstall", summary, evidence_dir,
                                            lambda stage: stage_web_install(package, evidence_dir, stage))
    # The upgrade stage adopts a prepared 12.2 workspace and must therefore start from a clean,
    # run-owned workspace rather than the workspace the web-install stage just used.
    summary["upgrade"] = (run_compat_stage("upgrade", summary, evidence_dir,
                                           lambda stage: stage_upgrade(package, upgrade_source, evidence_dir, stage))
                          if upgrade_source else
                          {"status": "SKIPPED", "reason": "no --upgrade-source-workspace was provided"})
    summary["smallLibrary"] = run_compat_stage("smallLibrary", summary, evidence_dir,
                                               lambda stage: stage_small_library(package, evidence_dir, stage))
    return summary


def archive_compat_runtime_evidence(evidence_dir: Path | None) -> dict:
    """Archive this run's original native logs and container states next to the other evidence.

    The compatibility stages reuse existing helpers instead of adding an evidence system, so the
    original server log (which carries the real ffprobe starts) and the final container states are
    copied out of the instance before any cleanup removes the workspace.
    """
    if evidence_dir is None:
        return {}
    archived: dict[str, object] = {}
    log_dir = pe.WORK / "config" / "log"
    written: list[str] = []
    if log_dir.is_dir():
        for path in sorted(log_dir.glob("log_*.log")):
            target = evidence_dir / "server-logs" / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            written.append(str(target))
    archived["serverLogs"] = written
    lines = [line for path in log_dir.glob("log_*.log")
             for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
             if 'Starting "/usr/lib/jellyfin-ffmpeg/ffprobe"' in line]
    target = evidence_dir / "server-ffprobe-lines.log"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    archived["serverProbeLines"] = {"path": str(target), "count": len(lines)}
    try:
        archived["mediaLogs"] = playback.archive_media_logs()
    except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError, RuntimeError) as error:
        archived["mediaLogsError"] = f"{type(error).__name__}: {error}"
    return archived


def render_compat_index(summary: dict, evidence_dir: Path) -> str:
    lines = ["# Jellyfin 12.3 compatibility evidence index", "",
             f"- Status: **{summary.get('status')}**",
             f"- Package: `{summary.get('package')}`",
             f"- Package SHA-256: `{(summary.get('package_identity') or {}).get('archiveSha256')}`",
             f"- Server: {json.dumps(summary.get('serverIdentity') or {}, sort_keys=True)}",
             f"- Workspace: `{summary.get('workspace')}`",
             f"- Elapsed seconds: {summary.get('elapsedSeconds')}", ""]
    if summary.get("error"):
        lines += ["## Failure", "", f"```\n{summary['error']}\n```", ""]
    for stage in ("webInstall", "upgrade", "smallLibrary"):
        entry = summary.get(stage) or {}
        lines.append(f"- {stage}: **{entry.get('status')}**"
                     + (f" — `{entry.get('error')}`" if entry.get("error") else ""))
    lines.append("")
    web = summary.get("webInstall") or {}
    if web:
        lines += ["## Native web install", "",
                  f"- repository POST / install POST: "
                  f"{(web.get('nativeInstall') or {}).get('repository', {}).get('repositoryPostStatus')} / "
                  f"{(web.get('nativeInstall') or {}).get('install', {}).get('installPostStatus')}",
                  f"- public version after restart: {web.get('publicVersion')}",
                  f"- plugin status: {web.get('pluginStatus')}",
                  f"- payload matches archive: {json.dumps(web.get('payloadMatchesArchive'))}",
                  f"- fingerprint store: {json.dumps(web.get('fingerprintStore'))}",
                  f"- first trust: {json.dumps(web.get('firstTrust'))[:400]}", ""]
    upgrade = summary.get("upgrade") or {}
    if upgrade:
        lines += ["## 12.2 copy upgraded to 12.3", "",
                  f"- source: `{(upgrade.get('source') or {}).get('source')}`",
                  f"- before/after public version: "
                  f"{(upgrade.get('before') or {}).get('publicVersion')} → "
                  f"{(upgrade.get('after') or {}).get('publicVersion')}",
                  f"- preserved (read-only, before any PlaybackInfo): {upgrade.get('preserved')}",
                  f"- source unchanged after copy: {upgrade.get('sourceUnchangedAfterCopy')}",
                  f"- payload matches archive: {json.dumps(upgrade.get('payloadMatchesArchive'))}", ""]
    small = summary.get("smallLibrary") or {}
    if small:
        mixed = small.get("mixed") or {}
        rounds = small.get("nativeRounds") or {}
        perms = small.get("permissions") or {}
        multi = small.get("multiSource") or {}
        lines += ["## Six sources in two native libraries", "",
                  f"- fixtures: {json.dumps(small.get('fixtures'))}",
                  f"- mixed round: `{mixed.get('summary')}`",
                  f"- unchanged repeat: `{(mixed.get('repeat') or {}).get('summary')}`",
                  f"- stopped round completion: `{(rounds.get('stop') or {}).get('current_round_completion')}`",
                  f"- sharing probes (batch_first / playback_first): "
                  f"{(rounds.get('sharing') or {}).get('batch_first', {}).get('slow_probe_requests')} / "
                  f"{(rounds.get('sharing') or {}).get('playback_first', {}).get('slow_probe_requests')}",
                  f"- concurrency peak / limit: "
                  f"{(rounds.get('mixed') or {}).get('peak_running_probes')} / 2",
                  f"- disabled delegation: {json.dumps(perms.get('disabledDelegation'), sort_keys=True)[:400]}",
                  f"- static (allowMediaProbe=false) window: {json.dumps(perms.get('staticWindow'), sort_keys=True)}",
                  f"- allowed Web Play after the static window: "
                  f"{json.dumps(perms.get('afterStaticWebPlay'), sort_keys=True)[:300]}",
                  f"- explicit multi-source selection: "
                  f"{json.dumps((multi.get('playback') or {}).get('sourceSelection'), sort_keys=True)[:400]}",
                  f"- multi-source restart read-back frozen/observed fingerprints equal: "
                  f"{(multi.get('frozen') or {}).get('fingerprint') == (multi.get('readOnlyAfterRestart') or {}).get('fingerprint')}",
                  f"- post-restart playback probe delta: "
                  f"{(multi.get('afterRestartPlayback') or {}).get('probeDelta')}", ""]
    lines += ["## Evidence files", "",
              "- `stage-webInstall.json`, `stage-upgrade.json`, `stage-smallLibrary.json`: per-stage records.",
              "- `upgrade-before.json`, `upgrade-after.json`: the read-only pre/post upgrade state.",
              "- `web-install/`, `config-page/`, `multi-source-play*/`, `disabled-native-play/`, "
              "`static-window-play/`: screenshots and driver stdout/stderr per real Web operation.",
              "- `server-logs/`, `server-ffprobe-lines.log`: original server log and its ffprobe starts.",
              ""]
    return "\n".join(lines)


def run_compat_stage(name: str, summary: dict, evidence_dir: Path | None, operation) -> dict:
    """Run one compatibility stage and record what it really reached before re-raising.

    The stage functions are handed this same dictionary through ``summary[name]`` so a stage that
    fails halfway still leaves every completed sub-stage in the recorded evidence. Each stage
    archives its own original server log and container states before the next stage's reset removes
    the workspace areas those logs live in.
    """
    stage: dict[str, object] = {}
    stage["startedAt"] = iso_now()
    stage["startedMonotonic"] = started = time.monotonic()
    summary[name] = stage
    try:
        stage.update(operation(stage))
    except (RuntimeError, OSError, ValueError, KeyError, json.JSONDecodeError,
            urllib.error.URLError, subprocess.SubprocessError, pe.PackageEnvironmentError) as error:
        stage["status"] = "FAIL"
        stage["error"] = f"{type(error).__name__}: {error}"
        archive_stage_runtime(name, stage, evidence_dir)
        compat_record(evidence_dir, f"stage-{name}-failure.json", stage)
        raise
    stage["status"] = "PASS"
    archive_stage_runtime(name, stage, evidence_dir)
    compat_record(evidence_dir, f"stage-{name}.json", stage)
    return stage


def archive_stage_runtime(name: str, stage: dict, evidence_dir: Path | None) -> None:
    """Copy this stage's own original server log and container states out of the workspace.

    The compatibility stages clear the instance areas (``config`` carries Jellyfin's log) between
    stages, so a single archive at the end of the run cannot preserve an earlier stage's original
    log. Each stage therefore copies its own log before it returns, and a failed stage keeps the
    log that explains the failure.
    """
    stage["finishedAt"] = iso_now()
    if "startedMonotonic" in stage:
        stage["elapsedSeconds"] = round(time.monotonic() - float(stage.pop("startedMonotonic")), 1)
    if evidence_dir is None:
        return
    log_dir = pe.WORK / "config" / "log"
    copied: list[dict] = []
    lines: list[str] = []
    if log_dir.is_dir():
        for path in sorted(log_dir.glob("log_*.log")):
            target = evidence_dir / f"server-logs-{name}" / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied.append({"file": path.name, "bytes": target.stat().st_size,
                           "sha256": compat_sha256(target.read_bytes()), "path": str(target)})
            lines.extend(line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
                         if 'Starting "/usr/lib/jellyfin-ffmpeg/ffprobe"' in line)
    probe_log = evidence_dir / f"server-ffprobe-lines-{name}.log"
    probe_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    stage["runtimeArchive"] = {"serverLogs": copied, "serverLogFiles": len(copied),
                               "ffprobeLineCount": len(lines), "ffprobeLog": str(probe_log)}
    try:
        stage["containerStates"] = pe.inspect_owned_container_states()
    except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError) as error:
        stage["containerStatesError"] = f"{type(error).__name__}: {error}"


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run_invocation(args) -> dict:
    """The exact command this run was started with, kept next to its results."""
    return {"argv": [str(part) for part in sys.argv],
            "literalCommand": " ".join(_shell_quote(str(part)) for part in sys.argv),
            "arguments": {key: str(value) for key, value in vars(args).items()},
            "pythonVersion": sys.version.split()[0], "pythonExecutable": sys.executable,
            "workingDirectory": str(Path.cwd()), "startedAt": iso_now()}


def _shell_quote(value: str) -> str:
    return value if re.fullmatch(r"[A-Za-z0-9_./:=,@+-]+", value) else "'" + value.replace("'", "'\\''") + "'"


def tool_input_identity() -> dict:
    """Content identity of the test tooling and the two version inputs actually used.

    The inspected release ZIP embeds its own build inputs from before this Task; this record only
    identifies the test tooling that produced the compatibility evidence, and it never stands in
    for the archive's original build inputs.
    """
    scripts = ["run_isolated_package_integration.py", "run_isolated_playback_integration.py",
               "run_isolated_batch_integration.py", "package_environment.py", "package_plugin.py",
               "configuration_page_driver.mjs", "package_playback_driver.mjs",
               "isolated_media_server.py"]
    files = {name: compat_sha256((ROOT / "scripts" / name).read_bytes()) for name in scripts}
    inputs = {name: {"path": path, "sha256": compat_sha256((ROOT / path).read_bytes())}
              for name, path in (("serverSpec", pe.SERVER_VERSIONS[pe.SERVER_VERSION]["spec"]),
                                 ("imageLock", pe.LOCK_RELATIVE),
                                 ("mediaLock", "dev/images.lock.json"))}
    return {"scripts": files, "versionInputs": inputs, "serverVersion": pe.SERVER_VERSION}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--baseline-revision")
    parser.add_argument("--scenario", default="all",
                        choices=["all", "clean", "upgrade", "recovery", "invalid", "compatibility"])
    parser.add_argument("--server-version", default="12.2", choices=sorted(pe.SERVER_VERSIONS),
                        help="Select one server version and its own committed spec/lock (default: 12.2).")
    parser.add_argument("--upgrade-source-workspace", type=Path,
                        help="Existing prepared (12.2) package-environment run workspace to copy read-only "
                             "into this run and upgrade. Never reused or modified in place.")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--workspace", type=Path,
                        help="Fresh run-owned workspace under artifacts/package-env (default: auto-created).")
    parser.add_argument("--keep-workspace", action="store_true",
                        help="Leave this run's workspace and instance in place for inspection (default: clean up).")
    args = parser.parse_args()

    package = args.package.resolve()
    evidence_dir = args.evidence_dir.resolve() if args.evidence_dir else None
    summary: dict[str, object] = {"scenario": args.scenario, "package": str(package)}
    exit_code = 1
    before_state = None
    workspace = None
    started = time.time()
    summary["invocation"] = run_invocation(args)
    try:
        # Validate the package before claiming a workspace, so a missing or invalid archive has no
        # filesystem side effect at all (and never touches an existing workspace).
        verification = package_plugin.verify_archive(package)
        summary["package_identity"] = {
            "archiveSha256": verification["archiveSha256"],
            "version": verification["version"],
            "guid": verification["guid"],
            "targetAbi": verification["targetAbi"],
            "runtime": verification["runtime"],
            "entries": verification["entries"],
        }
        summary["serverIdentity"] = pe.select_server_version(args.server_version)
        if args.scenario == "compatibility":
            require(args.server_version == "12.3",
                    "The compatibility scenario only runs the fixed 12.3 target; 12.2 keeps its own scenarios.")
            require(evidence_dir is not None,
                    "The compatibility scenario requires --evidence-dir for its staged evidence.")
            # A missing prepared 12.2 source cannot be downgraded to SKIPPED: the non-empty upgrade
            # preservation is a Required Outcome, so an incomplete run is refused before measuring.
            require(args.upgrade_source_workspace is not None,
                    "The compatibility scenario requires --upgrade-source-workspace: the non-empty 12.2 "
                    "upgrade preservation is a required result and is never reported as skipped.")
            # Capture compatibility-only provenance here; legacy scenarios keep their existing
            # workspace and environment setup order.
            summary["toolInputs"] = tool_input_identity()
        workspace = pe.select_workspace(args.workspace)
        summary["workspace"] = str(workspace)
        before_state = pe.capture_instance_state()
        if args.scenario == "compatibility":
            summary.update(scenario_compatibility(
                package, args.upgrade_source_workspace.resolve() if args.upgrade_source_workspace else None,
                evidence_dir))
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
        summary["status"] = "PASS"
        exit_code = 0
    except (RuntimeError, OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError,
            zipfile.BadZipFile, package_plugin.PackageError, pe.PackageEnvironmentError) as error:
        summary["status"] = "FAIL"
        summary["error"] = f"{type(error).__name__}: {error}"
        exit_code = 1
    finally:
        if args.scenario == "compatibility":
            summary["elapsedSeconds"] = round(time.time() - started, 1)
            summary["startedAt"] = summary["invocation"]["startedAt"]
            summary["finishedAt"] = iso_now()
            if evidence_dir is not None:
                try:
                    summary["evidenceArchive"] = archive_compat_runtime_evidence(evidence_dir)
                except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError) as error:
                    summary["evidenceArchiveError"] = f"{type(error).__name__}: {error}"
        # Teardown: reconcile every owned input and, when requested, remove only this run's
        # marker-owned workspace. A disturbed input or a teardown failure turns the overall
        # result into FAIL, so a failed recovery can never still report PASS.
        if before_state is not None:
            try:
                summary["instance_reconciliation"] = pe.reconcile_instance_state(before_state)
            except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError) as teardown_error:
                summary["teardown_error"] = f"{type(teardown_error).__name__}: {teardown_error}"
                summary["status"] = "FAIL"
                exit_code = 1
        if workspace is not None and not args.keep_workspace:
            try:
                summary["cleanup"] = pe.cleanup_instance()
            except (OSError, pe.PackageEnvironmentError, subprocess.SubprocessError) as cleanup_error:
                summary["cleanup_error"] = f"{type(cleanup_error).__name__}: {cleanup_error}"
                summary["status"] = "FAIL"
                exit_code = 1
        if evidence_dir is not None:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / "package-integration-result.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            if args.scenario == "compatibility":
                (evidence_dir / "INDEX.md").write_text(render_compat_index(summary, evidence_dir),
                                                       encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
