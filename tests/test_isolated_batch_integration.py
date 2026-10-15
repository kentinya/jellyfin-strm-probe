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
        path = ROOT / "artifacts" / "dev-env" / "strm" / (name + ".strm")
        path.unlink(missing_ok=True)
        try:
            written = batch.temporary_fixture(name, "http://media:8080/fixture.mp4", "a" * 40, 10)
            self.assertEqual(written, path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("# strm-probe-version:1", text)
            self.assertIn("http://media:8080/fixture.mp4", text)
            # A second write must fail rather than silently clobber an existing fixture.
            with self.assertRaises(FileExistsError):
                batch.temporary_fixture(name, "http://media:8080/other.mp4", "b" * 40, 11)
        finally:
            path.unlink(missing_ok=True)

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
        self.assertIn("candidate_set_retained_bytes", batch.REQUIRED_COST_FIELDS)
        self.assertNotIn("candidate_set_capacity_bytes", batch.REQUIRED_COST_FIELDS)

    def test_max_running_probes_reports_the_peak_from_the_plugin_counter(self):
        lines = [
            "[INF] Native STRM probe started for item x; running probes 1, active permits 1.",
            "[INF] Native STRM probe started for item y; running probes 2, active permits 2.",
            "[INF] Native STRM probe started for item z; running probes 1, active permits 1.",
        ]
        self.assertEqual(batch.max_running_probes(lines), 2)
        self.assertEqual(batch.max_running_probes([]), 0)

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
                f"[INF] {batch.TASK_NAME} Cancelled after 0 minute(s) and 5 seconds\n"
                f"[INF] {batch.TASK_NAME} Completed after 0 minute(s) and 1 seconds\n"
                "[INF] Some Other Task Completed after 0 minute(s) and 1 seconds\n"
            ),
            "stderr": "",
        })()
        with patch.object(batch.base, "run", return_value=logs):
            events = batch.task_completion_events("container")
        self.assertEqual(events, ["Cancelled", "Completed"])

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


if __name__ == "__main__":
    unittest.main()
