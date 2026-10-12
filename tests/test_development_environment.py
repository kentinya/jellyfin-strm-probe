"""Deployment guardrails only; these are not real Jellyfin acceptance tests."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "development_environment", Path(__file__).resolve().parents[1] / "scripts/development_environment.py"
)
envtool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(envtool)


class EnvironmentGuardTests(unittest.TestCase):
    def test_wrong_sdk_archive_never_reaches_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "environment"
            archive = Path(directory) / "bad.tar.gz"
            archive.write_bytes(b"not the official SDK")
            with patch.object(envtool, "WORK", work), patch.object(envtool, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "SHA-512 mismatch"):
                    envtool.install_sdk(archive)
                run.assert_not_called()
                self.assertEqual(list((work / "sdk").iterdir()), [])

    def test_symlink_environment_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "foreign"
            target.mkdir()
            work = Path(directory) / "environment"
            work.symlink_to(target, target_is_directory=True)
            with patch.object(envtool, "WORK", work):
                with self.assertRaisesRegex(RuntimeError, "symlink"):
                    envtool.workspace()
            self.assertEqual(list(target.iterdir()), [])

    def test_mutable_or_foreign_image_lock_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(envtool, "WORK", Path(directory)):
            for bad in ("jellyfin/jellyfin:latest", "other/image@sha256:" + "a" * 64):
                data = {"spec": envtool.SPEC, "images": {
                    "server": bad, "media": "python@sha256:" + "b" * 64}}
                (envtool.WORK / "images.lock.json").write_text(json.dumps(data))
                with self.assertRaisesRegex(RuntimeError, "immutable image lock"):
                    envtool.load_lock()

    def test_foreign_container_mounts_prevent_up_or_stop(self):
        inspection = [{"Mounts": [{"Type": "bind", "Source": "/opt/production-jellyfin"}]}]
        with patch.object(envtool, "run", side_effect=["foreign-id", json.dumps(inspection)]):
            with self.assertRaisesRegex(RuntimeError, "foreign mounts"):
                envtool.guard_containers()

    def test_local_docker_endpoint_is_explicit(self):
        self.assertEqual(envtool.DOCKER[1:], ["--host", "unix:///var/run/docker.sock"])

    def test_real_compose_config_is_isolated(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(envtool, "WORK", Path(directory)):
            data = {"spec": envtool.SPEC, "images": {
                "server": "jellyfin/jellyfin@sha256:" + "a" * 64,
                "media": "python@sha256:" + "b" * 64}}
            (envtool.WORK / "images.lock.json").write_text(json.dumps(data))
            args, environment = envtool.compose_args()
            # Synthetic digests only validate configuration; no pull or server is run.
            result = subprocess.run([*args, "config", "--format", "json"], env=environment,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            config = json.loads(result.stdout)
            services = config["services"]
            self.assertEqual(set(services), {"jellyfin", "media"})
            port = services["jellyfin"]["ports"][0]
            self.assertEqual((port["host_ip"], str(port["published"]), port["target"]),
                             ("127.0.0.1", "18096", 8096))
            self.assertNotIn("ports", services["media"])
            for service in services.values():
                self.assertNotIn("network_mode", service)
                self.assertFalse(service.get("privileged", False))
                for mount in service["volumes"]:
                    self.assertTrue(Path(mount["source"]).is_relative_to(Path(directory)))
                    if mount["target"].startswith("/media"):
                        self.assertTrue(mount["read_only"])
            self.assertTrue(config["networks"]["acceptance"]["internal"])


if __name__ == "__main__":
    unittest.main()
