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
    def test_probe_outcome_events_include_unaccepted_native_results(self):
        item_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        source_key = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        lines = [
            "2026-10-16T23:59:59.000000000Z [WRN] Native probe result was not accepted for item "
            "ffffffff-ffff-ffff-ffff-ffffffffffff, source cccccccc-cccc-cccc-cccc-cccccccccccc; calls 1.",
            "2026-10-17T08:00:01.000000000Z [WRN] Native probe result was not accepted for item "
            f"{item_id}, source {source_key}; calls 1, encoder primary False.",
        ]
        with patch.object(scan, "docker_log_lines", return_value=lines):
            events = scan.probe_outcome_events("container", since=_utc(0))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "not_accepted")
        self.assertEqual(events[0]["item_id"], "a" * 32)
        self.assertEqual(events[0]["source_key"], "b" * 32)

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

    def test_probe_commit_after_change_accepts_same_round_completion(self):
        item_id = "0123456789abcdef0123456789abcdef"
        source_key = "abcdef0123456789abcdef0123456789"
        starts = [{"item_id": item_id, "source_key": source_key, "timestamp": _utc(2)}]
        outcomes = [{"item_id": item_id, "source_key": source_key, "kind": "accepted", "timestamp": _utc(3)}]
        result = scan.accepted_probe_after_change(item_id, source_key, _utc(1), starts, outcomes)
        self.assertIsNotNone(result)
        self.assertEqual(result["probe_start"]["timestamp"], _utc(2))
        self.assertEqual(result["accepted"]["timestamp"], _utc(3))

    def test_probe_commit_after_change_rejects_probe_that_started_before_change(self):
        item_id = "0123456789abcdef0123456789abcdef"
        source_key = "abcdef0123456789abcdef0123456789"
        starts = [{"item_id": item_id, "source_key": source_key, "timestamp": _utc(1)}]
        outcomes = [{"item_id": item_id, "source_key": source_key, "kind": "accepted", "timestamp": _utc(3)}]
        self.assertIsNone(scan.accepted_probe_after_change(item_id, source_key, _utc(2), starts, outcomes))

    def test_probe_commit_after_change_skips_stale_start_when_later_probe_succeeds(self):
        item_id = "0123456789abcdef0123456789abcdef"
        source_key = "abcdef0123456789abcdef0123456789"
        starts = [
            {"item_id": item_id, "source_key": source_key, "timestamp": _utc(1)},
            {"item_id": item_id, "source_key": source_key, "timestamp": _utc(3)},
        ]
        outcomes = [
            {"item_id": item_id, "source_key": source_key, "kind": "accepted", "timestamp": _utc(2)},
            {"item_id": item_id, "source_key": source_key, "kind": "accepted", "timestamp": _utc(4)},
        ]
        result = scan.accepted_probe_after_change(item_id, source_key, _utc(2), starts, outcomes)
        self.assertIsNotNone(result)
        self.assertEqual(result["probe_start"]["timestamp"], _utc(3))
        self.assertEqual(result["accepted"]["timestamp"], _utc(4))

    def test_probe_commit_after_change_requires_matching_source_and_acceptance(self):
        item_id = "0123456789abcdef0123456789abcdef"
        source_key = "abcdef0123456789abcdef0123456789"
        starts = [{"item_id": item_id, "source_key": source_key, "timestamp": _utc(2)}]
        wrong_source = [{"item_id": item_id, "source_key": "ffffffffffffffffffffffffffffffff",
                         "kind": "accepted", "timestamp": _utc(3)}]
        failed = [{"item_id": item_id, "source_key": source_key, "kind": "failed", "timestamp": _utc(3)}]
        self.assertIsNone(scan.accepted_probe_after_change(item_id, source_key, _utc(1), starts, wrong_source))
        self.assertIsNone(scan.accepted_probe_after_change(item_id, source_key, _utc(1), starts, failed))


