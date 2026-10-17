"""Guardrails for the isolated scan-acceptance tooling; these are not real Jellyfin acceptance tests.

The tests prove the tool's own controls: a missing real scan/probe intersection cannot PASS, a
cross-day or older-session log line is not attributed to the current round, a range/expired
version reconciliation failure is refused, and an abnormal exit cannot delete a previous run's
workspace. They do not claim any real Jellyfin result.
"""

from __future__ import annotations

import datetime
import importlib.util
import sys
import tempfile
import unittest
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
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


package_environment = load("package_environment", "scripts/package_environment.py")
package_plugin = load("package_plugin", "scripts/package_plugin.py")
package_integration = load("run_isolated_package_integration", "scripts/run_isolated_package_integration.py")
scan = load("run_isolated_scan_integration", "scripts/run_isolated_scan_integration.py")


def _utc(second: int) -> datetime.datetime:
    return datetime.datetime(2026, 10, 17, 8, 0, second, tzinfo=datetime.timezone.utc)


class ScanOverlapControlTests(unittest.TestCase):
    def test_a_real_intersection_is_accepted(self):
        scan_interval = (_utc(0), _utc(10))
        result = scan.assert_scan_probe_overlap(scan_interval, _utc(3), _utc(8), "batch")
        self.assertTrue(result["overlapped"])

    def test_a_missing_intersection_cannot_pass(self):
        # A probe that ended before the scan started must be refused.
        with self.assertRaises(RuntimeError):
            scan.assert_scan_probe_overlap((_utc(10), _utc(20)), _utc(0), _utc(5), "batch")
        # A probe that started after the scan ended must be refused.
        with self.assertRaises(RuntimeError):
            scan.assert_scan_probe_overlap((_utc(0), _utc(5)), _utc(10), _utc(15), "playback")

    def test_a_zero_length_probe_interval_is_refused(self):
        # A queued/permitted request that never actually ran must not be accepted as an overlap.
        with self.assertRaises(RuntimeError):
            scan.assert_scan_probe_overlap((_utc(0), _utc(10)), _utc(5), _utc(5), "batch")

    def test_a_probe_that_only_touches_the_scan_boundary_still_intersects(self):
        # A probe ending exactly when the scan starts is a real (if tight) intersection; the tool
        # must not silently drop it, and the assertion is deterministic on inclusive bounds.
        result = scan.assert_scan_probe_overlap((_utc(10), _utc(20)), _utc(5), _utc(10), "batch")
        self.assertTrue(result["overlapped"])


class ScanLogAttributionTests(unittest.TestCase):
    def test_probe_start_events_exclude_older_sessions(self):
        lines = [
            "2026-10-16T23:59:59.000000000Z [INF] Native STRM probe started for item AAAA; running probes 1, active permits 1.",
            "2026-10-17T08:00:01.000000000Z [INF] Native STRM probe started for item BBBB; running probes 2, active permits 2.",
        ]
        with patch.object(scan, "docker_log_lines", return_value=lines):
            all_events = scan.probe_start_events("container")
            current = scan.probe_start_events("container", since=_utc(0))
        self.assertEqual([event["item_id"] for event in all_events], ["aaaa", "bbbb"])
        # A previous day's session must never be attributed to the current round.
        self.assertEqual([event["item_id"] for event in current], ["bbbb"])

    def test_delay_request_events_exclude_older_sessions(self):
        lines = [
            "2026-10-16T23:59:59.000000000Z SLOW_MEDIA_REQUEST_STARTED old-request",
            "2026-10-17T08:00:02.000000000Z SLOW_MEDIA_REQUEST_STARTED current-request",
        ]
        with patch.object(scan, "docker_log_lines", return_value=lines):
            current = scan.delay_request_events("media", since=_utc(0))
        self.assertEqual([event["request_id"] for event in current], ["current-request"])

    def test_scan_execution_interval_reads_the_authoritative_utc_result(self):
        task = {"LastExecutionResult": {"StartTimeUtc": "2026-10-17T08:00:00.000000Z",
                                        "EndTimeUtc": "2026-10-17T08:00:05.000000Z"}}
        start, end = scan.scan_execution_interval(task)
        self.assertEqual(start, _utc(0))
        self.assertEqual(end, _utc(5))

    def test_scan_execution_interval_requires_both_bounds(self):
        with self.assertRaises(RuntimeError):
            scan.scan_execution_interval({"LastExecutionResult": {"StartTimeUtc": "2026-10-17T08:00:00Z"}})

    def test_probe_start_for_item_normalizes_guid_formats(self):
        events = [{"item_id": "0123456789abcdef0123456789abcdef", "running": 1, "timestamp": _utc(0)}]
        self.assertIsNotNone(scan.probe_start_for_item(events, "01234567-89ab-cdef-0123-456789abcdef"))
        self.assertIsNone(scan.probe_start_for_item(events, "ffffffff-ffff-ffff-ffff-ffffffffffff"))


