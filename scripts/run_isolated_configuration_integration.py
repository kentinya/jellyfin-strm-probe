#!/usr/bin/env python3
"""Exercise the STRM Probe Optimizer configuration page against the repository's isolated Jellyfin instance.

The script only uses the repository's isolated Compose project, the local synthetic media service and temporary
hand-written STRM fixtures. It deploys the built plugin, snapshots the plugin configuration file and every native
scheduled task trigger, then restores and verifies them in a finally block.

It drives the real web UI with a pinned headless browser (scripts/configuration_page_driver.mjs): an administrator
logs in, opens the native plugin entry, follows the configuration link and edits/saves the page. The browser run
covers page load, the five editable fields, all/explicit library scope, empty-selection rejection, request and save
failure feedback, and read-back after a real server restart. A representative native task run then proves the
page-saved partial scope actually drives which libraries the batch task processes.

The browser toolchain is not a plugin production dependency. It is pinned under artifacts/dev-env/browser-tools
(git-ignored). Prepare it with:

    python3 scripts/prepare_browser_tools.py
    # If headless Chromium reports missing system libraries, install the printed package list, e.g.:
    sudo apt-get install -y --no-install-recommends libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
        libxkbcommon0 libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libcairo2 \
        libpango-1.0-0 libasound2

When the toolchain is missing the script reports BLOCKED and the exact preparation commands; it never skips the
interaction silently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_isolated_plugin_integration as base  # noqa: E402

ROOT = base.ROOT
FIXTURE = base.FIXTURE
CONFIGURATION_FILE = base.CONFIGURATION_FILE
PLUGIN_ID = base.PLUGIN_ID
PAGE_NAME = "StrmProbeOptimizer"
TASK_NAME = "STRM 媒体信息检查"
BROWSER_TOOLS = ROOT / "artifacts" / "dev-env" / "browser-tools"
NODE_MODULES = BROWSER_TOOLS / "node" / "node_modules"
DRIVER = ROOT / "scripts" / "configuration_page_driver.mjs"
PLAYWRIGHT_PACKAGE = "playwright@1.55.0"
CHROMIUM_REVISION = "chromium-1187"

# Every problem found while restoring the isolated instance or cleaning temporary entries. A non-empty list turns
# the run into a failure even when the browser scenarios passed, so a PASS never hides a leaked fixture.
RESTORE_PROBLEMS: list[str] = []


def record_problem(message: str) -> None:
    RESTORE_PROBLEMS.append(message)


def browser_available() -> bool:
    return (NODE_MODULES / "playwright" / "package.json").is_file()


def node_executable() -> str | None:
    return shutil.which("node")


SYSTEM_PACKAGES = (
    "libnss3", "libatk1.0-0", "libatk-bridge2.0-0", "libcups2", "libxkbcommon0", "libatspi2.0-0",
    "libxcomposite1", "libxdamage1", "libxfixes3", "libxrandr2", "libgbm1", "libcairo2", "libpango-1.0-0",
    "libasound2",
)


def browser_preparation_commands() -> list[str]:
    return [
        "python3 scripts/prepare_browser_tools.py",
        "sudo apt-get install -y --no-install-recommends " + " ".join(SYSTEM_PACKAGES),
    ]


def playwright_version() -> str:
    package = NODE_MODULES / "playwright" / "package.json"
    if package.is_file():
        return json.loads(package.read_text(encoding="utf-8")).get("version", "unknown")
    return "unknown"


def virtual_folders(api: base.JellyfinApi) -> list[dict]:
    return base.request_json(api.base_url + "/Library/VirtualFolders", headers=api.headers, timeout=20)


def libraries_by_location(api: base.JellyfinApi) -> dict[str, str]:
    by_path: dict[str, str] = {}
    for folder in virtual_folders(api):
        for info in folder.get("LibraryOptions", {}).get("PathInfos", []):
            by_path[str(info.get("Path", ""))] = folder["ItemId"]
    return by_path


def strm_and_local_library_ids(api: base.JellyfinApi) -> tuple[str, str]:
    by_path = libraries_by_location(api)
    strm_library = next((library_id for path, library_id in by_path.items() if path.rstrip("/").endswith("/strm")), None)
    local_library = next((library_id for path, library_id in by_path.items() if path.rstrip("/").endswith("/local")), None)
    base.require(strm_library is not None and local_library is not None, f"The isolated environment must expose a STRM and a local library: {by_path}.")
    base.require(strm_library != local_library, "The STRM and local candidates must come from distinct libraries.")
    return strm_library, local_library


def configuration_snapshot(api: base.JellyfinApi) -> dict:
    _, body = api.request_response(f"/Plugins/{PLUGIN_ID}/Configuration")
    return json.loads(body)


def run_browser(scenario: dict, timeout: int = 240) -> dict:
    node = node_executable()
    base.require(node is not None, "Node.js is required to run the browser configuration-page driver.")
    with tempfile.TemporaryDirectory(prefix="strm-config-browser-") as workspace:
        scenario_path = Path(workspace) / "scenario.json"
        scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
        environment = os.environ.copy()
        environment["PLAYWRIGHT_BROWSERS_PATH"] = str(Path.home() / ".cache" / "ms-playwright")
        environment["STRM_CONFIG_PLAYWRIGHT_ROOT"] = str(BROWSER_TOOLS / "node")
        completed = subprocess.run(
            [node, str(DRIVER), str(scenario_path)],
            cwd=str(BROWSER_TOOLS / "node"),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=environment,
        )
    output = completed.stdout.strip().splitlines()
    parsed: dict | None = None
    for line in reversed(output):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        parsed = candidate
        break
    if parsed is None:
        raise RuntimeError(
            "The browser driver produced no JSON result. stderr tail: "
            + " | ".join((completed.stderr.strip().splitlines() or ["<empty>"])[-3:])
        )
    parsed["exit_code"] = completed.returncode
    return parsed


def driver_scenario(api: base.JellyfinApi, scenario: str, screenshot_dir: Path, **extra: object) -> dict:
    cred = json.loads((ROOT / "artifacts" / "dev-env" / "credentials.local.json").read_text(encoding="utf-8"))
    payload = {
        "scenario": scenario,
        "baseUrl": cred["base_url"],
        "username": cred["username"],
        "password": cred["password"],
        "pluginId": PLUGIN_ID,
        "pageName": PAGE_NAME,
        "screenshotDir": str(screenshot_dir),
    }
    payload.update(extra)
    return run_browser(payload)


def browser_fingerprint() -> dict:
    browser_binary = Path.home() / ".cache" / "ms-playwright" / CHROMIUM_REVISION / "chrome-linux" / "chrome"
    return {
        "node": node_executable() or "missing",
        "playwright": playwright_version(),
        "chromium_revision": CHROMIUM_REVISION,
        "chromium_present": browser_binary.is_file(),
    }


def is_benign_browser_noise(entry: dict) -> bool:
    """Return True only for Jellyfin's own web-client noise that is unrelated to the plugin configuration page.

    Each pattern is tied to a specific Jellyfin bundle or endpoint so an error originating from this plugin's page
    (whose location is the dashboard document and whose marker is ``strm-config-load-failed``) is never ignored.
    """
    text = str(entry.get("text", ""))
    url = str(entry.get("url", "")) + " " + str(entry.get("stack", ""))
    if "WebSocket connection to 'ws://" in text and "jellyfin.sdk.bundle.js" in url:
        return True
    if "CancelledError" in text and ("hometab" in url or "tanstack.query-core" in url):
        return True
    if "failed to get tab controller" in text and "hometab" in url:
        return True
    if "status of 404" in text and "/Packages/" in str(entry.get("url", "")):
        return True
    return False


def require_browser_clean(result: dict, label: str, allowed_failed_urls: tuple[str, ...] = (), allow_page_load_marker: bool = False) -> None:
    base.require("error" not in result, f"The browser scenario {label} failed: {result.get('error')}.")
    page_errors = [error for error in result.get("pageErrors", []) if not is_benign_browser_noise(error)]
    console_errors = [line for line in result.get("consoleErrors", []) if not is_benign_browser_noise(line)]
    base.require(not page_errors, f"The browser scenario {label} produced page errors: {page_errors}.")
    # A scenario that deliberately injects a failure may whitelist exactly the endpoint it controls; the console
    # entry for that injected response is allowed, but any other console error still fails the scenario.
    if allowed_failed_urls:
        console_errors = [
            line for line in console_errors
            if not ("status of " in str(line.get("text", "")) and any(marker in str(line.get("url", "")) for marker in allowed_failed_urls))
        ]
    if allow_page_load_marker:
        console_errors = [line for line in console_errors if "strm-config-load-failed" not in str(line.get("text", ""))]
    base.require(not console_errors, f"The browser scenario {label} produced console errors: {console_errors}.")

    # The plugin's own page and configuration endpoints must never fail during a successful scenario.
    failed_responses = result.get("failedResponses", [])
    page_failures = [
        response for response in failed_responses
        if "/Packages/" not in str(response.get("url", ""))
        and not any(marker in str(response.get("url", "")) for marker in allowed_failed_urls)
    ]
    base.require(not page_failures, f"The browser scenario {label} saw a failed response: {page_failures}.")
    marker_errors = [
        line for line in result.get("consoleErrors", [])
        if "strm-config-load-failed" in str(line.get("text", ""))
    ]
    if not allow_page_load_marker:
        base.require(not marker_errors, f"The configuration page reported its own load failure: {marker_errors}.")


def scenario_load(api: base.JellyfinApi, screenshot_dir: Path) -> dict:
    """AC-U1: open the page from the plugin entry; the five effective values and the real library list load."""
    expected = configuration_snapshot(api)
    result = driver_scenario(api, "inspect", screenshot_dir)
    require_browser_clean(result, "load")
    state = result["final"]
    base.require(state["pagePresent"] and state["loaded"], f"The configuration page did not load: {state}.")
    base.require(state["enabled"] == expected["Enabled"], f"Enabled was not loaded: {state} != {expected}.")
    base.require(state["playbackAutoCheck"] == expected["PlaybackAutoCheck"], f"PlaybackAutoCheck was not loaded: {state}.")
    base.require(int(state["maxConcurrentProbes"]) == int(expected["MaxConcurrentProbes"]), f"MaxConcurrentProbes was not loaded: {state}.")
    base.require(state["detailedLog"] == expected["DetailedLog"], f"DetailedLog was not loaded: {state}.")
    base.require(state["batchAllLibraries"] == expected["BatchAllLibraries"], f"BatchAllLibraries was not loaded: {state}.")
    real_libraries = {str(folder["ItemId"]).replace("-", "").lower() for folder in virtual_folders(api)}
    rendered = {entry["id"].replace("-", "").lower() for entry in state["libraries"]}
    base.require(rendered == real_libraries, f"The page did not render the real library list: {rendered} != {real_libraries}.")
    return {
        "loaded_values": state,
        "real_library_count": len(real_libraries),
        "screenshots": result["screenshots"],
    }


def scenario_save_and_restart(api: base.JellyfinApi, screenshot_dir: Path, strm_library: str) -> dict:
    """AC-U2/AC-U3: edit all five fields, save a partial scope, verify persistence and restart read-back."""
    edited = {
        "enabled": False,
        "playbackAutoCheck": False,
        "detailedLog": True,
        "maxConcurrentProbes": 6,
        "batchAllLibraries": False,
        "libraryIds": [strm_library],
    }
    result = driver_scenario(api, "save_valid", screenshot_dir, edits=edited)
    require_browser_clean(result, "save_valid")
    final = result["final"]
    base.require(final["saveState"] == "success", f"A valid save did not report success: {final}.")
    base.require(final["enabled"] is False and final["playbackAutoCheck"] is False and final["detailedLog"] is True, f"The saved fields were not reflected: {final}.")
    base.require(int(final["maxConcurrentProbes"]) == 6, f"The saved concurrency was not reflected: {final}.")
    base.require(final["batchAllLibraries"] is False, f"The saved scope toggle was not reflected: {final}.")
    base.require(
        [entry["id"] for entry in final["libraries"] if entry["checked"]] == [strm_library]
        or [e["id"].replace("-", "").lower() for e in final["libraries"] if e["checked"]] == [strm_library.replace("-", "").lower()],
        f"The saved partial selection was not reflected: {final}.",
    )

    # The effective configuration and the persisted file must match the page edit.
    effective = configuration_snapshot(api)
    base.require(effective["Enabled"] is False and effective["PlaybackAutoCheck"] is False, f"The saved values were not effective: {effective}.")
    base.require(effective["DetailedLog"] is True and int(effective["MaxConcurrentProbes"]) == 6, f"The saved values were not effective: {effective}.")
    base.require(effective["BatchAllLibraries"] is False, f"The saved scope was not effective: {effective}.")
    base.require(
        [part.strip().replace("-", "").lower() for part in str(effective["BatchLibraryIds"]).split(",") if part.strip()]
        == [strm_library.replace("-", "").lower()],
        f"The saved partial selection was not persisted: {effective}.",
    )
    file_text = CONFIGURATION_FILE.read_text(encoding="utf-8")
    base.require("<BatchAllLibraries>false</BatchAllLibraries>" in file_text, "The saved scope toggle was not written to the configuration file.")

    # A real restart must read the same values back, and the page must show them again.
    container = base.restart_isolated_server()
    api = base.JellyfinApi()
    after_restart = configuration_snapshot(api)
    base.require(after_restart == effective, f"The saved configuration did not survive restart: {after_restart} != {effective}.")
    reload_result = driver_scenario(api, "inspect", screenshot_dir)
    require_browser_clean(reload_result, "reload_after_restart")
    reload_state = reload_result["final"]
    base.require(reload_state["enabled"] is False and reload_state["detailedLog"] is True, f"The page did not read the persisted values after restart: {reload_state}.")
    base.require(int(reload_state["maxConcurrentProbes"]) == 6, f"The page did not read the persisted concurrency after restart: {reload_state}.")
    return {
        "edited": edited,
        "effective": effective,
        "after_restart": after_restart,
        "screenshots": result["screenshots"] + reload_result["screenshots"],
        "restart_container": container,
    }


def scenario_empty_scope(api: base.JellyfinApi, screenshot_dir: Path) -> dict:
    """AC-U3: an explicit scope with no library is refused by the page and does not change the saved config."""
    before = configuration_snapshot(api)
    file_before = CONFIGURATION_FILE.read_bytes()
    result = driver_scenario(api, "save_empty_scope", screenshot_dir)
    require_browser_clean(result, "empty_scope")
    final = result["final"]
    base.require(final["saveState"] == "error", f"The empty explicit scope was not refused: {final}.")
    base.require("未选择任何媒体库" in final["statusText"] or "空选择" in final["statusText"], f"The empty-scope feedback was not actionable: {final}.")
    base.require(configuration_snapshot(api) == before, "A refused empty scope changed the effective configuration.")
    base.require(CONFIGURATION_FILE.read_bytes() == file_before, "A refused empty scope changed the persisted configuration file.")
    return {"status_text": final["statusText"], "screenshots": result["screenshots"]}


def scenario_library_read_failure(api: base.JellyfinApi, screenshot_dir: Path) -> dict:
    """AC-U3: when the library list cannot be read, the page reports it and does not fabricate a selection."""
    result = driver_scenario(api, "library_read_failure", screenshot_dir)
    require_browser_clean(result, "library_read_failure", allowed_failed_urls=("/Library/VirtualFolders",))
    final = result["final"]
    base.require(final["loaded"], f"The page did not load while the library list was unavailable: {final}.")
    base.require(not final["libraries"], f"The page rendered libraries despite the read failure: {final}.")
    base.require("媒体库列表失败" in final["statusText"] or "无法读取媒体库列表" in final["statusText"], f"The library read failure was not surfaced: {final}.")
    return {"status_text": final["statusText"], "screenshots": result["screenshots"]}


def scenario_save_failure(api: base.JellyfinApi, screenshot_dir: Path) -> dict:
    """AC-U4: a rejected save shows an accurate error and leaves the saved configuration unchanged."""
    before = configuration_snapshot(api)
    file_before = CONFIGURATION_FILE.read_bytes()
    result = driver_scenario(api, "save_failure", screenshot_dir, edits={"enabled": True, "detailedLog": False})
    require_browser_clean(result, "save_failure", allowed_failed_urls=("/Configuration",))
    final = result["final"]
    base.require(final["saveState"] == "error", f"A rejected save did not report an error: {final}.")
    base.require("未被更改" in final["statusText"] or "保存被拒绝" in final["statusText"], f"The save failure feedback was not accurate: {final}.")
    base.require(configuration_snapshot(api) == before, "A rejected save changed the effective configuration.")
    base.require(CONFIGURATION_FILE.read_bytes() == file_before, "A rejected save changed the persisted configuration file.")
    return {"status_text": final["statusText"], "screenshots": result["screenshots"]}


def scenario_load_failure(api: base.JellyfinApi, screenshot_dir: Path) -> dict:
    """AC-U1/AC-U3: a failed configuration load disables saving instead of overwriting with defaults."""
    before = configuration_snapshot(api)
    result = driver_scenario(api, "load_failure", screenshot_dir)
    require_browser_clean(result, "load_failure", allowed_failed_urls=("/Configuration",), allow_page_load_marker=True)
    final = result["final"]
    base.require(not final["loaded"], f"The page claimed a successful load despite the read failure: {final}.")
    base.require(final["saveState"] == "error", f"The failed load did not surface an error: {final}.")
    base.require("保存已禁用" in final["statusText"] or "读取当前配置失败" in final["statusText"], f"The load failure was not actionable: {final}.")
    base.require(configuration_snapshot(api) == before, "A failed load changed the effective configuration.")
    return {"status_text": final["statusText"], "screenshots": result["screenshots"]}


def scenario_native_task_scope(api: base.JellyfinApi, container: str, media_container: str, strm_library: str, local_library: str) -> dict:
    """AC-U3/AC-U5: the page-saved partial scope actually drives which libraries the native task processes."""
    media = (ROOT / "artifacts" / "dev-env" / "media" / "fixture.mp4").read_bytes()
    sha1 = hashlib.sha1(media).hexdigest()
    plain_url = "http://media:8080/fixture.mp4"
    nonce = uuid.uuid4().hex[:8]
    strm_dir = ROOT / "artifacts" / "dev-env" / "strm"
    local_dir = ROOT / "artifacts" / "dev-env" / "media"
    in_scope_name = f"Config Page InScope {nonce}"
    out_scope_name = f"Config Page OutScope {nonce}"
    in_scope_path = strm_dir / (in_scope_name + ".strm")
    out_scope_path = local_dir / (out_scope_name + ".strm")
    try:
        with in_scope_path.open("xb") as fixture:
            fixture.write(base.write_versioned_fixture(FIXTURE.read_bytes(), base.unique_query_url(plain_url, nonce + "in"), sha1, len(media)))
        with out_scope_path.open("xb") as fixture:
            fixture.write(base.write_versioned_fixture(FIXTURE.read_bytes(), base.unique_query_url(plain_url, nonce + "out"), sha1, len(media)))
        api.refresh_library()
        in_scope_item = api.wait_for_named_library_item(in_scope_name)
        out_scope_item = api.wait_for_named_library_item(out_scope_name)

        # Scope was already saved to the STRM library through the browser in scenario_save_and_restart; re-save it
        # through the API so this scenario is self-contained and does not depend on scenario ordering.
        status = configure_via_api(api, {
            "Enabled": True,
            "PlaybackAutoCheck": True,
            "MaxConcurrentProbes": 2,
            "DetailedLog": False,
            "BatchAllLibraries": False,
            "BatchLibraryIds": strm_library,
        })
        base.require(status == 204, f"Jellyfin rejected the representative partial scope ({status}).")

        run_native_task(api, container)
        base.require(
            batch_fingerprint_row(in_scope_item["Id"]) is not None,
            "The native task did not process the in-scope STRM library candidate.",
        )
        base.require(
            batch_fingerprint_row(out_scope_item["Id"]) is None,
            "The native task processed an out-of-scope library candidate despite the page-saved partial scope.",
        )

        # Switch back to all libraries and prove the previously out-of-scope candidate is now processed.
        status = configure_via_api(api, {
            "Enabled": True,
            "PlaybackAutoCheck": True,
            "MaxConcurrentProbes": 2,
            "DetailedLog": False,
            "BatchAllLibraries": True,
            "BatchLibraryIds": "",
        })
        base.require(status == 204, f"Jellyfin rejected the all-library scope ({status}).")
        run_native_task(api, container)
        base.require(
            batch_fingerprint_row(out_scope_item["Id"]) is not None,
            "Switching back to all libraries did not process the previously out-of-scope candidate.",
        )
        return {
            "in_scope_processed": True,
            "out_of_scope_unprocessed_under_partial": True,
            "out_of_scope_processed_under_all": True,
            "strm_library_id": strm_library,
            "local_library_id": local_library,
        }
    finally:
        in_scope_path.unlink(missing_ok=True)
        out_scope_path.unlink(missing_ok=True)
        try:
            configure_via_api(api, {
                "Enabled": True,
                "PlaybackAutoCheck": True,
                "MaxConcurrentProbes": 2,
                "DetailedLog": False,
                "BatchAllLibraries": True,
                "BatchLibraryIds": "",
            })
        except Exception as error:
            record_problem(f"configuration restore after native task scenario failed: {type(error).__name__}")
        try:
            api.refresh_library()
        except Exception:
            pass
        for name in (in_scope_name, out_scope_name):
            try:
                api.wait_for_named_library_item_absent(name)
            except Exception as error:
                record_problem(f"temporary library item {name!r} was not removed: {type(error).__name__}")


def configure_via_api(api: base.JellyfinApi, payload: dict) -> int:
    status, _ = api.request_response(f"/Plugins/{PLUGIN_ID}/Configuration", method="POST", data=json.dumps(payload).encode("utf-8"))
    return status


def run_native_task(api: base.JellyfinApi, container: str) -> dict:
    task = next((task for task in base.request_json(api.base_url + "/ScheduledTasks", headers=api.headers, timeout=20) if task.get("Name") == TASK_NAME), None)
    base.require(task is not None, f"Expected exactly one native task named {TASK_NAME!r}.")
    previous_start = (task.get("LastExecutionResult") or {}).get("StartTimeUtc")
    status, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="POST")
    base.require(status == 204, "Jellyfin did not accept the manual native task start.")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        current = next((item for item in base.request_json(api.base_url + "/ScheduledTasks", headers=api.headers, timeout=20) if item.get("Id") == task["Id"]), None)
        state = str((current or {}).get("State", "")).lower()
        if state in {"running", "cancelling", "1", "2"} or (current or {}).get("LastExecutionResult", {}).get("StartTimeUtc") != previous_start:
            if state in {"idle", "0"}:
                return current
        time.sleep(0.5)
    raise RuntimeError("The native batch task did not settle before the timeout.")


def batch_fingerprint_row(item_id: str) -> dict | None:
    return base.fingerprint_row(item_id, item_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="all", choices=["all"])
    parser.parse_args()

    summary: dict = {
        "status": "NOT RUN",
        "browser": browser_fingerprint(),
        "browser_available": browser_available(),
    }

    if not browser_available():
        summary["status"] = "BLOCKED"
        summary["reason"] = "The pinned browser toolchain is not prepared."
        summary["preparation"] = browser_preparation_commands()
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    base.require(FIXTURE.is_file(), "The isolated STRM fixture is missing.")
    original_configuration = CONFIGURATION_FILE.read_bytes() if CONFIGURATION_FILE.is_file() else b""
    trigger_snapshot: dict[str, list[dict]] = {}
    api: base.JellyfinApi | None = None
    container: str | None = None
    media_container: str | None = None
    evidence_dir = Path(os.environ.get("STRM_CONFIG_EVIDENCE_DIR", tempfile.mkdtemp(prefix="strm-config-evidence-")))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    exit_code = 1
    try:
        summary["deployment"] = base.deploy_plugin()
        container = base.restart_isolated_server()
        api = base.JellyfinApi()
        base.require(api.public_info().get("Version") == "12.2.0", "The active isolated Jellyfin version is not 12.2.0.")
        summary["plugin_status"] = api.plugin_status()
        media_container = base.isolated_media_container_name()
        trigger_snapshot = snapshot_triggers(api)
        strm_library, local_library = strm_and_local_library_ids(api)
        summary["libraries"] = {"strm": strm_library, "local": local_library}

        summary["scenario_load"] = scenario_load(api, evidence_dir)
        summary["scenario_save_and_restart"] = scenario_save_and_restart(api, evidence_dir, strm_library)
        # The restart in the previous scenario invalidated the session.
        api = base.JellyfinApi()
        container = base.isolated_container_name()
        media_container = base.isolated_media_container_name()
        summary["scenario_empty_scope"] = scenario_empty_scope(api, evidence_dir)
        summary["scenario_library_read_failure"] = scenario_library_read_failure(api, evidence_dir)
        summary["scenario_save_failure"] = scenario_save_failure(api, evidence_dir)
        summary["scenario_load_failure"] = scenario_load_failure(api, evidence_dir)
        summary["scenario_native_task_scope"] = scenario_native_task_scope(api, container, media_container, strm_library, local_library)

        summary["status"] = "PASS" if not RESTORE_PROBLEMS else "FAIL"
        exit_code = 0 if not RESTORE_PROBLEMS else 1
        if RESTORE_PROBLEMS:
            summary["cleanup_problems"] = list(RESTORE_PROBLEMS)
    finally:
        summary["configuration_restoration"] = restore_configuration(original_configuration, trigger_snapshot)
        if exit_code == 0 and summary["configuration_restoration"] != "restored and verified":
            summary["status"] = "FAIL"
            summary["error"] = "The isolated plugin configuration or task triggers could not be restored and verified."
            exit_code = 1
        summary["evidence_directory"] = str(evidence_dir)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


def restore_configuration(original_configuration: bytes, trigger_snapshot: dict[str, list[dict]]) -> str:
    problems: list[str] = []
    if CONFIGURATION_FILE.is_file() and CONFIGURATION_FILE.read_bytes() != original_configuration:
        CONFIGURATION_FILE.write_bytes(original_configuration)
    if original_configuration and (not CONFIGURATION_FILE.is_file() or CONFIGURATION_FILE.read_bytes() != original_configuration):
        problems.append("configuration file not restored")

    try:
        api = base.JellyfinApi()
        if original_configuration:
            payload = configuration_payload_from_xml(original_configuration)
            status = configure_via_api(api, payload)
            if status != 204:
                problems.append(f"effective configuration re-publish returned {status}")
        for task_id, triggers in trigger_snapshot.items():
            status, _ = api.request_response(f"/ScheduledTasks/{task_id}/Triggers", method="POST", data=json.dumps(triggers).encode("utf-8"))
            if status != 204:
                problems.append(f"trigger restore for {task_id} returned {status}")
        base.restart_isolated_server()
        api = base.JellyfinApi()
        effective = configuration_snapshot(api)
        if original_configuration:
            expected = configuration_payload_from_xml(original_configuration)
            for key, value in expected.items():
                if effective.get(key) != value:
                    problems.append(f"effective configuration {key} mismatch: {effective.get(key)!r} != {value!r}")
        for task_id, triggers in trigger_snapshot.items():
            tasks = base.request_json(api.base_url + "/ScheduledTasks", headers=api.headers, timeout=20)
            current = next((item for item in tasks if str(item.get("Id", "")).lower() == str(task_id).lower()), None)
            if current is None or (current.get("Triggers") or []) != triggers:
                problems.append(f"trigger identity mismatch for {task_id}")
    except Exception as error:
        problems.append(f"configuration restore failed: {type(error).__name__}")

    return "restored and verified" if not problems else "NOT RESTORED: " + "; ".join(problems)


def configuration_payload_from_xml(data: bytes) -> dict:
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


def snapshot_triggers(api: base.JellyfinApi) -> dict[str, list[dict]]:
    tasks = base.request_json(api.base_url + "/ScheduledTasks", headers=api.headers, timeout=20)
    return {str(task["Id"]): (task.get("Triggers") or []) for task in tasks if task.get("Id")}


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
