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

    def test_increment_controls_use_real_guid_batches_and_size_has_no_sha1(self):
        package_root = ROOT / "artifacts" / "package-env" / "runs"
        package_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=package_root) as temporary:
            workspace = Path(temporary)
            (workspace / "media").mkdir()
            (workspace / "strm").mkdir()
            (workspace / "media" / large.pe.MEDIA_MP4).write_bytes(b"media-a")
            (workspace / "media" / large.MEDIA_B_NAME).write_bytes(b"media-bb")
            with patch.object(large.pe, "WORK", workspace):
                fixture = large.build_fixture(512, "run")
                # Name order is deliberately opposite to native Guid order.
                items = {name: {"Id": f"{511-index:032x}"}
                         for index, name in enumerate(fixture["names"])}
                candidate_ids = [item["Id"] for item in items.values()]
                recorder = MagicMock()
                large.assign_increment_controls(fixture, items, candidate_ids, recorder)
                groups = [fixture[group] for group in ("url_group", "content_group", "size_group")]
                self.assertEqual(len({name for group in groups for name in group}), 12)
                for group in groups:
                    self.assertEqual({int(items[name]["Id"], 16) // 128 for name in group}, {0, 1, 2, 3})
                self.assertEqual(len(recorder.record.call_args.kwargs["controls"]), 12)

            for name in fixture["url_group"] + fixture["content_group"]:
                manifest = large.scan.read_versioned_manifest(fixture["paths"][name])
                self.assertIsNotNone(manifest["sha1"])
            for name in fixture["size_group"]:
                manifest = large.scan.read_versioned_manifest(fixture["paths"][name])
                self.assertIsNone(manifest["sha1"])
                self.assertIsNotNone(manifest["file_size"])

    def test_increment_controls_reject_insufficient_real_batches(self):
        fixture = {"names": ["one"]}
        with self.assertRaisesRegex(RuntimeError, "four distinct"):
            large.assign_increment_controls(fixture, {"one": {"Id": "0" * 32}}, ["0" * 32], MagicMock())

    def test_resource_sample_includes_both_services_and_host_storage(self):
        recorder = MagicMock()
        sampler = large.ResourceSampler("owned-jellyfin", recorder)
        host = {"memory_available_bytes": 100, "root_disk_free_bytes": 200, "root_inode_free": 300}
        with patch.object(large, "system_profile", return_value=host), \
             patch.object(large, "docker_stats", side_effect=[{"memory": "jf"}, {"memory": "media"}]) as stats, \
             patch.object(large.pe, "container_name", return_value="owned-media"):
            sampler.sample_once()
        self.assertEqual([call.args[0] for call in stats.call_args_list], ["owned-jellyfin", "owned-media"])
        self.assertEqual(recorder.record.call_args.kwargs["disk_free_bytes"], 200)
        self.assertEqual(recorder.record.call_args.kwargs["inode_free"], 300)

    def test_planned_restart_records_gap_but_propagates_restart_failure(self):
        recorder = MagicMock()
        sampler = large.ResourceSampler("owned-jellyfin", recorder)
        with patch.object(large.scan, "restart", side_effect=RuntimeError("restart failed")):
            with self.assertRaisesRegex(RuntimeError, "restart failed"):
                large.sampled_restart(sampler)
        self.assertEqual([call.args[0] for call in recorder.record.call_args_list],
                         ["resource_sampling_gap_started", "resource_sampling_gap_ended"])

    def test_sampling_failure_still_fails_closed_outside_planned_restart(self):
        sampler = large.ResourceSampler("owned-jellyfin", MagicMock())
        with patch.object(sampler.stopped, "wait", side_effect=[False, True]), \
             patch.object(sampler, "sample_once", side_effect=RuntimeError("sample failed")):
            sampler._sample()
        self.assertEqual(sampler.failure, "RuntimeError")
        self.assertTrue(sampler.stopped.is_set())

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


class PreparedLibraryReuseTests(unittest.TestCase):
    def make_prepared(self, root):
        source = root / "runs" / "prepared"
        for name in ("config/data", "strm", "media", "cache", "media-server"):
            (source / name).mkdir(parents=True, exist_ok=True)
        (source / large.pe.RUN_MARKER).write_text("a" * 32 + "\n")
        (source / "credentials.local.json").write_text('{}')
        with contextlib.closing(large.sqlite3.connect(source / "config/data/jellyfin.db")) as connection:
            connection.execute("create table test (value text)")
        (source / "strm/sentinel.strm").write_text("unchanged-source")
        return source

    def test_copy_keeps_all_files_with_new_token_and_no_shared_inodes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = self.make_prepared(base)
            with patch.multiple(large.pe, BASE=base, WORK=base, _OWNED_WORKSPACE=None, _RUN_TOKEN=None), \
                 patch.object(large, "require_source_stopped"):
                copied, before = large.copy_prepared_workspace(source)
                self.assertEqual(large.prepared_manifest(source), before)
                self.assertNotEqual((copied / large.pe.RUN_MARKER).read_bytes(),
                                    (source / large.pe.RUN_MARKER).read_bytes())
                self.assertEqual((copied / "strm/sentinel.strm").read_text(), "unchanged-source")
                self.assertFalse(large.os.path.samefile(source / "strm/sentinel.strm",
                                                       copied / "strm/sentinel.strm"))
                (copied / "strm/sentinel.strm").write_text("only-copy")
                self.assertEqual(large.prepared_manifest(source), before)

    def test_copy_refuses_live_source_before_claiming_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = self.make_prepared(base)
            with patch.object(large.pe, "BASE", base), \
                 patch.object(large, "require_source_stopped", side_effect=RuntimeError("live")), \
                 patch.object(large.pe, "select_workspace") as select:
                with self.assertRaisesRegex(RuntimeError, "live"):
                    large.copy_prepared_workspace(source)
                select.assert_not_called()

    def test_copy_refuses_arbitrary_instance_symlink_and_transaction_sidecars(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = self.make_prepared(base)
            with patch.object(large.pe, "BASE", base), \
                 patch.object(large, "require_source_stopped"), \
                 patch.object(large.pe, "select_workspace") as select:
                with self.assertRaisesRegex(RuntimeError, "retained package run"):
                    large.copy_prepared_workspace(base)
                link = base / "runs/link"
                link.symlink_to(source, target_is_directory=True)
                with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                    large.copy_prepared_workspace(link)
                (source / "strm/link.strm").symlink_to(source / "strm/sentinel.strm")
                with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                    large.copy_prepared_workspace(source)
                (source / "strm/link.strm").unlink()
                for suffix in ("-wal", "-shm", "-journal"):
                    sidecar = source / ("config/data/jellyfin.db" + suffix)
                    sidecar.touch()
                    with self.assertRaisesRegex(RuntimeError, "sidecars"):
                        large.copy_prepared_workspace(source)
                    sidecar.unlink()
                select.assert_not_called()

    def test_source_mount_guard_rejects_parent_child_and_exact_overlap(self):
        source = Path("/safe/prepared")
        for mounted in (source, source.parent, source / "config"):
            containers = [{"Mounts": [{"Type": "bind", "Source": str(mounted)}]}]
            with patch.object(large.pe, "run", side_effect=[
                    MagicMock(returncode=0, stdout="id"),
                    MagicMock(returncode=0, stdout=json.dumps(containers))]):
                with self.assertRaisesRegex(RuntimeError, "live copy"):
                    large.require_source_stopped(source)
        with patch.object(large.pe, "run", return_value=MagicMock(returncode=1)):
            with self.assertRaisesRegex(RuntimeError, "Cannot check"):
                large.require_source_stopped(source)

    def test_reuse_guard_refuses_foreign_workspace_even_beneath_package_base(self):
        container = {"Config": {"Labels": {"com.docker.compose.project.config_files":
                                            str(large.pe.WORK / "compose.yaml")}},
                     "Mounts": [{"Type": "bind", "Source": str(large.pe.BASE / "runs/foreign")}]}
        with patch.object(large.pe, "WORK", large.pe.BASE / "runs/owned"), \
             patch.object(large.pe, "run", side_effect=[MagicMock(returncode=0, stdout="id"),
                 MagicMock(returncode=0, stdout=json.dumps([container]))]):
            with self.assertRaisesRegex(RuntimeError, "different compose|foreign workspace"):
                large.require_owned_reuse_containers()

    def test_prepared_fixture_retains_1004_not_truncated_to_1000(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "strm").mkdir(); (root / "media").mkdir()
            for index in range(1004):
                (root / "strm" / f"item-{index}.strm").write_text(
                    "# strm-probe-version:1\nhttp://media:8080/a.mp4\n")
            (root / "strm/legacy.strm").write_text("http://media:8080/a.mp4\n")
            (root / "strm/unknown.strm").write_text("# strm-probe-version:99\nhttp://media:8080/a.mp4\n")
            (root / "strm/ordinary.mp4").write_bytes(b"\x00\xff")
            (root / "media/external.strm").write_text("outside")
            with patch.object(large.pe, "WORK", root):
                self.assertEqual(len(large.prepared_fixture(1000)["names"]), 1004)
                with self.assertRaisesRegex(RuntimeError, "below the minimum"):
                    large.prepared_fixture(1005)

    def test_reset_only_moves_owned_copy_store_and_preserves_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = self.make_prepared(base)
            with patch.multiple(large.pe, BASE=base, WORK=base, _OWNED_WORKSPACE=None, _RUN_TOKEN=None), \
                 patch.object(large, "require_source_stopped"):
                copied, _ = large.copy_prepared_workspace(source)
                database = large.pkg.fingerprint_database()
                database.parent.mkdir(parents=True, exist_ok=True)
                database.write_bytes(b"retained-store")
                large.reset_copied_fingerprints(MagicMock())
                self.assertFalse(database.exists())
                self.assertEqual((copied / "baseline-backup/strm-fingerprints.db").read_bytes(), b"retained-store")
                self.assertTrue((source / "strm/sentinel.strm").exists())
            with patch.object(large.pe, "workspace", side_effect=RuntimeError("not owned")):
                with self.assertRaisesRegex(RuntimeError, "not owned"):
                    large.reset_copied_fingerprints(MagicMock())

    def test_reuse_reconciliation_protects_inputs_but_allows_verified_outputs(self):
        before = {area: {"file": "hash"} for area in large.pe.STATE_AREAS}
        after = {**before, "fingerprint_database": {"file": "new-fingerprint"},
                 "scheduled_tasks": {"file": "new-execution-result"}}
        with patch.object(large.pe, "capture_instance_state", return_value=after):
            self.assertEqual(large.reconcile_prepared_inputs(before)["status"], "CLEAN")
            for area in large.REUSE_PROTECTED_AREAS:
                changed = {**after, area: {"file": "unexpected"}}
                with patch.object(large.pe, "capture_instance_state", return_value=changed):
                    with self.assertRaisesRegex(RuntimeError, "input changed"):
                        large.reconcile_prepared_inputs(before)

    def test_reuse_reconciliation_allows_tracked_controlled_edits_only(self):
        before = {area: {"file": "hash"} for area in large.pe.STATE_AREAS}
        edited = {**before, "media": {"file": "hash", "large-source/c0.mp4": "new"},
                  "strm": {"file": "hash", "Large 1.strm": "new"}}
        tracker = {"media": {"large-source/c0.mp4": "new"}, "strm": {"Large 1.strm": "new"}}
        with patch.object(large, "_REUSE_EDIT_TRACKER", tracker), \
             patch.object(large.pe, "capture_instance_state", return_value=edited):
            result = large.reconcile_prepared_inputs(before)
        self.assertEqual(result["status"], "CLEAN")
        self.assertEqual(result["controlled_edits"], {"media": ["large-source/c0.mp4"],
                                                      "strm": ["Large 1.strm"]})
        # An untracked edit to the same area is still rejected.
        untracked = {**edited, "media": {"file": "hash", "large-source/c1.mp4": "surprise"}}
        with patch.object(large, "_REUSE_EDIT_TRACKER", tracker), \
             patch.object(large.pe, "capture_instance_state", return_value=untracked):
            with self.assertRaisesRegex(RuntimeError, "input changed: media"):
                large.reconcile_prepared_inputs(before)

    def test_stop_checks_both_service_exits_and_never_deletes(self):
        states = [{"service": service, "status": "exited", "exit_code": 0, "oom_killed": False,
                   "error": "", "finished_at": "2026-10-19T00:00:00Z"} for service in ("jellyfin", "media")]
        with patch.object(large.pe, "workspace"), patch.object(large, "require_owned_reuse_containers"), \
             patch.object(large.pe, "compose") as compose, \
             patch.object(large.pe, "inspect_owned_container_states", return_value=states), \
             patch.object(large.shutil, "rmtree") as delete:
            self.assertEqual(large.stop_and_retain_reuse()["status"], "STOPPED AND RETAINED")
            compose.assert_called_once_with("stop")
            delete.assert_not_called()
            states[0]["exit_code"] = 137
            with self.assertRaisesRegex(RuntimeError, "did not exit cleanly"):
                large.stop_and_retain_reuse()
            states.pop()
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                large.stop_and_retain_reuse()

    def execute_mock_reuse(self, failure=None, scenario="unchanged", checks_error=None):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        recorder = MagicMock()
        patches = {
            "copy_prepared_workspace": (ROOT / "artifacts/package-env/runs/test-copy", {"file": "hash"}),
            "prepared_manifest": {"file": "hash"}, "require_owned_reuse_containers": None,
            "system_profile": {}, "RunBudget": MagicMock(limits={}, floors={}),
            "ResourceSampler": MagicMock(), "plugin_probe_count": 0,
            "stop_and_retain_reuse": {"status": "STOPPED AND RETAINED"},
            "reconcile_prepared_inputs": {"status": "CLEAN"},
            "prepared_fixture": {"names": ["a"] * 1004, "controls": {}},
        }
        mocks = {name: stack.enter_context(patch.object(large, name, return_value=value))
                 for name, value in patches.items()}
        checks = stack.enter_context(patch.object(large, "run_prepared_checks", return_value={
            "supported_count": 1004, "candidate_count": 1007, "rounds": {"unchanged": "PASS"}},
            side_effect=checks_error))
        mocks["checks"] = checks
        full = stack.enter_context(patch.object(
            large, "run_reuse_full_scenario",
            side_effect=lambda auth, fixture, minimum, recorder, state, summary, timeout, deploy:
                summary.update(status="PASS")))
        mocks["full"] = full
        stack.enter_context(patch.object(large.pp, "verify_archive", return_value={"archiveSha256": "hash"}))
        stack.enter_context(patch.object(large.scan, "EvidenceRecorder", return_value=recorder))
        for name, value in {"capture_instance_state": {}, "deploy_archive": {}, "compose": None,
                            "wait_healthy": "container", "container_name": "container",
                            "reconcile_instance_state": {"status": "CLEAN"}}.items():
            mocks[name] = stack.enter_context(patch.object(large.pe, name, return_value=value))
        for name, value in {"api_auth": "auth", "plugin_status": "Active", "task_list": [],
                            "snapshot_triggers": {}, "restore_triggers": None,
                            "docker_container_identity": {}}.items():
            mocks[name] = stack.enter_context(patch.object(large.scan, name, return_value=value))
        stack.enter_context(patch.object(large.pkg, "deployed_matches_archive", return_value={"matched": True}))
        stack.enter_context(patch.object(large, "full_docker_log", return_value=["log"]))
        for name in ("getitimer", "getsignal", "signal", "setitimer"):
            stack.enter_context(patch.object(large.signal, name, return_value=(0, 0) if name == "getitimer" else 0))
        listener = stack.enter_context(patch.object(large.socket, "socket"))
        for name in ("build_fixture", "prepare_native_streams", "prepare_indexed_fixture"):
            mocks[name] = stack.enter_context(patch.object(large, name, side_effect=AssertionError("must not rebuild")))
        mocks["prepare_clean_instance"] = stack.enter_context(patch.object(large.pe, "prepare_clean_instance",
                                                                       side_effect=AssertionError("must not initialize")))
        mocks["cleanup_instance"] = stack.enter_context(patch.object(large.pe, "cleanup_instance",
                                                                 side_effect=AssertionError("must not delete")))
        if failure:
            mocks[failure].side_effect = RuntimeError("finalization failed")
        with contextlib.redirect_stdout(io.StringIO()):
            result = large.run_reuse_scenario(Path("candidate.zip"), Path("source"), 1000, scenario,
                                             Path("evidence"), 300, False)
        return result, recorder.finish.call_args.args[1], mocks

    def test_reuse_orchestration_never_rebuilds_or_claims_full_acceptance(self):
        result, summary, mocks = self.execute_mock_reuse()
        self.assertEqual(result, 0)
        self.assertEqual(summary["status"], "PARTIAL")
        self.assertEqual(summary["focused_status"], "PASS")
        self.assertEqual(summary["full_task_acceptance"], "NOT RUN")
        self.assertEqual(summary["supported_count"], 1004)
        self.assertTrue(summary["source_unchanged"])
        for name in ("build_fixture", "prepare_native_streams", "prepare_indexed_fixture",
                     "prepare_clean_instance", "cleanup_instance"):
            mocks[name].assert_not_called()
        mocks["stop_and_retain_reuse"].assert_called_once()
        mocks["full"].assert_not_called()

    def test_reuse_all_runs_full_scenario_without_rebuilding_or_rescanning(self):
        # B FIX REQUIRED: reuse --scenario all must run the complete required behavior on the copied
        # library rather than reject the scenario or run a weaker focused path.
        result, summary, mocks = self.execute_mock_reuse(scenario="all")
        self.assertEqual(result, 0)
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["focused_status"], "PASS")
        self.assertEqual(summary["full_task_acceptance"], "PASS")
        self.assertEqual(summary["not_run"], ["independent-B-review"])
        mocks["full"].assert_called_once()
        mocks["checks"].assert_not_called()
        for name in ("build_fixture", "prepare_native_streams", "prepare_indexed_fixture",
                     "prepare_clean_instance", "cleanup_instance"):
            mocks[name].assert_not_called()
        mocks["stop_and_retain_reuse"].assert_called_once()

    def test_reuse_all_full_scenario_failure_is_nonzero_and_preserved(self):
        result, summary, mocks = self.execute_mock_reuse("full", scenario="all")
        self.assertEqual(result, 1)
        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual(summary["focused_status"], "FAIL")
        self.assertNotEqual(summary.get("full_task_acceptance"), "PASS")
        mocks["stop_and_retain_reuse"].assert_called_once()

    def test_reuse_full_scenario_verifies_copy_and_delegates_without_rebuilding(self):
        names = [f"Large 29666cbef60d {i:05d}" for i in range(1004)]
        paths = {name: Path(f"/tmp/{name}.strm") for name in names}
        fixture = {"names": names, "paths": paths, "controls": {"out_of_scope": "external"}, "urls": {}}
        items = {name: {"Id": f"{index:032x}", "Name": name,
                        "Path": "/media/strm/" + name + ".strm"} for index, name in enumerate(names)}
        items["external"] = {"Id": "f" * 32, "Name": "external", "Path": "/media/local/external.strm"}
        supported_ids = [items[name]["Id"] for name in names]
        candidates = {"supported_ids": supported_ids, "ids": supported_ids,
                      "control_ids": {}, "count": len(names), "supported_count": len(names)}
        expected = {("1" * 32, "2" * 32): {"item_id": "1" * 32, "source_key": "2" * 32,
                    "url_hash": "hash", "sha1": None, "file_size": 7}}
        seen = {}
        def assign(fx, it, ids, recorder):
            fx.update(url_group=["u"], content_group=["c"], size_group=["s"])
        with patch.object(large, "resolve_prepared_items", return_value=items), \
             patch.object(large, "prepared_selected_library", return_value="library"), \
             patch.object(large.pe, "media_sha1", return_value=("a" * 40, 25179)), \
             patch.object(large, "capture_candidates", return_value=candidates), \
             patch.object(large, "assign_increment_controls", side_effect=assign), \
             patch.object(large, "wait_native_task_idle"), \
             patch.object(large.scan, "run_native_scan_completed", return_value=({}, ("a", "b"))), \
             patch.object(large, "poll_fixture_items", return_value={}), \
             patch.object(large, "prepare_reuse_increment_baselines") as prepare, \
             patch.object(large.scan, "plugin_action", return_value=204), \
             patch.object(large, "sampled_restart"), \
             patch.object(large, "wait_items_by_name", return_value=items), \
             patch.object(large, "reconcile_candidate_identities", return_value={}), \
             patch.object(large, "expected_all_rows", return_value=expected), \
             patch.object(large, "assert_native_sources"), \
             patch.object(large, "fingerprint_map", return_value={}), \
             patch.object(large, "capture_state", return_value={"source": "stable"}), \
             patch.object(large, "container_identity", return_value={"id": "owned"}), \
             patch.object(large.pe, "container_name", return_value="owned"), \
             patch.object(large.scan, "api_auth", return_value="auth"), \
             patch.object(large, "run_full_behavior",
                    side_effect=lambda *a, **kw: seen.update(args=a, kwargs=kw)):
            large.run_reuse_full_scenario("auth", fixture, 1000, MagicMock(), large.ScenarioState(),
                                          {}, 120, {"deployment": "zip"})
        prepare.assert_called_once()
        self.assertEqual(prepare.call_args.args[2], ["u", "c", "s"])
        self.assertEqual(seen["args"][2], "owned")

    def test_reuse_full_scenario_refuses_nonempty_fingerprints_without_reset(self):
        fixture = {"names": ["one"], "paths": {"one": Path("/tmp/one.strm")}, "controls": {"out_of_scope": "external"}, "urls": {}}
        items = {"one": {"Id": "1" * 32}, "external": {"Id": "f" * 32}}
        with patch.object(large, "resolve_prepared_items", return_value=items), \
             patch.object(large, "prepared_selected_library", return_value="library"), \
             patch.object(large.pe, "media_sha1", return_value=("a" * 40, 25179)), \
             patch.object(large, "capture_candidates", return_value={"supported_ids": ["1" * 32],
                    "ids": ["1" * 32], "control_ids": {}, "count": 1, "supported_count": 1}), \
             patch.object(large, "assign_increment_controls",
                    side_effect=lambda fx, *a: fx.update(url_group=[], content_group=[], size_group=[])), \
             patch.object(large, "wait_native_task_idle"), \
             patch.object(large.scan, "run_native_scan_completed", return_value=({}, ("a", "b"))), \
             patch.object(large, "poll_fixture_items", return_value={}), \
             patch.object(large, "prepare_reuse_increment_baselines"), \
             patch.object(large.scan, "plugin_action", return_value=204), \
             patch.object(large, "sampled_restart"), \
             patch.object(large, "wait_items_by_name", return_value=items), \
             patch.object(large, "reconcile_candidate_identities", return_value={}), \
             patch.object(large, "expected_all_rows", return_value={("1" * 32, "2" * 32): {}}), \
             patch.object(large, "assert_native_sources"), \
             patch.object(large, "fingerprint_map", return_value={("1" * 32, "2" * 32): {}}), \
             patch.object(large.scan, "api_auth", return_value="auth"), \
             patch.object(large, "run_full_behavior") as behavior:
            with self.assertRaisesRegex(RuntimeError, "empty copied fingerprint"):
                large.run_reuse_full_scenario("auth", fixture, 1, MagicMock(), large.ScenarioState(), {}, 120, {})
            behavior.assert_not_called()

    def test_reuse_finalization_failures_force_nonzero_and_keep_workspace(self):
        for failure in ("stop_and_retain_reuse", "restore_triggers", "prepared_manifest", "reconcile_prepared_inputs"):
            with self.subTest(failure=failure):
                result, summary, _ = self.execute_mock_reuse(failure)
                self.assertEqual(result, 1)
                self.assertEqual(summary["status"], "FAIL")
                self.assertTrue(summary["finalization_errors"])

    def test_failed_check_still_restores_triggers_stops_and_retains(self):
        result, summary, mocks = self.execute_mock_reuse(checks_error=RuntimeError("bad state"))
        self.assertEqual(result, 1)
        mocks["restore_triggers"].assert_called_once()
        mocks["stop_and_retain_reuse"].assert_called_once()
        mocks["cleanup_instance"].assert_not_called()

    def drive_prepared_checks(self, scenario, baseline=None):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        names = ["item"]
        controls = {"legacy": "legacy", "unknown": "unknown", "ordinary": "ordinary", "out_of_scope": "external"}
        fixture = {"names": names, "controls": controls}
        items = {name: {"Id": f"{index+1:032x}", "Name": name,
                       "Path": "/media/" + ("local/" if name == "external" else "strm/") + name + ".strm"}
                 for index, name in enumerate(names + list(controls.values()))}
        expected = {("1" * 32, "2" * 32): {"item_id": "1" * 32, "source_key": "2" * 32,
                    "url_hash": "hash", "sha1": None, "file_size": 7}}
        ids = [items[name]["Id"] for name in names + ["legacy", "unknown", "ordinary"]]
        candidates = {"supported_ids": [ids[0]], "ids": ids, "control_ids": dict(zip(["legacy", "unknown", "ordinary"], ids[1:])),
                      "count": 4, "supported_count": 1}
        for name, value in {"prepared_fixture": fixture, "resolve_prepared_items": items,
                            "prepared_selected_library": "library", "native_items_by_id": {i["Id"]: i for i in items.values()},
                            "capture_candidates": candidates, "expected_all_rows": expected,
                            "assert_native_sources": None, "fingerprint_map": expected if baseline is None else baseline,
                            "plugin_probe_count": 0}.items():
            stack.enter_context(patch.object(large, name, return_value=value))
        stack.enter_context(patch.object(large.pe, "container_name", return_value="owned"))
        stack.enter_context(patch.object(large.scan, "api_auth", return_value="auth"))
        events = []
        capture = stack.enter_context(patch.object(large, "capture_state",
                   side_effect=lambda *a, **kw: events.append((a[5], kw)) or {"source": "stable"}))
        run = stack.enter_context(patch.object(large, "run_round", return_value={"fields": {"actual_probe_calls": 0}}))
        restart = stack.enter_context(patch.object(large, "sampled_restart", side_effect=lambda *a: events.append(("restart", {}))))
        return lambda: large.run_prepared_checks("auth", scenario, 1000, MagicMock(), large.ScenarioState(), 120), events, run

    def test_first_trust_refuses_existing_fingerprints_without_silent_reset(self):
        execute, events, run = self.drive_prepared_checks("baseline")
        with self.assertRaisesRegex(RuntimeError, "empty copied fingerprint"):
            execute()
        run.assert_not_called()
        self.assertEqual(events, [])

    def test_baseline_snapshots_native_before_first_trust_and_restart_before_playback(self):
        execute, events, run = self.drive_prepared_checks("baseline", baseline={})
        result = execute()
        self.assertEqual(list(result["rounds"]), ["first_trust", "unchanged", "restart"])
        self.assertEqual(events[0], ("before-check", {"empty_fingerprints": True}))
        self.assertEqual(events[-2:], [("restart", {}), ("restart-before-playback", {})])
        self.assertEqual([call.args[6] for call in run.call_args_list], [1, 0])
        self.assertTrue(all(call.args[5] == 0 for call in run.call_args_list))

    def test_unchanged_only_does_not_restart(self):
        execute, events, run = self.drive_prepared_checks("unchanged")
        result = execute()
        self.assertEqual(list(result["rounds"]), ["unchanged"])
        self.assertFalse(any(label == "restart" for label, _ in events))
        run.assert_called_once()

    def test_cli_requires_explicit_mode_and_refuses_invalid_combinations(self):
        common = ["runner", "--package", "candidate.zip", "--evidence-dir", "new-evidence"]
        for options in ([], ["--reuse-workspace", "source", "--fresh"],
                        ["--reuse-workspace", "source", "--reset-copied-fingerprints"],
                        ["--fresh", "--scenario", "baseline"], ["--fresh", "--count", "999"]):
            with patch.object(large.sys, "argv", common + options), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    large.main()
                self.assertEqual(error.exception.code, 2)

    def test_cli_accepts_reuse_all_as_the_full_retained_library_scenario(self):
        common = ["runner", "--package", "candidate.zip", "--evidence-dir", "new-evidence",
                  "--reuse-workspace", "source", "--count", "1000", "--scenario", "all",
                  "--reset-copied-fingerprints"]
        with patch.object(large.sys, "argv", common), \
             patch.object(large, "run_reuse_scenario", return_value=0) as execute:
            self.assertEqual(large.main(), 0)
            self.assertEqual(execute.call_args.args[2:4], (1000, "all"))
            self.assertTrue(execute.call_args.args[6])

    def test_cli_defaults_to_1000_minimum_unchanged_and_accepts_actual_1004(self):
        common = ["runner", "--package", "candidate.zip", "--evidence-dir", "new-evidence",
                  "--reuse-workspace", "source"]
        for options, count in (([], 1000), (["--count", "1004"], 1004)):
            with patch.object(large.sys, "argv", common + options), \
                 patch.object(large, "run_reuse_scenario", return_value=0) as execute:
                self.assertEqual(large.main(), 0)
                self.assertEqual(execute.call_args.args[2:4], (count, "unchanged"))


if __name__ == "__main__":
    unittest.main()
