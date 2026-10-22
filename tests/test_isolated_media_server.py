"""Guardrails for the synthetic media service used by isolated acceptance runs."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("isolated_media_server", ROOT / "scripts" / "isolated_media_server.py")
assert SPEC is not None and SPEC.loader is not None
media = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(media)


class IsolatedMediaServerTests(unittest.TestCase):
    def test_requests_cannot_block_graceful_compose_stop(self):
        self.assertTrue(media.IsolatedMediaServer.daemon_threads)
        self.assertFalse(media.IsolatedMediaServer.block_on_close)
        self.assertTrue(media.IsolatedMediaServer.allow_reuse_address)




import http.client
import tempfile
import threading


def _start_server(directory):
    def handler(*args, **kwargs):
        return media.MediaHandler(*args, directory=str(directory), **kwargs)

    server = media.IsolatedMediaServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, server.socket.getsockname()[1]


class RangeSupportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)
        self.body = bytes(range(256)) * 4  # 1024 bytes
        (self.directory / "clip.mp4").write_bytes(self.body)
        self.server, self.thread, self.port = _start_server(self.directory)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    def request(self, method, path, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        return response, payload

    def test_a_rangeless_get_keeps_the_legacy_full_file_behaviour(self):
        response, payload = self.request("GET", "/clip.mp4")
        self.assertEqual(response.status, 200)
        self.assertEqual(payload, self.body)

    def test_a_single_byte_range_is_served_with_206_and_content_range(self):
        response, payload = self.request("GET", "/clip.mp4", headers={"Range": "bytes=5-9"})
        self.assertEqual(response.status, 206)
        self.assertEqual(payload, self.body[5:10])
        self.assertEqual(response.getheader("Content-Range"), f"bytes 5-9/{len(self.body)}")
        self.assertEqual(int(response.getheader("Content-Length")), 5)
        self.assertEqual(response.getheader("Accept-Ranges"), "bytes")

    def test_a_head_range_returns_headers_only(self):
        response, payload = self.request("HEAD", "/clip.mp4", headers={"Range": "bytes=0-3"})
        self.assertEqual(response.status, 206)
        self.assertEqual(payload, b"")
        self.assertEqual(int(response.getheader("Content-Length")), 4)
        self.assertEqual(response.getheader("Content-Range"), f"bytes 0-3/{len(self.body)}")

    def test_an_open_ended_range_stops_at_the_real_file_length(self):
        response, payload = self.request("GET", "/clip.mp4", headers={"Range": "bytes=999-"})
        self.assertEqual(response.status, 206)
        self.assertEqual(payload, self.body[999:])
        self.assertEqual(response.getheader("Content-Range"),
                         f"bytes 999-{len(self.body) - 1}/{len(self.body)}")

    def test_an_unsatisfiable_range_is_416_with_the_valid_range(self):
        response, payload = self.request("GET", "/clip.mp4", headers={"Range": "bytes=999999-9999999"})
        self.assertEqual(response.status, 416)
        self.assertEqual(payload, b"")
        self.assertEqual(response.getheader("Content-Range"), f"bytes */{len(self.body)}")

    def test_query_parameter_aliases_keep_serving_the_underlying_file(self):
        response, payload = self.request("GET", "/clip.mp4?alias=1", headers={"Range": "bytes=0-15"})
        self.assertEqual(response.status, 206)
        self.assertEqual(payload, self.body[0:16])

    def test_multi_suffix_and_malformed_ranges_fall_back_to_the_legacy_full_file(self):
        for header in ("bytes=0-4,10-14", "bytes=-4", "bytes=abc"):
            response, payload = self.request("GET", "/clip.mp4", headers={"Range": header})
            self.assertEqual(response.status, 200, header)
            self.assertEqual(payload, self.body, header)

    def test_a_range_for_a_missing_file_is_the_existing_404(self):
        response, _ = self.request("GET", "/absent.mp4", headers={"Range": "bytes=0-3"})
        self.assertEqual(response.status, 404)


    def test_a_special_route_answers_one_whole_file_read_per_request(self):
        """One native probe must produce exactly one request marker, not one per Range read.

        The diagnostic routes (``slow``/``delay``/``independent``) exist to hold a probe open and
        to count real probe reads. When the range path also served them, a single ffprobe emitted
        two ``SLOW_MEDIA_REQUEST_STARTED`` lines and the shared-probe gate misread one probe as two.
        """
        captured: list[str] = []
        for header, expected_status, expected_body in (
            (None, 200, self.body),
            ({"Range": "bytes=5-9"}, 200, self.body),
        ):
            with self.subTest(header=header):
                import contextlib
                import io

                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    response, payload = self.request("GET", "/slow/req-1/clip.mp4", headers=header or {})
                captured.extend(line for line in buffer.getvalue().splitlines() if line)
                self.assertEqual(response.status, expected_status)
                self.assertEqual(payload, expected_body)
        self.assertEqual(sum(line.startswith("SLOW_MEDIA_REQUEST_STARTED ") for line in captured), 2)
        self.assertEqual(sum(line.startswith("PROBE_MEDIA_REQUEST_FINISHED ") for line in captured), 2)
        self.assertEqual([line for line in captured if line.startswith("SLOW_MEDIA_REQUEST_STARTED ")],
                         ["SLOW_MEDIA_REQUEST_STARTED req-1", "SLOW_MEDIA_REQUEST_STARTED req-1"])

    def test_a_delay_route_keeps_its_whole_file_behaviour_for_range_requests(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            response, payload = self.request("GET", "/delay/0/req-2/clip.mp4",
                                             headers={"Range": "bytes=0-15"})
        self.assertEqual(response.status, 200)
        self.assertEqual(payload, self.body)
        self.assertIn("SLOW_MEDIA_REQUEST_STARTED req-2", buffer.getvalue())
        self.assertNotIn("MEDIA_RANGE", buffer.getvalue())

    def test_an_independent_route_keeps_its_whole_file_behaviour_for_range_requests(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            response, payload = self.request("GET", "/independent/req-3/clip.mp4",
                                             headers={"Range": "bytes=0-3"})
        self.assertEqual(response.status, 200)
        self.assertEqual(payload, self.body)
        self.assertIn("INDEPENDENT_MEDIA_REQUEST_STARTED req-3", buffer.getvalue())

    def test_a_plain_file_request_still_serves_a_real_range(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            response, payload = self.request("GET", "/clip.mp4", headers={"Range": "bytes=0-3"})
        self.assertEqual(response.status, 206)
        self.assertEqual(payload, self.body[0:4])
        self.assertIn("MEDIA_RANGE GET /clip.mp4 0-3/", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
