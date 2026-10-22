"""Guardrails for the isolated batch integration script; these are not real Jellyfin acceptance tests."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_isolated_batch_integration", ROOT / "scripts" / "run_isolated_batch_integration.py"
)
batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(batch)


class BatchScriptGuardTests(unittest.TestCase):
    def test_slow_url_uses_the_isolated_slow_route(self):
        result = batch.slow_url("http://media:8080/fixture.mp4", "abc123")
        self.assertEqual(result, "http://media:8080/slow/abc123/fixture.mp4")

    def test_delay_url_encodes_a_parameterized_settlement_window(self):
        result = batch.delay_url("http://media:8080/fixture.mp4", 8, "abc123")
        self.assertEqual(result, "http://media:8080/delay/8/abc123/fixture.mp4")
        fractional = batch.delay_url("http://media:8080/fixture.mp4", 2.5, "def")
        self.assertEqual(fractional, "http://media:8080/delay/2.5/def/fixture.mp4")

    def test_temporary_fixture_refuses_to_overwrite_and_writes_a_versioned_manifest(self):
        name = "Batch Guard Test"
        # The guard test keeps exercising the real temporary_fixture writer, but roots it in a
        # temporary directory: it must never create or unlink files under the shared artifacts/.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "artifacts" / "dev-env" / "strm" / "Environment Fixture.strm"
            source.parent.mkdir(parents=True)
            source.write_text(
                "# strm-probe-version:1\n# strm-probe-sha1:" + "c" * 40 +
                "\n# strm-probe-size:7\nhttp://media:8080/source.mp4\n",
                encoding="utf-8",
            )
            with patch.object(batch, "ROOT", root), patch.object(batch, "FIXTURE", source):
                path = root / "artifacts" / "dev-env" / "strm" / (name + ".strm")
                written = batch.temporary_fixture(name, "http://media:8080/fixture.mp4", "a" * 40, 10)
                self.assertEqual(written, path)
                text = path.read_text(encoding="utf-8")
                self.assertIn("# strm-probe-version:1", text)
                self.assertIn("# strm-probe-sha1:" + "a" * 40, text)
                self.assertIn("# strm-probe-size:10", text)
                self.assertIn("http://media:8080/fixture.mp4", text)
                self.assertNotIn("http://media:8080/source.mp4", text)
                # A second write must fail rather than silently clobber an existing fixture.
                with self.assertRaises(FileExistsError):
                    batch.temporary_fixture(name, "http://media:8080/other.mp4", "b" * 40, 11)
                self.assertIn("http://media:8080/fixture.mp4", path.read_text(encoding="utf-8"))
            # The test's own input STRM is unchanged and nothing was written to the repository fixtures.
            self.assertIn("http://media:8080/source.mp4", source.read_text(encoding="utf-8"))
        self.assertFalse((ROOT / "artifacts" / "dev-env" / "strm" / (name + ".strm")).exists())

    def test_fingerprint_row_reads_only_the_minimal_five_fields(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "strm-fingerprints.db"
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE strm_fingerprint (item_id TEXT NOT NULL, source_key TEXT NOT NULL, "
                "url_hash TEXT NOT NULL, sha1 TEXT, file_size INTEGER, PRIMARY KEY (item_id, source_key))"
            )
            source_id = "0123456789abcdef0123456789abcdef"
            connection.execute(
                "INSERT INTO strm_fingerprint VALUES (?, ?, ?, ?, ?)",
                (source_id, source_id, "f" * 64, None, 42),
            )
            connection.commit()
            connection.close()
            with patch.object(batch, "FINGERPRINT_DATABASE", database):
                row = batch.fingerprint_row("01234567-89ab-cdef-0123-456789abcdef")
            self.assertEqual(set(row), {"item_id", "source_key", "url_hash", "sha1", "file_size"})
            self.assertIsNone(row["sha1"])
            self.assertEqual(row["file_size"], 42)

    def test_batch_summary_line_is_redacted(self):
        line = (
            "[INF] [9] Jellyfin.Plugin.StrmProbeOptimizer.Tasks.StrmProbeScheduledTask: "
            "STRM media information check finished: candidates 3 (raw 3), checked 1, skipped 1."
        )
        summary = batch.base.safe_event(line)
        self.assertIn("candidates 3", summary)
        self.assertNotIn("http", summary)
        self.assertNotIn("token", summary)

    def test_restore_fixture_reports_unavailable_without_an_item(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "Environment Fixture.strm"
            fixture.write_bytes(b"original")
            with patch.object(batch, "FIXTURE", fixture):
                status = batch.restore_fixture(None, b"restored")
            self.assertEqual(fixture.read_bytes(), b"restored")
            self.assertIn("sync not available", status)

    def test_parse_summary_field_reads_a_redacted_counter(self):
        line = (
            "STRM media information check finished: candidates 3 (raw 3, duplicates 0), checked 2, "
            "actual probe calls 1, store unavailable True."
        )
        self.assertEqual(batch.parse_summary_field(line, "candidates"), 3)
        self.assertEqual(batch.parse_summary_field(line, "actual probe calls"), 1)
        self.assertIsNone(batch.parse_summary_field(line, "missing field"))

    def test_future_time_of_day_ticks_is_ahead_of_now(self):
        import datetime

        ticks = batch.future_time_of_day_ticks(seconds_ahead=70)
        seconds = ticks / 10_000_000
        self.assertGreaterEqual(seconds, 0)
        self.assertLess(seconds, 24 * 3600)
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        target = now_utc + datetime.timedelta(seconds=70)
        # The tick value encodes a time of day; it must be the near-future target (allowing for a minute boundary).
        delta = abs(seconds - (target.hour * 3600 + target.minute * 60 + target.second))
        self.assertLess(min(delta, 86400 - delta), 120)

    def test_restore_state_reports_not_restored_when_the_api_is_unavailable(self):
        # With no reachable isolated server the restore helper must report the failure instead of claiming success.
        # The isolated API and restart are stubbed so this guard test has no real server side effect.
        with patch.object(batch, "CONFIGURATION_FILE", Path("/nonexistent/config.xml")), \
                patch.object(batch.base, "JellyfinApi", side_effect=RuntimeError("no server")), \
                patch.object(batch.base, "restart_isolated_server", side_effect=RuntimeError("no server")):
            status = batch.restore_state(b"<x/>", {"task": [{"Type": "DailyTrigger"}]})
        self.assertIn("NOT RESTORED", status)

    def test_slow_request_counts_counts_each_actual_start(self):
        logs = type("Logs", (), {"returncode": 0, "stdout": "SLOW_MEDIA_REQUEST_STARTED abc\nSLOW_MEDIA_REQUEST_STARTED abc\nSLOW_MEDIA_REQUEST_STARTED def\n", "stderr": ""})()
        with patch.object(batch.base, "run", return_value=logs):
            counts = batch.slow_request_counts("container")
        # A set subtraction cannot detect the same request id starting twice; exact counts must.
        self.assertEqual(counts, {"abc": 2, "def": 1})

    def test_require_cost_fields_rejects_missing_and_negative_values(self):
        complete = {field: 1 for field in batch.REQUIRED_COST_FIELDS}
        batch.require_cost_fields(complete, "summary")
        missing = dict(complete)
        missing.pop("candidate_set_estimated_bytes")
        with self.assertRaises(RuntimeError):
            batch.require_cost_fields(missing, "summary")
        negative = dict(complete, batch_reads=-1)
        with self.assertRaises(RuntimeError):
            batch.require_cost_fields(negative, "summary")

    def test_required_cost_fields_use_the_estimate_and_retained_identity_measurements(self):
        self.assertIn("candidate_set_estimated_bytes", batch.REQUIRED_COST_FIELDS)
        self.assertIn("candidate_set_measured_capacity_bytes", batch.REQUIRED_COST_FIELDS)
        self.assertIn("candidate_set_retained_bytes", batch.REQUIRED_COST_FIELDS)
        self.assertIn("candidate_fetch_peak_bytes", batch.REQUIRED_COST_FIELDS)
        self.assertNotIn("candidate_set_capacity_bytes", batch.REQUIRED_COST_FIELDS)

    def test_parse_log_epoch_reads_the_leading_log_timestamp(self):
        self.assertAlmostEqual(batch.parse_log_epoch("[04:43:37.205] [INF] x"), 4 * 3600 + 43 * 60 + 37.205)
        with self.assertRaises(RuntimeError):
            batch.parse_log_epoch("no timestamp here")

    def test_trigger_arm_time_of_day_seconds_reads_the_local_fire_time(self):
        logs = type("Logs", (), {
            "returncode": 0,
            "stdout": (
                "[INF] Daily trigger for Other Task set to fire at 2026-10-16 03:00:00.000 +00:00, which is 1h from now.\n"
                f"[INF] Daily trigger for {batch.TASK_NAME} set to fire at 2026-10-16 07:12:34.000 +00:00, which is 1h from now.\n"
            ),
            "stderr": "",
        })()
        with patch.object(batch.base, "run", return_value=logs):
            seconds = batch.trigger_arm_time_of_day_seconds("container")
        self.assertEqual(seconds, 7 * 3600 + 12 * 60 + 34)

    def test_probe_start_entries_attribute_starts_per_item(self):
        logs = type("Logs", (), {
            "returncode": 0,
            "stdout": (
                "[04:43:37.205] [INF] Native STRM probe started for item AAAA; running probes 1, active permits 1.\n"
                "[04:43:38.205] [INF] Native STRM probe started for item BBBB; running probes 2, active permits 2.\n"
            ),
            "stderr": "",
        })()
        with patch.object(batch.base, "run", return_value=logs):
            entries = batch.probe_start_entries("container")
            filtered = batch.probe_start_entries("container", since=4 * 3600 + 43 * 60 + 38)
        self.assertEqual(entries, [
            {"item_id": "aaaa", "running": 1, "timestamp": 4 * 3600 + 43 * 60 + 37.205},
            {"item_id": "bbbb", "running": 2, "timestamp": 4 * 3600 + 43 * 60 + 38.205},
        ])
        self.assertEqual([entry["item_id"] for entry in filtered], ["bbbb"])

    def test_trigger_arm_times_parse_the_task_specific_daily_trigger(self):
        logs = type("Logs", (), {
            "returncode": 0,
            "stdout": (
                "[INF] Daily trigger for Other Task set to fire at 2026-10-16 03:00:00.000 +00:00, which is 1h from now.\n"
                f"[INF] Daily trigger for {batch.TASK_NAME} set to fire at 2026-10-16 03:00:00.000 +00:00, which is 1h from now.\n"
            ),
            "stderr": "",
        })()
        with patch.object(batch.base, "run", return_value=logs):
            times = batch.trigger_arm_times("container")
        self.assertEqual(len(times), 1)

    def test_task_completion_events_returns_native_statuses_in_order(self):
        logs = type("Logs", (), {
            "returncode": 0,
            "stdout": (
                f"[04:43:37.205] [INF] {batch.TASK_NAME} Cancelled after 0 minute(s) and 5 seconds\n"
                f"[04:43:38.205] [INF] {batch.TASK_NAME} Completed after 0 minute(s) and 1 seconds\n"
                "[04:43:39.205] [INF] Some Other Task Completed after 0 minute(s) and 1 seconds\n"
            ),
            "stderr": "",
        })()
        with patch.object(batch.base, "run", return_value=logs):
            events = batch.task_completion_events("container")
            self.assertEqual(events, ["Cancelled", "Completed"])
            with_time = batch.task_completion_events_with_time("container")
        self.assertEqual(with_time, [(4 * 3600 + 43 * 60 + 37.205, "Cancelled"), (4 * 3600 + 43 * 60 + 38.205, "Completed")])

    def test_current_round_completion_binds_by_timestamp(self):
        logs = type("Logs", (), {
            "returncode": 0,
            "stdout": (
                f"[04:43:37.205] [INF] {batch.TASK_NAME} Completed after 0 minute(s) and 5 seconds\n"
                f"[04:43:45.205] [INF] {batch.TASK_NAME} Cancelled after 0 minute(s) and 5 seconds\n"
            ),
            "stderr": "",
        })()
        with patch.object(batch.base, "run", return_value=logs):
            # The current round started at 04:43:40, so the older Completed must not be attributed to it.
            self.assertEqual(batch.current_round_completion("container", 4 * 3600 + 43 * 60 + 40), "Cancelled")
            self.assertEqual(batch.current_round_completion("container", 4 * 3600 + 43 * 60 + 30), "Completed")

    def test_parse_summary_float_keeps_fractional_timings(self):
        line = "STRM media information check finished: candidate fetch 9.4124 ms, batch read 29.7333 ms."
        self.assertAlmostEqual(batch.parse_summary_float(line, "candidate fetch"), 9.4124)
        self.assertAlmostEqual(batch.parse_summary_float(line, "batch read"), 29.7333)

    def test_scenario_choices_include_stop_sharing_scope_and_failure(self):
        parser_source = (ROOT / "scripts" / "run_isolated_batch_integration.py").read_text(encoding="utf-8")
        for scenario in ("suite", "discovery", "stop", "sharing", "scope", "failure", "shared_stop", "mixed"):
            self.assertIn(scenario, parser_source)

    def test_summary_fields_reads_the_reconciliation_counters(self):
        line = (
            "STRM media information check finished: candidates 130 (raw 131, duplicates 1), checked 130, "
            "skipped 120, first trust 120, need probe 10, reliable success 8, probe incomplete 2, "
            "check-stage incomplete 0, not processed 0, missing 0, revoked 0, read incomplete 0, unread 0, "
            "actual probe calls 8, candidate fetch 12 ms, candidate fetch allocated 4096 bytes, "
            "candidate set estimated 2080 bytes, candidate set retained 3072 bytes, stop query return 4.5 ms, "
            "batch reads 2, batch read 30 ms, batch read allocated 8192 bytes, stop requested False, store unavailable False."
        )
        fields = batch.summary_fields(line)
        self.assertEqual(fields["candidates"], 130)
        self.assertEqual(fields["raw_candidates"], 131)
        self.assertEqual(fields["duplicates"], 1)
        self.assertEqual(fields["actual_probe_calls"], 8)
        self.assertEqual(fields["candidate_fetch_allocated_bytes"], 4096)
        self.assertEqual(fields["candidate_set_estimated_bytes"], 2080)
        self.assertEqual(fields["candidate_set_retained_bytes"], 3072)
        self.assertAlmostEqual(fields["stop_query_return_ms"], 4.5)
        self.assertEqual(fields["batch_reads"], 2)
        self.assertFalse(fields["stop_requested"])
        self.assertFalse(fields["store_unavailable"])

    def test_assert_summary_equations_accepts_consistent_counters_and_rejects_inconsistent_ones(self):
        good = {
            "checked": 10,
            "skipped": 6,
            "need_probe": 4,
            "check_stage_incomplete": 0,
            "reliable_success": 3,
            "probe_incomplete": 1,
        }
        batch.assert_summary_equations(good)
        bad = dict(good, checked=11)
        with self.assertRaises(RuntimeError):
            batch.assert_summary_equations(bad)

    def test_configuration_payload_from_xml_round_trips_the_five_fields(self):
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<PluginConfiguration>\n'
            "  <Enabled>false</Enabled>\n"
            "  <PlaybackAutoCheck>true</PlaybackAutoCheck>\n"
            "  <MaxConcurrentProbes>4</MaxConcurrentProbes>\n"
            "  <DetailedLog>true</DetailedLog>\n"
            "  <BatchAllLibraries>false</BatchAllLibraries>\n"
            "  <BatchLibraryIds>11111111-1111-1111-1111-111111111111</BatchLibraryIds>\n"
            "</PluginConfiguration>\n"
        ).encode("utf-8")
        payload = batch.configuration_payload_from_xml(xml)
        self.assertFalse(payload["Enabled"])
        self.assertEqual(payload["MaxConcurrentProbes"], 4)
        self.assertFalse(payload["BatchAllLibraries"])
        self.assertEqual(payload["BatchLibraryIds"], "11111111-1111-1111-1111-111111111111")

    def test_slow_request_ids_started_reads_only_request_ids(self):
        logs = type("Logs", (), {"returncode": 0, "stdout": "SLOW_MEDIA_REQUEST_STARTED abc123\nSLOW_MEDIA_REQUEST_STARTED def456\n", "stderr": ""})()
        with patch.object(batch.base, "run", return_value=logs):
            started = batch.slow_request_ids_started("container")
        self.assertEqual(started, {"abc123", "def456"})


class CleanupConvergenceTests(unittest.TestCase):
    """A leftover fixture is still a failure; only the native refresh is retried.

    A native scan can settle before it reconciles an already-deleted ``.strm``, so one refresh is not
    a reliable trigger. Retrying the refresh must never turn a genuinely leftover entry into a pass.
    """

    def _api(self, outcomes):
        calls = {"refresh": 0, "present": 0}

        class Api:
            def refresh_library(self):
                calls["refresh"] += 1

            def wait_for_named_library_item_absent(self, name, timeout=30):
                calls["present"] += 1
                result = outcomes.pop(0) if outcomes else False
                if not result:
                    raise RuntimeError(f"still present: {name}")

        return Api(), calls

    def test_a_late_native_reconciliation_converges_and_leaves_no_problem(self):
        api, calls = self._api([False, True])
        with patch.object(batch, "CLEANUP_PROBLEMS", []):
            batch.cleanup_fixtures(api, ["Batch Mixed Playback abc"])
            self.assertEqual(batch.CLEANUP_PROBLEMS, [])
        self.assertEqual(calls["refresh"], 2)

    def test_a_really_leftover_entry_is_still_recorded_as_a_cleanup_problem(self):
        api, calls = self._api([])
        with patch.object(batch, "CLEANUP_PROBLEMS", []):
            batch.cleanup_fixtures(api, ["Batch Mixed Playback abc"], timeout=0.5)
            self.assertTrue(batch.CLEANUP_PROBLEMS)
            self.assertIn("was not removed", batch.CLEANUP_PROBLEMS[0])
        # The refresh really was retried instead of giving up after one attempt.
        self.assertGreater(calls["refresh"], 1)



class AbsoluteRoundAttributionTests(unittest.TestCase):
    """A round must be measured on real instants, never on a bare time of day.

    The isolated server keeps one rolling log, so an earlier session's entry can carry a later
    time of day than today's round start. That made one pre-existing entry-line count as this
    round's and refused the round for having "20" entries.
    """

    def test_the_container_absolute_prefix_is_authoritative(self):
        line = ("2026-10-22T10:42:27.512000000Z [10:42:27.512] [INF] [7] X: "
                "STRM media information check entered: stop requested False.")
        self.assertAlmostEqual(batch.round_marker(line), 1792665747.512, places=3)
        with self.assertRaises(RuntimeError):
            batch.round_marker("[10:42:27.512] [INF] [7] X: no container prefix")

    def test_an_earlier_days_entry_is_not_attributed_to_todays_round(self):
        old = ("2026-10-21T17:05:10.476000000Z [17:05:10.476] [INF] X: "
               "STRM media information check entered: stop requested at entry False.")
        current = ("2026-10-22T10:42:27.512000000Z [10:42:27.512] [INF] X: "
                   "STRM media information check entered: stop requested at entry False.")
        logs = type("Logs", (), {"returncode": 0, "stdout": old + "\n" + current + "\n", "stderr": ""})()
        round_start = 1792665740.0  # today, just before the current entry
        with patch.object(batch.base, "run", return_value=logs):
            entries = batch.batch_run_entries_absolute("container", round_start)
        self.assertEqual(len(entries), 1)
        self.assertIn("10:42:27.512", entries[0]["line"])
        self.assertNotIn("2026-10-22T", entries[0]["line"])

    def test_summaries_and_completions_use_the_same_absolute_window(self):
        old = ("2026-10-21T17:05:10.476000000Z [17:05:10.476] [INF] X: "
               + batch.TASK_NAME + " Completed after 0 minute(s) and 1 seconds")
        current = ("2026-10-22T10:43:00.000000000Z [10:43:00.000] [INF] X: "
                   + batch.TASK_NAME + " Cancelled after 0 minute(s) and 20 seconds")
        summary_old = ("2026-10-21T17:05:10.476000000Z [17:05:10.476] [INF] X: "
                       "STRM media information check finished: candidates 4")
        summary_current = ("2026-10-22T10:43:00.000000000Z [10:43:00.000] [INF] X: "
                           "STRM media information check finished: candidates 6")
        stdout = "\n".join([old, current, summary_old, summary_current]) + "\n"
        logs = type("Logs", (), {"returncode": 0, "stdout": stdout, "stderr": ""})()
        round_start = 1792665740.0
        with patch.object(batch.base, "run", return_value=logs):
            completions = batch.task_completion_events_absolute("container", round_start)
            summaries = batch.batch_events_absolute("container", round_start)
        self.assertEqual([entry["status"] for entry in completions], ["Cancelled"])
        self.assertEqual(len(summaries), 1)
        self.assertIn("candidates 6", summaries[0]["line"])

    def test_probe_starts_use_the_absolute_window_too(self):
        old = ("2026-10-21T17:05:10.476000000Z [17:05:10.476] [INF] X: "
               "Native STRM probe started for item AAAA; running probes 1, active permits 1.")
        current = ("2026-10-22T10:42:40.000000000Z [10:42:40.000] [INF] X: "
                   "Native STRM probe started for item BBBB; running probes 1, active permits 1.")
        logs = type("Logs", (), {"returncode": 0, "stdout": old + "\n" + current + "\n", "stderr": ""})()
        with patch.object(batch.base, "run", return_value=logs):
            entries = batch.probe_start_entries_absolute("container", 1792665740.0)
        self.assertEqual([entry["item_id"] for entry in entries], ["bbbb"])

    def test_the_shared_stop_and_mixed_scenarios_also_measure_on_real_instants(self):
        source = (ROOT / "scripts" / "run_isolated_batch_integration.py").read_text(encoding="utf-8")
        shared = source[source.index("def _shared_stop_direction("):source.index("def scenario_mixed(")]
        self.assertIn("stopped_at_epoch = time.time()", shared)
        self.assertIn("task_completion_events_absolute(container, stopped_at_epoch)", shared)
        self.assertNotIn("current_round_completion(container, stopped_at)", shared)
        mixed = source[source.index("def scenario_mixed("):source.index("def scenario_failure(")]
        self.assertIn("probe_start_entries_absolute(container, mixed_started_epoch)", mixed)
        self.assertNotIn("probe_start_entries(container, since=mixed_started_at)", mixed)

    def test_the_stop_scenario_measures_on_real_instants(self):
        source = (ROOT / "scripts" / "run_isolated_batch_integration.py").read_text(encoding="utf-8")
        stop_body = source[source.index("def scenario_stop("):source.index("def scenario_sharing(")]
        self.assertIn("round_started_epoch = time.time()", stop_body)
        self.assertIn("stopped_at_epoch = time.time()", stop_body)
        self.assertNotIn("batch_run_entries(container, since=round_started_at)", stop_body)
        self.assertNotIn("current_round_completion(container, stopped_at)", stop_body)
        # The settlement obligations themselves are unchanged.
        for required in ("entries_timeline[1:]", "settlement_probe_starts", "entries_after >= 2",
                         "queued_entry[\"epoch\"] >= cancelled_at_epoch"):
            self.assertIn(required, stop_body)



class NativeScanSettlementTests(unittest.TestCase):
    """The stop scenario must measure from a settled native scan, not from a busy scheduler.

    The pinned ``TaskManager`` drains its queue whenever any task completes and only starts queued
    work from an Idle worker, so a native scan finishing inside the settlement window can drop the
    queued batch run whose observation the scenario depends on. This is a measurement precondition
    only: no plugin queue, native scheduler or settlement assertion is changed.
    """

    def _scan(self, *, key="RefreshLibrary", state="Running", status="Completed"):
        return {"Id": "task-1", "Key": key, "State": state,
                "LastExecutionResult": {"Status": status, "StartTimeUtc": "2026-10-22T05:00:00Z"}}

    def _api(self):
        return type("Api", (), {"base_url": "http://127.0.0.1:1", "headers": {}})()

    def test_the_native_scan_task_is_read_by_its_key_and_not_by_name(self):
        with patch.object(batch.base, "request_json", return_value=[self._scan()]):
            state = batch.native_scan_state(self._api())
        self.assertEqual(state["id"], "task-1")
        self.assertEqual(state["state"], "running")
        self.assertEqual(state["lastStatus"], "Completed")
        with patch.object(batch.base, "request_json", return_value=[]):
            with self.assertRaises(RuntimeError):
                batch.native_scan_state(self._api())

    def test_an_unsettled_post_scan_sequence_is_not_accepted_as_settled(self):
        running = type("Logs", (), {"returncode": 0, "stdout": "Running 9 post-scan task(s)\n", "stderr": ""})()
        with patch.object(batch.base, "run", return_value=running):
            self.assertFalse(batch.post_scan_settled("container"))
        finished = type("Logs", (), {
            "returncode": 0,
            "stdout": ("Running post-scan task 1/9: \"X\"\n"
                       "All post-scan tasks completed after 0 minute(s) and 7 seconds\n"), "stderr": ""})()
        with patch.object(batch.base, "run", return_value=finished):
            self.assertTrue(batch.post_scan_settled("container"))

    def test_a_still_running_native_scan_blocks_the_measurement_boundary(self):
        with patch.object(batch, "native_scan_state", return_value={"state": "running"}), \
                patch.object(batch, "post_scan_settled", return_value=True), \
                patch.object(batch.time, "sleep", lambda seconds: None):
            with self.assertRaises(RuntimeError) as raised:
                batch.wait_for_native_scan_settled(self._api(), "container", timeout=0.2)
        self.assertIn("never settled", str(raised.exception))

    def test_a_settled_native_scan_is_returned_with_its_observation_count(self):
        idle = {"state": "idle", "id": "task-1", "lastStatus": "Completed", "lastStart": "x"}
        with patch.object(batch, "native_scan_state", return_value=idle), \
                patch.object(batch, "post_scan_settled", return_value=True):
            settled = batch.wait_for_native_scan_settled(self._api(), "container", timeout=5)
        self.assertFalse(settled["waited"])
        self.assertEqual(settled["settled"], idle)
        self.assertGreaterEqual(settled["observations"], 1)

    def test_the_stop_scenario_waits_for_settlement_before_its_own_round_starts(self):
        source = (ROOT / "scripts" / "run_isolated_batch_integration.py").read_text(encoding="utf-8")
        stop_body = source[source.index("def scenario_stop("):source.index("def scenario_sharing(")]
        settle_at = stop_body.index("wait_for_native_scan_settled(")
        start_at = stop_body.index('api.request_response("/ScheduledTasks/Running/" + task_id')
        self.assertLess(settle_at, start_at)
        self.assertIn("nativeSettlementBeforeRound", stop_body)
        # The settlement rules the scenario asserts must be untouched.
        for recovery in ("entries_after >= 2", "new_probe_during_settlement", "current_round_result"):
            self.assertIn(recovery, stop_body)


if __name__ == "__main__":
    unittest.main()