class ScanReconciliationTests(unittest.TestCase):
    def test_source_path_matches_hash_only_accepts_the_current_address(self):
        url = "http://media:8080/package-mp4.mp4"
        response = {"MediaSources": [{"Path": url}]}
        self.assertTrue(scan.source_path_matches_hash(response, scan.expected_url_hash(url)))
        self.assertFalse(scan.source_path_matches_hash(response, scan.expected_url_hash("http://media:8080/old.mp4")))

    def test_rewrite_strm_refuses_a_path_outside_the_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            (workspace / "strm").mkdir(parents=True)
            foreign = Path(tmp) / "foreign.strm"
            foreign.write_text("# strm-probe-version:1\nhttp://media:8080/old.mp4\n", encoding="utf-8")
            with patch.object(package_environment, "WORK", workspace):
                with self.assertRaises(package_environment.PackageEnvironmentError):
                    scan.rewrite_strm(foreign, "http://media:8080/new.mp4", "a" * 40, 1)
            # The foreign file must be untouched.
            self.assertIn("old.mp4", foreign.read_text(encoding="utf-8"))

    def test_rewrite_strm_writes_a_versioned_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            (workspace / "strm").mkdir(parents=True)
            path = workspace / "strm" / "case.strm"
            path.write_text("# strm-probe-version:1\n# strm-probe-sha1:" + "b" * 40 +
                            "\n# strm-probe-size:9\nhttp://media:8080/old.mp4\n", encoding="utf-8")
            with patch.object(package_environment, "WORK", workspace):
                scan.rewrite_strm(path, "http://media:8080/new.mp4", None, 12)
            text = path.read_text(encoding="utf-8")
            self.assertIn("# strm-probe-version:1", text)
            self.assertNotIn("strm-probe-sha1", text)
            self.assertIn("# strm-probe-size:12", text)
            self.assertTrue(text.rstrip().endswith("http://media:8080/new.mp4"))

    def test_delay_and_unique_urls_keep_the_isolated_host(self):
        delayed = scan.delay_url("http://media:8080/package-mp4.mp4", 8, "abc")
        self.assertEqual(delayed, "http://media:8080/delay/8/abc/package-mp4.mp4")
        unique = scan.unique_url("http://media:8080/package-mp4.mp4", "k")
        self.assertTrue(unique.startswith("http://media:8080/package-mp4.mp4?scan_case="))

    def test_scenario_choices_include_overlap_stop_and_recovery(self):
        source = (ROOT / "scripts" / "run_isolated_scan_integration.py").read_text(encoding="utf-8")
        for scenario in ("overlap", "controls", "stop", "recovery"):
            self.assertIn(scenario, source)

    def test_fingerprint_row_reads_the_package_instance(self):
        # A regression where the scan tool read the development instance database would silently
        # check the wrong instance. The helper must delegate to the package integration's reader.
        with patch.object(package_integration, "fingerprint_row", return_value={"item_id": "x"}) as reader:
            row = scan.fingerprint_row("01234567-89ab-cdef-0123-456789abcdef")
        self.assertEqual(row, {"item_id": "x"})
        reader.assert_called_once_with("01234567-89ab-cdef-0123-456789abcdef",
                                       "01234567-89ab-cdef-0123-456789abcdef")

    def test_all_scenario_runs_overlap_controls_stop_and_recovery(self):
        source = (ROOT / "scripts" / "run_isolated_scan_integration.py").read_text(encoding="utf-8")
        self.assertIn('{"all", "overlap"}', source)
        self.assertIn('{"all", "controls"}', source)
        self.assertIn('{"all", "stop"}', source)
        self.assertIn('{"all", "recovery"}', source)

    def test_tool_never_calls_the_development_deployment_helper(self):
        # The scan acceptance must consume only the archive; a stray dev deployment would make the
        # result meaningless. A text scan keeps this guard independent of import side effects.
        source = (ROOT / "scripts" / "run_isolated_scan_integration.py").read_text(encoding="utf-8")
        self.assertNotIn("deploy_plugin", source)
        self.assertNotIn("development_environment", source)


class ScanRunOwnershipTests(unittest.TestCase):
    def _valid_package(self, directory: Path) -> Path:
        import tests.test_package_plugin as builder

        directory.mkdir(parents=True, exist_ok=True)
        return builder.build_valid_archive_with_sidecar(directory)

    def _run_main(self, argv: list[str]) -> int:
        with patch.object(sys, "argv", ["run_isolated_scan_integration", *argv]):
            return scan.main()

    def test_missing_package_leaves_a_previous_runs_workspace_untouched(self):
        base = Path(tempfile.mkdtemp())
        previous = base / "run-previous"
        previous.mkdir()
        (previous / package_environment.RUN_MARKER).write_text("previous-run-token\n", encoding="utf-8")
        (previous / "prior.strm").write_bytes(b"previous run data")
        with patch.object(package_environment, "BASE", base), \
                patch.object(package_environment, "compose") as compose:
            code = self._run_main(["--package", str(base / "missing.zip"),
                                   "--scenario", "overlap", "--workspace", str(previous)])
        self.assertEqual(code, 1)
        compose.assert_not_called()
        self.assertTrue(previous.is_dir(), "a previous run's workspace was removed")
        self.assertEqual((previous / "prior.strm").read_bytes(), b"previous run data")

    def test_scenario_failure_still_cleans_up_only_its_own_workspace(self):
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
                patch.object(scan, "scenario_overlap", side_effect=RuntimeError("scenario boom")):
            code = self._run_main(["--package", str(package), "--scenario", "overlap"])
        self.assertEqual(code, 1)
        self.assertIn("workspace", created)
        self.assertFalse(created["workspace"].exists(), "the run did not clean up its own workspace")


if __name__ == "__main__":
    unittest.main()
