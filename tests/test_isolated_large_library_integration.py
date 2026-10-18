from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_isolated_large_library_integration.py"
SPEC = importlib.util.spec_from_file_location("large_library_integration", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
large = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(large)


class LargeLibraryControlTests(unittest.TestCase):
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
            "batch_reads": 1,
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
            "batch_reads": 1,
        }

        with self.assertRaisesRegex(RuntimeError, "Expected 3 first-trust sources"):
            large.validate_settlement(fields, expected_candidates=3, expected_probe_calls=0,
                                      expected_first_trust=3)

    def test_missing_cost_field_is_rejected(self):
        fields = {name: 0 for name in large.REQUIRED_SUMMARY_FIELDS}
        del fields["batch_read_allocated_bytes"]
        with self.assertRaisesRegex(RuntimeError, "missing the cost field"):
            large.validate_settlement(fields, expected_candidates=0, expected_probe_calls=0)

    def test_negative_cost_field_is_rejected(self):
        fields = {name: 0 for name in large.REQUIRED_SUMMARY_FIELDS}
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
