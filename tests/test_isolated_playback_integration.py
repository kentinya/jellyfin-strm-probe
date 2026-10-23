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
import uuid
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
ITEM_ID = "8" * 8 + "-1111-2222-3333-" + "a" * 12
SOURCE_ID = "b" * 8 + "-1111-2222-3333-" + "c" * 12
OTHER_SOURCE_ID = "d" * 8 + "-4444-5555-6666-" + "e" * 12
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
    def test_a_row_for_another_item_or_source_is_refused(self):
        # The baseline compares the stored row with the item and the native source this playback
        # actually owns, not just with "some" row for the item.
        row = fingerprint(item_id=uuid.UUID(int=1).hex, source_key=uuid.UUID(int=2).hex)
        matches = playback.fingerprint_fields_match(
            row, expected_url=URL, sha1=SHA1, size=SIZE,
            expected_item_id=str(uuid.UUID(int=1)), expected_source_id=str(uuid.UUID(int=2)))
        self.assertEqual(matches, [])
        wrong_source = playback.fingerprint_fields_match(
            row, expected_url=URL, sha1=SHA1, size=SIZE,
            expected_item_id=str(uuid.UUID(int=1)), expected_source_id=str(uuid.UUID(int=3)))
        self.assertTrue(any("source key" in failure for failure in wrong_source), wrong_source)
        wrong_item = playback.fingerprint_fields_match(
            row, expected_url=URL, sha1=SHA1, size=SIZE,
            expected_item_id=str(uuid.UUID(int=3)), expected_source_id=str(uuid.UUID(int=2)))
        self.assertTrue(any("item id" in failure for failure in wrong_item), wrong_item)
