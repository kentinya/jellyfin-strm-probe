"""Guardrails for the isolated plugin journey tooling; these are not real Jellyfin acceptance tests.

They cover the entry defects that blocked the Task 5.3 full journey:

* the ordinary-media control must be located by its real regular-media file path, because
  Jellyfin's metadata providers own the display name and renamed ``fixture`` to
  ``Substitute Fixture``;
* a rejected native PlaybackInfo must keep the server's own error body instead of replacing it
  with an empty object, without ever retaining the request URL or credentials;
* the rejection's real status and body are written to the ignored evidence file while the
  response is still readable, so a later failure hands over its own reason from the raw output
  instead of an empty object, and a later success never carries an older rejection forward.

They do not claim any real Jellyfin result.
"""

from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_isolated_plugin_integration", ROOT / "scripts" / "run_isolated_plugin_integration.py"
)
plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin)


class _Api:
    """A minimal stand-in that exercises the real lookup and request code paths."""

    def __init__(self, items=None, error=None, responses=None):
        self.base_url = "http://127.0.0.1:1"
        self.headers = {"Authorization": "private-test-token"}
        self.user_id = "user"
        self.items = items or []
        self.error = error
        self.responses = list(responses or [])
        self.last_error_body = ""

    def request_response(self, path: str, *, method: str = "GET", data: bytes | None = None) -> tuple[int, bytes]:
        return (self.responses.pop(0) if self.responses else (200, b"{}"))

    def _listing(self):
        return {"Items": self.items}

    def library_item_by_path(self, path, fields="MediaSources,MediaStreams,Path"):
        return plugin.JellyfinApi.library_item_by_path(self, path, fields)

    def playback_info(self, item_id, timeout=75):
        return plugin.JellyfinApi.playback_info(self, item_id, timeout)


class OrdinaryMediaLocationTests(unittest.TestCase):
    def test_the_ordinary_control_is_located_by_its_real_file_path(self):
        renamed = {"Id": "a" * 32, "Name": "Substitute Fixture", "Path": plugin.ORDINARY_MEDIA_PATH}
        other = {"Id": "b" * 32, "Name": "fixture", "Path": "/media/strm/fixture.strm"}
        api = _Api(items=[other, renamed])
        with patch.object(plugin, "request_json", return_value=api._listing()):
            item = plugin.JellyfinApi.library_item_by_path(api, plugin.ORDINARY_MEDIA_PATH)
        self.assertEqual(item["Id"], renamed["Id"])
        self.assertNotEqual(item["Name"], "fixture")

    def test_a_same_named_strm_entry_cannot_substitute_for_the_ordinary_file(self):
        strm = {"Id": "b" * 32, "Name": "fixture", "Path": "/media/strm/fixture.strm"}
        api = _Api(items=[strm])
        with patch.object(plugin, "request_json", return_value=api._listing()):
            with self.assertRaises(RuntimeError) as raised:
                plugin.JellyfinApi.library_item_by_path(api, plugin.ORDINARY_MEDIA_PATH)
        self.assertIn("real path", str(raised.exception))

    def test_a_duplicate_definition_of_the_same_path_is_refused(self):
        first = {"Id": "a" * 32, "Name": "Substitute Fixture", "Path": plugin.ORDINARY_MEDIA_PATH}
        second = {"Id": "c" * 32, "Name": "Other Fixture", "Path": plugin.ORDINARY_MEDIA_PATH}
        api = _Api(items=[first, second])
        with patch.object(plugin, "request_json", return_value=api._listing()):
            with self.assertRaises(RuntimeError):
                plugin.JellyfinApi.library_item_by_path(api, plugin.ORDINARY_MEDIA_PATH)

    def test_the_ordinary_control_still_requires_a_video_source_and_no_plugin_events(self):
        item = {"Id": "a" * 32, "Name": "Substitute Fixture", "Path": plugin.ORDINARY_MEDIA_PATH}
        api = _Api(items=[item])
        delegated = {"http_status": 200, "has_media_source": True, "has_video": True,
                     "source_path_is_local": True, "plugin_events": []}
        with patch.object(plugin, "request_json", return_value=api._listing()), \
                patch.object(plugin, "delegated_playback", return_value=delegated):
            result = plugin.ordinary_media_delegation_check(api, "container")
        self.assertEqual(result["item_path"], plugin.ORDINARY_MEDIA_PATH)
        self.assertTrue(result["display_name_changed"])
        for key, value in (("has_video", False), ("source_path_is_local", False)):
            broken = dict(delegated, **{key: value})
            with patch.object(plugin, "request_json", return_value=api._listing()), \
                    patch.object(plugin, "delegated_playback", return_value=broken):
                with self.assertRaises(RuntimeError):
                    plugin.ordinary_media_delegation_check(api, "container")
        intercepted = dict(delegated, plugin_events=["STRM source reused saved media information"])
        with patch.object(plugin, "request_json", return_value=api._listing()), \
                patch.object(plugin, "delegated_playback", return_value=intercepted):
            with self.assertRaises(RuntimeError):
                plugin.ordinary_media_delegation_check(api, "container")