class ScanStopControlTests(unittest.TestCase):
    def test_stop_sources_follow_fixture_name_order_within_the_actual_batch(self):
        names = [f"Scan Stop fixture {index:03d}" for index in range(4)]
        ids = {name: f"{index + 1:032x}" for index, name in enumerate(names)}
        first_batch = [ids[names[3]], ids[names[0]], ids[names[2]]]
        second_batch = [ids[names[1]]]
        selected, unread = scan.select_stop_round_sources(names, ids, first_batch, second_batch)
        self.assertEqual(selected, [names[0], names[2], names[3]])
        self.assertEqual(unread, ids[names[1]])

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

    def test_stopped_round_must_commit_started_and_joined_work_before_reprobe(self):
        old = {"item_id": "a" * 32, "source_key": "a" * 32, "url_hash": "old",
               "sha1": "b" * 40, "file_size": 7}
        new = {"item_id": "a" * 32, "source_key": "a" * 32, "url_hash": "new",
               "sha1": "b" * 40, "file_size": 7}
        scan.validate_stop_round_snapshot(
            {"a" * 32: old}, {"a" * 32}, {"a" * 32: new},
            {"a" * 32: {"url_hash": "new", "has_main_stream": True}},
            {"a" * 32: new}, joined_item_ids={"a" * 32}, reliable_success=1)
        # A later convergence run must not hide a stop round that failed to commit.
        with self.assertRaises(RuntimeError):
            scan.validate_stop_round_snapshot(
                {"a" * 32: old}, {"a" * 32}, {"a" * 32: old},
                {"a" * 32: {"url_hash": "new", "has_main_stream": True}},
                {"a" * 32: new}, joined_item_ids={"a" * 32}, reliable_success=1)

    def test_a_cancelled_joined_probe_cannot_be_counted_as_a_success(self):
        old = {"item_id": "a" * 32, "source_key": "a" * 32, "url_hash": "old",
               "sha1": "b" * 40, "file_size": 7}
        with self.assertRaises(RuntimeError):
            scan.validate_stop_round_snapshot(
                {"a" * 32: old}, {"a" * 32}, {"a" * 32: old},
                {"a" * 32: {"url_hash": "old", "has_main_stream": True}},
                {"a" * 32: "new"}, joined_item_ids={"a" * 32}, reliable_success=0)


class ScanRecoveryControlTests(unittest.TestCase):
    def test_a_failure_route_must_be_repaired_and_committed_before_recovery_passes(self):
        expected = {"item_id": "a" * 32, "source_key": "a" * 32,
                    "url_hash": scan.expected_url_hash("http://media/new.mp4"),
                    "sha1": "b" * 40, "file_size": 7}
        source = {"Id": "a" * 32, "Path": "http://media/new.mp4", "MediaStreams": [{"Type": "Video"}]}
        row = dict(expected)
        summary = {"actual_probe_calls": 1, "reliable_success": 1, "probe_incomplete": 0, "need_probe": 1}
        scan.require_recovery_source_success(expected, source, row, summary, [{"kind": "accepted"}],
                                             "repaired source")
        with self.assertRaises(RuntimeError):
            scan.require_recovery_source_success(expected, source, None, summary, [{"kind": "accepted"}],
                                                 "uncommitted source")

    def test_completed_recovery_with_an_unfixed_failure_route_cannot_pass(self):
        expected = {"item_id": "a" * 32, "source_key": "a" * 32, "url_hash": "new",
                    "sha1": "b" * 40, "file_size": 7}
        failed_source = {"Id": "a" * 32, "Path": "http://media/missing.mp4", "MediaStreams": []}
        with self.assertRaises(RuntimeError):
            scan.require_recovery_source_success(
                expected, failed_source, None,
                {"actual_probe_calls": 0, "reliable_success": 0, "probe_incomplete": 1, "need_probe": 1},
                [], "unfixed source")


