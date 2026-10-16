"""Guardrails for the package-acceptance tooling; these are not real Jellyfin acceptance tests."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


package_environment = load("package_environment", "scripts/package_environment.py")
integration = load("run_isolated_package_integration", "scripts/run_isolated_package_integration.py")


class PackageEnvironmentTests(unittest.TestCase):
    def test_compose_uses_a_separate_project_port_and_no_source_mount(self):
        with patch.object(package_environment, "PORT", 18099):
            with tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                with patch.object(package_environment, "WORK", work):
                    path = package_environment.write_compose()
                text = path.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1:18099:8096", text)
        # The server must never see source, SDK, NuGet or build output.
        for forbidden in ("/src", "/tests", "/scripts", "sdk", "nuget", "bin", "obj"):
            self.assertNotIn(forbidden, text, f"the package compose must not mount {forbidden!r}")
        self.assertIn("internal: true", text)

    def test_media_fixture_names_are_distinct_and_versioned_strm_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "strm").mkdir()
            with patch.object(package_environment, "WORK", work):
                path = package_environment.write_strm("Case", "http://media:8080/x.mp4", "a" * 40, 10)
                text = path.read_text(encoding="utf-8")
        self.assertIn("# strm-probe-version:1", text)
        self.assertIn("# strm-probe-sha1:" + "a" * 40, text)
        self.assertIn("# strm-probe-size:10", text)
        self.assertTrue(text.rstrip().endswith("http://media:8080/x.mp4"))

    def test_write_strm_omits_missing_optional_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "strm").mkdir()
            with patch.object(package_environment, "WORK", work):
                path = package_environment.write_strm("NoSha", "http://media:8080/x.mp4", None, None)
                text = path.read_text(encoding="utf-8")
        self.assertNotIn("strm-probe-sha1", text)
        self.assertNotIn("strm-probe-size", text)
        self.assertIn("# strm-probe-version:1", text)

    def test_deploy_archive_refuses_an_invalid_archive_without_disturbing_the_valid_one(self):
        publish = Path(tempfile.mkdtemp()) / "publish"
        publish.mkdir(parents=True)
        # Build a minimal valid archive via the real builder using the published test helpers.
        import tests.test_package_plugin as builder

        valid = builder.build_valid_archive(Path(tempfile.mkdtemp()))
        work = Path(tempfile.mkdtemp())
        (work / "config" / "plugins").mkdir(parents=True)
        with patch.object(package_environment, "WORK", work):
            first = package_environment.deploy_archive(valid)
            self.assertEqual(first["folder"], "Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0")
            before = package_environment.deployed_payload()
            self.assertTrue(before)
            # A GUID-mismatched archive must be refused and leave the payload untouched.
            broken = Path(tempfile.mkdtemp()) / "broken.zip"
            with zipfile.ZipFile(valid) as source, zipfile.ZipFile(broken, "w") as target:
                for name in source.namelist():
                    data = source.read(name)
                    if name.endswith("meta.json"):
                        meta = json.loads(data)
                        meta["guid"] = "00000000-0000-0000-0000-000000000000"
                        data = json.dumps(meta).encode()
                    target.writestr(name, data)
            with self.assertRaises((integration.package_plugin.PackageError, package_environment.PackageEnvironmentError)):
                package_environment.deploy_archive(broken)
            self.assertEqual(package_environment.deployed_payload(), before)


class IntegrationHelperTests(unittest.TestCase):
    def test_source_for_url_matches_by_hashed_path(self):
        url = "http://media:8080/package-mp4.mp4"
        response = {"MediaSources": [{"Path": url, "MediaStreams": [{"Type": "Video"}, {"Type": "Audio"}]}]}
        matched = integration.source_for_url(response, url)
        self.assertTrue(matched["path_matches"])
        self.assertTrue(matched["has_video"])
        self.assertIsNone(integration.source_for_url({"MediaSources": []}, url))

    def test_expected_url_hash_is_stable_sha256(self):
        import hashlib

        self.assertEqual(integration.expected_url_hash("x"), hashlib.sha256(b"x").hexdigest())

    def test_probe_calls_reads_the_redacted_counter(self):
        self.assertEqual(integration.probe_calls("... plugin probe calls 1, address persisted True"), 1)
        self.assertIsNone(integration.probe_calls("no counter here"))

    def test_benign_console_entries_do_not_mask_real_plugin_errors(self):
        benign = [
            {"text": "WebSocket connection to 'ws://x/socket' failed: ...", "url": "/web/node_modules.%40jellyfin.sdk.bundle.js"},
            {"text": "failed to get tab controller TypeError", "url": "/web/hometab.chunk.js"},
            {"text": "[Home] failed to get tab controller TypeError: Cannot read properties of undefined", "url": "/web/hometab.0ec3d9a22cad691c217e.chunk.js"},
            {"text": "HLS Error: Type: otherError Details: internalException Fatal: false", "url": "/web/main.jellyfin.bundle.js"},
            {"text": "HLS Error: Type: mediaError Details: bufferStalledError Fatal: false", "url": "/web/main.jellyfin.bundle.js"},
        ]
        for entry in benign:
            self.assertTrue(integration.benign_console_entry(entry), entry)
        # A fatal HLS error, or a non-HLS error from another bundle, must never be hidden.
        fatal = {"text": "HLS Error: Type: mediaError Details: bufferStalledError Fatal: true", "url": "/web/main.jellyfin.bundle.js"}
        self.assertFalse(integration.benign_console_entry(fatal))
        real = {"text": "strm-config-load-failed", "url": "/web/index.html"}
        self.assertFalse(integration.benign_console_entry(real))
        result = {"consoleErrors": [*benign, fatal, real]}
        self.assertEqual(integration.unexpected_console_errors(result), [fatal, real])

    def test_normalized_plugin_id_ignores_dashes_and_case(self):
        self.assertEqual(integration._normalized_id("B061643E-D17D-4C6E-8BA2-6B57E286BD20"),
                         integration._normalized_id(integration.PLUGIN_ID))


if __name__ == "__main__":
    unittest.main()
