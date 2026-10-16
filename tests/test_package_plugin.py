"""Guardrails for the local package builder and archive verifier.

These are tool tests: they prove the packaging preconditions and the archive verifier reject
unsafe or incomplete input. They are not real Jellyfin acceptance tests; the archive is
installed and exercised by scripts/run_isolated_package_integration.py.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("package_plugin", ROOT / "scripts" / "package_plugin.py")
package_plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_plugin)

DEPS_TARGET = ".NETCoreApp,Version=v10.0/linux-x64"
DEPS = {
    "runtimeTarget": {"name": DEPS_TARGET, "signature": ""},
    "targets": {
        DEPS_TARGET: {
            "Jellyfin.Plugin.StrmProbeOptimizer/0.1.0": {
                "runtime": {"Jellyfin.Plugin.StrmProbeOptimizer.dll": {}},
            },
            "Microsoft.Data.Sqlite/10.0.0": {},
            "Microsoft.Data.Sqlite.Core/10.0.0": {
                "runtime": {"lib/net8.0/Microsoft.Data.Sqlite.dll": {}},
            },
            "SQLite/3.53.4": {
                "native": {"runtimes/linux-x64/native/libe_sqlite3.so": {}},
            },
            "SQLitePCLRaw.bundle_e_sqlite3/3.0.5": {},
            "SQLitePCLRaw.config.e_sqlite3/3.0.5": {
                "runtime": {"lib/net8.0/SQLitePCLRaw.batteries_v2.dll": {}},
            },
            "SQLitePCLRaw.core/3.0.5": {
                "runtime": {"lib/net8.0/SQLitePCLRaw.core.dll": {}},
            },
            "SQLitePCLRaw.provider.e_sqlite3/3.0.5": {
                "runtime": {"lib/net8.0/SQLitePCLRaw.provider.e_sqlite3.dll": {}},
            },
        }
    },
    "libraries": {
        "Jellyfin.Plugin.StrmProbeOptimizer/0.1.0": {"type": "project"},
        "Microsoft.Data.Sqlite/10.0.0": {"type": "package", "path": "microsoft.data.sqlite/10.0.0"},
        "Microsoft.Data.Sqlite.Core/10.0.0": {"type": "package", "path": "microsoft.data.sqlite.core/10.0.0"},
        "SQLite/3.53.4": {"type": "package", "path": "sqlite/3.53.4"},
        "SQLitePCLRaw.bundle_e_sqlite3/3.0.5": {"type": "package", "path": "sqlitepclraw.bundle_e_sqlite3/3.0.5"},
        "SQLitePCLRaw.config.e_sqlite3/3.0.5": {"type": "package", "path": "sqlitepclraw.config.e_sqlite3/3.0.5"},
        "SQLitePCLRaw.core/3.0.5": {"type": "package", "path": "sqlitepclraw.core/3.0.5"},
        "SQLitePCLRaw.provider.e_sqlite3/3.0.5": {"type": "package", "path": "sqlitepclraw.provider.e_sqlite3/3.0.5"},
    },
}

MANIFEST = {
    "category": "General",
    "description": "test",
    "guid": package_plugin.PLUGIN_GUID,
    "name": "STRM Probe Optimizer",
    "overview": "test",
    "owner": "local-development",
    "targetAbi": "12.2.0.0",
    "version": "0.1.0.0",
    "assemblies": ["Jellyfin.Plugin.StrmProbeOptimizer.dll"],
}

PAYLOAD_FILES = {
    "Jellyfin.Plugin.StrmProbeOptimizer.dll": b"plugin-bytes",
    "Microsoft.Data.Sqlite.dll": b"sqlite-managed",
    "SQLitePCLRaw.batteries_v2.dll": b"batteries",
    "SQLitePCLRaw.core.dll": b"core",
    "SQLitePCLRaw.provider.e_sqlite3.dll": b"provider",
    "libe_sqlite3.so": b"native-sqlite",
}


def make_publish(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "Jellyfin.Plugin.StrmProbeOptimizer.deps.json").write_text(json.dumps(DEPS), encoding="utf-8")
    for name, data in PAYLOAD_FILES.items():
        (directory / name).write_bytes(data)
    return directory


def build_valid_archive(directory: Path, manifest: dict | None = None) -> Path:
    publish_dir = make_publish(directory / "publish")
    files, _ = package_plugin.build_archive_layout(
        publish_dir, manifest or MANIFEST, "0.1.0.0", "a" * 40, "10.0.401", "linux-x64", "Release")
    archive = directory / "plugin.zip"
    package_plugin.write_archive(archive, files)
    return archive


class PackageLayoutTests(unittest.TestCase):
    def test_payload_plan_includes_managed_and_linux_native_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            publish_dir = make_publish(Path(tmp))
            managed, native, _ = package_plugin.payload_plan(publish_dir, "linux-x64")
            self.assertIn("Microsoft.Data.Sqlite.dll", managed)
            self.assertIn("SQLitePCLRaw.core.dll", managed)
            self.assertIn("libe_sqlite3.so", native)
            # A foreign-platform native asset must never be selected.
            self.assertNotIn("e_sqlite3.dll", native)

    def test_build_layout_whitelists_every_shipped_assembly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            publish_dir = make_publish(Path(tmp))
            files, identity = package_plugin.build_archive_layout(
                publish_dir, MANIFEST, "0.1.0.0", "a" * 40, "10.0.401", "linux-x64", "Release")
            manifest = json.loads(files["Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0/meta.json"])
            self.assertEqual(len(manifest["assemblies"]), len(set(manifest["assemblies"])))
            self.assertIn("Jellyfin.Plugin.StrmProbeOptimizer.dll", manifest["assemblies"])
            self.assertIn("Microsoft.Data.Sqlite.dll", manifest["assemblies"])
            self.assertNotIn("libe_sqlite3.so", manifest["assemblies"])
            self.assertEqual(identity["runtime"], "linux-x64")
            self.assertEqual(identity["sourceRevision"], "a" * 40)

    def test_layout_excludes_pdb_and_non_linux_runtimes(self):
        with tempfile.TemporaryDirectory() as tmp:
            publish_dir = make_publish(Path(tmp))
            (publish_dir / "Jellyfin.Plugin.StrmProbeOptimizer.pdb").write_bytes(b"symbols")
            files, _ = package_plugin.build_archive_layout(
                publish_dir, MANIFEST, "0.1.0.0", "a" * 40, "10.0.401", "linux-x64", "Release")
            names = {Path(name).name for name in files}
            self.assertNotIn("Jellyfin.Plugin.StrmProbeOptimizer.pdb", names)
            self.assertNotIn("e_sqlite3.dll", names)

    def test_missing_native_asset_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            publish_dir = make_publish(Path(tmp))
            (publish_dir / "libe_sqlite3.so").unlink()
            with self.assertRaises(package_plugin.PackageError):
                package_plugin.build_archive_layout(
                    publish_dir, MANIFEST, "0.1.0.0", "a" * 40, "10.0.401", "linux-x64", "Release")

    def test_missing_dependency_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            publish_dir = make_publish(Path(tmp))
            (publish_dir / "Jellyfin.Plugin.StrmProbeOptimizer.deps.json").unlink()
            with self.assertRaises(package_plugin.PackageError):
                package_plugin.payload_plan(publish_dir, "linux-x64")

    def test_unsupported_runtime_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            publish_dir = make_publish(Path(tmp))
            with self.assertRaises(package_plugin.PackageError):
                package_plugin.payload_plan(publish_dir, "win-x64")

    def test_guid_and_abi_are_enforced_by_the_manifest_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta = Path(tmp) / "meta.json"
            bad_guid = dict(MANIFEST, guid="00000000-0000-0000-0000-000000000000")
            meta.write_text(json.dumps(bad_guid), encoding="utf-8")
            with patch.object(package_plugin, "META_SOURCE", meta):
                with self.assertRaises(package_plugin.PackageError):
                    package_plugin.load_plugin_manifest()
            bad_abi = dict(MANIFEST, targetAbi="10.11.0.0")
            meta.write_text(json.dumps(bad_abi), encoding="utf-8")
            with patch.object(package_plugin, "META_SOURCE", meta):
                with self.assertRaises(package_plugin.PackageError):
                    package_plugin.load_plugin_manifest()
            meta.write_text(json.dumps(MANIFEST), encoding="utf-8")
            with patch.object(package_plugin, "META_SOURCE", meta):
                self.assertEqual(package_plugin.load_plugin_manifest()["guid"], package_plugin.PLUGIN_GUID)

    def test_source_revision_rejects_a_short_or_non_hex_value(self):
        with self.assertRaises(package_plugin.PackageError):
            package_plugin.source_revision("abc")
        with self.assertRaises(package_plugin.PackageError):
            package_plugin.source_revision("z" * 40)
        self.assertEqual(package_plugin.source_revision("a" * 40), "a" * 40)

    def test_licence_mapping_covers_every_shipped_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "packages.lock.json"
            lock.write_text(json.dumps({"version": 1, "dependencies": {"net10.0": {
                "Microsoft.Data.Sqlite": {"resolved": "10.0.0"},
                "Microsoft.Data.Sqlite.Core": {"resolved": "10.0.0"},
                "SQLite": {"resolved": "3.53.4"},
                "SQLitePCLRaw.core": {"resolved": "3.0.5"},
                "SQLitePCLRaw.provider.e_sqlite3": {"resolved": "3.0.5"},
                "SQLitePCLRaw.config.e_sqlite3": {"resolved": "3.0.5"},
            }}}), encoding="utf-8")
            with patch.object(package_plugin, "LOCK_FILE", lock):
                notices = package_plugin.shipped_licenses(
                    ["Microsoft.Data.Sqlite.dll", "SQLitePCLRaw.core.dll", "SQLitePCLRaw.provider.e_sqlite3.dll",
                     "SQLitePCLRaw.batteries_v2.dll"],
                    ["libe_sqlite3.so"])
            packages = {entry["package"]: entry["license"] for entry in notices}
            self.assertEqual(packages["microsoft.data.sqlite"], "MIT")
            self.assertEqual(packages["sqlite"], "Public-Domain")
            self.assertEqual(packages["sqlitepclraw.core"], "Apache-2.0")
            self.assertTrue(all(entry["version"] for entry in notices))

    def test_unknown_shipped_dependency_without_licence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "packages.lock.json"
            lock.write_text(json.dumps({"dependencies": {"net10.0": {"Microsoft.Data.Sqlite": {"resolved": "10.0.0"}}}}), encoding="utf-8")
            with patch.object(package_plugin, "LOCK_FILE", lock), \
                    patch.object(package_plugin, "LICENSE_BY_PREFIX", ()):
                with self.assertRaises(package_plugin.PackageError):
                    package_plugin.shipped_licenses(["Microsoft.Data.Sqlite.dll"], [])
            with patch.object(package_plugin, "LOCK_FILE", lock):
                with self.assertRaises(package_plugin.PackageError):
                    package_plugin.shipped_licenses(["Unknown.Provider.dll"], [])


class ArchiveVerifierTests(unittest.TestCase):
    def test_valid_archive_passes_and_reports_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = build_valid_archive(Path(tmp))
            result = package_plugin.verify_archive(archive)
            self.assertEqual(result["guid"], package_plugin.PLUGIN_GUID)
            self.assertEqual(result["targetAbi"], "12.2.0.0")
            self.assertEqual(result["runtime"], "linux-x64")
            self.assertEqual(len(result["entries"]), 9)
            names = {Path(entry["path"]).name for entry in result["entries"]}
            self.assertIn("libe_sqlite3.so", names)
            self.assertIn("THIRD-PARTY-NOTICES.txt", names)

    def test_missing_native_asset_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = build_valid_archive(Path(tmp))
            broken = Path(tmp) / "broken.zip"
            with zipfile.ZipFile(archive) as source, zipfile.ZipFile(broken, "w") as target:
                for name in source.namelist():
                    if name.endswith("libe_sqlite3.so"):
                        continue
                    target.writestr(name, source.read(name))
            with self.assertRaises(package_plugin.PackageError):
                package_plugin.verify_archive(broken)

    def test_guid_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = build_valid_archive(Path(tmp))
            broken = Path(tmp) / "guid.zip"
            with zipfile.ZipFile(archive) as source, zipfile.ZipFile(broken, "w") as target:
                for name in source.namelist():
                    data = source.read(name)
                    if name.endswith("meta.json"):
                        manifest = json.loads(data)
                        manifest["guid"] = "00000000-0000-0000-0000-000000000000"
                        data = json.dumps(manifest).encode()
                    target.writestr(name, data)
            with self.assertRaises(package_plugin.PackageError):
                package_plugin.verify_archive(broken)

    def test_target_abi_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = build_valid_archive(Path(tmp))
            broken = Path(tmp) / "abi.zip"
            with zipfile.ZipFile(archive) as source, zipfile.ZipFile(broken, "w") as target:
                for name in source.namelist():
                    data = source.read(name)
                    if name.endswith("meta.json"):
                        manifest = json.loads(data)
                        manifest["targetAbi"] = "10.11.0.0"
                        data = json.dumps(manifest).encode()
                    target.writestr(name, data)
            with self.assertRaises(package_plugin.PackageError):
                package_plugin.verify_archive(broken)

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = build_valid_archive(Path(tmp))
            broken = Path(tmp) / "traversal.zip"
            with zipfile.ZipFile(archive) as source, zipfile.ZipFile(broken, "w") as target:
                for name in source.namelist():
                    target.writestr(name, source.read(name))
                target.writestr("Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0/../evil.dll", b"x")
            with self.assertRaises(package_plugin.PackageError):
                package_plugin.verify_archive(broken)

    def test_symbolic_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = build_valid_archive(Path(tmp))
            broken = Path(tmp) / "symlink.zip"
            with zipfile.ZipFile(archive) as source, zipfile.ZipFile(broken, "w") as target:
                for name in source.namelist():
                    target.writestr(name, source.read(name))
                info = zipfile.ZipInfo("Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0/link")
                info.external_attr = 0o120777 << 16
                target.writestr(info, "meta.json")
            with self.assertRaises(package_plugin.PackageError):
                package_plugin.verify_archive(broken)

    def test_truncated_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = build_valid_archive(Path(tmp))
            broken = Path(tmp) / "truncated.zip"
            original = archive.read_bytes()
            broken.write_bytes(original[: len(original) // 2])
            with self.assertRaises((package_plugin.PackageError, zipfile.BadZipFile)):
                package_plugin.verify_archive(broken)

    def test_two_top_level_folders_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = build_valid_archive(Path(tmp))
            broken = Path(tmp) / "two-roots.zip"
            with zipfile.ZipFile(archive) as source, zipfile.ZipFile(broken, "w") as target:
                for name in source.namelist():
                    target.writestr(name, source.read(name))
                target.writestr("OtherPlugin_1.0.0.0/meta.json", b"{}")
            with self.assertRaises(package_plugin.PackageError):
                package_plugin.verify_archive(broken)

    def test_archive_is_deterministic_for_identical_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = build_valid_archive(Path(tmp) / "a")
            second = build_valid_archive(Path(tmp) / "b")
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_missing_archive_is_rejected(self):
        with self.assertRaises(package_plugin.PackageError):
            package_plugin.verify_archive(Path("/nonexistent/package.zip"))


if __name__ == "__main__":
    unittest.main()
