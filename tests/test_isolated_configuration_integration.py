"""Guardrails for the isolated configuration-page integration script and its browser driver.

These are not real Jellyfin acceptance tests; they protect the redaction, failure-classification and restoration
logic of the tooling so a run cannot silently pass with an ignored plugin error or an unverified restore.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_isolated_configuration_integration", ROOT / "scripts" / "run_isolated_configuration_integration.py"
)
configuration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(configuration)


class ConfigurationScriptGuardTests(unittest.TestCase):
    def test_benign_noise_is_limited_to_known_jellyfin_bundles(self):
        # Jellyfin's own pre-login socket, navigation cancel and plugin-repo metadata 404 are ignored.
        self.assertTrue(configuration.is_benign_browser_noise({
            "text": "WebSocket connection to 'ws://127.0.0.1:18096/socket' failed: Error during WebSocket handshake: Unexpected response code: 403",
            "url": "http://127.0.0.1:18096/web/node_modules.%40jellyfin.sdk.bundle.js",
        }))
        self.assertTrue(configuration.is_benign_browser_noise({
            "text": "e: CancelledError\n    at Object.cancel",
            "url": "http://127.0.0.1:18096/web/hometab.abc.chunk.js",
        }))
        self.assertTrue(configuration.is_benign_browser_noise({
            "text": "Failed to load resource: the server responded with a status of 404 (Not Found)",
            "url": "http://127.0.0.1:18096/Packages/STRM%20Probe%20Optimizer?assemblyGuid=abc",
        }))

    def test_plugin_page_errors_are_never_classified_as_benign(self):
        # A load failure raised by this plugin's page must always be treated as a real error.
        self.assertFalse(configuration.is_benign_browser_noise({
            "text": "strm-config-load-failed [object Response]",
            "url": "",
        }))
        # A different 404 (not the plugin-repo metadata endpoint) must fail the scenario.
        self.assertFalse(configuration.is_benign_browser_noise({
            "text": "Failed to load resource: the server responded with a status of 404 (Not Found)",
            "url": "http://127.0.0.1:18096/Plugins/b061643e-d17d-4c6e-8ba2-6b57e286bd20/Configuration",
        }))
        # A page error from another bundle that is not an allowlisted Jellyfin noise source must fail.
        self.assertFalse(configuration.is_benign_browser_noise({
            "text": "TypeError: something broke",
            "url": "http://127.0.0.1:18096/web/configurationpage.abc.chunk.js",
        }))

    def test_scrollbuttons_teardown_race_is_classified_only_by_its_exact_bundle(self):
        # Jellyfin's own emby-scrollbuttons teardown race is ignored only for the exact scrollbuttons bundle.
        self.assertTrue(configuration.is_benign_browser_noise({
            "text": "t.scrollHandler is not a function",
            "url": "http://127.0.0.1:18096/web/49275.fcf2b77489e84c80e220.chunk.js",
        }))
        # The same message from another bundle, or a different message from the scrollbuttons bundle, is not noise.
        self.assertFalse(configuration.is_benign_browser_noise({
            "text": "t.scrollHandler is not a function",
            "url": "http://127.0.0.1:18096/web/configurationpage.abc.chunk.js",
        }))
        self.assertFalse(configuration.is_benign_browser_noise({
            "text": "t.otherHandler is not a function",
            "url": "http://127.0.0.1:18096/web/49275.fcf2b77489e84c80e220.chunk.js",
        }))

    def test_configuration_payload_from_xml_round_trips_all_five_fields(self):
        xml = (
            "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
            "<PluginConfiguration>\n"
            "  <Enabled>false</Enabled>\n"
            "  <PlaybackAutoCheck>true</PlaybackAutoCheck>\n"
            "  <MaxConcurrentProbes>5</MaxConcurrentProbes>\n"
            "  <DetailedLog>true</DetailedLog>\n"
            "  <BatchAllLibraries>false</BatchAllLibraries>\n"
            "  <BatchLibraryIds>77887268a073916466e59eae1c052c2c</BatchLibraryIds>\n"
            "</PluginConfiguration>\n"
        )
        payload = configuration.configuration_payload_from_xml(xml.encode("utf-8"))
        self.assertEqual(payload, {
            "Enabled": False,
            "PlaybackAutoCheck": True,
            "MaxConcurrentProbes": 5,
            "DetailedLog": True,
            "BatchAllLibraries": False,
            "BatchLibraryIds": "77887268a073916466e59eae1c052c2c",
        })

    def test_missing_new_fields_default_to_the_documented_values(self):
        xml = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<PluginConfiguration></PluginConfiguration>\n"
        payload = configuration.configuration_payload_from_xml(xml.encode("utf-8"))
        self.assertEqual(payload["Enabled"], True)
        self.assertEqual(payload["PlaybackAutoCheck"], True)
        self.assertEqual(payload["MaxConcurrentProbes"], 2)
        self.assertEqual(payload["DetailedLog"], False)
        self.assertEqual(payload["BatchAllLibraries"], True)
        self.assertEqual(payload["BatchLibraryIds"], "")

    def test_browser_preparation_commands_pin_playwright_and_chromium(self):
        commands = configuration.browser_preparation_commands()
        self.assertTrue(any("prepare_browser_tools.py" in command for command in commands))
        # The preparation helper pins the same playwright version and Chromium revision this runner expects.
        self.assertEqual(configuration.PLAYWRIGHT_PACKAGE, "playwright@1.55.0")
        self.assertEqual(configuration.CHROMIUM_REVISION, "chromium-1187")
        helper = (ROOT / "scripts" / "prepare_browser_tools.py").read_text(encoding="utf-8")
        self.assertIn(configuration.PLAYWRIGHT_PACKAGE, helper)
        self.assertIn(configuration.CHROMIUM_REVISION, helper)
        self.assertIn('"playwright", "install", "chromium"', helper)

    def test_driver_declares_the_five_editable_fields_and_no_second_run_entry(self):
        driver = (ROOT / "scripts" / "configuration_page_driver.mjs").read_text(encoding="utf-8")
        for field in ("#Enabled", "#PlaybackAutoCheck", "#MaxConcurrentProbes", "#DetailedLog", "#BatchAllLibraries"):
            self.assertIn(field, driver)
        self.assertNotIn("ScheduledTasks/Running", driver)
        self.assertNotIn("updatePluginConfiguration(pluginUniqueId, config).then(function (result)", driver)
        # The driver pins a real locale so headless Chromium never inherits a POSIX locale that breaks Jellyfin.
        self.assertIn("locale: 'zh-CN'", driver)

    def test_runner_asserts_the_stale_scope_and_unconfirmed_save_behaviour(self):
        runner = (ROOT / "scripts" / "run_isolated_configuration_integration.py").read_text(encoding="utf-8")
        # FR-U1: the stale-scope scenario must assert the blocked save sent no POST and the corrected save dropped it.
        self.assertIn("attemptsAfterBlock", runner)
        self.assertIn("The stale scope must not produce a configuration POST", runner)
        # FR-U2: the lost-response scenario must assert an unconfirmed result rather than an unchanged promise.
        self.assertIn("save-unconfirmed", runner)
        self.assertIn("The page still promised the configuration was unchanged", runner)
        # The native-task journey must be driven by page saves and check the real terminal result.
        self.assertIn("scenario_native_task_journey", runner)
        self.assertIn("The disabled plugin still processed a new candidate", runner)

    def test_restoration_reports_a_problem_when_the_file_differs(self):
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.xml"
            original = b"<PluginConfiguration></PluginConfiguration>"
            path.write_bytes(b"<PluginConfiguration><Enabled>false</Enabled></PluginConfiguration>")
            with patch.object(configuration, "CONFIGURATION_FILE", path), patch.object(
                configuration.base, "JellyfinApi", side_effect=RuntimeError("api unavailable")
            ):
                result = configuration.restore_configuration(original, {})
        self.assertTrue(result.startswith("NOT RESTORED"), result)


if __name__ == "__main__":
    unittest.main()