class PlaybackErrorBodyTests(unittest.TestCase):
    def _native_500(self, body: bytes) -> HTTPError:
        return HTTPError("http://127.0.0.1:1/Items/x/PlaybackInfo?UserId=user", 500,
                         "Internal Server Error", {}, io.BytesIO(body))

    def test_the_native_error_body_is_kept_as_the_failure_reason(self):
        body = b'{"message":"The STRM changed during Jellyfin\'s native probe; playback must retry."}'
        api = _Api()
        api.last_error_body = ""
        with patch.object(plugin, "urlopen", side_effect=self._native_500(body)):
            status, payload = plugin.JellyfinApi.playback_info(api, "a" * 32)
        self.assertEqual(status, 500)
        self.assertEqual(payload["message"],
                         "The STRM changed during Jellyfin's native probe; playback must retry.")
        self.assertIn("playback must retry", api.last_error_body)
        # The retained text is the server's own message, never the request URL or credentials.
        self.assertNotIn("PlaybackInfo", api.last_error_body)
        self.assertNotIn("private-test-token", api.last_error_body)

    def test_a_non_json_error_body_is_still_retained_verbatim(self):
        api = _Api()
        api.last_error_body = ""
        with patch.object(plugin, "urlopen", side_effect=self._native_500(b"plain native failure")):
            status, payload = plugin.JellyfinApi.playback_info(api, "a" * 32)
        self.assertEqual((status, payload), (500, {}))
        self.assertEqual(api.last_error_body, "plain native failure")

    def test_a_successful_request_does_not_populate_an_error_body(self):
        api = _Api()
        response = io.BytesIO(b'{"MediaSources":[]}')
        response.status = 200
        with patch.object(plugin, "urlopen", return_value=response):
            status, payload = plugin.JellyfinApi.playback_info(api, "a" * 32)
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"MediaSources": []})
        self.assertEqual(api.last_error_body, "")

    def test_an_error_without_a_readable_body_keeps_an_empty_reason(self):
        class _Unreadable:
            code = 500

            def read(self) -> bytes:
                raise OSError("no body")

        self.assertEqual(plugin.raw_error_body(_Unreadable()), "")


class NativeErrorEvidenceTests(unittest.TestCase):
    """The rejection evidence must land on disk with the response, not only in memory."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.evidence = Path(self._tmp.name) / "playback-error-evidence.jsonl"
        patcher = patch.object(plugin, "ERROR_EVIDENCE_PATH", self.evidence)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_a_rejected_playback_is_written_to_the_evidence_file(self):
        body = b'{"message":"Jellyfin did not save a usable media source for the current STRM version."}'
        api = _Api()
        with patch.object(plugin, "urlopen", side_effect=PlaybackErrorBodyTests._native_500(api, body)):
            status, payload = plugin.JellyfinApi.playback_info(api, "a" * 32)
        self.assertEqual(status, 500)
        lines = self.evidence.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["request"], "GET PlaybackInfo")
        self.assertEqual(record["item_id"], "a" * 32)
        self.assertEqual(record["http_status"], 500)
        self.assertIn("Jellyfin did not save a usable media source", record["body"])
        # The handover record never contains the request URL or credentials.
        self.assertNotIn("PlaybackInfo?", record["body"])
        self.assertNotIn("private-test-token", json.dumps(record))

    def test_a_stale_error_never_survives_a_later_success(self):
        api = _Api()
        api.last_error_body = "old rejection"
        response = io.BytesIO(b'{"MediaSources":[]}')
        response.status = 200
        with patch.object(plugin, "urlopen", return_value=response):
            status, _ = plugin.JellyfinApi.playback_info(api, "a" * 32)
        self.assertEqual(status, 200)
        self.assertEqual(api.last_error_body, "")
        self.assertFalse(self.evidence.exists())

    def test_a_rejected_merge_version_body_is_also_recorded(self):
        api = _Api(responses=[(500, b"native merge refusal")])
        status = plugin.JellyfinApi.merge_versions(api, ["a" * 32, "b" * 32])
        self.assertEqual(status, 500)
        record = json.loads(self.evidence.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(record["request"], "POST /Videos/MergeVersions")
        self.assertEqual(record["http_status"], 500)
        self.assertEqual(record["body"], "native merge refusal")

    def test_a_successful_merge_does_not_record_any_error(self):
        api = _Api(responses=[(204, b"")])
        status = plugin.JellyfinApi.merge_versions(api, ["a" * 32])
        self.assertEqual(status, 204)
        self.assertFalse(self.evidence.exists())

    def test_the_run_summary_reports_the_recorded_rejections(self):
        self.assertEqual(plugin.native_error_evidence_summary(),
                         {"recorded": 0, "path": str(self.evidence)})
        plugin.record_native_error("GET PlaybackInfo", "a" * 32, 500, "first rejection")
        plugin.record_native_error("GET PlaybackInfo", "b" * 32, 500, "second rejection")
        summary = plugin.native_error_evidence_summary()
        self.assertEqual(summary["recorded"], 2)
        self.assertTrue(summary["path"].endswith("playback-error-evidence.jsonl"))

    def test_a_truncated_or_unreadable_evidence_file_is_reported_as_empty(self):
        plugin.ERROR_EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        plugin.ERROR_EVIDENCE_PATH.write_text("not-a-json-line\n", encoding="utf-8")
        # A malformed line still counts as recorded content; it must not silently vanish.
        self.assertEqual(plugin.native_error_evidence_summary()["recorded"], 1)
        plugin.reset_native_error_evidence()
        self.assertEqual(plugin.native_error_evidence_summary()["recorded"], 0)


if __name__ == "__main__":
    unittest.main()
