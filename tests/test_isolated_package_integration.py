"""Guardrails for the package-acceptance tooling; these are not real Jellyfin acceptance tests."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    # Reuse an already-imported module so the whole test session shares one set of exception
    # classes; re-executing a module under the same name would create a second PackageError and
    # make assertRaises in a sibling test module miss the raised exception.
    if name in sys.modules:
        return sys.modules[name]
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
        # The lock is injected from a temporary directory so the guard test never depends on the
        # ignored artifacts/dev-env/images.lock.json of a provisioned host.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock = {"spec": package_environment.SPEC, "images": {
                "server": "jellyfin/jellyfin@sha256:" + "a" * 64,
                "media": "python@sha256:" + "b" * 64}}
            lock_path = root / "artifacts" / "dev-env" / "images.lock.json"
            lock_path.parent.mkdir(parents=True)
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            with patch.object(package_environment, "ROOT", root), \
                    patch.object(package_environment, "PORT", 18099):
                with tempfile.TemporaryDirectory() as work_tmp:
                    work = Path(work_tmp)
                    with patch.object(package_environment, "WORK", work):
                        path = package_environment.write_compose()
                    text = path.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1:18099:8096", text)
        self.assertIn("jellyfin/jellyfin@sha256:" + "a" * 64, text)
        # The server must never see source, SDK, NuGet or build output.
        for forbidden in ("/src", "/tests", "/scripts", "sdk", "nuget", "bin", "obj"):
            self.assertNotIn(forbidden, text, f"the package compose must not mount {forbidden!r}")
        self.assertIn("internal: true", text)

    def test_compose_refuses_a_missing_mutable_or_foreign_image_lock(self):
        # The injected-lock path above must not weaken the real lock rules.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(package_environment, "ROOT", root):
                with self.assertRaisesRegex(package_environment.PackageEnvironmentError,
                                            "immutable image lock is missing"):
                    package_environment.load_image_lock()
                lock_path = root / "artifacts" / "dev-env" / "images.lock.json"
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                cases = {
                    "mutable tag": {"spec": package_environment.SPEC, "images": {
                        "server": "jellyfin/jellyfin:12.2",
                        "media": "python@sha256:" + "b" * 64}},
                    "foreign specification": {"spec": {"server": {"version": "other"}}, "images": {
                        "server": "jellyfin/jellyfin@sha256:" + "a" * 64,
                        "media": "python@sha256:" + "b" * 64}},
                    "wrong repository": {"spec": package_environment.SPEC, "images": {
                        "server": "python@sha256:" + "a" * 64,
                        "media": "python@sha256:" + "b" * 64}},
                }
                for label, data in cases.items():
                    with self.subTest(label), self.assertRaises(
                            package_environment.PackageEnvironmentError):
                        lock_path.write_text(json.dumps(data), encoding="utf-8")
                        package_environment.load_image_lock()

    def test_inspect_owned_container_states_rejects_forced_exit(self):
        listed = subprocess.CompletedProcess([], 0, stdout="container-id\n", stderr="")
        inspected = subprocess.CompletedProcess([], 0, stdout=json.dumps([{
            "Name": "/package-media",
            "State": {"Status": "exited", "ExitCode": 137, "OOMKilled": False,
                      "Error": "", "FinishedAt": "2026-10-19T00:00:00Z"},
        }]), stderr="")
        with patch.object(package_environment, "run", side_effect=[listed, inspected]):
            states = package_environment.inspect_owned_container_states()
        self.assertEqual(states[0]["exit_code"], 137)
        self.assertFalse(states[0]["oom_killed"])

    def test_inspect_owned_container_states_records_clean_exit(self):
        listed = subprocess.CompletedProcess([], 0, stdout="container-id\n", stderr="")
        inspected = subprocess.CompletedProcess([], 0, stdout=json.dumps([{
            "Name": "/package-jellyfin",
            "State": {"Status": "exited", "ExitCode": 0, "OOMKilled": False,
                      "Error": "", "FinishedAt": "2026-10-19T00:00:00Z"},
        }]), stderr="")
        with patch.object(package_environment, "run", side_effect=[listed, inspected]):
            states = package_environment.inspect_owned_container_states()
        self.assertEqual(states, [{
            "name": "package-jellyfin", "service": None, "status": "exited", "exit_code": 0,
            "oom_killed": False, "error": "", "finished_at": "2026-10-19T00:00:00Z",
        }])

    def test_cleanup_refuses_forced_container_exit_and_keeps_workspace(self):
        base = Path(tempfile.mkdtemp())
        with patch.object(package_environment, "BASE", base):
            workspace = package_environment.select_workspace(base / "run")
            with patch.object(package_environment, "WORK", workspace), \
                    patch.object(package_environment, "compose"), \
                    patch.object(package_environment, "inspect_owned_container_states", return_value=[{
                        "name": "package-media", "status": "exited", "exit_code": 137,
                        "oom_killed": False, "error": "", "finished_at": "now",
                    }]):
                with self.assertRaisesRegex(package_environment.PackageEnvironmentError,
                                             "did not terminate cleanly"):
                    package_environment.cleanup_instance()
            self.assertTrue(workspace.exists())

    def test_started_cleanup_requires_both_service_exit_records(self):
        for services in ([], [{"service": "jellyfin", "status": "exited", "exit_code": 0,
                               "oom_killed": False, "error": "", "finished_at": "now"}]):
            with self.subTest(services=services), tempfile.TemporaryDirectory() as tmp:
                with patch.object(package_environment, "BASE", Path(tmp)):
                    workspace = package_environment.select_workspace(Path(tmp) / "run")
                    with patch.object(package_environment, "WORK", workspace), \
                         patch.object(package_environment, "compose"), \
                         patch.object(package_environment, "inspect_owned_container_states", return_value=services):
                        with self.assertRaisesRegex(package_environment.PackageEnvironmentError, "exit evidence"):
                            package_environment.cleanup_instance(required_services=("jellyfin", "media"))
                    self.assertTrue(workspace.exists())

    def test_cleanup_rejects_active_incomplete_and_error_states(self):
        clean = {"status": "exited", "exit_code": 0, "oom_killed": False,
                 "error": "", "finished_at": "2026-10-19T00:00:00Z"}
        for values in ({"status": "restarting"}, {"status": "paused"}, {"oom_killed": None},
                       {"error": "runtime error"}, {"finished_at": None}):
            with self.subTest(values=values), tempfile.TemporaryDirectory() as tmp:
                with patch.object(package_environment, "BASE", Path(tmp)):
                    workspace = package_environment.select_workspace(Path(tmp) / "run")
                    with patch.object(package_environment, "WORK", workspace), \
                         patch.object(package_environment, "compose"), \
                         patch.object(package_environment, "inspect_owned_container_states",
                                      return_value=[{**clean, **values}]):
                        with self.assertRaisesRegex(package_environment.PackageEnvironmentError, "terminate cleanly"):
                            package_environment.cleanup_instance()
                    self.assertTrue(workspace.exists())

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

    def test_select_workspace_claims_fresh_and_refuses_any_existing_directory(self):
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
            # A workspace already claimed (even by this process) is never re-selected: a fresh
            # run must use a new or empty directory.
            with self.assertRaises(package_environment.PackageEnvironmentError):
                package_environment.select_workspace(fresh)
            # An existing empty directory is still claimable.
            empty = base / "empty"
            empty.mkdir()
            self.assertEqual(package_environment.select_workspace(empty), empty)

    def test_select_workspace_refuses_a_previous_runs_marked_directory(self):
        # A directory left by an earlier run still carries its marker and data; the current run
        # must refuse it rather than reuse or later delete it (BR-41-3b).
        base = Path(tempfile.mkdtemp())
        with patch.object(package_environment, "BASE", base):
            previous = base / "run-previous"
            previous.mkdir()
            (previous / package_environment.RUN_MARKER).write_text("previous-run-token\n", encoding="utf-8")
            prior = previous / "prior.strm"
            prior.write_bytes(b"previous run data")
            with self.assertRaises(package_environment.PackageEnvironmentError):
                package_environment.select_workspace(previous)
            self.assertEqual(prior.read_bytes(), b"previous run data")

    def test_workspace_refuses_to_write_into_a_different_runs_workspace(self):
        base = Path(tempfile.mkdtemp())
        with patch.object(package_environment, "BASE", base):
            owned = package_environment.select_workspace(base / "owned")
            # A different run (simulated by replacing the on-disk token) must not be written to.
            (owned / package_environment.RUN_MARKER).write_text("some-other-run\n", encoding="utf-8")
            with patch.object(package_environment, "WORK", owned):
                with self.assertRaises(package_environment.PackageEnvironmentError):
                    package_environment.workspace()

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
            # A previous run's marked workspace is also never cleaned up by this run.
            previous = base / "previous"
            previous.mkdir()
            (previous / package_environment.RUN_MARKER).write_text("previous-token\n", encoding="utf-8")
            prior = previous / "prior.strm"
            prior.write_bytes(b"previous run data")
            with patch.object(package_environment, "WORK", previous), \
                    patch.object(package_environment, "compose"):
                with self.assertRaises(package_environment.PackageEnvironmentError):
                    package_environment.cleanup_instance()
            self.assertEqual(prior.read_bytes(), b"previous run data")
            # The marked workspace is removed in full.
            with patch.object(package_environment, "WORK", workspace), \
                    patch.object(package_environment, "compose"):
                result = package_environment.cleanup_instance()
            self.assertEqual(result["status"], "CLEANED")
            self.assertFalse(workspace.exists())


class PackageRunOwnershipTests(unittest.TestCase):
    """CLI-level ownership and teardown behaviour for the package-acceptance run (BR-41-3b)."""

    def _valid_package(self, directory: Path) -> Path:
        import tests.test_package_plugin as builder

        directory.mkdir(parents=True, exist_ok=True)
        return builder.build_valid_archive_with_sidecar(directory)

    def _run_main(self, argv: list[str]) -> int:
        with patch.object(sys, "argv", ["run_isolated_package_integration", *argv]):
            return integration.main()

    def _digests(self, directory: Path) -> dict[str, str]:
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in directory.iterdir()}

    def test_missing_package_leaves_a_previous_runs_workspace_untouched(self):
        base = Path(tempfile.mkdtemp())
        previous = base / "run-previous"
        previous.mkdir()
        (previous / package_environment.RUN_MARKER).write_text("previous-run-token\n", encoding="utf-8")
        (previous / "prior.strm").write_bytes(b"previous run data")
        before = self._digests(previous)
        with patch.object(package_environment, "BASE", base), \
                patch.object(package_environment, "compose") as compose:
            code = self._run_main(["--package", str(base / "missing.zip"),
                                   "--scenario", "invalid", "--workspace", str(previous)])
        self.assertEqual(code, 1)
        compose.assert_not_called()
        self.assertTrue(previous.is_dir(), "a previous run's workspace was removed")
        self.assertEqual(self._digests(previous), before)

    def test_broken_package_leaves_a_previous_runs_workspace_untouched(self):
        base = Path(tempfile.mkdtemp())
        valid = self._valid_package(base / "pkg")
        broken = base / "broken.zip"
        broken.write_bytes(valid.read_bytes()[: len(valid.read_bytes()) // 2])
        previous = base / "run-previous"
        previous.mkdir()
        (previous / package_environment.RUN_MARKER).write_text("previous-run-token\n", encoding="utf-8")
        (previous / "prior.strm").write_bytes(b"previous run data")
        before = self._digests(previous)
        with patch.object(package_environment, "BASE", base), \
                patch.object(package_environment, "compose") as compose:
            code = self._run_main(["--package", str(broken),
                                   "--scenario", "invalid", "--workspace", str(previous)])
        self.assertEqual(code, 1)
        compose.assert_not_called()
        self.assertTrue(previous.is_dir(), "a previous run's workspace was removed")
        self.assertEqual(self._digests(previous), before)

    def test_fresh_run_cleans_up_its_own_workspace_on_scenario_failure(self):
        base = Path(tempfile.mkdtemp())
        package = self._valid_package(base / "pkg")
        created: dict[str, Path] = {}
        real_select = package_environment.select_workspace

        def spy_select(path=None):
            workspace = real_select(path)
            created["workspace"] = workspace
            return workspace

        with patch.object(package_environment, "BASE", base), \
                patch.object(package_environment, "select_workspace", side_effect=spy_select), \
                patch.object(package_environment, "compose"), \
                patch.object(integration, "scenario_invalid", side_effect=RuntimeError("scenario boom")):
            code = self._run_main(["--package", str(package), "--scenario", "invalid"])
        self.assertEqual(code, 1)
        self.assertIn("workspace", created)
        self.assertFalse(created["workspace"].exists(), "the run did not clean up its own workspace")

    def test_cleanup_failure_turns_the_overall_result_into_fail(self):
        base = Path(tempfile.mkdtemp())
        package = self._valid_package(base / "pkg")
        with patch.object(package_environment, "BASE", base), \
                patch.object(package_environment, "compose"), \
                patch.object(integration, "scenario_invalid", return_value={}), \
                patch.object(package_environment, "cleanup_instance",
                             side_effect=package_environment.PackageEnvironmentError("cleanup failed")):
            code = self._run_main(["--package", str(package), "--scenario", "invalid"])
        self.assertEqual(code, 1)

    def test_keep_workspace_leaves_the_fresh_workspace(self):
        base = Path(tempfile.mkdtemp())
        package = self._valid_package(base / "pkg")
        created: dict[str, Path] = {}
        real_select = package_environment.select_workspace

        def spy_select(path=None):
            workspace = real_select(path)
            created["workspace"] = workspace
            return workspace

        with patch.object(package_environment, "BASE", base), \
                patch.object(package_environment, "select_workspace", side_effect=spy_select), \
                patch.object(package_environment, "compose"), \
                patch.object(integration, "scenario_invalid", return_value={}):
            code = self._run_main(["--package", str(package), "--scenario", "invalid", "--keep-workspace"])
        self.assertEqual(code, 0)
        self.assertTrue(created["workspace"].is_dir())


def valid_archive(directory: Path) -> Path:
    import tests.test_package_plugin as builder

    directory.mkdir(parents=True, exist_ok=True)
    return builder.build_valid_archive_with_sidecar(directory)


def run_main(argv: list[str]) -> int:
    with patch.object(sys, "argv", ["run_isolated_package_integration", *argv]):
        return integration.main()


class ServerVersionSelectionTests(unittest.TestCase):
    """The two-version selector must never fall back to the other server."""

    def setUp(self):
        self.original = (package_environment.SERVER_VERSION, package_environment.SPEC,
                         package_environment.LOCK_RELATIVE)

    def tearDown(self):
        (package_environment.SERVER_VERSION, package_environment.SPEC,
         package_environment.LOCK_RELATIVE) = self.original

    def test_default_version_is_still_12_2(self):
        self.assertEqual(package_environment.SERVER_VERSION, "12.2")
        self.assertEqual(package_environment.SERVER_VERSIONS["12.2"]["spec"], "dev/environment-spec.json")
        self.assertEqual(package_environment.SERVER_VERSIONS["12.2"]["lock"],
                         "artifacts/dev-env/images.lock.json")

    def test_selecting_12_3_switches_to_its_own_spec_and_lock(self):
        identity = package_environment.select_server_version("12.3")
        self.assertEqual(identity["version"], "12.3")
        self.assertEqual(identity["publicVersion"], "12.3.0")
        self.assertEqual(identity["sourceSha"], "06de749d435e2d0be0c5119a41f2300fdd7143e5")
        self.assertEqual(identity["specFile"], "dev/environment-spec-12.3.json")
        self.assertEqual(identity["lockFile"], "dev/images-12.3.lock.json")
        self.assertEqual(package_environment.SPEC["server"]["version"], "12.3")
        images = package_environment.load_image_lock()
        self.assertEqual(images["server"],
                         "jellyfin/jellyfin@sha256:720ad28968e040f1ea049749f4ce546b28c7251244a6eb8aacf9147d8afbc24d")
        self.assertEqual(images["media"],
                         "python@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89")

    def test_unknown_version_is_refused_without_changing_the_selection(self):
        with self.assertRaisesRegex(package_environment.PackageEnvironmentError, "Unknown server version"):
            package_environment.select_server_version("12.4")
        self.assertEqual(package_environment.SERVER_VERSION, "12.2")
        self.assertEqual(package_environment.LOCK_RELATIVE, "artifacts/dev-env/images.lock.json")

    def test_a_spec_that_declares_another_version_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dev").mkdir()
            spec = json.loads((ROOT / "dev" / "environment-spec-12.3.json").read_text())
            spec["server"]["version"] = "12.2"
            (root / "dev" / "environment-spec-12.3.json").write_text(json.dumps(spec))
            with patch.object(package_environment, "ROOT", root):
                with self.assertRaisesRegex(package_environment.PackageEnvironmentError,
                                            "does not declare server version"):
                    package_environment.select_server_version("12.3")

    def test_the_12_3_lock_cannot_be_used_by_the_12_2_spec(self):
        """A wrong lock must fail before anything is measured, not be silently ignored."""
        data = json.loads((ROOT / "dev" / "images-12.3.lock.json").read_text())
        data["spec"]["server"]["version"] = "12.2"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dev").mkdir()
            (root / "dev" / "images-12.3.lock.json").write_text(json.dumps(data))
            with patch.object(package_environment, "ROOT", root), \
                    patch.object(package_environment, "SERVER_VERSION", "12.3"), \
                    patch.object(package_environment, "LOCK_RELATIVE", "dev/images-12.3.lock.json"), \
                    patch.object(package_environment, "SPEC", dict(package_environment.SPEC,
                                                                  server={"version": "12.3"})):
                with self.assertRaisesRegex(package_environment.PackageEnvironmentError,
                                            "belongs to a different environment specification"):
                    package_environment.load_image_lock()

    def test_a_missing_12_3_lock_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dev").mkdir()
            (root / "dev" / "environment-spec-12.3.json").write_text(
                (ROOT / "dev" / "environment-spec-12.3.json").read_text())
            with patch.object(package_environment, "ROOT", root):
                package_environment.select_server_version("12.3")
                with self.assertRaisesRegex(package_environment.PackageEnvironmentError,
                                            "immutable image lock is missing"):
                    package_environment.load_image_lock()

    def test_a_mutable_or_foreign_12_3_lock_is_refused(self):
        original = json.loads((ROOT / "dev" / "images-12.3.lock.json").read_text())
        cases = {
            "mutable tag": "jellyfin/jellyfin:12.3",
            "wrong repository": "python@sha256:" + "a" * 64,
            "short digest": "jellyfin/jellyfin@sha256:abc",
        }
        for label, server in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "dev").mkdir()
                (root / "dev" / "environment-spec-12.3.json").write_text(
                    (ROOT / "dev" / "environment-spec-12.3.json").read_text())
                data = json.loads(json.dumps(original))
                data["images"]["server"] = server
                (root / "dev" / "images-12.3.lock.json").write_text(json.dumps(data))
                with patch.object(package_environment, "ROOT", root):
                    package_environment.select_server_version("12.3")
                    with self.assertRaises(package_environment.PackageEnvironmentError):
                        package_environment.load_image_lock()

    def test_the_locked_server_image_platform_is_verified_before_a_start(self):
        """A digest that is not present, or not linux/amd64, must stop the start."""
        images = {"server": "jellyfin/jellyfin@sha256:" + "a" * 64,
                  "media": "python@sha256:" + "b" * 64}
        missing = subprocess.CompletedProcess([], 1, stdout="", stderr="No such image")
        with patch.object(package_environment, "run", return_value=missing):
            with self.assertRaisesRegex(package_environment.PackageEnvironmentError,
                                        "not present locally"):
                package_environment.verify_server_image(images)
        foreign = subprocess.CompletedProcess(
            [], 0, stdout='linux/arm64 sha256:fff ["jellyfin/jellyfin@sha256:%s"]' % ("a" * 64),
            stderr="")
        with patch.object(package_environment, "run", return_value=foreign):
            with self.assertRaisesRegex(package_environment.PackageEnvironmentError, "linux/amd64"):
                package_environment.verify_server_image(images)
        other = subprocess.CompletedProcess(
            [], 0, stdout='linux/amd64 sha256:fff ["other/image@sha256:%s"]' % ("c" * 64), stderr="")
        with patch.object(package_environment, "run", return_value=other):
            with self.assertRaisesRegex(package_environment.PackageEnvironmentError,
                                        "does not match the locked digest"):
                package_environment.verify_server_image(images)
        good = subprocess.CompletedProcess(
            [], 0, stdout='linux/amd64 sha256:fff ["jellyfin/jellyfin@sha256:%s"]' % ("a" * 64),
            stderr="")
        with patch.object(package_environment, "run", return_value=good):
            identity = package_environment.verify_server_image(images)
        self.assertEqual(identity["platform"], "linux/amd64")

    def test_the_public_version_assertion_follows_the_selected_version(self):
        package_environment.select_server_version("12.3")
        self.assertEqual(package_environment.server_public_version(), "12.3.0")
        package_environment.select_server_version("12.2")
        self.assertEqual(package_environment.server_public_version(), "12.2.0")


class CompatibilityScenarioGuardTests(unittest.TestCase):
    """Structural guards for the compatibility sequencing; these are not real Jellyfin acceptance."""

    def test_the_compatibility_scenario_requires_the_fixed_12_3_target(self):
        base = Path(tempfile.mkdtemp())
        package = valid_archive(base / "pkg")
        before = sorted(str(path) for path in base.rglob("*"))
        with patch.object(package_environment, "BASE", base), \
                patch.object(package_environment, "compose") as compose:
            code = run_main(["--package", str(package), "--scenario", "compatibility"])
        self.assertEqual(code, 1)
        compose.assert_not_called()
        self.assertEqual(sorted(str(path) for path in base.rglob("*")), before)

    def test_a_compatibility_run_without_an_upgrade_source_is_refused_not_skipped(self):
        # The non-empty 12.2 upgrade preservation is a Required Outcome: an omitted source must fail
        # before any instance starts instead of being recorded as SKIPPED inside a passing run.
        base = Path(tempfile.mkdtemp())
        package = valid_archive(base / "pkg")
        evidence = base / "evidence"
        with patch.object(package_environment, "BASE", base), \
                patch.object(package_environment, "select_workspace") as workspace, \
                patch.object(package_environment, "compose") as compose:
            code = run_main(["--package", str(package), "--server-version", "12.3",
                             "--scenario", "compatibility", "--evidence-dir", str(evidence)])
        self.assertEqual(code, 1)
        workspace.assert_not_called()
        compose.assert_not_called()
        result = json.loads((evidence / "package-integration-result.json").read_text())
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("--upgrade-source-workspace", result["error"])

    def test_the_public_repository_index_must_serve_the_archive_under_test(self):
        class Response:
            status = 200

            def __init__(self, payload):
                self.payload = payload

            def read(self):
                return self.payload

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        base = Path(tempfile.mkdtemp())
        package = valid_archive(base / "pkg")
        md5 = hashlib.md5(package.read_bytes(), usedforsecurity=False).hexdigest()
        good = [{"guid": integration.PLUGIN_ID, "name": "STRM Probe Optimizer",
                 "versions": [{"version": "0.1.0.0", "targetAbi": "12.2.0.0",
                               "sourceUrl": integration.PUBLIC_RELEASE_URL, "checksum": md5}]}]
        with patch.object(integration.urllib.request, "urlopen",
                          lambda *a, **kw: Response(json.dumps(good).encode())):
            result = integration.fetch_public_catalog(package)
        self.assertEqual(result["repositoryUrl"], integration.PUBLIC_REPOSITORY_URL)
        self.assertEqual(result["catalog"]["versions"][0]["sourceUrl"], integration.PUBLIC_RELEASE_URL)
        for wrong in ({**good[0], "guid": "00000000-0000-0000-0000-000000000000"},
                      {**good[0], "versions": [{**good[0]["versions"][0], "checksum": "0" * 32}]},
                      {**good[0], "versions": [{**good[0]["versions"][0], "sourceUrl": "http://media:8080/x.zip"}]}):
            with patch.object(integration.urllib.request, "urlopen",
                              lambda *a, **kw: Response(json.dumps([wrong]).encode())):
                with self.assertRaises(RuntimeError):
                    integration.fetch_public_catalog(package)

    def test_the_install_scenario_uses_the_public_index_not_a_local_one(self):
        source = (ROOT / "scripts" / "run_isolated_package_integration.py").read_text(encoding="utf-8")
        install = source[source.index("def stage_web_install("):
                                     source.index("def first_trust_after_install(")]
        self.assertIn('summary["publicRepository"] = fetch_public_catalog(package)', install)
        self.assertIn('summary["publicRepository"]["repositoryUrl"]', install)
        self.assertNotIn("publish_local_repository", source)

    def test_each_compatibility_stage_archives_its_own_runtime_log(self):
        source = (ROOT / "scripts" / "run_isolated_package_integration.py").read_text(encoding="utf-8")
        stage = source[source.index("def run_compat_stage("):source.index("def iso_now(")]
        self.assertEqual(stage.count("archive_stage_runtime(name, stage, evidence_dir)"), 2)
        self.assertIn('f"server-logs-{name}"', source)
        self.assertIn('f"server-ffprobe-lines-{name}.log"', source)
        # The run records its exact command, interpreter and tool inputs, not only a summary label.
        self.assertIn('summary["invocation"] = run_invocation(args)', source)
        self.assertIn('summary["toolInputs"] = tool_input_identity()', source)

    def test_the_native_install_record_is_a_mapping_not_an_accidental_tuple(self):
        # A trailing comma after a multi-line dict literal silently turns the record into a tuple;
        # the shape is checked structurally so recorded evidence keeps its documented keys.
        import ast

        tree = ast.parse((ROOT / "scripts" / "run_isolated_package_integration.py").read_text(encoding="utf-8"))
        keys = {"nativeInstall", "publicRepository", "invocation", "toolInputs", "runtimeArchive"}
        assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Subscript)
                               and isinstance(target.slice, ast.Constant)
                               and target.slice.value in keys
                               for target in node.targets)]
        self.assertTrue(assignments, "The compatibility record assignments were not found.")
        for node in assignments:
            self.assertIsInstance(node.value, (ast.Dict, ast.Call, ast.Name, ast.Attribute),
                                  f"{ast.dump(node.targets[0])[:80]} is not a mapping-valued record")

    def test_the_web_sharing_stage_uses_the_plugin_start_and_join_counters(self):
        import ast

        source = (ROOT / "scripts" / "run_isolated_package_integration.py").read_text(encoding="utf-8")
        sharing = source[source.index("def stage_web_sharing("):source.index("def stage_sharing_concurrency(")]
        # The physical probe is the plugin's own start/join line, never a raw media-request counter:
        # the Web Play's transcode job reads the same probe route.
        self.assertIn('"Native STRM probe started"', sharing)
        self.assertIn("joined a running native probe", sharing)
        self.assertNotIn("physicalProbeRequests", sharing)
        # The API-level PlaybackInfo sharing is reported as what it is, not as a Web Play.
        rounds = source[source.index("def stage_small_library_native_rounds("):
                              source.index("def stage_web_sharing(")]
        self.assertIn('"kind": "PlaybackInfo HTTP call, not a Web Play"', rounds)
        check = ast.parse(sharing)
        self.assertTrue(any(isinstance(node, ast.FunctionDef) and node.name == "stage_web_sharing"
                            for node in check.body))

    def test_an_adopted_upgrade_source_must_be_an_owned_run_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "runs" / "run-1"
            candidate.mkdir(parents=True)
            with patch.object(package_environment, "BASE", root):
                with self.assertRaisesRegex(RuntimeError, "no run marker"):
                    integration.verify_upgrade_source(candidate)

    def test_an_upgrade_source_with_transaction_side_files_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "runs" / "run-1"
            (source / "config").mkdir(parents=True)
            (source / package_environment.RUN_MARKER).write_text("token\n")
            (source / "config" / "jellyfin.db-wal").write_bytes(b"")
            with patch.object(package_environment, "BASE", root):
                with self.assertRaisesRegex(RuntimeError, "transaction side files"):
                    integration.verify_upgrade_source(source)

    def test_an_upgrade_source_with_a_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "runs" / "run-1"
            source.mkdir(parents=True)
            (source / package_environment.RUN_MARKER).write_text("token\n")
            (source / "link").symlink_to(source / package_environment.RUN_MARKER)
            with patch.object(package_environment, "BASE", root):
                with self.assertRaisesRegex(RuntimeError, "symbolic links"):
                    integration.verify_upgrade_source(source)

    def test_an_empty_prepared_copy_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "runs" / "run-1"
            (source / "config").mkdir(parents=True)
            (source / package_environment.RUN_MARKER).write_text("token\n")
            with patch.object(package_environment, "BASE", root):
                with self.assertRaisesRegex(RuntimeError, "no plugin fingerprint store"):
                    integration.verify_upgrade_source(source)

    def test_upgrade_preservation_reports_every_required_difference(self):
        before = {"configuration": {"MaxConcurrentProbes": 3},
                  "configurationFileSha256": "a",
                  "items": {"A": {"itemId": "1", "sources": [{"id": "s", "pathHash": "h"}],
                                  "fingerprint": {"url_hash": "u"}, "itemPathHash": "p"}}}
        after = {"configuration": {"MaxConcurrentProbes": 2},
                 "configurationFileSha256": "b",
                 "items": {"A": {"itemId": "1", "sources": [{"id": "s", "pathHash": "other"}],
                                 "fingerprint": None, "itemPathHash": "p"},
                           "B": {"itemId": "2", "sources": [], "fingerprint": None, "itemPathHash": "q"}}}
        failures = integration.upgrade_preservation_failures(before, after)
        joined = " | ".join(failures)
        for expected in ("effective plugin configuration changed", "persisted configuration bytes",
                         "STRM item set changed", "saved native address/streams changed",
                         "trusted fingerprint changed", "trusted fingerprint was lost"):
            self.assertIn(expected, joined)
        self.assertEqual(integration.upgrade_preservation_failures(before, before), [])

    def test_the_fingerprint_store_schema_check_is_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            plugin_dir = workspace / "config" / "data" / "plugins" / integration.FLAT_PLUGIN_ID
            plugin_dir.mkdir(parents=True)
            database = plugin_dir / "strm-fingerprints.db"
            import sqlite3 as sqlite

            with sqlite.connect(database) as connection:
                connection.execute("CREATE TABLE strm_fingerprint (item_id TEXT, source_key TEXT, "
                                   "url_hash TEXT, sha1 TEXT, file_size INTEGER, extra TEXT)")
            with patch.object(package_environment, "WORK", workspace):
                with self.assertRaisesRegex(RuntimeError, "five-field schema"):
                    integration.fingerprint_store_report()

    def test_the_playback_driver_declares_the_explicit_source_selection(self):
        driver = (ROOT / "scripts" / "package_playback_driver.mjs").read_text()
        self.assertIn("async function chooseSource(page, item)", driver)
        self.assertIn(".selectSource", driver)
        self.assertIn("selectedSourceId", driver)
        self.assertIn("alternateVersionLoaded", driver)

    def test_the_configuration_driver_declares_the_native_repository_install(self):
        driver = (ROOT / "scripts" / "configuration_page_driver.mjs").read_text()
        self.assertIn("async function addPluginRepository(page)", driver)
        self.assertIn("Manage Repositories", driver)
        self.assertIn("Confirm Plugin Installation", driver)
        self.assertIn("async web_install(page)", driver)


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
