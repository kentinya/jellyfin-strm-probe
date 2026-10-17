"""Guardrails for the package-acceptance tooling; these are not real Jellyfin acceptance tests."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    # Register under the plain module name so the environment/integration scripts' lazy
    # ``import package_plugin`` resolves to the same object and exception classes.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


package_environment = load("package_environment", "scripts/package_environment.py")
integration = load("run_isolated_package_integration", "scripts/run_isolated_package_integration.py")
package_plugin = load("package_plugin", "scripts/package_plugin.py")


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
        # Build a minimal valid archive with its published sidecar via the real builder helpers.
        import tests.test_package_plugin as builder

        source = Path(tempfile.mkdtemp())
        valid = builder.build_valid_archive_with_sidecar(source)
        work = Path(tempfile.mkdtemp())
        (work / "config" / "plugins").mkdir(parents=True)
        with patch.object(package_environment, "WORK", work):
            first = package_environment.deploy_archive(valid)
            self.assertEqual(first["folder"], "Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0")
            before = package_environment.deployed_payload()
            self.assertTrue(before)
            # A GUID-mismatched archive with a stale sidecar must be refused and leave the payload untouched.
            broken = Path(tempfile.mkdtemp()) / "broken.zip"
            with zipfile.ZipFile(valid) as source_zip, zipfile.ZipFile(broken, "w") as target:
                for name in source_zip.namelist():
                    data = source_zip.read(name)
                    if name.endswith("meta.json"):
                        meta = json.loads(data)
                        meta["guid"] = "00000000-0000-0000-0000-000000000000"
                        data = json.dumps(meta).encode()
                    target.writestr(name, data)
            shutil.copy2(package_plugin.sidecar_manifest_path(valid), package_plugin.sidecar_manifest_path(broken))
            with self.assertRaises((package_plugin.PackageError, package_environment.PackageEnvironmentError)):
                package_environment.deploy_archive(broken)
            self.assertEqual(package_environment.deployed_payload(), before)

    def test_deploy_archive_refuses_an_archive_without_its_sidecar(self):
        import tests.test_package_plugin as builder

        source = Path(tempfile.mkdtemp())
        valid = builder.build_valid_archive_with_sidecar(source)
        orphan = Path(tempfile.mkdtemp()) / "orphan.zip"
        shutil.copy2(valid, orphan)
        work = Path(tempfile.mkdtemp())
        (work / "config" / "plugins").mkdir(parents=True)
        with patch.object(package_environment, "WORK", work):
            with self.assertRaises((package_plugin.PackageError, package_environment.PackageEnvironmentError)):
                package_environment.deploy_archive(orphan)
            self.assertEqual(package_environment.deployed_payload(), {})

    def test_deploy_archive_refuses_a_foreign_plugins_symlink(self):
        import tests.test_package_plugin as builder

        source = Path(tempfile.mkdtemp())
        valid = builder.build_valid_archive_with_sidecar(source)
        work = Path(tempfile.mkdtemp())
        foreign = Path(tempfile.mkdtemp())
        (work / "config").mkdir(parents=True)
        (work / "config" / "plugins").symlink_to(foreign, target_is_directory=True)
        sentinel = foreign / "foreign-sentinel.txt"
        sentinel.write_text("must remain untouched", encoding="utf-8")
        with patch.object(package_environment, "WORK", work):
            with self.assertRaises(package_environment.PackageEnvironmentError):
                package_environment.deploy_archive(valid)
        self.assertTrue(sentinel.is_file(), "a foreign deployment directory was modified")

    def test_remove_deployed_plugin_refuses_a_symlinked_folder(self):
        work = Path(tempfile.mkdtemp())
        plugins = work / "config" / "plugins"
        plugins.mkdir(parents=True)
        foreign = Path(tempfile.mkdtemp())
        (foreign / "sentinel.txt").write_text("keep", encoding="utf-8")
        (plugins / "Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0").symlink_to(foreign, target_is_directory=True)
        with patch.object(package_environment, "WORK", work):
            with self.assertRaises(package_environment.PackageEnvironmentError):
                package_environment.remove_deployed_plugin()
        self.assertTrue((foreign / "sentinel.txt").is_file())

    def test_require_owned_path_rejects_escape_and_symlink(self):
        work = Path(tempfile.mkdtemp())
        (work / "config").mkdir()
        foreign = Path(tempfile.mkdtemp())
        (work / "config" / "link").symlink_to(foreign, target_is_directory=True)
        with patch.object(package_environment, "WORK", work):
            with self.assertRaises(package_environment.PackageEnvironmentError):
                package_environment.require_owned_path(work / "config" / "link" / "x")
            with self.assertRaises(package_environment.PackageEnvironmentError):
                package_environment.require_owned_path(Path("/etc/passwd"))
            # A normal owned path resolves.
            self.assertTrue(str(package_environment.require_owned_path(work / "config")))

    def test_require_owned_path_rejects_an_internal_parent_symlink(self):
        # A symlink that points back inside the workspace must still be refused: resolve() would
        # otherwise strip it and the raw path chain would be missed.
        work = Path(tempfile.mkdtemp())
        (work / "actual").mkdir()
        (work / "alias").symlink_to(work / "actual", target_is_directory=True)
        with patch.object(package_environment, "WORK", work):
            with self.assertRaises(package_environment.PackageEnvironmentError):
                package_environment.require_owned_path(work / "alias" / "file")

    def test_backup_state_refuses_a_symlinked_destination_file(self):
        work = Path(tempfile.mkdtemp())
        config = work / "config" / "plugins" / "configurations" / "Jellyfin.Plugin.StrmProbeOptimizer.xml"
        database = work / "config" / "data" / "plugins" / "b061643ed17d4c6e8ba26b57e286bd20" / "strm-fingerprints.db"
        config.parent.mkdir(parents=True)
        database.parent.mkdir(parents=True)
        config.write_bytes(b"owned configuration")
        database.write_bytes(b"owned fingerprint")
        backup = work / "backup"
        backup.mkdir()
        foreign = Path(tempfile.mkdtemp()) / "sentinel"
        foreign.write_bytes(b"foreign must remain untouched")
        (backup / config.name).symlink_to(foreign)
        with patch.object(package_environment, "WORK", work):
            with self.assertRaises(package_environment.PackageEnvironmentError):
                package_environment.backup_state(backup)
        self.assertEqual(foreign.read_bytes(), b"foreign must remain untouched")

    def test_backup_and_restore_round_trip_on_owned_paths(self):
        work = Path(tempfile.mkdtemp())
        config = work / "config" / "plugins" / "configurations" / "Jellyfin.Plugin.StrmProbeOptimizer.xml"
        database = work / "config" / "data" / "plugins" / "b061643ed17d4c6e8ba26b57e286bd20" / "strm-fingerprints.db"
        config.parent.mkdir(parents=True)
        database.parent.mkdir(parents=True)
        config.write_bytes(b"owned configuration")
        database.write_bytes(b"owned fingerprint")
        with patch.object(package_environment, "WORK", work):
            backup = package_environment.backup_state(work / "backup")
            config.write_bytes(b"mutated")
            restored = package_environment.restore_state(work / "backup")
        self.assertEqual(restored["configuration"]["sha256"], backup["configuration"]["sha256"])
        self.assertEqual(config.read_bytes(), b"owned configuration")

    def test_select_workspace_marks_fresh_and_refuses_unmarked_reuse(self):
        base = Path(tempfile.mkdtemp())
        with patch.object(package_environment, "BASE", base):
            reused = base / "reused"
            reused.mkdir()
            (reused / "prior.strm").write_bytes(b"pre-existing fixture")
            with self.assertRaises(package_environment.PackageEnvironmentError):
                package_environment.select_workspace(reused)
            self.assertEqual((reused / "prior.strm").read_bytes(), b"pre-existing fixture")
            fresh = package_environment.select_workspace(base / "fresh")
            with patch.object(package_environment, "WORK", fresh):
                package_environment.workspace()
            self.assertTrue((fresh / package_environment.RUN_MARKER).is_file())
            # A previously marked workspace may be re-selected.
            self.assertEqual(package_environment.select_workspace(fresh), fresh)

    def test_reconcile_refuses_disturbed_input_and_cleanup_requires_marker(self):
        base = Path(tempfile.mkdtemp())
        with patch.object(package_environment, "BASE", base):
            workspace = package_environment.select_workspace(base / "run")
            with patch.object(package_environment, "WORK", workspace):
                package_environment.workspace()
                (workspace / "strm").mkdir(exist_ok=True)
                prior = workspace / "strm" / "prior.strm"
                prior.write_bytes(b"pre-existing fixture")
                before = package_environment.capture_instance_state()
                prior.write_bytes(b"changed during run")
                with self.assertRaises(package_environment.PackageEnvironmentError):
                    package_environment.reconcile_instance_state(before)
            # A foreign directory without the marker must never be cleaned up.
            foreign = base / "foreign"
            foreign.mkdir()
            (foreign / "keep.txt").write_bytes(b"keep")
            with patch.object(package_environment, "WORK", foreign), \
                    patch.object(package_environment, "compose"):
                with self.assertRaises(package_environment.PackageEnvironmentError):
                    package_environment.cleanup_instance()
            self.assertTrue((foreign / "keep.txt").is_file())
            # The marked workspace is removed in full.
            with patch.object(package_environment, "WORK", workspace), \
                    patch.object(package_environment, "compose"):
                result = package_environment.cleanup_instance()
            self.assertEqual(result["status"], "CLEANED")
            self.assertFalse(workspace.exists())


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