class PlaybackObservationTests(unittest.TestCase):
    def _entry(self, tmp: Path, **overrides) -> dict:
        start = tmp / "start.png"
        progress = tmp / "progress.png"
        start.write_bytes(b"\x89PNG" + b"0" * 4000)
        progress.write_bytes(b"\x89PNG" + b"0" * 4000)
        entry = {
            "name": "Baseline MP4", "itemId": ITEM_ID, "mediaType": "video", "advanced": True,
            "currentTime": 6.4, "startCurrentTime": 0.4, "advancedSeconds": 6.0,
            "duration": 24.0, "element": "video", "videoWidth": 320,
            "videoHeight": 180, "decodedFrames": 92, "readyState": 4, "paused": False,
            "mediaErrorCode": None, "playerVisible": True,
            "startScreenshot": str(start), "progressScreenshot": str(progress), "incompleteScreenshot": None,
            "strictObservations": [
                {"phase": "start", "currentTime": 0.4, "element": "video", "decodedFrames": 6,
                 "picture": {"grid": list(range(0, 64)), "distinctColors": 40, "meanLuma": 96.5,
                             "width": 320, "height": 180}},
                {"phase": "progress", "currentTime": 6.4, "element": "video", "decodedFrames": 92,
                 "advancedSeconds": 6.0,
                 "picture": {"grid": [((index * 37) % 200) for index in range(64)], "distinctColors": 44,
                             "meanLuma": 101.2, "width": 320, "height": 180}},
            ],
            "mediaRequests": [{"status": 200, "path": "/videos/" + ITEM_ID + "/master.m3u8", "kind": "media"}],
            "playbackInfo": [{"status": 200, "method": "GET", "urlPath": "/Items/x/PlaybackInfo",
                              "body": {"playbackInfo": None, "mediaSources": [
                                  {"id": SOURCE_ID,
                                   "pathHash": playback.hashlib.sha256(URL.encode()).hexdigest(),
                                   "pathValue": URL, "streamTypes": ["Audio", "Video"]}]}}],
        }
        entry.update(overrides)
        return entry
    def test_complete_video_observation_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(playback.playback_failures(self._entry(Path(tmp)), expected_url=URL,
                                                        media_type="video",
                                                        expected_source_id=SOURCE_ID), [])
    def test_short_progress_is_refused(self):
        # run-9 accepted ~4.85 s of real advance because the check compared the absolute media
        # position with 5 s; the advance between start and progress is what the contract requires.
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(Path(tmp), currentTime=5.148011, startCurrentTime=0.295978,
                                advancedSeconds=4.852033)
            failures = playback.playback_failures(entry, expected_url=URL, media_type="video",
                                                  expected_source_id=SOURCE_ID)
        self.assertTrue(any("less than 5.0 s" in failure for failure in failures), failures)
    def test_absolute_position_above_the_threshold_is_not_enough(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(Path(tmp), currentTime=12.0, startCurrentTime=8.0, advancedSeconds=4.0)
            failures = playback.playback_failures(entry, expected_url=URL, media_type="video",
                                                  expected_source_id=SOURCE_ID)
        self.assertTrue(any("less than 5.0 s" in failure for failure in failures), failures)
    def test_missing_or_inconsistent_advance_evidence_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = {
                "no advance": {"advancedSeconds": None},
                "no start time": {"startCurrentTime": None},
                "inconsistent": {"advancedSeconds": 9.0},
                "missing start observation": {"strictObservations": [
                    {"phase": "progress", "currentTime": 6.4,
                     "picture": {"grid": [((index * 37) % 200) for index in range(64)],
                                 "distinctColors": 44}}]},
                "missing progress observation": {"strictObservations": [
                    {"phase": "start", "currentTime": 0.4,
                     "picture": {"grid": list(range(64)), "distinctColors": 40}}]},
            }
            for label, overrides in cases.items():
                failures = playback.playback_failures(self._entry(root, **overrides), expected_url=URL,
                                                      media_type="video", expected_source_id=SOURCE_ID)
                self.assertTrue(failures, label)
    def test_automation_flag_alone_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            failures = playback.playback_failures(
                self._entry(Path(tmp), advanced=True, currentTime=0.3, startCurrentTime=0.2,
                            advancedSeconds=0.1, decodedFrames=0, videoWidth=0,
                            playbackInfo=[], mediaRequests=[]),
                expected_url=URL, media_type="video", expected_source_id=SOURCE_ID)
        joined = "; ".join(failures)
        self.assertIn("less than 5.0 s", joined)
        self.assertIn("decoded video frames", joined)
        self.assertIn("decoded picture width", joined)
        self.assertIn("successful media request", joined)
        self.assertIn("PlaybackInfo", joined)
    def test_media_requests_of_another_item_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(Path(tmp), mediaRequests=[
                {"status": 200, "path": "/videos/" + OTHER_SOURCE_ID + "/master.m3u8", "kind": "media"}])
            failures = playback.playback_failures(entry, expected_url=URL, media_type="video",
                                                  expected_source_id=SOURCE_ID)
        self.assertTrue(any("attributable to item" in failure for failure in failures), failures)
    def test_missing_or_tiny_screenshots_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            small = root / "small.png"
            small.write_bytes(b"x")
            for overrides in ({"progressScreenshot": None}, {"progressScreenshot": str(root / "absent.png")},
                              {"progressScreenshot": str(small)}):
                failures = playback.playback_failures(self._entry(root, **overrides), expected_url=URL,
                                                      media_type="video", expected_source_id=SOURCE_ID)
                self.assertTrue(any("screenshot" in failure for failure in failures), failures)
    def test_media_error_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            failures = playback.playback_failures(self._entry(Path(tmp), mediaErrorCode=4),
                                                  expected_url=URL, media_type="video",
                                                  expected_source_id=SOURCE_ID)
        self.assertTrue(any("error code 4" in failure for failure in failures), failures)
    def test_audio_playback_refuses_a_decoded_picture_or_a_missing_element(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_entry = self._entry(Path(tmp), mediaType="audio", element="audio", videoWidth=None,
                                      decodedFrames=None,
                                      playbackInfo=[{"status": 200, "method": "GET", "urlPath": "/x",
                                                     "body": {"mediaSources": [
                                                         {"id": SOURCE_ID,
                                                          "pathHash": playback.hashlib.sha256(URL.encode()).hexdigest(),
                                                          "streamTypes": ["Audio"]}]}}])
            self.assertEqual(playback.playback_failures(audio_entry, expected_url=URL, media_type="audio",
                                                        expected_source_id=SOURCE_ID), [])
            picture = dict(audio_entry, videoWidth=320)
            failures = playback.playback_failures(picture, expected_url=URL, media_type="audio",
                                                  expected_source_id=SOURCE_ID)
            self.assertTrue(any("decoded a video picture" in failure for failure in failures), failures)
            absent = dict(audio_entry, element=None)
            failures = playback.playback_failures(absent, expected_url=URL, media_type="audio",
                                                  expected_source_id=SOURCE_ID)
        self.assertTrue(any("no native media element" in failure for failure in failures), failures)
    def test_source_url_or_primary_stream_mismatch_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(Path(tmp))
            entry["playbackInfo"] = [{"status": 200, "method": "GET", "urlPath": "/x",
                                      "body": {"mediaSources": [
                                          {"id": SOURCE_ID,
                                           "pathHash": playback.hashlib.sha256(b"http://media:8080/other.mp4").hexdigest(),
                                           "streamTypes": ["Audio", "Video"]}]}}]
            failures = playback.playback_failures(entry, expected_url=URL, media_type="video",
                                                  expected_source_id=SOURCE_ID)
            self.assertTrue(any("PlaybackInfo" in failure for failure in failures), failures)
            entry["playbackInfo"] = [{"status": 200, "method": "GET", "urlPath": "/x",
                                      "body": {"mediaSources": [
                                          {"id": SOURCE_ID,
                                           "pathHash": playback.hashlib.sha256(URL.encode()).hexdigest(),
                                           "streamTypes": ["Audio"]}]}}]
            failures = playback.playback_failures(entry, expected_url=URL, media_type="video",
                                                  expected_source_id=SOURCE_ID)
        self.assertTrue(any("Video stream" in failure for failure in failures), failures)
    def test_a_playback_info_from_another_source_id_is_refused(self):
        # The accepted URL/stream pair must belong to the source this row owns: a response for a
        # different media source GUID is a different source even when the address hash matches.
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(Path(tmp))
            entry["playbackInfo"][0]["body"]["mediaSources"][0]["id"] = OTHER_SOURCE_ID
            failures = playback.playback_failures(entry, expected_url=URL, media_type="video",
                                                  expected_source_id=SOURCE_ID)
            self.assertTrue(any("source id" in failure for failure in failures), failures)
    def test_a_missing_expected_source_id_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            failures = playback.playback_failures(self._entry(Path(tmp)), expected_url=URL,
                                                  media_type="video", expected_source_id=None)
        self.assertTrue(any("expected native media source id was not recorded" in failure
                            for failure in failures), failures)
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
    def test_freeze_uses_fresh_auth_after_the_browser_login(self):
        from unittest.mock import patch
        row = {"item": {"Id": ITEM_ID}, "sourceKey": SOURCE_ID, "url": URL}
        with patch.object(playback.pkg, "api_auth", return_value="fresh-auth") as login, \
             patch.object(playback, "fingerprint_row_for_item", return_value=fingerprint()) as read_fp, \
             patch.object(playback, "native_source_snapshot", return_value={"sources": []}) as read_native, \
             patch.object(playback, "probe_count", return_value=1):
            frozen = playback.freeze_state("revoked-auth", row)
        login.assert_called_once_with()
        read_fp.assert_called_once_with("fresh-auth", ITEM_ID, SOURCE_ID)
        read_native.assert_called_once_with("fresh-auth", ITEM_ID)
        self.assertNotIn("auth", frozen)

    def test_freeze_still_rejects_a_failed_native_read(self):
        from unittest.mock import patch
        row = {"item": {"Id": ITEM_ID}, "sourceKey": SOURCE_ID, "url": URL}
        with patch.object(playback.pkg, "api_auth", return_value="fresh-auth"), \
             patch.object(playback, "fingerprint_row_for_item", return_value=fingerprint()), \
             patch.object(playback, "native_source_snapshot", side_effect=playback.BaselineError("native read failed")):
            with self.assertRaises(playback.BaselineError):
                playback.freeze_state("revoked-auth", row)

    sources = [{"id": SOURCE_ID, "path": URL, "pathHash": "8c5bb2d1" + "0" * 56, "protocol": "Http",
                "container": "mp4", "runTimeTicks": 240000000, "size": SIZE,
                "streams": [{"Type": "Audio", "fields": {"Index": 1, "Codec": "aac", "ColorRange": None}},
                            {"Type": "Video", "fields": {"Index": 0, "Codec": "h264", "Width": 320,
                                                         "Height": 180, "ColorRange": "tv"}}]}]
    frozen = {"fingerprint": {"url_hash": "a" * 64, "sha1": SHA1, "file_size": SIZE},
              "nativeSources": {"itemId": "a" * 32, "itemPath": "/media/strm/Baseline MP4.strm",
                                "sources": sources},
              "strm_sha256": "c" * 64, "probe_count": 5}
    def test_matching_read_only_state_is_accepted(self):
        self.assertEqual(playback.restart_readback_failures(self.frozen, json.loads(json.dumps(self.frozen))), [])
    def test_missing_freeze_is_refused(self):
        self.assertTrue(playback.restart_readback_failures({}, json.loads(json.dumps(self.frozen))))
    def test_lost_fingerprint_stream_or_probe_free_read_is_refused(self):
        cases = {
            "fingerprint": {"fingerprint": None},
            "strm": {"strm_sha256": "d" * 64},
            "probe": {"probe_count": 6},
        }
        for label, override in cases.items():
            observed = {**json.loads(json.dumps(self.frozen)), **override}
            self.assertTrue(playback.restart_readback_failures(self.frozen, observed), label)
    def test_changed_address_codec_dimensions_or_source_id_is_refused(self):
        # run-9 only compared the set of stream types (["Audio", "Video"]), so an address change or
        # a completely different saved stream still compared equal; the full source must be compared.
        mutations = {
            "address": lambda sources: sources[0].__setitem__("path", "http://media:8080/baseline-mp4-b.mp4"),
            "path hash": lambda sources: sources[0].__setitem__("pathHash", "f" * 64),
            "source id": lambda sources: sources[0].__setitem__("id", OTHER_SOURCE_ID),
            "codec": lambda sources: sources[0]["streams"][1]["fields"].__setitem__("Codec", "hevc"),
            "width": lambda sources: sources[0]["streams"][1]["fields"].__setitem__("Width", 1920),
            "color range": lambda sources: sources[0]["streams"][1]["fields"].__setitem__("ColorRange", "pc"),
        }
        for label, mutate in mutations.items():
            observed = json.loads(json.dumps(self.frozen))
            mutate(observed["nativeSources"]["sources"])
            self.assertTrue(playback.restart_readback_failures(self.frozen, observed), label)
    def test_a_dropped_saved_source_is_refused(self):
        observed = json.loads(json.dumps(self.frozen))
        observed["nativeSources"]["sources"] = []
        self.assertTrue(playback.restart_readback_failures(self.frozen, observed))
    def test_a_freeze_without_native_sources_is_refused(self):
        frozen = {key: value for key, value in self.frozen.items() if key != "nativeSources"}
        self.assertTrue(playback.restart_readback_failures(frozen, json.loads(json.dumps(self.frozen))))
class NativeSourceSnapshotTests(unittest.TestCase):
    payload = {"Id": "b" * 8 + "-1111-2222-3333-" + "c" * 12, "Path": "/media/strm/Baseline MP4.strm",
               "MediaSources": [{"Id": "B" * 8 + "-1111-2222-3333-" + "C" * 12, "Path": URL, "Protocol": "Http",
                                  "Container": "mp4", "RunTimeTicks": 240000000, "Size": SIZE,
                                  "MediaStreams": [{"Type": "Video", "Index": 0, "Codec": "h264", "Width": 320,
                                                     "Height": 180, "ColorRange": "tv"},
                                                    {"Type": "Audio", "Index": 1, "Codec": "aac"}]}]}
    def test_snapshot_keeps_source_identity_address_and_stream_fields(self):
        original = playback.pe.request_json
        playback.pe.request_json = lambda *args, **kwargs: (200, json.loads(json.dumps(self.payload)))
        try:
            snapshot = playback.native_source_snapshot("auth", self.payload["Id"])
        finally:
            playback.pe.request_json = original
        self.assertEqual(len(snapshot["sources"]), 1)
        source = snapshot["sources"][0]
        self.assertEqual(source["id"], SOURCE_ID)
        self.assertEqual(source["path"], URL)
        self.assertEqual(source["pathHash"], playback.hashlib.sha256(URL.encode()).hexdigest())
        types = {stream["Type"]: stream["fields"] for stream in source["streams"]}
        self.assertEqual(types["Video"]["Codec"], "h264")
        self.assertEqual(types["Video"]["Width"], 320)
        self.assertEqual(types["Video"]["ColorRange"], "tv")
        # The snapshot keeps the complete native stream objects: every field the server saved is
        # present, so a restart comparison cannot miss a change outside a fixed projection list.
        self.assertEqual(types["Video"], dict(self.payload["MediaSources"][0]["MediaStreams"][0]))
        self.assertEqual(types["Audio"], {"Type": "Audio", "Index": 1, "Codec": "aac"})
    def test_snapshot_refuses_a_failed_query(self):
        original = playback.pe.request_json
        playback.pe.request_json = lambda *args, **kwargs: (500, {})
        try:
            with self.assertRaises(playback.BaselineError):
                playback.native_source_snapshot("auth", self.payload["Id"])
        finally:
            playback.pe.request_json = original
    def test_a_private_path_is_not_copied_into_the_evidence(self):
        payload = json.loads(json.dumps(self.payload))
        payload["MediaSources"][0]["Path"] = "/media/private/user/library/movie.mp4"
        original = playback.pe.request_json
        playback.pe.request_json = lambda *args, **kwargs: (200, payload)
        try:
            snapshot = playback.native_source_snapshot("auth", self.payload["Id"])
        finally:
            playback.pe.request_json = original
        self.assertIsNone(snapshot["sources"][0]["path"])
        self.assertEqual(snapshot["sources"][0]["pathHash"],
                         playback.hashlib.sha256(b"/media/private/user/library/movie.mp4").hexdigest())
class ScenarioDefinitionTests(unittest.TestCase):
    def test_baseline_rows_cover_only_video_strm_formats(self):
        rows = {row["id"]: row for row in playback.ROWS}
        self.assertEqual(sorted(rows), ["B01", "B02"])
        self.assertEqual(playback.BASELINE_ROW_IDS, ("B01", "B02"))
        self.assertEqual(rows["B01"]["file"], "baseline-mp4-a.mp4")
        self.assertEqual(rows["B02"]["file"], "baseline-mkv-a.mkv")
        self.assertTrue(all(row["media_type"] == "video" for row in rows.values()))
        self.assertGreaterEqual(playback.MINIMUM_PROGRESS_SECONDS, 5)
        self.assertGreaterEqual(playback.FIXTURE_SECONDS, 20)
    def test_every_fixture_has_a_distinct_name_and_a_drawn_marker(self):
        names = list(playback.VIDEO_FIXTURES)
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
                args = ["--package", str(Path(tmp) / "missing.zip"), "--evidence-dir", tmp, "--rows", "B03"]
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
class MatrixRowIdTests(unittest.TestCase):
    FIXTURES = {}

    @classmethod
    def setUpClass(cls):
        sha = {"a": "a" * 40, "b": "b" * 40, "c": "c" * 40, "d": "d" * 40, "e": "e" * 40,
               "f": "f" * 40, "s": "1" * 40}
        for ext in ("mp4", "mkv"):
            cls.FIXTURES.update({
                f"baseline-{ext}-a.{ext}": {"sha1": sha["a"], "size": 1000},
                f"baseline-{ext}-b.{ext}": {"sha1": sha["b"], "size": 1200},
                f"matrix-{ext}-p4b.{ext}": {"sha1": sha["c"], "size": 700},
                f"matrix-{ext}-p06up.{ext}": {"sha1": sha["d"], "size": 1400},
                f"matrix-{ext}-b-padded.{ext}": {"sha1": sha["e"], "size": 1000},
                f"matrix-{ext}-a-trunc.{ext}": {"sha1": sha["f"], "size": 333},
                f"baseline-{ext}-limited.{ext}": {"sha1": sha["s"], "size": 900},
                f"baseline-{ext}-full.{ext}": {"sha1": sha["s"], "size": 900},
                f"baseline-{ext}-unspecified.{ext}": {"sha1": sha["s"], "size": 900},
                f"matrix-{ext}-short-limited.{ext}": {"sha1": sha["s"], "size": 800},
                f"matrix-{ext}-short-full.{ext}": {"sha1": sha["s"], "size": 800},
                f"matrix-{ext}-short-unspecified.{ext}": {"sha1": sha["s"], "size": 800},
            })
        cls.FIXTURES.update({f"matrix-mkv-{tail}.mkv": {"sha1": sha["s"], "size": 900}
                             for tail in ("limited", "full", "unspecified")})

    @classmethod
    def rows_by_id(cls):
        rows = playback.build_matrix_rows(cls.FIXTURES)
        return {row["id"]: row for row in rows}

    def test_the_fixed_expansion_has_exactly_the_contract_rows(self):
        ids = playback.matrix_row_ids()
        self.assertEqual(len(ids), 116)
        for fmt in ("MP4", "MKV"):
            for t in ("01", "02", "03", "04"):
                self.assertIn(f"{fmt}.P01.{t}", ids)
            for t in ("01", "02", "03", "04", "05", "06", "07", "08"):
                self.assertIn(f"{fmt}.P02.{t}", ids)
            for t in ("01", "02", "03", "04", "05"):
                self.assertIn(f"{fmt}.P03.{t}", ids)
                self.assertIn(f"{fmt}.P05.{t}", ids)
            for t in ("01", "02", "03"):
                self.assertIn(f"{fmt}.P04.{t}", ids)
                self.assertIn(f"{fmt}.P08.{t}", ids)
            for t in ("01", "02", "03", "04", "05"):
                for d in ("up", "down"):
                    self.assertIn(f"{fmt}.P06.{t}.{d}", ids)
            for t in ("01", "02", "03", "04", "05", "06"):
                self.assertIn(f"{fmt}.P07.{t}", ids)
            for t in ("limited", "full", "unspecified"):
                self.assertIn(f"{fmt}.C02.{t}", ids)
                self.assertIn(f"{fmt}.C06.{t}", ids)
            for g in ("F01", "F02"):
                self.assertIn(f"{fmt}.{g}", ids)
            for g in ("D01", "D02", "D03", "D04", "D05", "D06"):
                self.assertIn(f"{fmt}.{g}", ids)
        # 44 P rows + 6 C rows + 2 F rows + 6 D rows per format
        for fmt in ("MP4", "MKV"):
            self.assertEqual(sum(1 for i in ids if i.startswith(fmt + ".")), 58)

class MatrixPreconditionTests(MatrixRowIdTests):
    """The fixed rows must write the contract's real preconditions, not a degraded variant.

    A manifest rewrite names its new tokens explicitly; a token it does not name keeps the old
    value, and only the explicit DELETE instruction removes one, so a missing old SHA-1 can
    never silently degrade back into the old value.
    """

    def resolved_tokens(self, row):
        tokens = {}
        for field in ("sha1", "size"):
            if field in row["apply"]:
                if row["apply"][field] is not playback.DELETE:
                    tokens[field] = row["apply"][field]
            else:
                tokens[field] = row["old"][field]
        return tokens

    def test_a_missing_sha1_is_removed_not_replaced_with_the_old_value(self):
        rows = self.rows_by_id()
        # P03.04 must really drop the new size; P05.01 must really drop the new SHA-1.
        self.assertNotIn("size", self.resolved_tokens(rows["MP4.P03.04"]))
        self.assertNotIn("sha1", self.resolved_tokens(rows["MP4.P05.01"]))
        # P03.05 and P07 rows write their invalid values as literal manifest text.
        self.assertEqual(self.resolved_tokens(rows["MP4.P03.05"])["size"], "-1")

    def test_p03_03_writes_an_uppercase_hash_not_the_old_value(self):
        rows = self.rows_by_id()
        for fmt in ("MP4", "MKV"):
            tokens = self.resolved_tokens(rows[f"{fmt}.P03.03"])
            self.assertEqual(tokens["sha1"], ("a" * 40).upper())
            self.assertNotEqual(tokens["sha1"], rows[f"{fmt}.P03.03"]["old"]["sha1"])

    def test_p07_keeps_the_contract_directions(self):
        rows = self.rows_by_id()
        # 01: valid old hash, old size absent, new hash dropped, new size valid; 03: neither side
        # has a hash nor a size.
        self.assertEqual(rows["MP4.P07.01"]["old"], {"sha1": "a" * 40, "size": None})
        self.assertEqual(self.resolved_tokens(rows["MP4.P07.01"]), {"size": "1000"})
        self.assertEqual(rows["MP4.P07.03"]["old"], {"sha1": None, "size": None})
        # The rewrite keeps both absent tokens (their old values are already None), so the resolved
        # manifest carries neither hash nor size.
        tokens = self.resolved_tokens(rows["MP4.P07.03"])
        self.assertEqual({k: v for k, v in tokens.items() if v is not None}, {})
        self.assertEqual(tokens, {"sha1": None, "size": None})
        self.assertEqual(self.resolved_tokens(rows["MP4.P07.02"]), {"sha1": "a" * 40})
        # 04 turns the old valid hash into the 39-char length form; 05 starts from the 39-char form
        # and gains a valid hash with a valid size, while the old size stays non-numeric text.
        for row_id in ("MP4.P07.04", "MKV.P07.04"):
            row = rows[row_id]
            self.assertEqual(row["old"]["sha1"], "a" * 40)
            self.assertEqual(self.resolved_tokens(row)["sha1"], "a" * 39 + "z")
        for row_id in ("MP4.P07.05", "MKV.P07.05"):
            row = rows[row_id]
            self.assertEqual(row["old"]["sha1"], "a" * 39 + "z")
            self.assertEqual(row["old"]["size"], "not-a-size")
            tokens = self.resolved_tokens(row)
            self.assertEqual(tokens["sha1"], "a" * 40)
            self.assertEqual(tokens["size"], "1000")

    def test_p06_writes_the_hash_of_the_bytes_the_row_actually_serves(self):
        rows = self.rows_by_id()
        for fmt, ext in (("MP4", "mp4"), ("MKV", "mkv")):
            up = rows[f"{fmt}.P06.02.up"]
            down = rows[f"{fmt}.P06.02.down"]
            self.assertEqual(up["apply"]["to"], f"matrix-{ext}-p06up.{ext}")
            self.assertEqual(down["apply"]["to"], f"matrix-{ext}-p4b.{ext}")
            up_sha, _ = playback.parsed_tokens(up["apply"]["sha1"], None)
            down_sha, _ = playback.parsed_tokens(down["apply"]["sha1"], None)
            self.assertEqual(up_sha, self.FIXTURES[f"matrix-{ext}-p06up.{ext}"]["sha1"])
            self.assertEqual(down_sha, self.FIXTURES[f"matrix-{ext}-p4b.{ext}"]["sha1"])

    def test_p06_real_sizes_follow_the_fixed_up_and_down_directions(self):
        # The direction is a property of the real files, not of the row label: every ``up`` row
        # must serve more bytes than A and every ``down`` row fewer.
        rows = self.rows_by_id()
        for fmt, ext in (("MP4", "mp4"), ("MKV", "mkv")):
            a_size = self.FIXTURES[f"baseline-{ext}-a.{ext}"]["size"]
            for tail in ("01", "02", "03", "04", "05"):
                up = rows[f"{fmt}.P06.{tail}.up"]
                down = rows[f"{fmt}.P06.{tail}.down"]
                self.assertGreater(int(up["apply"]["size"]), a_size)
                self.assertLess(int(down["apply"]["size"]), a_size)
                self.assertGreater(self.FIXTURES[up["apply"]["to"]]["size"], a_size)
                self.assertLess(self.FIXTURES[down["apply"]["to"]]["size"], a_size)

    def test_p06_fixtures_with_wrong_directions_are_refused_before_any_row(self):
        # A longer duration does not imply a longer file; the generated partners are measured and
        # the row build stops if the real byte sizes contradict the fixed direction.
        playback.require_p06_directions("MP4", 1000, 1400, 700)
        with self.assertRaises(playback.BaselineError):
            playback.require_p06_directions("MP4", 1660446, 381375, 700)
        with self.assertRaises(playback.BaselineError):
            playback.require_p06_directions("MP4", 1000, 1400, 1200)
        broken = dict(self.FIXTURES)
        broken["matrix-mp4-p06up.mp4"] = {"sha1": "d" * 40, "size": 900}
        with self.assertRaises(playback.BaselineError):
            playback.build_matrix_rows(broken)

    def test_the_p06_up_partner_is_encoded_with_real_per_frame_noise(self):
        # smptebars alone encodes smaller than the shorter A clip even at a longer duration, so the
        # up partner needs a real content difference; the generation parameters alone prove
        # nothing, which is why the measured sizes are checked separately above.
        for fmt in ("MP4", "MKV"):
            spec = playback.matrix_extra_specs(fmt)["matrix-{}-p06up.{}".format(
                "mp4" if fmt == "MP4" else "mkv", "mp4" if fmt == "MP4" else "mkv")]
            self.assertTrue(spec.get("noise"))
            args = playback.fixture_ffmpeg_args(spec, "p06up.out")
            self.assertIn(str(spec["noise"]), args[args.index("-vf") + 1])
            down = playback.matrix_extra_specs(fmt)["matrix-{}-p4b.{}".format(
                "mp4" if fmt == "MP4" else "mkv", "mp4" if fmt == "MP4" else "mkv")]
            self.assertNotIn("noise", down)

    def test_c02_is_a_url_change_not_a_fixed_url_byte_swap(self):
        rows = self.rows_by_id()
        for fmt, ext in (("MP4", "mp4"), ("MKV", "mkv")):
            row = rows[f"{fmt}.C02.limited"]
            self.assertEqual(row["apply_kind"], "manifest-url")
            self.assertNotEqual(row["apply"]["url"], playback.MEDIA_PREFIX + f"baseline-{ext}-a.{ext}")
            self.assertEqual(row["fp_url"], row["apply"]["url"])
            self.assertEqual(row["watch_media"], row["apply"]["url"].rsplit("/", 1)[-1])

    def test_the_f02_rows_use_the_corrupt_bytes_and_their_real_identity(self):
        rows = MatrixRowIdTests.rows_by_id()
        for fmt, ext in (("MP4", "mp4"), ("MKV", "mkv")):
            row = rows[f"{fmt}.F02"]
            trunc = MatrixRowIdTests.FIXTURES[f"matrix-{ext}-a-trunc.{ext}"]
            recovery = MatrixRowIdTests.FIXTURES[f"matrix-{ext}-p4b.{ext}"]
            self.assertEqual(row["apply"]["corrupt_to"], f"matrix-{ext}-a-trunc.{ext}")
            self.assertEqual(row["apply"]["corrupt_sha1"], trunc["sha1"])
            self.assertEqual(row["apply"]["corrupt_size"], str(trunc["size"]))
            self.assertEqual(row["fp_tokens"], (recovery["sha1"], str(recovery["size"])))

    def test_f01_failure_manifest_keeps_the_prepared_recovery_identity(self):
        rows = self.rows_by_id()
        for fmt, ext in (("MP4", "mp4"), ("MKV", "mkv")):
            apply = rows[f"{fmt}.F01"]["apply"]
            self.assertEqual(apply["sha1"], self.FIXTURES[f"matrix-{ext}-p4b.{ext}"]["sha1"])
            self.assertEqual(apply["size"], str(self.FIXTURES[f"matrix-{ext}-p4b.{ext}"]["size"]))

    def test_matrix_rows_use_a_stable_strm_name_not_the_item_dictionary(self):
        # write_matrix_strm keys the file path on the stable row name; the scanned item dictionary
        # replaces row["item"] and must never end up in the STRM path.
        rows = self.rows_by_id()
        for row in rows.values():
            self.assertIn("strm_name", row)
            self.assertEqual(row["strm_name"], row["item"])

class F02CorruptionTests(unittest.TestCase):
    """F02's fixed URL must serve bytes the native probe really rejects.

    The earlier first-third cut was still a valid container: its moov/Matroska metadata was at the
    front, so ffprobe returned Video/Audio and the "failure" playback advanced. The controlled
    partner is now a strict 512-byte prefix and generation refuses any result that still exposes a
    video stream or a successful probe.
    """

    def test_the_f02_partner_is_a_strict_512_byte_truncation(self):
        data = bytes(range(256)) * 8
        prefix = playback.f02_truncated_bytes(data)
        self.assertEqual(len(prefix), playback.F02_CORRUPT_PREFIX_BYTES)
        self.assertEqual(prefix, data[:playback.F02_CORRUPT_PREFIX_BYTES])
        self.assertLess(len(prefix), len(data))

    def test_a_short_source_is_refused_instead_of_silently_written_as_is(self):
        with self.assertRaises(playback.BaselineError):
            playback.f02_truncated_bytes(b"x" * (playback.F02_CORRUPT_PREFIX_BYTES - 1))

    def test_a_probeable_video_or_a_successful_probe_is_refused(self):
        with self.assertRaises(playback.BaselineError):
            playback.require_f02_unprobeable(
                "matrix-mp4-a-trunc.mp4", [{"codec_type": "video", "codec_name": "h264"}], None)
        with self.assertRaises(playback.BaselineError):
            playback.require_f02_unprobeable(
                "matrix-mkv-a-trunc.mkv", [], None)  # ffprobe returned success with no error
        playback.require_f02_unprobeable(
            "matrix-mp4-a-trunc.mp4", [], "ffprobe failed for /out/matrix-mp4-a-trunc.mp4")

class MatrixApplyTests(unittest.TestCase):
    """apply_matrix_change must switch a fixed URL through a row-owned staging copy so the shared
    partner files survive for the following rows, and reset_row_media must re-establish the A
    baseline before each journey."""

    class _FakeError(Exception):
        pass

    def _row(self, media="switch-x.mp4", partner="matrix-mp4-p4b.mp4"):
        return {"id": "MP4.X.01", "fmt": "MP4", "strm_name": "Matrix MP4 X 01",
                "item": "Matrix MP4 X 01", "media": media, "old": {"sha1": "a" * 40, "size": 1000},
                "apply": {"to": partner, "sha1": "c" * 40, "size": 700}, "apply_kind": "switch",
                "url": playback.MEDIA_PREFIX + media}

    def test_switch_keeps_the_partner_file_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = playback.pe.WORK
            playback.pe.WORK = Path(tmp)
            try:
                media = Path(tmp) / "media"
                media.mkdir()
                (media / "baseline-mp4-a.mp4").write_bytes(b"A-content")
                (media / "matrix-mp4-p4b.mp4").write_bytes(b"B-content")
                (media / "switch-x.mp4").write_bytes(b"A-content")
                row = self._row()
                record = playback.apply_matrix_change(row)
                self.assertEqual((media / "switch-x.mp4").read_bytes(), b"B-content")
                self.assertEqual((media / "matrix-mp4-p4b.mp4").read_bytes(), b"B-content")
                self.assertEqual(record["switchSha256"], playback.hashlib.sha256(b"B-content").hexdigest())
            finally:
                playback.pe.WORK = original

    def test_reset_row_media_restores_the_a_baseline_and_removes_the_404_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = playback.pe.WORK
            playback.pe.WORK = Path(tmp)
            try:
                media = Path(tmp) / "media"
                media.mkdir()
                (media / "baseline-mp4-a.mp4").write_bytes(b"A-content")
                (media / "matrix-mp4-p4b.mp4").write_bytes(b"B-content")
                (media / "switch-x.mp4").write_bytes(b"B-content")
                (media / "missing-f01-mp4.mp4").write_bytes(b"stale")
                switch_row = self._row()
                reset = playback.reset_row_media(switch_row)
                self.assertEqual((media / "switch-x.mp4").read_bytes(), b"A-content")
                f01_row = self._row(media="baseline-mp4-a.mp4")
                f01_row["id"] = "MP4.F01"
                f01_row["apply_kind"] = "f01"
                f01_row["apply"] = {"url": playback.MEDIA_PREFIX + "missing-f01-mp4.mp4",
                                    "sha1": "c" * 40, "size": 700,
                                    "recovery_file": "matrix-mp4-p4b.mp4"}
                reset = playback.reset_row_media(f01_row)
                self.assertFalse((media / "missing-f01-mp4.mp4").exists())
            finally:
                playback.pe.WORK = original

class ArgRouteTests(unittest.TestCase):
    def test_the_plugin_configuration_uses_the_documented_route(self):
        source = (ROOT / "scripts" / "run_isolated_playback_integration.py").read_text(encoding="utf-8")
        self.assertIn('f"/Plugins/{pkg.PLUGIN_ID}/Configuration"', source)
        self.assertNotIn("/Plugins/{pkg.PLUGIN_ID}/0.1.0.0/Configuration", source)


class RewriteApplyTests(unittest.TestCase):
    """DR53-1: the P08.03 byte-identical rewrite must work on the scanned row shape.

    ``prepare_matrix_rows`` replaces ``row["item"]`` with the native item dictionary, so a rewrite
    that keyed its staging path on ``row["item"]`` raised a TypeError on the real journey. The
    rewrite must key on the stable ``strm_name`` and keep the bytes identical.
    """

    def _scanned_row(self, tmp: Path) -> dict:
        return {"id": "MP4.P08.03", "fmt": "MP4", "strm_name": "Matrix MP4 P08 03",
                # The post-scan shape: the item is the native dictionary, not the name string.
                "item": {"Id": "8" * 8 + "-1111-2222-3333-" + "a" * 12, "Name": "Matrix MP4 P08"},
                "media": "baseline-mp4-a.mp4", "url": playback.MEDIA_PREFIX + "baseline-mp4-a.mp4",
                "old": {"sha1": "a" * 40, "size": "1000"}, "apply": {},
                "apply_kind": "rewrite"}

    def test_the_byte_identical_rewrite_accepts_the_scanned_item_dictionary(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = playback.pe.WORK
            playback.pe.WORK = Path(tmp)
            try:
                strm_dir = Path(tmp) / "strm"
                strm_dir.mkdir()
                target = strm_dir / "Matrix MP4 P08 03.strm"
                # A deliberately non-canonical original: the size line precedes the hash line and a
                # trailing comment is present. Reconstructing the manifest from the row's tokens
                # would reorder/drop these bytes, so only a real byte-identical rewrite passes.
                content = ("# strm-probe-version:1\n# strm-probe-size:1000\n# strm-probe-sha1:" + "a" * 40 +
                           "\n# Modified: 2026-10-21T00:00:00Z\n" + playback.MEDIA_PREFIX + "baseline-mp4-a.mp4\n")
                target.write_text(content, encoding="utf-8")
                record = playback.apply_matrix_change(self._scanned_row(Path(tmp)))
                self.assertEqual(target.read_text(encoding="utf-8"), content)
                self.assertIs(record["contentSha256Unchanged"], True)
                self.assertEqual(record["strm"]["sha256"],
                                 playback.hashlib.sha256(content.encode()).hexdigest())
                # Only this row's own STRM is rewritten; no stray file is created.
                self.assertEqual(sorted(p.name for p in strm_dir.iterdir()), [target.name])
            finally:
                playback.pe.WORK = original

    def test_an_mtime_only_change_keeps_the_bytes_and_reports_their_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = playback.pe.WORK
            playback.pe.WORK = Path(tmp)
            try:
                strm_dir = Path(tmp) / "strm"
                strm_dir.mkdir()
                target = strm_dir / "Matrix MP4 P08 01.strm"
                content = "# strm-probe-version:1\nhttp://media:8080/baseline-mp4-a.mp4\n"
                target.write_text(content, encoding="utf-8")
                row = self._scanned_row(Path(tmp))
                row.update({"id": "MP4.P08.01", "strm_name": "Matrix MP4 P08 01", "apply_kind": "mtime"})
                record = playback.apply_matrix_change(row)
                self.assertEqual(target.read_text(encoding="utf-8"), content)
                self.assertEqual(record["strm"]["sha256"],
                                 playback.hashlib.sha256(content.encode()).hexdigest())
                self.assertGreater(target.stat().st_mtime, playback.time.time() + 1800)
            finally:
                playback.pe.WORK = original


class DelegationJourneyAuthTests(unittest.TestCase):
    """DR53-3: the delegation journeys must re-authenticate after a real Web Play.

    The browser driver logs in with its own session, which revokes the API token the journey held
    before the playback. The source review found D02/D03 restoring the plugin or auto-check and
    D04/D05 reading the native source with that revoked token. These controls prove the read
    boundary now asks for a new token, that the new token is really used, and that a genuinely
    failing read still fails (the new token is not a pass-through).
    """

    def _row(self):
        return {"id": "MP4.D04", "fmt": "MP4", "strm_name": "Matrix Regular MP4",
                "item": {"Id": ITEM_ID}, "media_type": "video",
                "apply_kind": "d04", "url": playback.MEDIA_PREFIX + "regular-mp4/Matrix Regular MP4.mp4"}

    def test_the_refresh_returns_a_new_local_token(self):
        from unittest.mock import patch
        calls: list[str] = []

        def fake_login():
            calls.append("login")
            return "fresh-token"

        with patch.object(playback.pkg, "api_auth", fake_login):
            self.assertEqual(playback.refresh_auth(), "fresh-token")
        self.assertEqual(calls, ["login"])

    def test_a_follow_up_read_uses_the_refreshed_token_and_never_returns_it(self):
        from unittest.mock import patch
        seen: list[str] = []

        def fake_sources(auth, item_id):
            seen.append(auth)
            return {"itemId": item_id, "sources": []}

        with patch.object(playback.pkg, "api_auth", lambda: "fresh-token"), \
                patch.object(playback, "native_source_snapshot", fake_sources), \
                patch.object(playback, "fingerprint_row_for_item", lambda *a: None), \
                patch.object(playback, "probe_count", lambda url: 0), \
                patch.object(playback, "_strm_sha256", lambda row: None):
            state = playback.freeze_state("stale-token", self._row())
        self.assertEqual(seen, ["fresh-token"])
        self.assertNotIn("stale-token", json.dumps(state))
        self.assertNotIn("fresh-token", json.dumps(state))

    def test_a_read_that_really_fails_is_still_refused_after_the_refresh(self):
        from unittest.mock import patch

        def failing_sources(auth, item_id):
            raise RuntimeError("The read-only native media-source query failed.")

        with patch.object(playback.pkg, "api_auth", lambda: "fresh-token"), \
                patch.object(playback, "native_source_snapshot", failing_sources), \
                patch.object(playback, "fingerprint_row_for_item", lambda *a: None), \
                patch.object(playback, "probe_count", lambda url: 0), \
                patch.object(playback, "_strm_sha256", lambda row: None):
            with self.assertRaises(RuntimeError):
                playback.freeze_state("stale-token", self._row())

    def test_the_delegation_journeys_read_after_the_playback_boundary(self):
        source = (ROOT / "scripts" / "run_isolated_playback_integration.py").read_text(encoding="utf-8")
        for journey in ("journey_d02", "journey_d03", "journey_d04", "journey_d05"):
            start = source.index(f"def {journey}(")
            end = source.index("\ndef ", start + 10)
            body = source[start:end]
            # A second native play is required before the restart journey.
            self.assertTrue("native-play-second" in body or '"second-play"' in body, journey)
            self.assertIn("d_row_restart", body, journey)
            # The journey must not use the stale pre-playback token for a later request.
            self.assertNotIn("pkg.api_auth()", body, journey)

    def test_d02_and_d03_restore_the_configuration_only_after_the_restart_journey(self):
        source = (ROOT / "scripts" / "run_isolated_playback_integration.py").read_text(encoding="utf-8")
        for journey, restore in (("journey_d02", 'restore_plugin_enabled()'),
                                 ("journey_d03", 'restore_plugin_configuration(')):
            start = source.index(f"def {journey}(")
            end = source.index("\ndef ", start + 10)
            body = source[start:end]
            self.assertLess(body.index("d_row_restart"), body.index(restore),
                            f"{journey}: the configuration was restored before the restart journey")
            # The restore runs from the ``finally`` so a failed window cannot leak the switch.
            self.assertIn("finally:", body, journey)
            self.assertLess(body.index("d_row_restart"), body.index("finally:"), journey)


class ConfigurationBoundaryTests(unittest.TestCase):
    """B53-20261023-1: a native 204 is success, a failed row still restores, and nothing leaks.

    The pinned server answers the plugin configuration POST with 204 No Content (the accepted
    configuration gate records ``serverStatus: 204``), so requiring 200 made a successful toggle
    fail *after* the server had already applied it. Combined with the missing restore this left the
    next rows running against a changed switch and with a revoked token.
    """

    def _row(self):
        return {"id": "MP4.D03", "fmt": "MP4", "strm_name": "Matrix MP4 D03",
                "item": {"Id": ITEM_ID}, "media_type": "video", "apply_kind": "d03",
                "url": URL, "journey": "d03"}

    def test_a_native_204_is_success_and_the_read_back_is_verified(self):
        from unittest.mock import patch
        posts: list[dict] = []

        def fake_configuration(auth):
            return {"Enabled": True, "PlaybackAutoCheck": posts[-1]["PlaybackAutoCheck"] if posts else True}

        def fake_set(auth, changes):
            posts.append(dict(changes))
            return 204

        with patch.object(playback, "plugin_configuration", fake_configuration), \
                patch.object(playback, "set_plugin_configuration", fake_set):
            record = playback.apply_plugin_configuration("auth", {"PlaybackAutoCheck": False})
        self.assertEqual(record["status"], 204)
        self.assertEqual(record["observed"], {"PlaybackAutoCheck": False})

    def test_a_change_the_server_did_not_apply_is_refused_even_on_204(self):
        from unittest.mock import patch
        with patch.object(playback, "plugin_configuration", lambda auth: {"PlaybackAutoCheck": True}), \
                patch.object(playback, "set_plugin_configuration", lambda auth, changes: 204):
            with self.assertRaises(playback.BaselineError) as raised:
                playback.apply_plugin_configuration("auth", {"PlaybackAutoCheck": False})
        self.assertIn("was not applied", str(raised.exception))

    def test_a_rejected_status_is_not_success(self):
        from unittest.mock import patch
        with patch.object(playback, "plugin_configuration", lambda auth: {"PlaybackAutoCheck": True}), \
                patch.object(playback, "set_plugin_configuration", lambda auth, changes: 400):
            with self.assertRaises(playback.BaselineError):
                playback.apply_plugin_configuration("auth", {"PlaybackAutoCheck": False})

    def test_a_failed_window_after_the_switch_still_restores_the_real_original_value(self):
        from unittest.mock import patch
        state = {"PlaybackAutoCheck": True}

        def fake_configuration(auth):
            return dict(state)

        def fake_set(auth, changes):
            state.update(changes)
            return 204

        def failing_play(*args, **kwargs):
            raise playback.BaselineError("MP4.D03 native-play: the playback window failed")

        with patch.object(playback, "plugin_configuration", fake_configuration), \
                patch.object(playback, "set_plugin_configuration", fake_set), \
                patch.object(playback, "refresh_auth", lambda: "fresh-token"), \
                patch.object(playback, "pkg") as fake_pkg, \
                patch.object(playback, "trust_play", lambda *a: {"ffprobe": {}}), \
                patch.object(playback, "play_once", failing_play):
            fake_pkg.restart.return_value = ""
            with self.assertRaises(playback.RowEvidenceError) as raised:
                playback.journey_d03("old-auth", self._row(), Path(tempfile.gettempdir()))
        # The switch was really applied, the window failed, and the original value came back.
        self.assertIs(state["PlaybackAutoCheck"], True)
        # The row keeps its reached stages and restore record; it is never reported as PASS.
        self.assertNotEqual(raised.exception.result.get("status"), "PASS")
        self.assertEqual(raised.exception.result["restore"]["status"], "restored")
        self.assertIn("native-play: the playback window failed", str(raised.exception))

    def test_a_restore_that_cannot_be_verified_stops_the_row_instead_of_passing(self):
        from unittest.mock import patch
        state = {"PlaybackAutoCheck": True}
        calls: list[dict] = []

        def fake_configuration(auth):
            return dict(state)

        def fake_set(auth, changes):
            calls.append(dict(changes))
            # The first (disabling) change really applies; every restore attempt is rejected, so the
            # switch stays changed on the server.
            if len(calls) == 1:
                state.update(changes)
                return 204
            return 500

        with patch.object(playback, "plugin_configuration", fake_configuration), \
                patch.object(playback, "set_plugin_configuration", fake_set), \
                patch.object(playback, "refresh_auth", lambda: "fresh-token"), \
                patch.object(playback, "pkg") as fake_pkg, \
                patch.object(playback, "trust_play", lambda *a: {"ffprobe": {}}):
            fake_pkg.restart.return_value = ""
            with self.assertRaises(playback.ConfigurationRestoreError) as raised:
                playback.journey_d03("old-auth", self._row(), Path(tempfile.gettempdir()))
        self.assertIn("could not be restored", str(raised.exception))
        self.assertIn("MP4.D03", str(raised.exception))
        self.assertEqual(raised.exception.result["restore"]["status"], "FAILED")
        # The change really was applied before the failure, so the row must not claim a clean state.
        self.assertIs(state["PlaybackAutoCheck"], False)

    def test_the_restore_records_every_attempt_and_refuses_an_unverified_read_back(self):
        from unittest.mock import patch
        statuses: list[int] = []

        def fake_set(auth, changes):
            statuses.append(204)
            return 204

        with patch.object(playback, "plugin_configuration", lambda auth: {"PlaybackAutoCheck": True}), \
                patch.object(playback, "set_plugin_configuration", fake_set), \
                patch.object(playback, "refresh_auth", lambda: "fresh-token"):
            restored = playback.restore_plugin_configuration({"PlaybackAutoCheck": False})
        self.assertEqual(restored["status"], "FAILED")
        self.assertEqual(len(restored["attempts"]), 2)
        self.assertEqual(statuses, [204, 204])

    def _matrix_loop(self) -> str:
        source = (ROOT / "scripts" / "run_isolated_playback_integration.py").read_text(encoding="utf-8")
        start = source.index("    for row in rows:\n        # Every row starts from live credentials")
        end = source.index("    failed = [row_id for row_id, result in results.items()", start)
        return source[start:end]

    def test_the_failure_path_reauthenticates_before_the_next_row_reads(self):
        loop = self._matrix_loop()
        # A fresh login precedes every row and follows a failed row, so the revoked token is never
        # reused for the next row's first native read.
        self.assertLess(loop.index("auth = refresh_auth()"), loop.index("try:"))
        failure_handler = loop[loop.index("except (BaselineError"):]
        self.assertIn("auth = refresh_auth()", failure_handler)

    def test_a_changed_switch_cannot_silently_host_the_next_delegation_row(self):
        loop = self._matrix_loop()
        self.assertIn('precondition.get("PlaybackAutoCheck") is True', loop)
        self.assertIn('precondition.get("Enabled") is True', loop)
        self.assertIn('if row["journey"] not in ("d02", "d03")', loop)
        # A row whose configuration could not be restored aborts the batch; it is never reported as
        # PASS and later rows are not run against the changed server.
        self.assertIn("ConfigurationRestoreError", loop)
        self.assertIn("configurationRestored", loop)
        self.assertIn("abortedAfter", loop)

class RawScanDiagnosticTests(unittest.TestCase):
    ITEM_ID = "8" * 8 + "-1111-2222-3333-" + "a" * 12

    def _item(self, path, name="Matrix MP4 C02"):
        return {"Id": self.ITEM_ID, "Name": name, "Type": "Movie", "Path": path}

    def test_a_scan_failure_keeps_the_raw_query_attempts_and_log_tail(self):
        original = playback.pe.request_json
        original_lines = playback.server_log_lines
        playback.pe.request_json = lambda *args, **kwargs: (200, {"TotalRecordCount": 0, "Items": []})
        playback.server_log_lines = lambda: ["native log line 1", "native log line 2"]
        original_max = playback.MAX_WAIT
        playback.MAX_WAIT = 0
        try:
            with self.assertRaises(playback.BaselineError) as caught:
                playback.raw_item_query("auth", "Matrix MP4 P02 01")
        finally:
            playback.pe.request_json = original
            playback.server_log_lines = original_lines
            playback.MAX_WAIT = original_max
        message = str(caught.exception)
        self.assertIn("raw query attempts", message)
        self.assertIn("server log tail", message)
        self.assertIn("native log line", message)
        # The row is addressed by its STRM path, not the item name.
        self.assertIn("/media/strm/Matrix MP4 P02 01.strm", message)

    def test_a_found_item_is_matched_by_its_strm_path_not_its_name(self):
        # The native naming stripped the row suffix word ("... limited" became "... C02"); the
        # lookup must still resolve the row through its unique STRM path.
        item = self._item("/media/strm/Matrix MP4 C02 limited.strm", name="Matrix MP4 C02")
        other = self._item("/media/strm/Matrix MP4 P02 01.strm", name="Matrix MP4 P02 01")
        original_request = playback.pe.request_json
        playback.pe.request_json = lambda *args, **kwargs: (
            200, {"TotalRecordCount": 2, "Items": [dict(other), dict(item)]})
        try:
            result = playback.raw_item_query("auth", "Matrix MP4 C02 limited")
        finally:
            playback.pe.request_json = original_request
        self.assertEqual(result["status"], "FOUND")
        self.assertEqual(result["item"], item)

    def test_ordinary_media_is_located_by_its_real_file_path(self):
        from unittest.mock import patch
        path = "/media/local/regular-mp4/Matrix Regular MP4.mp4"
        ordinary = self._item(path, name="Matrix Regular MP4")
        stray_strm = self._item("/media/strm/Matrix Regular MP4.strm", name="Matrix Regular MP4")
        with patch.object(playback.pe, "request_json", return_value=(200, {"Items": [stray_strm, ordinary]})):
            found = playback.raw_item_query("auth", "Matrix Regular MP4", path)
        self.assertEqual(found["item"]["Path"], path)

    def test_the_d04_row_resolves_its_ordinary_file_while_other_rows_resolve_their_strm(self):
        # DR53-4: the ordinary-media control must be addressed by the real regular-media file, and
        # every other row by its versioned STRM. A D04 lookup that fell back to a STRM path (or a
        # STRM row that pointed at the regular-media directory) would not prove native delegation.
        d04 = {"id": "MP4.D04", "fmt": "MP4", "apply_kind": "d04",
               "media": "regular-mp4/Matrix Regular MP4.mp4", "strm_name": "Matrix Regular MP4"}
        self.assertEqual(playback.native_item_path(d04), "/media/local/regular-mp4/Matrix Regular MP4.mp4")
        for kind in ("none", "manifest", "switch", "d05", "d06", "f01", "f02"):
            row = {"id": f"MP4.{kind}", "fmt": "MP4", "apply_kind": kind,
                   "media": "baseline-mp4-a.mp4", "strm_name": "Matrix MP4 A"}
            self.assertIsNone(playback.native_item_path(row), kind)
        # The D04 lookup really refuses the stray same-name STRM item when the real file is absent.
        from unittest.mock import patch
        stray = self._item("/media/strm/Matrix Regular MP4.strm", name="Matrix Regular MP4")
        with patch.object(playback.pe, "request_json", return_value=(200, {"Items": [stray]})), \
                patch.object(playback, "MAX_WAIT", 0), \
                patch.object(playback, "server_log_lines", lambda: []):
            with self.assertRaises(playback.BaselineError) as caught:
                playback.raw_item_query("auth", "Matrix Regular MP4", playback.native_item_path(d04))
        self.assertIn("/media/local/regular-mp4/Matrix Regular MP4.mp4", str(caught.exception))

    def test_a_duplicate_strm_path_is_refused_with_the_raw_evidence(self):
        item = self._item("/media/strm/Matrix MP4 C02 limited.strm", name="Matrix MP4 C02")
        original_request = playback.pe.request_json
        playback.pe.request_json = lambda *args, **kwargs: (
            200, {"TotalRecordCount": 2, "Items": [dict(item), dict(item)]})
        try:
            with self.assertRaises(playback.BaselineError) as caught:
                playback.raw_item_query("auth", "Matrix MP4 C02 limited")
        finally:
            playback.pe.request_json = original_request
        self.assertIn("refusing to guess", str(caught.exception))
class FailureObservationTests(unittest.TestCase):
    def test_native_500_preserves_read_only_state_before_rejecting_the_playback(self):
        from contextlib import ExitStack
        from unittest.mock import patch
        row = {"id": "MP4.P02.01", "name": "Matrix MP4 P02 01", "media_type": "video",
               "item": {"Id": ITEM_ID}, "sourceKey": SOURCE_ID, "url": URL}
        driver = {"strict": True, "results": [{"advanced": False, "playbackInfo": [{"status": 500}]}]}
        patches = [(playback, "credentials", lambda: {"base_url": "http://127.0.0.1:1", "username": "test", "password": "test"}),
                   (playback, "probe_count", lambda url: 2),
                   (playback, "plugin_event_lines", lambda: []),
                   (playback, "plugin_event_delta", lambda before: []),
                   (playback, "media_server_requests", lambda: {}),
                   (playback.pkg, "run_browser_driver", lambda *a, **kw: driver),
                   (playback.pkg, "unexpected_console_errors", lambda result: [{"text": "native500"}]),
                   (playback.pkg, "api_auth", lambda: "private-test-token"),
                   (playback, "fingerprint_row_for_item", lambda *a: fingerprint()),
                   (playback, "native_source_snapshot", lambda *a: {"sources": []}),
                   (playback.time, "sleep", lambda seconds: None)]
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            for owner, name, replacement in patches:
                stack.enter_context(patch.object(owner, name, replacement))
            with self.assertRaises(playback.BaselineError):
                playback.play_once("old-auth", row, "window", Path(tmp))
            # Console-free capture returns the same redacted observation; the return value must
            # not carry credentials that a successful matrix journey would serialize later.
            stack.enter_context(patch.object(playback.pkg, "unexpected_console_errors", lambda result: []))
            returned = playback.play_once("old-auth", row, "capture", Path(tmp))
            self.assertNotIn("auth", returned)
            self.assertNotIn("private-test-token", json.dumps(returned))
            result = (Path(tmp) / row["id"] / "window" / "observation.json").read_text()
            saved = json.loads(result)
            self.assertEqual(saved["fingerprint"], fingerprint())
            self.assertEqual(saved["playback"]["playbackInfo"][0]["status"], 500)
            self.assertNotIn("auth", saved)
            self.assertNotIn("private-test-token", result)

    def test_the_journey_verifies_the_prepared_precondition_instead_of_repeating_the_surgery(self):
        """The bounded removal runs once in preparation; repeating it would delete missing rows."""
        source = (ROOT / "scripts" / "run_isolated_playback_integration.py").read_text(encoding="utf-8")
        journey = source[source.index("def journey_p01("):source.index("def journey_f01(")]
        self.assertNotIn('p01_stream_surgery([row], drop_spec, evidence_dir, "pre")', journey)
        self.assertIn("p01_precondition(auth, row)", journey)
        # The "with fingerprint" rows still remove the streams a second time, after the real prime.
        self.assertIn('p01_stream_surgery([row], drop_spec, evidence_dir, "prime-after")', journey)
        prepare = source[source.index("def prepare_matrix_rows("):source.index("def scenario_matrix(")]
        self.assertIn('p01_stream_surgery(p01_rows, drop_spec, evidence_dir, "pre")', prepare)

    def test_the_precondition_requires_no_video_and_keeps_audio_only_for_video_drops(self):
        from unittest.mock import patch
        row = {"id": "MP4.P01.03", "item": {"Id": ITEM_ID}, "apply": {"drop": "video", "prime": False}}
        with patch.object(playback, "saved_stream_types", lambda auth, item: ["Audio"]):
            result = playback.p01_precondition("auth", row)
        self.assertEqual(result["savedStreams"], ["Audio"])
        with patch.object(playback, "saved_stream_types", lambda auth, item: ["Audio", "Video"]):
            with self.assertRaises(playback.BaselineError):
                playback.p01_precondition("auth", row)
        dropped_all = {"id": "MP4.P01.01", "item": {"Id": ITEM_ID}, "apply": {"drop": "all", "prime": False}}
        with patch.object(playback, "saved_stream_types", lambda auth, item: ["Audio"]):
            with self.assertRaises(playback.BaselineError):
                playback.p01_precondition("auth", dropped_all)


class P01NativeDatabaseTests(unittest.TestCase):
    """The P01 surgery must adapt to the pinned native schema, not to an assumed one."""

    def _database(self, directory, *, name="jellyfin.db", item_id="00269FE5-4AF7-30BB-4084-A1725F020FD0",
                  stream_type="INTEGER", path_column="ItemId", type_column="StreamType",
                  raw_item_id=None):
        connection = playback.sqlite3.connect(Path(directory) / name)
        connection.execute(
            f'CREATE TABLE "MediaStreamInfos" ("{path_column}" {stream_type.replace("INTEGER", "TEXT")}, '
            f'"StreamIndex" INTEGER, "Codec" TEXT, "{type_column}" {stream_type})')
        stored = raw_item_id if raw_item_id is not None else item_id
        connection.execute(f'INSERT INTO "MediaStreamInfos" VALUES (?, ?, ?, ?)', [stored, 0, "h264", 1])
        connection.execute(f'INSERT INTO "MediaStreamInfos" VALUES (?, ?, ?, ?)', [stored, 1, "aac", 0])
        connection.commit()
        connection.close()

    def test_the_real_database_file_name_is_discovered_rather_than_assumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "config" / "data"
            data.mkdir(parents=True)
            self._database(data)
            self.assertEqual(playback.native_database_path(Path(tmp) / "config"), data / "jellyfin.db")
            (data / "db.sqlite3").write_bytes(b"")
            with self.assertRaises(playback.BaselineError):
                playback.native_database_path(Path(tmp) / "config")
            (data / "db.sqlite3").unlink()

    def test_a_missing_native_database_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "config" / "data").mkdir(parents=True)
            with self.assertRaises(playback.BaselineError) as raised:
                playback.native_database_path(Path(tmp) / "config")
            self.assertIn("jellyfin.db", str(raised.exception))

    def test_the_pinned_text_item_id_and_integer_stream_type_are_understood(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._database(tmp)
            connection = playback.sqlite3.connect(Path(tmp) / "jellyfin.db")
            table = playback.native_stream_table(connection)
            connection.close()
            self.assertEqual(table["table"], "MediaStreamInfos")
            self.assertEqual((table["itemColumn"], table["typeColumn"]), ("ItemId", "StreamType"))
            self.assertEqual(playback.native_item_identity("00269FE5-4AF7-30BB-4084-A1725F020FD0"),
                             "00269fe54af730bb4084a1725f020fd0")
            # An integer column must be written with integers; a string would silently match nothing.
            self.assertEqual(playback.native_stream_type_values("INTEGER", [0, 1], ["Video"]), [1])
            self.assertEqual(playback.native_stream_type_values("INTEGER", [0, 1], ["Video", "Audio"]), [1, 0])
            self.assertEqual(playback.native_stream_type_values("TEXT", ["Video"], ["Video"]), ["Video"])

    def test_a_raw_binary_guid_item_id_is_byte_swapped_exactly(self):
        guid = uuid.UUID("00269FE5-4AF7-30BB-4084-A1725F020FD0")
        self.assertEqual(playback.native_item_identity(guid.bytes_le), guid.hex)
        # A stored TEXT value is already the GUID's string form (the pinned layout); only raw bytes
        # use the mixed-endian layout, so a hex string is never re-swapped.
        self.assertEqual(playback.native_item_identity(guid.hex.upper()), guid.hex)
        self.assertEqual(playback.native_item_identity(str(guid)), guid.hex)

    def test_an_ambiguous_or_absent_stream_table_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jellyfin.db"
            connection = playback.sqlite3.connect(path)
            self.assertRaises(playback.BaselineError, playback.native_stream_table, connection)
            connection.execute('CREATE TABLE "AttachmentStreamInfos" ("ItemId" TEXT, "Codec" TEXT)')
            connection.commit()
            self.assertRaises(playback.BaselineError, playback.native_stream_table, connection)
            connection.close()

    def test_a_non_guid_stored_item_id_is_refused_instead_of_matched_loosely(self):
        with self.assertRaises(playback.BaselineError):
            playback.native_item_identity("not-an-item-id")
        with self.assertRaises(playback.BaselineError):
            playback.native_item_identity(b"\x00" * 8)


class ParsedTokenTests(unittest.TestCase):
    def test_a_valid_sha1_and_size_parse_to_the_stored_values(self):
        self.assertEqual(playback.parsed_tokens("A" * 40, "4096"), ("a" * 40, 4096))
    def test_missing_tokens_store_nulls(self):
        self.assertEqual(playback.parsed_tokens(None, None), (None, None))
    def test_a_short_or_non_hex_sha1_is_not_a_valid_content_hash(self):
        self.assertEqual(playback.parsed_tokens("a" * 39, "4096"), (None, 4096))
        self.assertEqual(playback.parsed_tokens("a" * 39 + "z", "4096"), (None, 4096))
    def test_negative_non_numeric_and_overflowing_sizes_parse_to_null(self):
        self.assertEqual(playback.parsed_tokens(None, "-1"), (None, None))
        self.assertEqual(playback.parsed_tokens(None, "not-a-size"), (None, None))
        self.assertEqual(playback.parsed_tokens(None, "9223372036854775808"), (None, None))
    def test_a_legal_zero_size_stays_zero(self):
        self.assertEqual(playback.parsed_tokens(None, "0"), (None, 0))
class FingerprintNullFieldTests(unittest.TestCase):
    def test_a_null_sha1_or_size_expectation_requires_the_field_to_be_empty(self):
        self.assertEqual(playback.fingerprint_fields_match(fingerprint(sha1=None, file_size=None),
                                                           expected_url=URL, sha1=None, size=None), [])
        self.assertNotEqual(playback.fingerprint_fields_match(fingerprint(sha1=SHA1),
                                                              expected_url=URL, sha1=None, size=SIZE), [])
        self.assertNotEqual(playback.fingerprint_fields_match(fingerprint(file_size=0),
                                                              expected_url=URL, sha1=SHA1, size=None), [])
class MeasurementDeltaTests(unittest.TestCase):
    def test_a_probe_row_accepts_exactly_one_probe_in_the_window(self):
        self.assertEqual(playback.measurement_failures(phase="r", probes_before=1, probes_after=2,
                                                       counter_validated=True, expected_delta=1), [])
        self.assertTrue(playback.measurement_failures(phase="r", probes_before=1, probes_after=1,
                                                      counter_validated=True, expected_delta=1))
        self.assertTrue(playback.measurement_failures(phase="r", probes_before=1, probes_after=3,
                                                      counter_validated=True, expected_delta=1))
    def test_a_record_only_window_reports_no_measurement_failure(self):
        self.assertEqual(playback.measurement_failures(phase="r", probes_before=0, probes_after=4,
                                                       counter_validated=True, expected_delta=None), [])
class PaddingTests(unittest.TestCase):
    def test_the_mp4_partner_grows_exactly_to_the_target_with_a_free_atom(self):
        # A minimal MP4 document: the padding is a trailing free atom, so the original bytes (and
        # therefore the moov/mdat chunk offsets) stay in place and the atom is simply skipped.
        document = bytes([0, 0, 0, 16]) + b"ftypisom" + bytes([0, 0, 2, 0]) + b"mdat" + b"\x00" * 100
        result = playback.pad_mp4_to(document, 500)
        self.assertEqual(len(result), 500)
        self.assertEqual(result[:len(document)], document)  # the original bytes stay intact
        free_size = 500 - len(document)
        self.assertEqual(int.from_bytes(result[len(document):len(document) + 4], "big"), free_size)
        self.assertEqual(result[len(document) + 4:len(document) + 8], b"free")
        self.assertEqual(result[len(document) + 8:], b"\x00" * (free_size - 8))
    def test_the_mkv_partner_grows_exactly_to_the_target_with_an_empty_element(self):
        # A minimal legal EBML document; the padding is a trailing Empty Element (id 0x1549 with
        # the unknown-size marker 0xFF, which matroska readers skip to end of file).
        document = b"\x1a\x45\xdf\xa3" + bytes([0x84]) + b"\x80\x42\x82\x08" + b"\x15\x4a" + b"\x00" * 200
        for target in (len(document) + 7, len(document) + 300, len(document) + 400_000):
            result = playback.pad_mkv_to(document, target)
            self.assertEqual(len(result), target)
            self.assertEqual(result[:len(document)], document)  # the original bytes stay intact
            self.assertEqual(result[len(document):len(document) + 3], b"\x15\x49\xff")

    def test_padding_refuses_to_shrink_or_misidentify_documents(self):
        with self.assertRaises(playback.BaselineError):
            playback.pad_mkv_to(b"\x1a\x45\xdf\xa3" + bytes([0x84]) + b"\x80", 4)
        with self.assertRaises(playback.BaselineError):
            playback.pad_mp4_to(b"\x00" * 64, 128)
class DriverContractTests(unittest.TestCase):
    def test_the_strict_driver_records_raw_responses_and_failure_screenshots(self):
        driver = (ROOT / "scripts" / "package_playback_driver.mjs").read_text(encoding="utf-8")
        self.assertIn("rawBodyFile", driver)
        self.assertIn("requestErrorScreenshot", driver)
        self.assertIn("incompleteScreenshot", driver)
        legacy_start = driver.index("let observed = null;")
        legacy_block = driver[legacy_start:driver.index("const strict = strictSettings(cfg);", legacy_start)]
        self.assertNotIn("rawBodyFile", legacy_block)
        self.assertNotIn("requestErrorShot", legacy_block)

if __name__ == "__main__":
    unittest.main()