class ScanSelectionControlTests(unittest.TestCase):
    def test_a_wrong_selected_version_cannot_pass(self):
        # A server that ignores the requested MediaSourceId and returns both sources must be refused.
        source_a = "a" * 32
        source_b = "b" * 32
        url_b = "http://media:8080/b.mp4"
        unfiltered = {"MediaSources": [{"Id": source_b, "Path": url_b}, {"Id": source_a, "Path": "http://media:8080/a.mp4"}]}
        # The requested A source being present does not make an unfiltered response acceptable.
        with self.assertRaises(RuntimeError):
            scan._require_selected_source(unfiltered, source_a, scan.expected_url_hash("http://media:8080/a.mp4"), "A")
        missing_requested = {"MediaSources": [{"Id": source_b, "Path": url_b}]}
        with self.assertRaises(RuntimeError):
            scan._require_selected_source(missing_requested, source_a, scan.expected_url_hash(url_b), "A")

    def test_a_source_returning_the_wrong_address_cannot_pass(self):
        source_a = "a" * 32
        response = {"MediaSources": [{"Id": source_a, "Path": "http://media:8080/other.mp4"}]}
        with self.assertRaises(RuntimeError):
            scan._require_selected_source(response, source_a, scan.expected_url_hash("http://media:8080/a.mp4"), "A")


