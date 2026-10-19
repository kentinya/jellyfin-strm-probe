from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_isolated_large_library_integration.py"
SPEC = importlib.util.spec_from_file_location("large_library_integration", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
large = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(large)


class LargeLibraryControlTests(unittest.TestCase):
    def run_round_fixture(self):
        fields = {name: 0 for name in large.REQUIRED_SUMMARY_FIELDS}
        fields.update(candidates=4, raw_candidates=4, checked=1, skipped=0, first_trust=0,
                      not_processed=3, actual_probe_calls=1, need_probe=1, reliable_success=1)
        fields.update({key: False for key in ("candidate_fetch_failed", "store_unavailable",
                       "scope_unavailable", "disabled", "stop_requested")})
        task = {"State": "Idle", "LastExecutionResult": {"Status": "Completed",
                "StartTimeUtc": "2026-01-01T00:00:01Z", "EndTimeUtc": "2026-01-01T00:00:02Z"}}
        execution = {"task": task, "start_time_previous": "2026-01-01T00:00:00Z",
                     "progress": [0, 50, 99], "stopped": False}
        keys = [("1" * 32, "2" * 32)]
        probes = [{"item_id": keys[0][0], "source_key": keys[0][1], "running": 2}]
        events = [{"kind": kind} for kind in ("CANDIDATE_QUERY_STARTED",
                  "CANDIDATE_QUERY_RETURNED", "CANDIDATE_SET_FIXED")]
        events.append({"kind": "OBJECT_READ_RETURNED",
                       "redacted_line": "RequestedCount 4 ReturnedCount 4"})
        return fields, execution, probes, events, keys

    def drive_round(self, fields, execution, probes, events, keys):
        with patch.object(large, "run_task", return_value=execution), \
             patch.object(large, "latest_summary_since", return_value="summary"), \
             patch.object(large, "require_complete_summary", return_value=fields), \
             patch.object(large, "probe_starts_since", return_value=probes), \
             patch.object(large, "batch_log_events", return_value=events):
            return large.run_round("auth", "offline", MagicMock(), "increment", 4, 1, 0,
                                   expected_probe_keys=keys)

    def test_real_round_control_accepts_success_and_rejects_failed_or_stale_execution(self):
        values = self.run_round_fixture()
        self.assertEqual(self.drive_round(*values)["fields"]["reliable_success"], 1)
        fields, execution, probes, events, keys = values
        for status in ("Failed", "Cancelled"):
            execution["task"]["LastExecutionResult"]["Status"] = status
            with self.assertRaisesRegex(RuntimeError, "did not complete"):
                self.drive_round(*values)
        execution["task"]["LastExecutionResult"]["Status"] = "Completed"
        execution["start_time_previous"] = "2026-01-01T00:00:01Z"
        with self.assertRaisesRegex(RuntimeError, "previous round"):
            self.drive_round(*values)

    def test_real_round_control_rejects_incomplete_work_flags_and_bad_progress(self):
        for key in ("check_stage_incomplete", "probe_incomplete", "missing", "revoked",
                    "read_incomplete", "unread", "store_unavailable", "scope_unavailable",
                    "disabled", "stop_requested"):
            with self.subTest(key=key):
                values = self.run_round_fixture()
                values[0][key] = True if key in {"store_unavailable", "scope_unavailable",
                                                "disabled", "stop_requested"} else 1
                with self.assertRaises(RuntimeError):
                    self.drive_round(*values)
        values = self.run_round_fixture(); values[1]["progress"] = [50, 10]
        with self.assertRaisesRegex(RuntimeError, "decreasing progress"):
            self.drive_round(*values)

    def test_real_round_control_rejects_wrong_probe_source_concurrency_and_batch_size(self):
        for mutate in (lambda p, e: p[0].update(source_key="3" * 32),
                       lambda p, e: p[0].update(running=3),
                       lambda p, e: p.clear(),
                       lambda p, e: e[-1].update(redacted_line="RequestedCount 9999 ReturnedCount 9999")):
            values = self.run_round_fixture(); mutate(values[2], values[3])
            with self.assertRaises(RuntimeError):
                self.drive_round(*values)

    def test_index_preparation_requires_scan_completed_before_item_visibility(self):
        fixture = {"names": ["supported"], "controls": {"ordinary": "ordinary",
                                                             "out_of_scope": "outside"}}
        with patch.object(large, "wait_native_task_idle"), \
             patch.object(large.scan, "run_native_scan_completed", side_effect=RuntimeError("scan Failed")), \
             patch.object(large, "poll_fixture_items") as poll:
            with self.assertRaisesRegex(RuntimeError, "scan Failed"):
                large.prepare_indexed_fixture("auth", fixture, MagicMock())
            poll.assert_not_called()

    def test_capture_state_saves_rows_before_rejecting_lost_fingerprint(self):
        item_id, source_key = "1" * 32, "2" * 32
        key = (item_id, source_key)
        expected = {key: {"item_id": item_id, "source_key": source_key, "url_hash": large.digest("url"),
                          "sha1": "a" * 40, "file_size": 123}}
        item = {"Id": item_id, "MediaSources": [{"Id": source_key, "Path": "url",
                "MediaStreams": [{"Type": "Video", "Codec": "h264"}]}]}
        recorder = MagicMock()
        with patch.object(large, "fingerprint_map", return_value={}), \
             patch.object(large, "native_items_by_id", return_value={item_id: item}):
            with self.assertRaisesRegex(RuntimeError, "do not reconcile"):
                large.capture_state("auth", {"names": ["one"]}, {"one": item}, expected, recorder, "stopped")
        saved = recorder.snapshot.call_args.args[1]
        self.assertEqual(saved["expected_rows"], [expected[key]])
        self.assertEqual(saved["actual_rows"], [])

    def test_failed_started_scenario_stops_but_does_not_delete_diagnostics(self):
        state = large.ScenarioState()
        state.workspace = Path("/unused-owned-workspace")
        state.instance_started = True
        summary = {"status": "FAIL"}
        with patch.object(large.pe, "compose") as compose, \
             patch.object(large.pe, "inspect_owned_container_states", return_value=[]), \
             patch.object(large.pe, "cleanup_instance") as cleanup:
            large.finalize_scenario(summary, state, False)
        compose.assert_called_once_with("stop")
        cleanup.assert_not_called()
        self.assertEqual(summary["cleanup"]["status"], "PRESERVED AFTER FAILURE")

    def test_successful_started_scenario_requires_complete_service_exit_evidence(self):
        state = large.ScenarioState()
        state.workspace = Path("/unused-owned-workspace")
        state.instance_started = True
        summary = {"status": "PASS"}
        with patch.object(large.pe, "cleanup_instance", side_effect=RuntimeError("missing service")) as cleanup:
            large.finalize_scenario(summary, state, False)
        cleanup.assert_called_once_with(required_services=("jellyfin", "media"))
        self.assertEqual(summary["status"], "FAIL")

    def test_capture_state_rejects_changed_native_stream_before_playback(self):
        item_id, source_key = "1" * 32, "2" * 32
        key = (item_id, source_key)
        expected = {key: {"item_id": item_id, "source_key": source_key, "url_hash": large.digest("url"),
                          "sha1": "a" * 40, "file_size": 123}}
        item = {"Id": item_id, "MediaSources": [{"Id": source_key, "Path": "url",
                "MediaStreams": [{"Type": "Video", "Codec": "h264"}]}]}
        with patch.object(large, "fingerprint_map", return_value=expected), \
             patch.object(large, "native_items_by_id", return_value={item_id: item}):
            native = large.capture_state("auth", {"names": ["one"]}, {"one": item},
                                         expected, MagicMock(), "pre-restart")
            item["MediaSources"][0]["MediaStreams"][0]["Codec"] = "hevc"
            with self.assertRaisesRegex(RuntimeError, "main-stream signature changed"):
                large.capture_state("auth", {"names": ["one"]}, {"one": item}, expected,
                                    MagicMock(), "restart-before-playback", native)

    def test_native_stop_callback_runs_after_accepted_stop_before_settlement(self):
        before = {"Id": "task", "State": "Idle",
                  "LastExecutionResult": {"StartTimeUtc": "old"}}
        running = {"Id": "task", "State": "Running", "CurrentProgressPercentage": 10}
        cancelled = {"Id": "task", "State": "Idle",
                     "LastExecutionResult": {"StartTimeUtc": "new", "Status": "Cancelled"}}
        order = []
        with patch.object(large, "current_task", side_effect=[before, running, cancelled]), \
             patch.object(large.scan, "start_task", return_value=204), \
             patch.object(large.scan, "stop_task", side_effect=lambda *args: order.append("stop") or 204):
            result = large.run_task("auth", MagicMock(), stop_after=lambda *args: True, poll_seconds=0,
                                    on_stop=lambda task: order.append("rerun"))
        self.assertEqual(order, ["stop", "rerun"])
        self.assertEqual(result["task"], cancelled)

    def test_candidate_identity_reconciliation_is_order_independent(self):
        result = large.reconcile_candidate_identities(
            ["00000000-0000-0000-0000-000000000002", "00000000-0000-0000-0000-000000000001"],
            ["00000000000000000000000000000001", "00000000000000000000000000000002"],
        )

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["missing"], 0)
        self.assertEqual(result["unexpected"], 0)

    def test_equal_counts_with_duplicate_and_missing_id_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "duplicate identities"):
            large.reconcile_candidate_identities(
                ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"],
                ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000001"],
            )

    def test_equal_counts_with_missing_and_replacement_id_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "do not reconcile"):
            large.reconcile_candidate_identities(
                ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"],
                ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000003"],
            )

    def test_settlement_rejects_unaccounted_candidates_and_wrong_probe_count(self):
        fields = {
            "candidates": 3, "raw_candidates": 3, "duplicates": 0, "checked": 3,
            "not_processed": 0, "missing": 0, "revoked": 0, "unread": 0, "read_incomplete": 0,
            "actual_probe_calls": 1, "reliable_success": 1, "probe_incomplete": 0, "need_probe": 1,
            "candidate_fetch_ms": 1, "candidate_fetch_allocated_bytes": 1, "candidate_fetch_peak_bytes": 0,
            "candidate_set_estimated_bytes": 1, "candidate_set_measured_capacity_bytes": 1,
            "candidate_set_retained_bytes": 1, "batch_read_ms": 1, "batch_read_allocated_bytes": 1,
            "batch_reads": 1, "check_stage_incomplete": 0,
            "candidate_fetch_failed": False, "store_unavailable": False, "scope_unavailable": False,
            "disabled": False, "stop_requested": False,
        }

        with self.assertRaisesRegex(RuntimeError, "Expected 0 real plugin probes"):
            large.validate_settlement(fields, expected_candidates=3, expected_probe_calls=0)
        with self.assertRaisesRegex(RuntimeError, "settlement does not reconcile"):
            large.validate_settlement(fields, expected_candidates=4, expected_probe_calls=1)

    def test_settlement_rejects_a_first_trust_mismatch(self):
        fields = {
            "candidates": 3, "raw_candidates": 3, "duplicates": 0, "checked": 3,
            "not_processed": 0, "missing": 0, "revoked": 0, "unread": 0, "read_incomplete": 0,
            "actual_probe_calls": 0, "reliable_success": 0, "probe_incomplete": 0, "need_probe": 0,
            "first_trust": 2,
            "candidate_fetch_ms": 1, "candidate_fetch_allocated_bytes": 1, "candidate_fetch_peak_bytes": 0,
            "candidate_set_estimated_bytes": 1, "candidate_set_measured_capacity_bytes": 1,
            "candidate_set_retained_bytes": 1, "batch_read_ms": 1, "batch_read_allocated_bytes": 1,
            "batch_reads": 1, "check_stage_incomplete": 0,
            "candidate_fetch_failed": False, "store_unavailable": False, "scope_unavailable": False,
            "disabled": False, "stop_requested": False,
        }

        with self.assertRaisesRegex(RuntimeError, "Expected 3 first-trust sources"):
            large.validate_settlement(fields, expected_candidates=3, expected_probe_calls=0,
                                      expected_first_trust=3)

    def test_missing_cost_field_is_rejected(self):
        fields = {name: 0 for name in large.REQUIRED_SUMMARY_FIELDS}
        fields.update({key: False for key in ("candidate_fetch_failed", "store_unavailable",
                       "scope_unavailable", "disabled", "stop_requested")})
        del fields["batch_read_allocated_bytes"]
        with self.assertRaisesRegex(RuntimeError, "missing the cost field"):
            large.validate_settlement(fields, expected_candidates=0, expected_probe_calls=0)

    def test_negative_cost_field_is_rejected(self):
        fields = {name: 0 for name in large.REQUIRED_SUMMARY_FIELDS}
        fields.update({key: False for key in ("candidate_fetch_failed", "store_unavailable",
                       "scope_unavailable", "disabled", "stop_requested")})
        fields["batch_read_allocated_bytes"] = -1
        with self.assertRaisesRegex(RuntimeError, "negative"):
            large.validate_settlement(fields, expected_candidates=0, expected_probe_calls=0)

    def test_probe_start_line_parsing_requires_the_full_marker(self):
        line = ("2026-01-01T00:00:00.000000000Z [INF] Native STRM probe started for item "
                "11111111-1111-1111-1111-111111111111, source_key "
                "22222222-2222-2222-2222-222222222222; running probes 1, active permits 1.")
        parsed = large.parse_probe_start_line(line)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["item_id"], "11111111111111111111111111111111")
        self.assertEqual(parsed["source_key"], "22222222222222222222222222222222")
        self.assertEqual(parsed["running"], 1)
        self.assertIsNone(large.parse_probe_start_line("Native probe accepted for item x."))

    def test_log_tail_never_repeats_a_line(self):
        tail = large.LogTail("unused-container", large.scan.now_utc())
        lines = ["a", "b", "a"]
        first = tail._dedupe(lines)  # type: ignore[attr-defined]
        self.assertEqual(first, ["a", "b"])

    def test_query_watcher_ignores_overlap_lines_from_before_attempt(self):
        started = large.dt.datetime(2026, 1, 1, 0, 0, 1, tzinfo=large.dt.timezone.utc)
        lines = [
            "2026-01-01T00:00:00.900000000Z old OBJECT_READ_STARTED",
            "2026-01-01T00:00:01.100000000Z current CANDIDATE_QUERY_STARTED",
        ]
        self.assertEqual(large.current_round_log_lines(lines, started), [lines[1]])

    def test_docker_log_follower_streams_and_closes_without_injection(self):
        class _FakeStdout:
            def __init__(self, lines):
                self._lines = list(lines)

            def readline(self):
                if not self._lines:
                    return ""
                return self._lines.pop(0)

        class _FakeProcess:
            def __init__(self, lines):
                self.stdout = _FakeStdout(lines)
                self.terminated = False
                self.waited = False

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                self.waited = True
                return 0

            def kill(self):
                raise AssertionError("kill must not be reached after a clean terminate")

        captured: dict[str, list[str]] = {}
        process = _FakeProcess(["2026-01-01T00:00:01.100000000Z CANDIDATE_QUERY_STARTED\n"])

        def fake_popen(args, **kwargs):
            captured["args"] = list(args)
            return process

        follower = large.DockerLogFollower(
            "container", large.dt.datetime(2026, 1, 1, tzinfo=large.dt.timezone.utc), popen=fake_popen)
        lines: list[str] = []
        for _ in range(200):
            lines.extend(follower.drain())
            if lines:
                break
            large.time.sleep(0.005)
        follower.close()

        self.assertIn("--follow", captured["args"])
        self.assertIn("container", captured["args"])
        self.assertEqual(len(lines), 1)
        self.assertIn("CANDIDATE_QUERY_STARTED", lines[0])
        self.assertTrue(process.terminated)
        self.assertTrue(process.waited)

    def query_stop_fixture(self):
        execution = {"stopped": True, "read_started": False, "progress": [0],
                     "stop_requested_utc": "2026-01-01T00:00:01+00:00",
                     "stop_acknowledged_utc": "2026-01-01T00:00:02+00:00",
                     "task": {"LastExecutionResult": {"Status": "Cancelled"}}}
        library = "LibraryId 11111111-1111-1111-1111-111111111111"
        events = [{"kind": "CANDIDATE_QUERY_STARTED", "timestamp": "2026-01-01T00:00:00+00:00",
                   "redacted_line": library},
                  {"kind": "CANDIDATE_QUERY_RETURNED", "timestamp": "2026-01-01T00:00:03+00:00",
                   "redacted_line": library}]
        return execution, events

    def test_query_stage_stop_requires_real_boundaries_and_cancelled_result(self):
        execution, events = self.query_stop_fixture()
        self.assertTrue(large.query_stop_observed(execution, events))
        for values in ({"stopped": False}, {"read_started": True}, {"progress": [1]},
                       {"stop_requested_utc": "2025-12-31T23:59:59+00:00"},
                       {"stop_acknowledged_utc": "2026-01-01T00:00:04+00:00"},
                       {"task": {"LastExecutionResult": {"Status": "Failed"}}}):
            with self.subTest(values=values):
                self.assertFalse(large.query_stop_observed({**execution, **values}, events))
        self.assertFalse(large.query_stop_observed(execution, []))
        self.assertFalse(large.query_stop_observed(execution, events[:1]))
        self.assertFalse(large.query_stop_observed(execution, events + [{"kind": "OBJECT_READ_STARTED"}]))
        self.assertFalse(large.query_stop_observed(execution, events + [{"kind": "CANDIDATE_ID"}]))

    def test_unobserved_required_query_stage_fails_overall_result_closed(self):
        # B FIX REQUIRED: three missed query-stop attempts must not let the acceptance command exit 0/PASS.
        self.assertEqual(large.overall_acceptance_status({"actual_query_stage_stop": False}), ("FAIL", 1))
        self.assertEqual(large.overall_acceptance_status({"actual_query_stage_stop": True}), ("PASS", 0))
        self.assertEqual(
            large.overall_acceptance_status({"actual_query_stage_stop": True, "other": False}),
            ("FAIL", 1))

    def test_query_stage_stop_attempts_keeps_every_missed_attempt_and_reports_unobserved(self):
        missed_stop = {"stopped": True, "query_started_utc": None, "read_started": False}
        calls: list[int] = []

        def attempt() -> tuple[dict, list[dict]]:
            calls.append(1)
            return missed_stop, [{"kind": "OBJECT_READ_STARTED"}]

        result = large.run_query_stage_stop_attempts(attempt)

        self.assertEqual(len(calls), 3)
        self.assertFalse(result["observed"])
        self.assertIsNone(result["stop"])
        self.assertEqual(len(result["attempts"]), 3)
        self.assertTrue(all(not item["observed"] for item in result["attempts"]))
        self.assertTrue(all(item["object_read_started"] for item in result["attempts"]))
        self.assertEqual(large.overall_acceptance_status(
            {"actual_query_stage_stop": bool(result["observed"])}), ("FAIL", 1))

    def test_query_stage_stop_attempts_stops_at_first_observed_window(self):
        observed_stop, observed_events = self.query_stop_fixture()
        missed_stop = {"stopped": True, "query_started_utc": None, "read_started": False}
        sequence = [
            (missed_stop, [{"kind": "OBJECT_READ_STARTED"}]),
            (observed_stop, observed_events),
        ]

        def attempt() -> tuple[dict, list[dict]]:
            return sequence.pop(0)

        result = large.run_query_stage_stop_attempts(attempt)

        self.assertTrue(result["observed"])
        self.assertIs(result["stop"], observed_stop)
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(sequence, [])
        self.assertEqual(large.overall_acceptance_status(
            {"actual_query_stage_stop": bool(result["observed"])}), ("PASS", 0))

    def _run_scenario_with_finalization(self, *, reconcile_error=None, cleanup_error=None, sampler=None):
        """Drive the real run_scenario/finalize_scenario control flow with a successful body and injected teardown.

        The scenario body is stubbed so no instance is needed, while the production finalization and exit-code
        handling run unchanged. Returns the process exit code and the printed, scrubbed summary.
        """

        def fake_body(package, count, run_id, recorder, summary, state, timeout):
            summary["status"] = "PASS"
            state.workspace = Path("/tmp/fake-large-workspace")
            state.before_state = {"marker": True}
            state.sampler = sampler

        class FakeRecorder:
            def __init__(self, *args, **kwargs):
                pass

            def record(self, *args, **kwargs):
                pass

            def set_metadata(self, *args, **kwargs):
                pass

            def finish(self, *args, **kwargs):
                pass

        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            with patch.object(large, "run_scenario_body", side_effect=fake_body), \
                 patch.object(large.scan, "EvidenceRecorder", FakeRecorder), \
                 patch.object(large.pe, "reconcile_instance_state",
                              side_effect=reconcile_error, return_value={} if reconcile_error is None else None), \
                 patch.object(large.pe, "cleanup_instance",
                              side_effect=cleanup_error, return_value={} if cleanup_error is None else None):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    exit_code = large.run_scenario(Path("package.zip"), 1000, evidence, 60, False)
            summary = json.loads(output.getvalue())

        return exit_code, summary

    def test_cleanup_failure_after_successful_body_forces_nonzero_exit_and_fail_status(self):
        # B FIX REQUIRED: a required cleanup failure must never leave the command reporting success, even when
        # the observed scenario body itself reported PASS.
        exit_code, summary = self._run_scenario_with_finalization(
            cleanup_error=RuntimeError("cleanup exploded"))
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["status"], "FAIL")
        self.assertIn("cleanup_error", summary)

    def test_reconciliation_failure_after_successful_body_forces_nonzero_exit_and_fail_status(self):
        exit_code, summary = self._run_scenario_with_finalization(
            reconcile_error=RuntimeError("instance disturbed"))
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["status"], "FAIL")
        self.assertIn("instance_reconciliation_error", summary)

    def test_sampler_stop_failure_after_successful_body_forces_nonzero_exit(self):
        class FailingSampler:
            def stop(self):
                raise RuntimeError("sampler stop failed")

        exit_code, summary = self._run_scenario_with_finalization(sampler=FailingSampler())
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["status"], "FAIL")
        self.assertIn("sampler_cleanup_error", summary)

    def test_successful_finalization_keeps_zero_exit(self):
        exit_code, summary = self._run_scenario_with_finalization()
        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "PASS")

    def test_per_source_media_route_replacement_does_not_change_neighbor(self):
        package_root = ROOT / "artifacts" / "package-env" / "runs"
        package_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=package_root) as temporary:
            workspace = Path(temporary)
            media = workspace / "media"
            media.mkdir()
            (media / "a.mp4").write_bytes(b"source-a")
            (media / "b.mp4").write_bytes(b"source-b")
            with patch.object(large.pe, "WORK", workspace):
                first = large.create_source_route("u0", "a.mp4")
                second = large.create_source_route("u1", "a.mp4")
                large.replace_source_route(first, "b.mp4")

            from urllib.parse import urlsplit

            first_path = media / urlsplit(first).path.lstrip("/")
            second_path = media / urlsplit(second).path.lstrip("/")
            self.assertEqual(first_path.read_bytes(), b"source-b")
            self.assertEqual(second_path.read_bytes(), b"source-a")

    def test_build_fixture_keeps_size_controls_without_sha1(self):
        package_root = ROOT / "artifacts" / "package-env" / "runs"
        package_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=package_root) as temporary:
            workspace = Path(temporary)
            (workspace / "media").mkdir()
            (workspace / "strm").mkdir()
            (workspace / "media" / large.pe.MEDIA_MP4).write_bytes(b"media-a")
            (workspace / "media" / large.MEDIA_B_NAME).write_bytes(b"media-bb")
            with patch.object(large.pe, "WORK", workspace):
                fixture = large.build_fixture(40, "run")

            for name in fixture["url_group"] + fixture["content_group"]:
                manifest = large.scan.read_versioned_manifest(fixture["paths"][name])
                self.assertIsNotNone(manifest["sha1"])
            for name in fixture["size_group"]:
                manifest = large.scan.read_versioned_manifest(fixture["paths"][name])
                self.assertIsNone(manifest["sha1"])
                self.assertIsNotNone(manifest["file_size"])

    def test_native_page_limit_covers_a_three_thousand_candidate_library(self):
        # The candidate read must be paged, not capped at the historical fixed 5000-limit query.
        calls: list[str] = []

        def fake_request_json(method, path, **kwargs):
            calls.append(path)
            start = int(path.split("StartIndex=")[1].split("&")[0])
            limit = 500
            total = 3000
            count = max(0, min(limit, total - start))
            return 200, {"Items": [{"Id": f"{start + index:032d}"} for index in range(count)],
                         "TotalRecordCount": total}

        with patch.object(large.pe, "request_json", side_effect=fake_request_json):
            items = large.paged_native_items("auth", {})

        self.assertEqual(len(items), 3000)
        self.assertEqual(len(calls), 6)


if __name__ == "__main__":
    unittest.main()
