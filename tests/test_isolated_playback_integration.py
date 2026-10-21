"""Guardrails for the Slice 5 baseline playback entry; these are not real Jellyfin acceptance tests.

The unit controls below only prove that the tooling refuses to report a baseline as passing when
the required evidence is missing. They are not evidence of native Jellyfin probing, persistence,
restart survival or real playback.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    # Reuse an already-imported module so the whole test session shares one set of exception
    # classes (the package integration script imports ``package_plugin``/``package_environment``
    # lazily and must see the same objects as the sibling test module).
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


playback = load("run_isolated_playback_integration", "scripts/run_isolated_playback_integration.py")

URL = "http://media:8080/baseline-mp4-a.mp4"
SHA1 = "0123456789abcdef0123456789abcdef01234567"
SIZE = 4096


def fingerprint(**overrides) -> dict:
    row = {"item_id": "a" * 32, "source_key": "a" * 32,
           "url_hash": playback.hashlib.sha256(URL.encode()).hexdigest(), "sha1": SHA1, "file_size": SIZE}
    row.update(overrides)
    return row


class FingerprintFieldTests(unittest.TestCase):
    def test_matching_five_field_fingerprint_is_accepted(self):
        self.assertEqual(playback.fingerprint_fields_match(fingerprint(), expected_url=URL,
                                                           sha1=SHA1, size=SIZE), [])

    def test_fingerprint_sha1_comparison_ignores_hex_case(self):
        self.assertEqual(playback.fingerprint_fields_match(fingerprint(sha1=SHA1.upper()),
                                                           expected_url=URL, sha1=SHA1, size=SIZE), [])

    def test_missing_fingerprint_is_refused(self):
        self.assertTrue(playback.fingerprint_fields_match(None, expected_url=URL, sha1=SHA1, size=SIZE))

    def test_wrong_url_hash_size_and_sha1_are_refused(self):
        for row, label in (
            (fingerprint(url_hash="b" * 64), "url"),
            (fingerprint(file_size=SIZE + 1), "size"),
            (fingerprint(sha1="f" * 40), "sha1"),
        ):
            failures = playback.fingerprint_fields_match(row, expected_url=URL, sha1=SHA1, size=SIZE)
            self.assertTrue(failures, label)

    def test_extra_or_missing_columns_are_refused(self):
        extra = fingerprint()
        extra["notes"] = "unexpected"
        self.assertTrue(playback.fingerprint_fields_match(extra, expected_url=URL, sha1=SHA1, size=SIZE))
        missing = fingerprint()
        del missing["sha1"]
        self.assertTrue(playback.fingerprint_fields_match(missing, expected_url=URL, sha1=SHA1, size=SIZE))


class PlaybackObservationTests(unittest.TestCase):
    def _entry(self, tmp: Path, **overrides) -> dict:
        start = tmp / "start.png"
        progress = tmp / "progress.png"
        start.write_bytes(b"\x89PNG" + b"0" * 4000)
        progress.write_bytes(b"\x89PNG" + b"0" * 4000)
        entry = {
            "name": "Baseline MP4", "itemId": "a" * 32, "mediaType": "video", "advanced": True,
            "currentTime": 6.4, "duration": 24.0, "element": "video", "videoWidth": 320,
            "videoHeight": 180, "decodedFrames": 92, "readyState": 4, "paused": False,
            "mediaErrorCode": None, "playerVisible": True,
            "startScreenshot": str(start), "progressScreenshot": str(progress), "incompleteScreenshot": None,
            "strictObservations": [
                {"phase": "start", "currentTime": 0.4, "element": "video", "decodedFrames": 6,
                 "picture": {"grid": list(range(0, 64)), "distinctColors": 40, "meanLuma": 96.5,
                             "width": 320, "height": 180}},
                {"phase": "progress", "currentTime": 6.4, "element": "video", "decodedFrames": 92,
                 "picture": {"grid": [((index * 37) % 200) for index in range(64)], "distinctColors": 44,
                             "meanLuma": 101.2, "width": 320, "height": 180}},
            ],
            "mediaRequests": [{"status": 200, "path": "/baseline-mp4-a.mp4", "kind": "media"}],
            "playbackInfo": [{"status": 200, "method": "GET", "urlPath": "/Items/x/PlaybackInfo",
                              "body": {"playbackInfo": None, "mediaSources": [
                                  {"pathHash": playback.hashlib.sha256(URL.encode()).hexdigest(),
                                   "pathValue": URL, "streamTypes": ["Audio", "Video"]}]}}],
        }
        entry.update(overrides)
        return entry

    def test_complete_video_observation_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(playback.playback_failures(self._entry(Path(tmp)), expected_url=URL,
                                                        media_type="video"), [])

    def test_short_progress_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            failures = playback.playback_failures(self._entry(Path(tmp), currentTime=1.2),
                                                  expected_url=URL, media_type="video")
        self.assertTrue(any("did not advance" in failure for failure in failures), failures)

    def test_automation_flag_alone_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            failures = playback.playback_failures(
                self._entry(Path(tmp), advanced=True, currentTime=0.3, decodedFrames=0, videoWidth=0,
                            playbackInfo=[], mediaRequests=[]),
                expected_url=URL, media_type="video")
        joined = "; ".join(failures)
        self.assertIn("did not advance", joined)
        self.assertIn("decoded video frames", joined)
        self.assertIn("decoded picture width", joined)
        self.assertIn("successful media request", joined)
        self.assertIn("PlaybackInfo", joined)

    def test_missing_or_tiny_screenshots_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            small = root / "small.png"
            small.write_bytes(b"x")
            for overrides in ({"progressScreenshot": None}, {"progressScreenshot": str(root / "absent.png")},
                              {"progressScreenshot": str(small)}):
                failures = playback.playback_failures(self._entry(root, **overrides), expected_url=URL,
                                                      media_type="video")
                self.assertTrue(any("screenshot" in failure for failure in failures), failures)

    def test_media_error_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            failures = playback.playback_failures(self._entry(Path(tmp), mediaErrorCode=4),
                                                  expected_url=URL, media_type="video")
        self.assertTrue(any("error code 4" in failure for failure in failures), failures)

    def test_audio_playback_refuses_a_decoded_picture_or_a_missing_element(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_entry = self._entry(Path(tmp), mediaType="audio", element="audio", videoWidth=None,
                                      decodedFrames=None,
                                      playbackInfo=[{"status": 200, "method": "GET", "urlPath": "/x",
                                                     "body": {"mediaSources": [
                                                         {"pathHash": playback.hashlib.sha256(URL.encode()).hexdigest(),
                                                          "streamTypes": ["Audio"]}]}}])
            self.assertEqual(playback.playback_failures(audio_entry, expected_url=URL, media_type="audio"), [])
            picture = dict(audio_entry, videoWidth=320)
            failures = playback.playback_failures(picture, expected_url=URL, media_type="audio")
            self.assertTrue(any("decoded a video picture" in failure for failure in failures), failures)
            absent = dict(audio_entry, element=None)
            failures = playback.playback_failures(absent, expected_url=URL, media_type="audio")
        self.assertTrue(any("no native media element" in failure for failure in failures), failures)

    def test_source_url_or_primary_stream_mismatch_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(Path(tmp))
            entry["playbackInfo"] = [{"status": 200, "method": "GET", "urlPath": "/x",
                                      "body": {"mediaSources": [
                                          {"pathHash": playback.hashlib.sha256(b"http://media:8080/other.mp4").hexdigest(),
                                           "streamTypes": ["Audio", "Video"]}]}}]
            failures = playback.playback_failures(entry, expected_url=URL, media_type="video")
            self.assertTrue(any("PlaybackInfo" in failure for failure in failures), failures)
            entry["playbackInfo"] = [{"status": 200, "method": "GET", "urlPath": "/x",
                                      "body": {"mediaSources": [
                                          {"pathHash": playback.hashlib.sha256(URL.encode()).hexdigest(),
                                           "streamTypes": ["Audio"]}]}}]
            failures = playback.playback_failures(entry, expected_url=URL, media_type="video")
        self.assertTrue(any("Video stream" in failure for failure in failures), failures)


class PictureEvidenceTests(unittest.TestCase):
    def _entry(self, picture, phase="progress"):
        return {"strictObservations": [{"phase": phase, "picture": picture}]}

    def test_a_decoded_picture_with_variation_is_accepted(self):
        picture = {"grid": [((index * 37) % 200) for index in range(64)], "distinctColors": 44}
        self.assertEqual(playback.picture_evidence_failures(self._entry(picture), "video"), [])

    def test_audio_rows_do_not_require_a_picture(self):
        self.assertEqual(playback.picture_evidence_failures({"strictObservations": []}, "audio"), [])

    def test_missing_uniform_or_unsampled_pictures_are_refused(self):
        cases = {
            "missing": {"strictObservations": []},
            "no progress phase": self._entry({"grid": list(range(64)), "distinctColors": 9}, phase="start"),
            "unsampled": self._entry(None),
            "draw error": self._entry({"error": "SecurityError"}),
            "wrong cell count": self._entry({"grid": [1, 2, 3], "distinctColors": 9}),
            "uniform": self._entry({"grid": [12] * 64, "distinctColors": 9}),
            "too few colours": self._entry({"grid": list(range(64)), "distinctColors": 2}),
        }
        for label, entry in cases.items():
            self.assertTrue(playback.picture_evidence_failures(entry, "video"), label)


class MeasurementWindowTests(unittest.TestCase):
    def test_zero_ffprobe_delta_is_accepted(self):
        self.assertEqual(playback.measurement_failures(phase="B01 first-trust", probes_before=3,
                                                       probes_after=3, counter_validated=True), [])

    def test_any_probe_inside_the_window_is_refused(self):
        failures = playback.measurement_failures(phase="B01 first-trust", probes_before=3,
                                                 probes_after=4, counter_validated=True)
        self.assertTrue(any("1 ffprobe call" in failure for failure in failures), failures)

    def test_missing_counter_evidence_is_not_treated_as_zero(self):
        failures = playback.measurement_failures(phase="B01 first-trust", probes_before=0,
                                                 probes_after=0, counter_validated=False)
        self.assertTrue(any("never validated" in failure for failure in failures), failures)

    def test_backwards_counter_is_refused(self):
        failures = playback.measurement_failures(phase="B01", probes_before=4, probes_after=2,
                                                 counter_validated=True)
        self.assertTrue(any("backwards" in failure for failure in failures), failures)


class RestartReadbackTests(unittest.TestCase):
    frozen = {"fingerprint": {"url_hash": "a" * 64, "sha1": SHA1, "file_size": SIZE},
              "streams": ["Audio", "Video"], "strm_sha256": "c" * 64, "probe_count": 5}

    def test_matching_read_only_state_is_accepted(self):
        self.assertEqual(playback.restart_readback_failures(self.frozen, dict(self.frozen)), [])

    def test_missing_freeze_is_refused(self):
        self.assertTrue(playback.restart_readback_failures({}, dict(self.frozen)))

    def test_lost_fingerprint_stream_or_probe_free_read_is_refused(self):
        cases = {
            "fingerprint": {"fingerprint": None},
            "streams": {"streams": ["Audio"]},
            "strm": {"strm_sha256": "d" * 64},
            "probe": {"probe_count": 6},
        }
        for label, override in cases.items():
            observed = {**self.frozen, **override}
            self.assertTrue(playback.restart_readback_failures(self.frozen, observed), label)


class ScenarioDefinitionTests(unittest.TestCase):
    def test_baseline_rows_cover_mp4_mkv_and_real_audio(self):
        rows = {row["id"]: row for row in playback.ROWS}
        self.assertEqual(sorted(rows), ["B01", "B02", "B03"])
        self.assertEqual(rows["B01"]["file"], "baseline-mp4-a.mp4")
        self.assertEqual(rows["B02"]["file"], "baseline-mkv-a.mkv")
        self.assertEqual(rows["B03"]["media_type"], "audio")
        self.assertEqual(rows["B03"]["library"], playback.MUSIC_LIBRARY)
        self.assertTrue(rows["B03"]["file"].endswith(".m4a"))
        self.assertGreaterEqual(playback.MINIMUM_PROGRESS_SECONDS, 5)
        self.assertGreaterEqual(playback.FIXTURE_SECONDS, 20)

    def test_every_fixture_has_a_distinct_name_and_a_drawn_marker(self):
        names = [*playback.VIDEO_FIXTURES, *playback.AUDIO_FIXTURES]
        self.assertEqual(len(names), len(set(names)))
        for name, spec in playback.VIDEO_FIXTURES.items():
            self.assertTrue(spec["marker"], name)
        for source, alias in playback.COPY_ALIASES.items():
            self.assertIn(source, names)
            self.assertNotIn(alias, names)

    def test_fixture_plan_covers_color_range_and_both_containers(self):
        ranges = {spec["color_range"] for spec in playback.VIDEO_FIXTURES.values()}
        self.assertEqual(ranges, {"tv", "pc", None})
        containers = {spec["container"] for spec in playback.VIDEO_FIXTURES.values()}
        self.assertEqual(containers, {"mp4", "mkv"})

    def test_unknown_rows_are_refused_by_the_entry_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(playback.BaselineError):
                # --rows validation happens before any workspace or container work.
                args = ["--package", str(Path(tmp) / "missing.zip"), "--evidence-dir", tmp, "--rows", "B99"]
                original = sys.argv
                sys.argv = ["run_isolated_playback_integration.py", *args]
                try:
                    playback.main()
                finally:
                    sys.argv = original


class ProbeCountTests(unittest.TestCase):
    LINE = ('[2026-10-21 02:15:11.494 +00:00] [DBG] [19] MediaBrowser.MediaEncoding.Encoder.MediaEncoder: '
            'Starting "/usr/lib/jellyfin-ffmpeg/ffprobe" with args "-analyzeduration 200M -probesize 1G '
            '-i \\"http://media:8080/baseline-mp4-a.mp4\\" -threads 0 -v warning -print_format json"')

    def test_escaped_quoted_url_is_counted_and_prefixes_are_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / "config" / "log"
            log_dir.mkdir(parents=True)
            (log_dir / "log_1.log").write_text("\n".join([
                self.LINE,
                self.LINE.replace("baseline-mp4-a.mp4", "baseline-mp4-a-copy.mp4"),
                # an unrelated ffprobe (the ffmpeg capability probe) must never be counted
                '[x] [DBG] MediaBrowser.MediaEncoding.Encoder.MediaEncoder: Starting "/usr/lib/jellyfin-ffmpeg/ffprobe" '
                'with args "-loglevel quiet -f lavfi -i nullsrc=s=1x1:d=1 -only_first_vframe"',
                # ffmpeg (not ffprobe) media reads must never be counted as probes
                '[x] [DBG] MediaBrowser.MediaEncoding.Encoder.MediaEncoder: '
                '"/usr/lib/jellyfin-ffmpeg/ffmpeg" "-i \\"http://media:8080/baseline-mp4-a.mp4\\""',
            ]) + "\n", encoding="utf-8")
            original = playback.pe.WORK
            playback.pe.WORK = Path(tmp)
            try:
                self.assertEqual(playback.probe_count("http://media:8080/baseline-mp4-a.mp4"), 1)
                self.assertEqual(playback.probe_count("http://media:8080/baseline-mp4-a-copy.mp4"), 1)
                self.assertEqual(playback.probe_count("http://media:8080/baseline-mkv-a.mkv"), 0)
            finally:
                playback.pe.WORK = original


class EntityClassTests(unittest.TestCase):
    def test_native_movie_and_audio_entities_are_accepted(self):
        self.assertEqual(playback.entity_class_failures(
            {"MediaType": "Video", "Type": "MediaBrowser.Controller.Entities.Movies.Movie"}, "video"), [])
        self.assertEqual(playback.entity_class_failures(
            {"MediaType": "Audio", "Type": "MediaBrowser.Controller.Entities.Audio.Audio"}, "audio"), [])

    def test_mismatched_entity_or_media_type_is_refused(self):
        self.assertTrue(playback.entity_class_failures(
            {"MediaType": "Video", "Type": "MediaBrowser.Controller.Entities.Audio.Audio"}, "video"))
        self.assertTrue(playback.entity_class_failures(
            {"MediaType": "Audio", "Type": "MediaBrowser.Controller.Entities.Movies.Movie"}, "audio"))
        self.assertTrue(playback.entity_class_failures({"MediaType": "Video", "Type": "X.Book"}, "video"))


class SubnetAdaptationTests(unittest.TestCase):
    def test_free_subnets_avoid_every_used_range(self):
        used = ["10.253.0.0/28", "10.253.0.16/28", "172.17.0.0/16"]
        chosen = playback.choose_free_subnets(used, 2)
        self.assertEqual(chosen, ["10.253.0.32/28", "10.253.0.48/28"])
        for cidr in chosen:
            first, last = playback.subnet_bounds(cidr)
            for other in used:
                used_first, used_last = playback.subnet_bounds(other)
                self.assertFalse(first <= used_last and used_first <= last, (cidr, other))

    def test_no_free_block_is_refused_instead_of_reusing_one(self):
        with self.assertRaises(playback.BaselineError):
            playback.choose_free_subnets(["10.253.0.0/16"], 2)

    def test_injected_ipam_blocks_only_name_the_requested_networks(self):
        text = ("services:\n  a:\n    networks:\n      - acceptance\nnetworks:\n"
                "  acceptance:\n    internal: true\n  frontend:\n    driver: bridge\n")
        patched = playback.inject_subnets(text, {"acceptance": "10.253.1.0/28"})
        self.assertIn('        - subnet: "10.253.1.0/28"', patched)
        self.assertEqual(patched.count("ipam:"), 1)
        self.assertIn("internal: true", patched)
        self.assertTrue(patched.endswith("\n"))

    def test_compose_without_networks_section_is_refused(self):
        with self.assertRaises(playback.BaselineError):
            playback.inject_subnets("services:\n  a: {}\n", {"acceptance": "10.253.1.0/28"})


class IndexRenderingTests(unittest.TestCase):
    def test_index_reports_failures_and_rows(self):
        summary = {
            "status": "FAIL", "scenario": "baseline", "rows": ["B01"], "package": "/tmp/pkg.zip",
            "packageIdentity": {"archiveSha256": "e" * 64}, "workspace": "/tmp/work",
            "elapsedSeconds": 12.5, "error": "BaselineError: B01 failed",
            "baseline": {
                "fixtures": {"fixtures": {"baseline-mp4-a.mp4": {
                    "sha1": SHA1, "size": SIZE,
                    "ffprobe": {"streams": [{"codec_type": "video", "codec_name": "h264", "color_range": "tv"},
                                            {"codec_type": "audio", "codec_name": "aac"}]}}}},
                "rowsResult": {"B01": {"status": "FAIL", "error": "media time did not advance"}},
            },
        }
        text = playback.render_index(summary)
        self.assertIn("Status: **FAIL**", text)
        self.assertIn("baseline-mp4-a.mp4", text)
        self.assertIn("media time did not advance", text)
        self.assertIn("B01", text)
        self.assertTrue(json.dumps(summary))


if __name__ == "__main__":
    unittest.main()