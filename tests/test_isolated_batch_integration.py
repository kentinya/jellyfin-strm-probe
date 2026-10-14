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
        with patch.object(batch, "CONFIGURATION_FILE", Path("/nonexistent/config.xml")):
            status = batch.restore_state(b"<x/>", {"task": [{"Type": "DailyTrigger"}]})
        self.assertIn("NOT RESTORED", status)

    def test_scenario_choices_include_stop_sharing_scope_and_failure(self):
        parser_source = (ROOT / "scripts" / "run_isolated_batch_integration.py").read_text(encoding="utf-8")
        for scenario in ("stop", "sharing", "scope", "failure"):
            self.assertIn(scenario, parser_source)


if __name__ == "__main__":
    unittest.main()
