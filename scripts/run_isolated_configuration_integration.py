#!/usr/bin/env python3
"""Exercise the STRM Probe Optimizer configuration page against the repository's isolated Jellyfin instance.

The script only uses the repository's isolated Compose project, the local synthetic media service and temporary
hand-written STRM fixtures. It deploys the built plugin, snapshots the plugin configuration file and every native
scheduled task trigger, then restores and verifies them in a finally block.

It drives the real web UI with a pinned headless browser (scripts/configuration_page_driver.mjs): an administrator
logs in, opens the native plugin entry, follows the configuration link and edits/saves the page. Every scenario is
run as a separate browser session and writes its own evidence directory (screenshots, driver result, console and
failed-response raw output). The run covers page load, the five editable fields, all/explicit/stale library scope,
empty selection, client-side concurrency bounds, rejected saves, request failures, a save whose response is lost
after the server committed, reload recovery, and legacy configurations without the scope fields. Representative
native task runs then prove that a page-saved partial scope, a page-disabled playback check and a page-disabled
plugin actually drive the native batch behaviour.

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
TASK_SETTLE_SECONDS = 150

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


def redacted_scenario(payload: dict) -> dict:
    redacted = dict(payload)
    redacted["username"] = "<redacted>"
    redacted["password"] = "<redacted>"
    return redacted


def run_browser(scenario: dict, evidence_dir: Path | None = None, timeout: int = 300) -> dict:
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
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "scenario.redacted.json").write_text(json.dumps(redacted_scenario(scenario), ensure_ascii=False, indent=2), encoding="utf-8")
        (evidence_dir / "driver-stdout.txt").write_text(completed.stdout, encoding="utf-8")
        (evidence_dir / "driver-stderr.txt").write_text(completed.stderr, encoding="utf-8")

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
    if evidence_dir is not None:
        (evidence_dir / "driver-result.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    return parsed


def driver_scenario(api: base.JellyfinApi, scenario: str, evidence_dir: Path, label: str, **extra: object) -> dict:
    cred = json.loads((ROOT / "artifacts" / "dev-env" / "credentials.local.json").read_text(encoding="utf-8"))
    scenario_dir = evidence_dir / label
    payload = {
        "scenario": scenario,
        "baseUrl": cred["base_url"],
        "username": cred["username"],
        "password": cred["password"],
        "pluginId": PLUGIN_ID,
        "pageName": PAGE_NAME,
        "screenshotDir": str(scenario_dir),
    }
    payload.update(extra)
    return run_browser(payload, evidence_dir=scenario_dir)


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
    # Jellyfin's own `emby-scrollbuttons` web component races its teardown: detachedCallback nulls scrollHandler
    # while a previously scheduled requestAnimationFrame still calls it. The stack is always Jellyfin's scrollbuttons
    # bundle, never this plugin's configuration page, so it is classified by exact bundle and exact message.
    if text == "t.scrollHandler is not a function" and "49275." in url and ".chunk.js" in url:
        return True
    return False


def require_browser_clean(
    result: dict,
    label: str,
    allowed_failed_urls: tuple[str, ...] = (),
    allow_page_load_marker: bool = False,
    allow_network_failure: bool = False,
) -> None:
    base.require("error" not in result, f"The browser scenario {label} failed: {result.get('error')}.")
    page_errors = [error for error in result.get("pageErrors", []) if not is_benign_browser_noise(error)]
    console_errors = [line for line in result.get("consoleErrors", []) if not is_benign_browser_noise(line)]
    # A scenario that deliberately injects a failure may whitelist exactly the endpoint it controls; the console
    # entry for that injected response is allowed, but any other console error still fails the scenario.
    if allowed_failed_urls:
        console_errors = [
            line for line in console_errors
            if not ("status of " in str(line.get("text", "")) and any(marker in str(line.get("url", "")) for marker in allowed_failed_urls))
        ]
    if allow_network_failure:
        # A browser-aborted configuration request surfaces as a fetch failure. Only the exact
        # "Failed to load resource: net::ERR_FAILED" wording is tolerated, and only when it refers to the
        # configuration endpoint the scenario controls or carries no URL.
        console_errors = [
            line for line in console_errors
            if not (
                "Failed to load resource: net::ERR_FAILED" in str(line.get("text", ""))
                and (str(line.get("url", "")) == "" or "/Configuration" in str(line.get("url", "")))
            )
        ]
    if allow_page_load_marker:
        console_errors = [line for line in console_errors if "strm-config-load-failed" not in str(line.get("text", ""))]
    base.require(not page_errors, f"The browser scenario {label} produced page errors: {page_errors}.")
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


def selected_library_ids(state: dict) -> list[str]:
    return sorted(entry["id"].replace("-", "").lower() for entry in state["libraries"] if entry["checked"])


def scenario_load(api: base.JellyfinApi, evidence_dir: Path) -> dict:
    """AC-U1: open the page from the plugin entry; the five effective values and the real library list load."""
    expected = configuration_snapshot(api)
    result = driver_scenario(api, "inspect", evidence_dir, "01-load")
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
    return {"loaded_values": state, "real_library_count": len(real_libraries), "evidence": "01-load"}


def scenario_save_and_restart(api: base.JellyfinApi, evidence_dir: Path, strm_library: str) -> dict:
    """AC-U2/AC-U3: edit all five fields, save a partial scope, verify persistence and restart read-back."""
    edited = {
        "enabled": False,
        "playbackAutoCheck": False,
        "detailedLog": True,
        "maxConcurrentProbes": 6,
        "batchAllLibraries": False,
        "libraryIds": [strm_library],
    }
    result = driver_scenario(api, "save_valid", evidence_dir, "02-save-and-restart", edits=edited)
    require_browser_clean(result, "save_valid")
    final = result["final"]
    base.require(final["saveState"] == "success", f"A valid save did not report success: {final}.")
    base.require(final["enabled"] is False and final["playbackAutoCheck"] is False and final["detailedLog"] is True, f"The saved fields were not reflected: {final}.")
    base.require(int(final["maxConcurrentProbes"]) == 6, f"The saved concurrency was not reflected: {final}.")
    base.require(final["batchAllLibraries"] is False, f"The saved scope toggle was not reflected: {final}.")
    base.require(selected_library_ids(final) == [strm_library.replace("-", "").lower()], f"The saved partial selection was not reflected: {final}.")
    base.require(result["postBodies"] and len(result["postBodies"]) == 1, f"Exactly one configuration POST was expected: {result.get('postBodies')}.")

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
    reload_result = driver_scenario(api, "inspect", evidence_dir, "03-reload-after-restart")
    require_browser_clean(reload_result, "reload_after_restart")
    reload_state = reload_result["final"]
    base.require(reload_state["enabled"] is False and reload_state["detailedLog"] is True, f"The page did not read the persisted values after restart: {reload_state}.")
    base.require(int(reload_state["maxConcurrentProbes"]) == 6, f"The page did not read the persisted concurrency after restart: {reload_state}.")
    base.require(selected_library_ids(reload_state) == [strm_library.replace("-", "").lower()], f"The page did not read the persisted partial scope after restart: {reload_state}.")
    return {
        "edited": edited,
        "effective": effective,
        "after_restart": after_restart,
        "evidence": ["02-save-and-restart", "03-reload-after-restart"],
        "restart_container": container,
    }


def scenario_stale_scope(api: base.JellyfinApi, evidence_dir: Path, strm_library: str) -> dict:
    """FR-U1/AC-U3: a saved but missing library is surfaced and blocks saving until the user corrects it."""
    before = configuration_snapshot(api)
    stale_library = uuid.uuid4().hex
    result = driver_scenario(
        api,
        "stale_scope",
        evidence_dir,
        "04-stale-scope",
        staleLibraryId=stale_library,
        realLibraryId=strm_library,
        baseConfig=before,
    )
    require_browser_clean(result, "stale_scope")
    initial = result["initial"]
    base.require(initial["staleWarning"], f"The page did not flag the missing saved library: {initial}.")
    base.require(any(entry["stale"] and entry["checked"] for entry in initial["libraries"]), f"The stale library was not kept visible and selected: {initial}.")
    blocked = result["blockedSave"]
    base.require(blocked["saveState"] == "error" and blocked["statusKind"] == "stale", f"The stale scope save was not refused: {blocked}.")
    base.require(result["attemptsAfterBlock"] == 0, f"The stale scope must not produce a configuration POST, saw {result['attemptsAfterBlock']}.")
    corrected = result["correctedSave"]
    base.require(corrected["saveState"] == "success", f"The corrected scope did not save: {corrected}.")
    base.require(selected_library_ids(corrected) == [strm_library.replace("-", "").lower()], f"The corrected scope still contained the stale library: {corrected}.")
    base.require(
        result["postBodies"]
        and [part.strip().replace("-", "").lower() for part in str(result["postBodies"][-1]["BatchLibraryIds"]).split(",") if part.strip()]
        == [strm_library.replace("-", "").lower()],
        f"The corrected POST still carried the stale library: {result.get('postBodies')}.",
    )
    effective = configuration_snapshot(api)
    base.require(stale_library not in str(effective.get("BatchLibraryIds", "")).replace("-", "").lower(), f"The stale library was persisted: {effective}.")
    return {"stale_library": stale_library, "evidence": "04-stale-scope", "blocked_save": blocked, "corrected_save": corrected}


def scenario_lost_save_response(api: base.JellyfinApi, evidence_dir: Path) -> dict:
    """FR-U2/AC-U4: the server commits the save but the browser loses the response."""
    result = driver_scenario(api, "lost_save_response", evidence_dir, "05-lost-save-response")
    require_browser_clean(result, "lost_save_response", allow_network_failure=True)
    base.require(result["postApplied"] == 1 and result.get("serverStatus") == 204, f"The lost-response scenario did not commit on the server: {result.get('serverStatus')}.")
    feedback = result["afterSave"]
    base.require(feedback["saveState"] == "error" and feedback["statusKind"] == "save-unconfirmed", f"The lost response was not reported as unconfirmed: {feedback}.")
    base.require("未确认" in feedback["statusText"], f"The unconfirmed feedback was not accurate: {feedback}.")
    base.require("未被更改" not in feedback["statusText"] and "未更改" not in feedback["statusText"], f"The page still promised the configuration was unchanged: {feedback}.")
    effective = result["effectiveAfter"]
    base.require(effective["DetailedLog"] != result["initial"]["detailedLog"], f"The server did not actually commit the toggled field: {effective}.")
    reloaded = result["reloaded"]
    base.require(reloaded["detailedLog"] == effective["DetailedLog"], f"The reload did not show the real effective value: {reloaded}.")
    return {"evidence": "05-lost-save-response", "effective_after_lost_save": effective, "feedback": feedback}


def scenario_pre_submit_failure(api: base.JellyfinApi, evidence_dir: Path) -> dict:
    """AC-U4: the save request never reaches the server, so nothing may change."""
    result = driver_scenario(api, "pre_submit_failure", evidence_dir, "06-pre-submit-failure")
    require_browser_clean(result, "pre_submit_failure", allow_network_failure=True)
    base.require(result["postApplied"] == 0, "The pre-submit failure scenario must not reach the server.")
    feedback = result["afterSave"]
    base.require(feedback["saveState"] == "error" and feedback["statusKind"] == "save-unconfirmed", f"The pre-submit failure was not reported as unconfirmed: {feedback}.")
    base.require("未被更改" not in feedback["statusText"] and "未更改" not in feedback["statusText"], f"The page promised the configuration was unchanged on an unconfirmed result: {feedback}.")
    base.require(result["effectiveAfter"] == result["before"], f"A request that never reached the server changed the effective configuration: {result['effectiveAfter']}.")
    base.require(result["reloaded"]["saveState"] == "" and result["reloaded"]["loaded"], f"The reload did not recover to a loaded state: {result['reloaded']}.")
    return {"evidence": "06-pre-submit-failure", "feedback": feedback}


def scenario_rejected_save(api: base.JellyfinApi, evidence_dir: Path) -> dict:
    """AC-U4: a genuine server rejection is reported as a rejection and leaves the configuration unchanged."""
    before = configuration_snapshot(api)
    file_before = CONFIGURATION_FILE.read_bytes()
    result = driver_scenario(api, "save_failure", evidence_dir, "07-rejected-save")
    require_browser_clean(result, "rejected_save", allowed_failed_urls=("/Configuration",))
    feedback = result["afterSave"]
    base.require(feedback["saveState"] == "error" and feedback["statusKind"] == "save-rejected", f"The rejection was not reported as a rejection: {feedback}.")
    base.require("拒绝" in feedback["statusText"], f"The rejection feedback was not accurate: {feedback}.")
    base.require(result["effectiveAfter"] == before, "A rejected save changed the effective configuration.")
    base.require(CONFIGURATION_FILE.read_bytes() == file_before, "A rejected save changed the persisted configuration file.")
    base.require(result["reloaded"]["loaded"], f"The page did not recover after a rejected save: {result['reloaded']}.")
    return {"evidence": "07-rejected-save", "feedback": feedback}


def scenario_concurrency_bounds(api: base.JellyfinApi, evidence_dir: Path, strm_library: str) -> dict:
    """AC-U4: an out-of-range concurrency is refused client-side, then recovered by a valid value."""
    before = configuration_snapshot(api)
    result = driver_scenario(api, "concurrent_out_of_range", evidence_dir, "08-concurrency-bounds")
    require_browser_clean(result, "concurrency_bounds")
    invalid = result["invalidSave"]
    base.require(invalid["saveState"] == "error" and "1～8" in invalid["statusText"], f"The out-of-range concurrency was not refused: {invalid}.")
    base.require(result["attemptsAfterInvalid"] == 0, f"An out-of-range concurrency must not produce a POST, saw {result['attemptsAfterInvalid']}.")
    # No POST was sent, so the effective configuration and the persisted file cannot have changed; the effective
    # value is re-read through the API immediately after the refusal to prove it.
    base.require(result["effectiveAfterInvalid"] == before, f"A refused concurrency changed the effective configuration: {result['effectiveAfterInvalid']} != {before}.")
    corrected = result["correctedSave"]
    base.require(corrected["saveState"] == "success" and int(corrected["maxConcurrentProbes"]) == 3, f"The corrected concurrency did not save: {corrected}.")
    base.require(int(configuration_snapshot(api)["MaxConcurrentProbes"]) == 3, "The corrected concurrency was not persisted.")
    return {"evidence": "08-concurrency-bounds", "invalid": invalid, "corrected": corrected}


def scenario_empty_scope(api: base.JellyfinApi, evidence_dir: Path, strm_library: str) -> dict:
    """AC-U3: an explicit scope with no library is refused, then recovered by selecting a real library."""
    before = configuration_snapshot(api)
    result = driver_scenario(api, "empty_scope", evidence_dir, "09-empty-scope", realLibraryId=strm_library)
    require_browser_clean(result, "empty_scope")
    refused = result["refusedSave"]
    base.require(refused["saveState"] == "error" and refused["statusKind"] == "empty-scope", f"The empty explicit scope was not refused: {refused}.")
    base.require("未选择任何媒体库" in refused["statusText"] or "空选择" in refused["statusText"], f"The empty-scope feedback was not actionable: {refused}.")
    base.require(result["attemptsAfterRefusal"] == 0, f"An empty scope must not produce a POST, saw {result['attemptsAfterRefusal']}.")
    base.require(result["effectiveAfterRefusal"] == before, f"A refused empty scope changed the effective configuration: {result['effectiveAfterRefusal']} != {before}.")
    corrected = result["correctedSave"]
    base.require(corrected["saveState"] == "success", f"The corrected empty scope did not save: {corrected}.")
    base.require(selected_library_ids(corrected) == [strm_library.replace("-", "").lower()], f"The corrected selection was not the chosen library: {corrected}.")
    return {"evidence": "09-empty-scope", "refused": refused, "corrected": corrected}


def scenario_load_failure(api: base.JellyfinApi, evidence_dir: Path) -> dict:
    """AC-U1/AC-U3: a failed configuration load disables saving; "重新读取" recovers."""
    before = configuration_snapshot(api)
    result = driver_scenario(api, "load_failure", evidence_dir, "10-load-failure")
    require_browser_clean(result, "load_failure", allowed_failed_urls=("/Configuration",), allow_page_load_marker=True)
    initial = result["initial"]
    base.require(not initial["loaded"], f"The page claimed a successful load despite the read failure: {initial}.")
    base.require(initial["saveState"] == "error" and initial["saveDisabled"], f"The failed load did not disable saving: {initial}.")
    base.require("保存已禁用" in initial["statusText"] or "读取当前配置失败" in initial["statusText"], f"The load failure was not actionable: {initial}.")
    base.require(configuration_snapshot(api) == before, "A failed load changed the effective configuration.")
    reloaded = result["reloaded"]
    base.require(reloaded["loaded"] and not reloaded["saveDisabled"], f"The reload did not recover the page: {reloaded}.")
    return {"evidence": "10-load-failure", "initial": initial, "reloaded": reloaded}


def scenario_library_read_failure(api: base.JellyfinApi, evidence_dir: Path) -> dict:
    """AC-U3: when the library list cannot be read, the page reports it and reloading recovers."""
    result = driver_scenario(api, "library_read_failure", evidence_dir, "11-library-read-failure")
    require_browser_clean(result, "library_read_failure", allowed_failed_urls=("/Library/VirtualFolders",))
    initial = result["initial"]
    base.require(initial["loaded"], f"The page did not load while the library list was unavailable: {initial}.")
    base.require(initial["libraryListUnavailable"] and not initial["libraries"], f"The page rendered libraries despite the read failure: {initial}.")
    base.require(initial["statusKind"] == "library-unavailable" and "媒体库列表" in initial["statusText"], f"The library read failure was not surfaced: {initial}.")
    reloaded = result["reloaded"]
    base.require(not reloaded["libraryListUnavailable"] and reloaded["libraries"], f"The reload did not restore the library list: {reloaded}.")
    return {"evidence": "11-library-read-failure", "initial": initial, "reloaded": reloaded}


def scenario_legacy_scope(api: base.JellyfinApi, evidence_dir: Path) -> dict:
    """AC-U1: a legacy configuration without the scope fields loads as the documented all-library default."""
    result = driver_scenario(api, "legacy_scope", evidence_dir, "12-legacy-scope")
    require_browser_clean(result, "legacy_scope")
    state = result["initial"]
    base.require(state["loaded"], f"The legacy configuration did not load: {state}.")
    base.require(state["batchAllLibraries"] is True, f"A legacy configuration without the scope fields must default to all libraries: {state}.")
    base.require(state["enabled"] is True and state["playbackAutoCheck"] is True, f"The legacy configuration did not keep its documented defaults: {state}.")
    return {"evidence": "12-legacy-scope", "state": state}


def configure_via_api(api: base.JellyfinApi, payload: dict) -> int:
    status, _ = api.request_response(f"/Plugins/{PLUGIN_ID}/Configuration", method="POST", data=json.dumps(payload).encode("utf-8"))
    return status


def run_native_task(api: base.JellyfinApi, container: str) -> dict:
    """Start the native task and wait for it to settle, returning the real terminal result."""
    task = next((task for task in base.request_json(api.base_url + "/ScheduledTasks", headers=api.headers, timeout=20) if task.get("Name") == TASK_NAME), None)
    base.require(task is not None, f"Expected exactly one native task named {TASK_NAME!r}.")
    previous_start = (task.get("LastExecutionResult") or {}).get("StartTimeUtc")
    status, _ = api.request_response("/ScheduledTasks/Running/" + task["Id"], method="POST")
    base.require(status == 204, f"Jellyfin did not accept the manual native task start (status {status}).")
    deadline = time.monotonic() + TASK_SETTLE_SECONDS
    while time.monotonic() < deadline:
        current = next((item for item in base.request_json(api.base_url + "/ScheduledTasks", headers=api.headers, timeout=20) if item.get("Id") == task["Id"]), None)
        state = str((current or {}).get("State", "")).lower()
        result = (current or {}).get("LastExecutionResult") or {}
        if state in {"idle", "0"} and result.get("StartTimeUtc") != previous_start:
            return current
        time.sleep(0.5)
    raise RuntimeError("The native batch task did not settle before the timeout.")


def terminal_status(task: dict) -> str:
    return str((task.get("LastExecutionResult") or {}).get("Status", ""))


def page_save_via_browser(api: base.JellyfinApi, evidence_dir: Path, label: str, edits: dict) -> dict:
    """Save the given edits through the real page and return the driver result after asserting success."""
    result = driver_scenario(api, "save_valid", evidence_dir, label, edits=edits)
    require_browser_clean(result, label)
    base.require(result["final"]["saveState"] == "success", f"The page save {label} did not succeed: {result['final']}.")
    base.require(result["postAttempts"] == 1, f"The page save {label} did not produce exactly one POST: {result.get('postAttempts')}.")
    return result


def scenario_native_task_journey(
    api: base.JellyfinApi,
    container: str,
    evidence_dir: Path,
    strm_library: str,
    local_library: str,
) -> dict:
    """AC-U3/AC-U5: page-saved scope, disabled playback check and disabled plugin drive the native task."""
    media = (ROOT / "artifacts" / "dev-env" / "media" / "fixture.mp4").read_bytes()
    sha1 = hashlib.sha1(media).hexdigest()
    plain_url = "http://media:8080/fixture.mp4"
    nonce = uuid.uuid4().hex[:8]
    strm_dir = ROOT / "artifacts" / "dev-env" / "strm"
    local_dir = ROOT / "artifacts" / "dev-env" / "media"
    in_scope_name = f"Config Page InScope {nonce}"
    out_scope_name = f"Config Page OutScope {nonce}"
    disabled_name = f"Config Page Disabled {nonce}"
    in_scope_path = strm_dir / (in_scope_name + ".strm")
    out_scope_path = local_dir / (out_scope_name + ".strm")
    disabled_path = strm_dir / (disabled_name + ".strm")
    created: list[Path] = []

    def write_fixture(path: Path, name: str) -> None:
        with path.open("xb") as fixture:
            fixture.write(base.write_versioned_fixture(FIXTURE.read_bytes(), base.unique_query_url(plain_url, name), sha1, len(media)))
        created.append(path)

    try:
        write_fixture(in_scope_path, nonce + "in")
        write_fixture(out_scope_path, nonce + "out")
        api.refresh_library()
        in_scope_item = api.wait_for_named_library_item(in_scope_name)
        out_scope_item = api.wait_for_named_library_item(out_scope_name)

        # Fixture preparation only: start from a known all-library, enabled state so the page edit below is the
        # value under test. The value that drives each run is always saved through the real page.
        base.require(configure_via_api(api, {
            "Enabled": True,
            "PlaybackAutoCheck": True,
            "MaxConcurrentProbes": 2,
            "DetailedLog": False,
            "BatchAllLibraries": True,
            "BatchLibraryIds": "",
        }) == 204, "The fixture-preparation configuration was rejected.")

        # Step 1: the page saves an explicit partial scope; the native task must process only that library.
        page_save_via_browser(api, evidence_dir, "13-native-partial-scope", {
            "batchAllLibraries": False,
            "libraryIds": [strm_library],
        })
        base.require(configuration_snapshot(api)["BatchAllLibraries"] is False, "The page partial scope was not effective.")
        partial_task = run_native_task(api, container)
        base.require(terminal_status(partial_task) == "Completed", f"The partial-scope native task did not complete: {terminal_status(partial_task)}.")
        base.require(base.fingerprint_row(in_scope_item["Id"], in_scope_item["Id"]) is not None, "The native task did not process the in-scope STRM candidate.")
        base.require(base.fingerprint_row(out_scope_item["Id"], out_scope_item["Id"]) is None, "The native task processed an out-of-scope candidate under a page-saved partial scope.")

        # Step 2: the page switches to all libraries; the previously out-of-scope candidate is processed.
        page_save_via_browser(api, evidence_dir, "14-native-all-scope", {"batchAllLibraries": True})
        base.require(configuration_snapshot(api)["BatchAllLibraries"] is True, "The page all-library scope was not effective.")
        all_task = run_native_task(api, container)
        base.require(terminal_status(all_task) == "Completed", f"The all-library native task did not complete: {terminal_status(all_task)}.")
        base.require(base.fingerprint_row(out_scope_item["Id"], out_scope_item["Id"]) is not None, "Switching to all libraries did not process the previously out-of-scope candidate.")

        # Step 3: the page disables the playback check; the independent batch task must still run over the full scope.
        page_save_via_browser(api, evidence_dir, "15-native-playback-off", {"playbackAutoCheck": False})
        base.require(configuration_snapshot(api)["PlaybackAutoCheck"] is False, "The page playback check toggle was not effective.")
        playback_off_task = run_native_task(api, container)
        base.require(terminal_status(playback_off_task) == "Completed", f"The batch task did not run with the playback check disabled: {terminal_status(playback_off_task)}.")

        # Create the disabled-state fixture only now, so the earlier full-scope runs cannot have processed it. It
        # must stay unprocessed while the plugin is disabled and be handled after the page re-enables it.
        write_fixture(disabled_path, nonce + "disabled")
        api.refresh_library()
        disabled_item = api.wait_for_named_library_item(disabled_name)
        base.require(base.fingerprint_row(disabled_item["Id"], disabled_item["Id"]) is None, "The disabled-state fixture was already processed before the disable run.")

        # Step 4: the page disables the plugin; the native task must not start a new probe on the unprocessed item.
        page_save_via_browser(api, evidence_dir, "16-native-disabled", {"enabled": False})
        base.require(configuration_snapshot(api)["Enabled"] is False, "The page plugin-disable toggle was not effective.")
        disabled_task = run_native_task(api, container)
        disabled_status = terminal_status(disabled_task)
        base.require(disabled_status == "Cancelled", f"The native task did not end early while the plugin was disabled: {disabled_status}.")
        base.require(base.fingerprint_row(disabled_item["Id"], disabled_item["Id"]) is None, "The disabled plugin still processed a new candidate.")

        # Step 5: the page re-enables the plugin; the previously unprocessed candidate is now handled.
        page_save_via_browser(api, evidence_dir, "17-native-reenabled", {"enabled": True})
        base.require(configuration_snapshot(api)["Enabled"] is True, "The page re-enable toggle was not effective.")
        reenabled_task = run_native_task(api, container)
        base.require(terminal_status(reenabled_task) == "Completed", f"The re-enabled native task did not complete: {terminal_status(reenabled_task)}.")
        base.require(base.fingerprint_row(disabled_item["Id"], disabled_item["Id"]) is not None, "Re-enabling did not process the previously unprocessed candidate.")

        return {
            "evidence": [
                "13-native-partial-scope",
                "14-native-all-scope",
                "15-native-playback-off",
                "16-native-disabled",
                "17-native-reenabled",
            ],
            "in_scope_processed": True,
            "out_of_scope_unprocessed_under_partial": True,
            "out_of_scope_processed_under_all": True,
            "batch_ran_with_playback_check_disabled": True,
            "disabled_did_not_process_new_candidate": True,
            "reenabled_processed_candidate": True,
            "strm_library_id": strm_library,
            "local_library_id": local_library,
        }
    finally:
        for path in created:
            path.unlink(missing_ok=True)
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
        for name in (in_scope_name, out_scope_name, disabled_name):
            try:
                api.wait_for_named_library_item_absent(name)
            except Exception as error:
                record_problem(f"temporary library item {name!r} was not removed: {type(error).__name__}")


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
        summary["deployment"]["dll_sha256"] = hashlib.sha256(base.PLUGIN_SOURCE.read_bytes()).hexdigest()
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
        summary["scenario_stale_scope"] = scenario_stale_scope(api, evidence_dir, strm_library)
        summary["scenario_lost_save_response"] = scenario_lost_save_response(api, evidence_dir)
        summary["scenario_pre_submit_failure"] = scenario_pre_submit_failure(api, evidence_dir)
        summary["scenario_rejected_save"] = scenario_rejected_save(api, evidence_dir)
        summary["scenario_concurrency_bounds"] = scenario_concurrency_bounds(api, evidence_dir, strm_library)
        summary["scenario_empty_scope"] = scenario_empty_scope(api, evidence_dir, strm_library)
        summary["scenario_load_failure"] = scenario_load_failure(api, evidence_dir)
        summary["scenario_library_read_failure"] = scenario_library_read_failure(api, evidence_dir)
        summary["scenario_legacy_scope"] = scenario_legacy_scope(api, evidence_dir)
        summary["scenario_native_task_journey"] = scenario_native_task_journey(api, container, evidence_dir, strm_library, local_library)

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