class ScanCandidateManifestTests(unittest.TestCase):
    def setUp(self):
        self.library_id = "00000000-0000-0000-0000-000000000001"
        self.root = "/media/strm"

    def _item(self, item_id, name, source_ids):
        return {"Id": item_id, "Name": name, "Path": f"{self.root}/{name}.strm",
                "MediaSources": [{"Id": source_id, "Path": f"http://media/{name}.mp4"}
                                 for source_id in source_ids]}

    def _scope_fixture(self, batch_size):
        names = [f"bulk-{index}" for index in range(4)]
        fixture_items = {
            name: self._item(f"00000000-0000-0000-0000-{index:012d}", name,
                             [f"10000000-0000-0000-0000-{index:012d}"])
            for index, name in enumerate(names, start=1)
        }
        manifest = scan.build_candidate_manifest(list(fixture_items.values()), self.library_id, self.root,
                                                 batch_size=batch_size)
        fixture = {"bulk_names": names, "items": fixture_items}
        return manifest, fixture

    def test_manifest_records_sorted_native_ids_source_mapping_and_batch_boundaries(self):
        items = [
            self._item("00000000-0000-0000-0000-000000000004", "four", ["10000000-0000-0000-0000-000000000004"]),
            self._item("00000000-0000-0000-0000-000000000001", "one", ["10000000-0000-0000-0000-000000000001",
                                                                       "10000000-0000-0000-0000-000000000002"]),
            self._item("00000000-0000-0000-0000-000000000003", "three", ["10000000-0000-0000-0000-000000000003"]),
            self._item("00000000-0000-0000-0000-000000000002", "two", ["10000000-0000-0000-0000-000000000002"]),
            {"Id": "00000000-0000-0000-0000-000000000099", "Name": "outside", "Path": "/media/local/outside.strm",
             "MediaSources": [{"Id": "10000000-0000-0000-0000-000000000099"}]},
        ]
        manifest = scan.build_candidate_manifest(items, self.library_id, self.root, batch_size=2)
        self.assertEqual([row["item_id"] for row in manifest["items"]], [
            "00000000000000000000000000000001", "00000000000000000000000000000002",
            "00000000000000000000000000000003", "00000000000000000000000000000004",
        ])
        self.assertEqual(manifest["items"][0]["source_ids"], [
            "10000000000000000000000000000001", "10000000000000000000000000000002",
        ])
        self.assertEqual([(batch["first_ordinal"], batch["last_ordinal"]) for batch in manifest["batches"]],
                         [(0, 1), (2, 3)])
        self.assertEqual(manifest["candidate_count"], 4)

    def test_current_native_query_restores_alternate_versions_hidden_by_library_dto_grouping(self):
        first = self._item("00000000-0000-0000-0000-000000000001", "same-project-a",
                           ["10000000-0000-0000-0000-000000000001"])
        alternate = self._item("00000000-0000-0000-0000-000000000002", "same-project-b",
                               ["10000000-0000-0000-0000-000000000002"])
        root_folder = {"Id": "00000000-0000-0000-0000-000000000099", "Name": "strm",
                       "Path": self.root, "MediaSources": []}
        outside = {"Id": "00000000-0000-0000-0000-000000000098", "Name": "outside",
                   "Path": "/media/local/outside.strm", "MediaSources": []}
        merged = scan.merge_selected_library_items([root_folder, first],
                                                   [root_folder, first, alternate, outside], self.root)
        self.assertEqual({row["Id"] for row in merged}, {first["Id"], alternate["Id"]})

    def test_current_grouped_source_ids_are_resolved_to_each_version_item(self):
        first = self._item("00000000-0000-0000-0000-000000000001", "same-project-a",
                           ["10000000-0000-0000-0000-000000000001"])
        alternate = self._item("00000000-0000-0000-0000-000000000002", "same-project-b",
                               ["10000000-0000-0000-0000-000000000002"])
        grouped = dict(alternate, MediaSources=[{"Id": first["Id"]}, {"Id": alternate["Id"]}])
        expanded = scan.expand_alternate_source_items([grouped], self.root,
                                                      lambda item_id: first if scan.canonical_guid(item_id, "test")
                                                      == scan.canonical_guid(first["Id"], "test") else None)
        self.assertEqual({item["Id"] for item in expanded}, {first["Id"], alternate["Id"]})

    def test_grouped_alternate_candidates_reconcile_under_the_visible_project_once(self):
        primary_id = "00000000-0000-0000-0000-000000000001"
        alternate_id = "00000000-0000-0000-0000-000000000002"
        primary_source = self._item(primary_id, "same-project-a", [primary_id])
        alternate_source = self._item(alternate_id, "same-project-b", [alternate_id])
        grouped_primary = dict(primary_source, MediaSources=[{"Id": primary_id}, {"Id": alternate_id}])
        grouped_alternate = dict(alternate_source, MediaSources=[{"Id": primary_id}, {"Id": alternate_id}])

        projects = scan.selected_library_project_items([grouped_primary], self.root)
        candidates = scan.build_candidate_manifest([grouped_primary, grouped_alternate], self.library_id, self.root)
        project_map = scan.map_candidate_items_to_projects(candidates, projects)

        self.assertEqual([item["Id"] for item in projects], [primary_id])
        self.assertEqual(project_map, {scan.canonical_guid(primary_id, "test"): scan.canonical_guid(primary_id, "test"),
                                       scan.canonical_guid(alternate_id, "test"): scan.canonical_guid(primary_id, "test")})

    def test_candidate_version_without_a_grouped_project_mapping_is_refused(self):
        primary_id = "00000000-0000-0000-0000-000000000001"
        alternate_id = "00000000-0000-0000-0000-000000000002"
        primary = self._item(primary_id, "same-project-a", [primary_id])
        alternate = self._item(alternate_id, "same-project-b", [alternate_id])
        candidates = scan.build_candidate_manifest([primary, alternate], self.library_id, self.root)
        projects = scan.selected_library_project_items([primary], self.root)

        with self.assertRaises(RuntimeError):
            scan.map_candidate_items_to_projects(candidates, projects)

    def test_native_refresh_fixture_mtime_advances_past_jellyfin_change_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            (workspace / "strm").mkdir(parents=True)
            path = workspace / "strm" / "refresh.strm"
            path.write_bytes(b"# strm-probe-version:1\nhttp://media/old.mp4\n")
            before = path.stat().st_mtime_ns
            content = path.read_bytes()
            with patch.object(package_environment, "WORK", workspace):
                evidence = scan.advance_fixture_mtime_for_native_refresh(path)
            self.assertGreater(evidence["after_mtime_ns"] - before, 1_000_000_000)
            self.assertEqual(path.read_bytes(), content)

    def test_current_native_item_query_must_agree_with_selected_library_membership(self):
        selected = self._item("00000000-0000-0000-0000-000000000001", "selected",
                              ["10000000-0000-0000-0000-000000000001"])
        with self.assertRaises(RuntimeError):
            scan.merge_selected_library_items([selected], [], self.root)

    def test_scope_change_plan_uses_a_held_first_batch_source_and_unread_later_targets(self):
        manifest, fixture = self._scope_fixture(batch_size=2)
        plan = scan.plan_scope_change(manifest, fixture, batch_size=2)
        self.assertEqual(plan["hold"]["batch_index"], 0)
        self.assertGreaterEqual(plan["delete"]["batch_index"], 1)
        self.assertGreaterEqual(plan["move_out"]["batch_index"], 1)

    def test_scope_change_accepts_two_safe_incomplete_targets_without_probing_them(self):
        manifest, fixture = self._scope_fixture(batch_size=2)
        plan = scan.plan_scope_change(manifest, fixture, batch_size=2)
        scan.validate_scope_change_round(
            manifest, plan, probe_item_ids_before_mutation=[],
            probe_item_ids_after_round=[plan["hold"]["item_id"]], moved_out_current_item_ids=[],
            summary_fields={"candidates": 4, "batch_reads": 2, "missing": 0,
                            "check_stage_incomplete": 2, "actual_probe_calls": 1,
                            "reliable_success": 1, "probe_incomplete": 0})

    def test_scope_change_rejects_a_target_without_a_safe_settlement_counter(self):
        manifest, fixture = self._scope_fixture(batch_size=2)
        plan = scan.plan_scope_change(manifest, fixture, batch_size=2)
        with self.assertRaises(RuntimeError):
            scan.validate_scope_change_round(
                manifest, plan, probe_item_ids_before_mutation=[], probe_item_ids_after_round=[],
                moved_out_current_item_ids=[],
                summary_fields={"candidates": 4, "batch_reads": 2, "missing": 1,
                                "check_stage_incomplete": 0, "actual_probe_calls": 1,
                                "reliable_success": 1, "probe_incomplete": 0})

    def test_scope_change_control_rejects_a_target_processed_before_mutation(self):
        manifest, fixture = self._scope_fixture(batch_size=2)
        plan = scan.plan_scope_change(manifest, fixture, batch_size=2)
        with self.assertRaises(RuntimeError):
            scan.validate_scope_change_round(
                manifest, plan, probe_item_ids_before_mutation=[plan["delete"]["item_id"]],
                probe_item_ids_after_round=[], moved_out_current_item_ids=[],
                summary_fields={"candidates": 4, "missing": 2, "batch_reads": 2})

    def test_scope_change_control_rejects_a_target_outside_the_actual_fixed_set(self):
        manifest, fixture = self._scope_fixture(batch_size=2)
        plan = scan.plan_scope_change(manifest, fixture, batch_size=2)
        plan["delete"]["item_id"] = "ffffffffffffffffffffffffffffffff"
        with self.assertRaises(RuntimeError):
            scan.validate_scope_change_round(
                manifest, plan, probe_item_ids_before_mutation=[], probe_item_ids_after_round=[],
                moved_out_current_item_ids=[], summary_fields={"candidates": 4, "missing": 2, "batch_reads": 2})

    def test_scope_change_control_rejects_a_moved_out_rekeyed_identity_that_was_probed(self):
        manifest, fixture = self._scope_fixture(batch_size=2)
        plan = scan.plan_scope_change(manifest, fixture, batch_size=2)
        moved_out_id = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        with self.assertRaises(RuntimeError):
            scan.validate_scope_change_round(
                manifest, plan, probe_item_ids_before_mutation=[], probe_item_ids_after_round=[moved_out_id],
                moved_out_current_item_ids=[moved_out_id],
                summary_fields={"candidates": 4, "missing": 2, "batch_reads": 2})

    def test_a_selected_source_without_a_main_stream_cannot_pass(self):
        source_a = "a" * 32
        response = {"MediaSources": [{"Id": source_a, "Path": "http://media:8080/a.mp4", "MediaStreams": []}]}
        with self.assertRaises(RuntimeError):
            scan._require_selected_source(response, source_a, scan.expected_url_hash("http://media:8080/a.mp4"), "A")


