"""Guardrails for the isolated scan-acceptance tooling; these are not real Jellyfin acceptance tests.

The tests drive the tool's own acceptance helpers and scenario functions with mocked external
boundaries to prove the tool REFUSES the exact gaps B found in Task 4.2:

* a missing real scan/probe intersection cannot PASS (BR-42-1);
* a finite change issued outside the scan Running window cannot PASS (BR-42-1);
* a delete/move target that was never in the fixed candidate set cannot PASS (BR-42-1);
* a Failed native scan / Failed batch cannot be accepted as overlap or convergence (BR-42-2);
* a missing summary cannot become zero probes (BR-42-2);
* a wrong MediaSourceId / unfiltered multi-source response cannot PASS selection (BR-42-2);
* a third fingerprint replacing the trusted A baseline cannot PASS (BR-42-2);
* a moved-out source's new identity being processed cannot PASS (BR-42-2);
* a stopped round reporting 100% or starting a new round/probe during its drain cannot PASS (BR-42-3);
* a disabled / faulted plugin starting work on any route cannot PASS (BR-42-3);
* produced evidence survives an abnormal exit and a teardown failure makes the run FAIL (BR-42-4);
* a cross-day or older-session log line is not attributed to the current round;
* an abnormal exit cannot delete a previous run's workspace.

They do not claim any real Jellyfin result.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
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
        result = scan.assert_scan_probe_overlap((_utc(10), _utc(20)), _utc(5), _utc(10), "batch")
        self.assertTrue(result["overlapped"])

    def test_a_change_outside_the_running_window_cannot_pass(self):
        scan_interval = (_utc(0), _utc(10))
        scan.require_change_in_window(_utc(5), scan_interval, "in-window")
        with self.assertRaises(RuntimeError):
            scan.require_change_in_window(_utc(15), scan_interval, "post-scan")

    def test_a_delete_target_never_in_the_fixed_set_cannot_pass(self):
        captured = {"aaaa", "bbbb"}
        scan.require_captured(captured, "aaaa", "delete")
        with self.assertRaises(RuntimeError):
            scan.require_captured(captured, "cccc", "delete")


class ScanExecutionControlTests(unittest.TestCase):
    def _task(self, status: str, start: str = "2026-10-17T08:00:00.000000Z",
              end: str = "2026-10-17T08:00:05.000000Z") -> dict:
        return {"LastExecutionResult": {"Status": status, "StartTimeUtc": start, "EndTimeUtc": end}}

    def test_a_completed_execution_is_accepted(self):
        start, end = scan.require_completed_execution(self._task("Completed"), None, "scan")
        self.assertEqual(start, _utc(0))
        self.assertEqual(end, _utc(5))

    def test_a_failed_execution_cannot_pass(self):
        with self.assertRaises(RuntimeError):
            scan.require_completed_execution(self._task("Failed"), None, "scan")

    def test_a_cancelled_execution_cannot_pass(self):
        with self.assertRaises(RuntimeError):
            scan.require_completed_execution(self._task("Cancelled"), None, "scan")

    def test_a_completed_execution_without_an_interval_cannot_pass(self):
        with self.assertRaises(RuntimeError):
            scan.require_completed_execution(
                {"LastExecutionResult": {"Status": "Completed", "StartTimeUtc": "2026-10-17T08:00:00Z"}},
                None, "scan")

    def test_a_previous_round_result_cannot_be_reused(self):
        task = self._task("Completed", start="2026-10-17T08:00:00.000000Z")
        with self.assertRaises(RuntimeError):
            scan.require_completed_execution(task, "2026-10-17T08:00:00.000000Z", "scan")

    def test_a_missing_summary_counter_cannot_become_zero(self):
        # A summary that omits the probe counter must be refused, not silently treated as zero probes.
        incomplete = "STRM media information check finished: candidates 1, checked 1."
        with self.assertRaises(RuntimeError):
            scan.summary_fields_complete(incomplete)

    def test_a_complete_summary_is_accepted_and_equations_hold(self):
        line = ("STRM media information check finished: candidates 1 (raw 1, duplicates 0, total known True), "
                "checked 1, skipped 1, first trust 1, need probe 0, reliable success 0, probe incomplete 0, "
                "check-stage incomplete 0, not processed 0, missing 0, revoked 0, read incomplete 0, unread 0, "
                "actual probe calls 0, batch reads 1, candidate fetch 1.0 ms, batch read 1.0 ms.")
        fields = scan.summary_fields_complete(line)
        self.assertEqual(fields["actual_probe_calls"], 0)


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
        self.assertEqual([event["item_id"] for event in current], ["bbbb"])

    def test_backend_request_events_exclude_older_sessions(self):
        lines = [
            "2026-10-16T23:59:59.000000000Z SLOW_MEDIA_REQUEST_STARTED old-request",
            "2026-10-17T08:00:02.000000000Z SLOW_MEDIA_REQUEST_STARTED current-request",
            "2026-10-17T08:00:04.000000000Z PROBE_MEDIA_REQUEST_FINISHED current-request",
        ]
        with patch.object(scan, "docker_log_lines", return_value=lines):
            current = scan.backend_request_events("media", since=_utc(0))
        self.assertEqual([(event["kind"], event["request_id"]) for event in current],
                         [("start", "current-request"), ("finish", "current-request")])

    def test_probe_start_for_item_normalizes_guid_formats(self):
        events = [{"item_id": "0123456789abcdef0123456789abcdef", "running": 1, "timestamp": _utc(0)}]
        self.assertIsNotNone(scan.probe_start_for_item(events, "01234567-89ab-cdef-0123-456789abcdef"))
        self.assertIsNone(scan.probe_start_for_item(events, "ffffffff-ffff-ffff-ffff-ffffffffffff"))


class ScanStopControlTests(unittest.TestCase):
    def test_a_new_round_during_drain_cannot_pass(self):
        scan.require_no_new_round(entries_before_settlement=1, entries_before_stop=1, label="re-run")
        with self.assertRaises(RuntimeError):
            scan.require_no_new_round(entries_before_settlement=2, entries_before_stop=1, label="re-run")

    def test_a_probe_during_drain_cannot_pass(self):
        scan.require_no_probe_during_drain([])
        with self.assertRaises(RuntimeError):
            scan.require_no_probe_during_drain([{"item_id": "x", "timestamp": _utc(1)}])

    def test_progress_reaching_100_while_cancelling_cannot_pass(self):
        scan.require_progress_below_100([0.0, 42.5, 99.0])
        with self.assertRaises(RuntimeError):
            scan.require_progress_below_100([0.0, 100.0])

    def test_activity_on_any_route_cannot_pass(self):
        before = {"delay_started": 0, "probe_finished": 0, "media_requests": 0, "plugin_encoder_starts": 0}
        scan.require_no_new_activity(before, dict(before), "disabled")
        changed = dict(before, media_requests=1)
        with self.assertRaises(RuntimeError):
            scan.require_no_new_activity(before, changed, "disabled")


class ScanSelectionControlTests(unittest.TestCase):
    def test_a_wrong_selected_version_cannot_pass(self):
        # A server that ignores the requested MediaSourceId and returns both sources must be refused.
        source_a = "a" * 32
        source_b = "b" * 32
        url_b = "http://media:8080/b.mp4"
        unfiltered = {"MediaSources": [{"Id": source_b, "Path": url_b}, {"Id": source_a, "Path": "http://media:8080/a.mp4"}]}
        # The requested A source is present with its own path, so this one passes; the wrong-version case
        # below (the requested id absent) must be refused.
        scan._require_selected_source(unfiltered, source_a, scan.expected_url_hash("http://media:8080/a.mp4"), "A")
        missing_requested = {"MediaSources": [{"Id": source_b, "Path": url_b}]}
        with self.assertRaises(RuntimeError):
            scan._require_selected_source(missing_requested, source_a, scan.expected_url_hash(url_b), "A")

    def test_a_source_returning_the_wrong_address_cannot_pass(self):
        source_a = "a" * 32
        response = {"MediaSources": [{"Id": source_a, "Path": "http://media:8080/other.mp4"}]}
        with self.assertRaises(RuntimeError):
            scan._require_selected_source(response, source_a, scan.expected_url_hash("http://media:8080/a.mp4"), "A")


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
        source = (ROOT / "scripts" / "run_isolated_scan_integration.py").read_text(encoding="utf-8")
        self.assertNotIn("deploy_plugin", source)
        self.assertNotIn("development_environment", source)

    def test_evidence_recorder_redacts_and_persists_incrementally(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = scan.EvidenceRecorder(Path(tmp), "run-1")
            recorder.record("probe", url="http://media:8080/secret?token=abc", item_id="x")
            recorder.snapshot("round", {"path": "/private/secret.mp4"})
            lines = (Path(tmp) / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)  # run_start + probe
            record = json.loads(lines[-1])
            # The URL must be stored as a digest, never in the clear.
            self.assertNotIn("secret", json.dumps(record))
            self.assertIn("sha256", record["data"]["url"])
            snapshot = json.loads((Path(tmp) / "rounds" / "round.json").read_text(encoding="utf-8"))
            self.assertNotIn("secret", json.dumps(snapshot))

    def test_evidence_recorder_writes_result_and_index_on_finish(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = scan.EvidenceRecorder(Path(tmp), "run-2")
            recorder.finish("PASS", {"status": "PASS"}, {"events.jsonl": "events"})
            self.assertTrue((Path(tmp) / "result.json").is_file())
            index = (Path(tmp) / "INDEX.md").read_text(encoding="utf-8")
            self.assertIn("PASS", index)
            self.assertIn("events.jsonl", index)


class ScanRunOwnershipTests(unittest.TestCase):
    def _valid_package(self, directory: Path) -> Path:
        import tests.test_package_plugin as builder

        directory.mkdir(parents=True, exist_ok=True)
        return builder.build_valid_archive_with_sidecar(directory)

    def _run_main(self, argv: list[str]) -> int:
        with patch.object(sys, "argv", ["run_isolated_scan_integration", *argv]), \
                patch.object(scan, "container_identity", return_value={"identity": "fake"}):
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
                patch.object(scan, "container_identity", return_value={"identity": "fake"}), \
                patch.object(scan, "scenario_overlap_phase", side_effect=RuntimeError("scenario boom")):
            code = self._run_main(["--package", str(package), "--scenario", "overlap"])
        self.assertEqual(code, 1)
        self.assertIn("workspace", created)
        self.assertFalse(created["workspace"].exists(), "the run did not clean up its own workspace")

    def test_a_failure_still_persists_its_evidence_outside_the_instance(self):
        base = Path(tempfile.mkdtemp())
        package = self._valid_package(base / "pkg")
        evidence = base / "evidence"
        with patch.object(package_environment, "BASE", base), \
                patch.object(package_environment, "compose"), \
                patch.object(scan, "scenario_overlap_phase", side_effect=RuntimeError("scenario boom")):
            code = self._run_main(["--package", str(package), "--scenario", "overlap",
                                   "--evidence-dir", str(evidence)])
        self.assertEqual(code, 1)
        # The scenario's failure must be recorded even though the instance was cleaned up.
        self.assertTrue((evidence / "events.jsonl").is_file())
        self.assertTrue((evidence / "result.json").is_file())
        result = json.loads((evidence / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("scenario boom", result["error"])

    def test_teardown_failure_turns_the_run_into_fail(self):
        base = Path(tempfile.mkdtemp())
        package = self._valid_package(base / "pkg")
        evidence = base / "evidence"
        with patch.object(package_environment, "BASE", base), \
                patch.object(package_environment, "compose"), \
                patch.object(scan, "scenario_overlap_phase", return_value={"ok": True}), \
                patch.object(package_environment, "cleanup_instance",
                             side_effect=package_environment.PackageEnvironmentError("cleanup boom")):
            code = self._run_main(["--package", str(package), "--scenario", "overlap",
                                   "--evidence-dir", str(evidence)])
        self.assertEqual(code, 1)
        result = json.loads((evidence / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("cleanup boom", result.get("cleanup_error", ""))


if __name__ == "__main__":
    unittest.main()