class ScanReconciliationTests(unittest.TestCase):
    def test_full_refresh_targets_the_named_version_item_not_its_shared_project(self):
        items = {
            "Scan MV A": {"Id": "fc9b4705125239edb88e1a72dd56616a"},
            "Scan MV B": {"Id": "a01a9461d89f3d18d5c58657b26f1a20"},
        }
        target = scan.full_refresh_target_item_id(items, "Scan MV A")
        self.assertEqual(target, "fc9b4705125239edb88e1a72dd56616a")
        self.assertNotEqual(target, items["Scan MV B"]["Id"])

    def test_source_path_matches_hash_only_accepts_the_current_address(self):
        url = "http://media:8080/package-mp4.mp4"
        response = {"MediaSources": [{"Path": url}]}
        self.assertTrue(scan.source_path_matches_hash(response, scan.expected_url_hash(url)))
        self.assertFalse(scan.source_path_matches_hash(response, scan.expected_url_hash("http://media:8080/old.mp4")))

    def test_current_manifest_rejects_a_matching_but_stale_native_address_and_row(self):
        expected = {"item_id": "a" * 32, "source_key": "b" * 32,
                    "url_hash": scan.expected_url_hash("http://media:8080/current.mp4"),
                    "sha1": "c" * 40, "file_size": 12}
        stale_hash = scan.expected_url_hash("http://media:8080/old.mp4")
        native_source = {"Id": "b" * 32, "Path": "http://media:8080/old.mp4",
                         "MediaStreams": [{"Type": "Video"}]}
        stale_row = {"item_id": "a" * 32, "source_key": "b" * 32,
                     "url_hash": stale_hash, "sha1": "c" * 40, "file_size": 12}
        with self.assertRaises(RuntimeError):
            scan.validate_source_reconciliation(expected, native_source, stale_row, "current source")

    def test_an_orphan_row_for_another_project_cannot_replace_the_current_key(self):
        expected = {"item_id": "a" * 32, "source_key": "b" * 32,
                    "url_hash": scan.expected_url_hash("http://media:8080/current.mp4"),
                    "sha1": "c" * 40, "file_size": 12}
        native_source = {"Id": "b" * 32, "Path": "http://media:8080/current.mp4",
                         "MediaStreams": [{"Type": "Video"}]}
        orphan = {"item_id": "d" * 32, "source_key": "b" * 32,
                  "url_hash": expected["url_hash"], "sha1": "c" * 40, "file_size": 12}
        with self.assertRaises(RuntimeError):
            scan.validate_source_reconciliation(expected, native_source, orphan, "current source")

    def test_every_fingerprint_field_is_checked_against_the_manifest(self):
        expected = {"item_id": "a" * 32, "source_key": "b" * 32,
                    "url_hash": scan.expected_url_hash("http://media:8080/current.mp4"),
                    "sha1": "c" * 40, "file_size": 12}
        native_source = {"Id": "b" * 32, "Path": "http://media:8080/current.mp4",
                         "MediaStreams": [{"Type": "Video"}]}
        changed_sha = dict(expected, sha1="d" * 40)
        changed_size = dict(expected, file_size=13)
        with self.assertRaises(RuntimeError):
            scan.validate_source_reconciliation(expected, native_source, changed_sha, "current source")
        with self.assertRaises(RuntimeError):
            scan.validate_source_reconciliation(expected, native_source, changed_size, "current source")

    def test_missing_identity_address_or_main_stream_cannot_be_silently_skipped(self):
        expected = {"item_id": "a" * 32, "source_key": "b" * 32,
                    "url_hash": scan.expected_url_hash("http://media:8080/current.mp4"),
                    "sha1": "c" * 40, "file_size": 12}
        row = dict(expected)
        for native_source in (
            {"Id": None, "Path": "http://media:8080/current.mp4", "MediaStreams": [{"Type": "Video"}]},
            {"Id": "b" * 32, "Path": None, "MediaStreams": [{"Type": "Video"}]},
            {"Id": "b" * 32, "Path": "http://media:8080/current.mp4", "MediaStreams": []},
        ):
            with self.subTest(source=native_source), self.assertRaises(RuntimeError):
                scan.validate_source_reconciliation(expected, native_source, row, "current source")

    def test_full_refresh_requires_this_operation_processing_and_end_signals(self):
        item_name = "Scan Refresh test"
        before = {"Etag": "etag-before"}
        after = {"Etag": "etag-after"}
        started = _utc(0)
        events = [{"kind": "started", "item_name": item_name, "timestamp": _utc(1)},
                  {"kind": "completed", "item_name": item_name, "timestamp": _utc(2)}]
        scan.require_refresh_completed(before, after, events, item_name, started, _utc(3), "full refresh")
        with self.assertRaises(RuntimeError):
            scan.require_refresh_completed(before, after, [], item_name, started, _utc(3), "full refresh")
        with self.assertRaises(RuntimeError):
            scan.require_refresh_completed(before, before, events, item_name, started, _utc(3), "full refresh")
        with self.assertRaises(RuntimeError):
            scan.require_refresh_completed({"Etag": "before"}, {}, events, item_name,
                                           started, _utc(3), "full refresh")

    def test_expected_fingerprint_row_retains_sha_only_for_the_same_unchanged_source(self):
        item_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        source_key = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        old_url = "http://media:8080/old.mp4"
        manifest = {"url_hash": scan.expected_url_hash(old_url), "sha1": None, "file_size": 12}
        previous = {"item_id": scan.canonical_guid(item_id, "item"),
                    "source_key": scan.canonical_guid(source_key, "source"),
                    "url_hash": manifest["url_hash"], "sha1": "c" * 40, "file_size": 12}
        self.assertEqual(scan.expected_fingerprint_row(item_id, source_key, manifest, previous)["sha1"], "c" * 40)

        for changed in (
            dict(previous, url_hash=scan.expected_url_hash("http://media:8080/new.mp4")),
            dict(previous, file_size=13),
            dict(previous, item_id="d" * 32),
            dict(previous, source_key="e" * 32),
            dict(previous, sha1="invalid"),
        ):
            with self.subTest(previous=changed):
                self.assertIsNone(scan.expected_fingerprint_row(item_id, source_key, manifest, changed)["sha1"])

    def test_scan_observed_b_address_keeps_the_full_a_row_until_c_is_probed(self):
        baseline = {"item_id": "a" * 32, "source_key": "b" * 32,
                    "url_hash": "c" * 64, "sha1": "d" * 40, "file_size": 12}
        allowed = {"c" * 64, "e" * 64, "f" * 64}
        native = {"native_url_hash": "e" * 64, "has_main_stream": True, "fingerprint": dict(baseline)}
        scan.validate_url_race_intermediate(native, baseline, allowed, "URL race")
        for changed in (
            dict(native, native_url_hash="9" * 64),
            dict(native, fingerprint=dict(baseline, file_size=13)),
            dict(native, has_main_stream=False),
        ):
            with self.subTest(state=changed), self.assertRaises(RuntimeError):
                scan.validate_url_race_intermediate(changed, baseline, allowed, "URL race")

    def test_probe_join_events_identify_only_actual_started_probe_joins(self):
        playback_join = ('2026-10-17T08:00:00.0000000Z INF Joined a running native probe for item '
                         'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa, source_key '
                         'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb')
        batch_join = ('2026-10-17T08:00:01.0000000Z INF Batch joined a running native probe for item '
                      'cccccccc-cccc-cccc-cccc-cccccccccccc, source_key '
                      'dddddddd-dddd-dddd-dddd-dddddddddddd')
        preparing_wait = ('2026-10-17T08:00:02.0000000Z INF Waiting for a same-source probe that is still preparing '
                          'for item eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee, source_key '
                          'ffffffff-ffff-ffff-ffff-ffffffffffff')
        with patch.object(scan, "docker_log_lines", return_value=[playback_join, batch_join, preparing_wait]):
            events = scan.probe_join_events("jellyfin")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["item_id"], "a" * 32)
        self.assertEqual(events[0]["source_key"], "b" * 32)
        self.assertEqual(events[0]["direction"], "playback")
        self.assertEqual(events[1]["item_id"], "c" * 32)
        self.assertEqual(events[1]["source_key"], "d" * 32)
        self.assertEqual(events[1]["direction"], "batch")

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
            recorder.record("exception", error="request failed for /private/secret.mp4 token=abc",
                            response={"message": "https://private.example/signed?key=secret"},
                            url_hash="a" * 64, sha1="b" * 40)
            recorder.snapshot("round", {"path": Path("/private/secret.mp4")})
            lines = (Path(tmp) / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 3)  # run_start + probe + nested exception response
            record = json.loads(lines[1])
            # The URL must be stored as a digest, never in the clear.
            self.assertNotIn("secret", json.dumps(record))
            self.assertIn("sha256", record["data"]["url"])
            exception_record = json.dumps(json.loads(lines[2]))
            self.assertNotIn("private.example", exception_record)
            self.assertNotIn("secret", exception_record)
            self.assertEqual(json.loads(lines[2])["data"]["url_hash"], "a" * 64)
            self.assertEqual(json.loads(lines[2])["data"]["sha1"], "b" * 40)
            snapshot = json.loads((Path(tmp) / "rounds" / "round.json").read_text(encoding="utf-8"))
            self.assertNotIn("secret", json.dumps(snapshot))

    def test_evidence_recorder_refuses_to_overwrite_an_existing_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "evidence"
            directory.mkdir()
            (directory / "events.jsonl").write_text("keep this", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                scan.EvidenceRecorder(directory, "run-3")
            self.assertEqual((directory / "events.jsonl").read_text(encoding="utf-8"), "keep this")

    def test_task_polling_is_appended_with_raw_results_and_container_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = scan.EvidenceRecorder(Path(tmp), "run-task")
            recorder.set_container_identity({"id": "container-id", "started_at": "2026-10-17T08:00:00Z"})
            tasks = [{"Key": "RefreshLibrary", "Id": "task-id", "State": "Running",
                      "LastExecutionResult": {"StartTimeUtc": "2026-10-17T08:00:00Z"}}]
            with patch.object(scan, "ACTIVE_RECORDER", recorder), \
                    patch.object(package_environment, "request_json", return_value=(200, tasks)):
                self.assertEqual(scan.task_list("auth"), tasks)
            lines = (Path(tmp) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            task_poll = json.loads(lines[-1])
            self.assertEqual(task_poll["kind"], "task_poll")
            self.assertEqual(task_poll["container_identity"]["id"], "container-id")
            self.assertEqual(task_poll["data"]["tasks"][0]["LastExecutionResult"]["StartTimeUtc"],
                             "2026-10-17T08:00:00Z")

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
                patch.object(scan, "scenario_overlap_phase", side_effect=self._record_then_fail):
            code = self._run_main(["--package", str(package), "--scenario", "overlap",
                                   "--evidence-dir", str(evidence)])
        self.assertEqual(code, 1)
        # The scenario's failure must be recorded even though the instance was cleaned up.
        self.assertTrue((evidence / "events.jsonl").is_file())
        self.assertTrue((evidence / "result.json").is_file())
        result = json.loads((evidence / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["error"]["type"], "RuntimeError")
        self.assertIn("sha256", result["error"]["message"])
        event_kinds = [json.loads(line)["kind"] for line in (evidence / "events.jsonl").read_text().splitlines()]
        self.assertIn("scenario_observation", event_kinds)
        self.assertLess(event_kinds.index("scenario_observation"), event_kinds.index("failure"))
        index = (evidence / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("Exit code: `1`", index)

    @staticmethod
    def _record_then_fail(*args):
        scan.ACTIVE_RECORDER.record("scenario_observation", item_id="a" * 32, source_key="b" * 32)
        raise RuntimeError("scenario boom")

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
        self.assertEqual(result["cleanup_error"]["type"], "PackageEnvironmentError")

    def test_log_capture_failure_is_fail_and_cleanup_still_runs(self):
        base = Path(tempfile.mkdtemp())
        package = self._valid_package(base / "pkg")
        evidence = base / "evidence"
        with patch.object(package_environment, "BASE", base), \
                patch.object(package_environment, "compose"), \
                patch.object(scan, "scenario_overlap_phase", return_value={"ok": True}), \
                patch.object(scan, "collect_runtime_evidence", side_effect=RuntimeError("log capture failed")), \
                patch.object(package_environment, "cleanup_instance", return_value={"status": "CLEANED"}) as cleanup:
            code = self._run_main(["--package", str(package), "--scenario", "overlap",
                                   "--evidence-dir", str(evidence)])
        self.assertEqual(code, 1)
        cleanup.assert_called_once()
        result = json.loads((evidence / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
