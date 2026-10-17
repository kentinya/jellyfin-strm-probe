#!/usr/bin/env python3
"""Serve synthetic media for the repository's isolated Jellyfin environment."""

from __future__ import annotations

import argparse
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class MediaHandler(SimpleHTTPRequestHandler):
    def _prepare_route(self) -> None:
        parsed = urlsplit(self.path)
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) == 3 and path_parts[0] == "slow":
            request_id, filename = path_parts[1:]
            print(f"SLOW_MEDIA_REQUEST_STARTED {request_id}", flush=True)
            time.sleep(3)
            self.path = "/" + filename
            print(f"MEDIA_REQUEST {self.command} " + filename, flush=True)
            print(f"PROBE_MEDIA_REQUEST_FINISHED {request_id}", flush=True)
            return

        # A parameterized delay route lets a scenario hold a probe open for a deterministic settlement window
        # without changing the fixed slow route the existing playback checks rely on.
        if len(path_parts) == 4 and path_parts[0] == "delay":
            try:
                seconds = min(float(path_parts[1]), 30.0)
            except ValueError:
                seconds = 3.0
            request_id, filename = path_parts[2:]
            print(f"SLOW_MEDIA_REQUEST_STARTED {request_id}", flush=True)
            time.sleep(seconds)
            self.path = "/" + filename
            print(f"MEDIA_REQUEST {self.command} " + filename, flush=True)
            print(f"PROBE_MEDIA_REQUEST_FINISHED {request_id}", flush=True)
            return

        if len(path_parts) == 3 and path_parts[0] == "independent":
            request_id, filename = path_parts[1:]
            print(f"INDEPENDENT_MEDIA_REQUEST_STARTED {request_id}", flush=True)
            time.sleep(3)
            self.path = "/" + filename
            print(f"MEDIA_REQUEST {self.command} " + filename, flush=True)
            return

        filename = path_parts[-1] if path_parts else "index"
        self.path = parsed.path
        print(f"MEDIA_REQUEST {self.command} " + filename, flush=True)

    def do_GET(self) -> None:
        self._prepare_route()
        super().do_GET()

    def do_HEAD(self) -> None:
        self._prepare_route()
        super().do_HEAD()

    def log_message(self, format: str, *args: object) -> None:
        # Request paths can contain private signed URLs; emit only the safe counters above.
        return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    def handler(*handler_args: object, **handler_kwargs: object) -> MediaHandler:
        return MediaHandler(*handler_args, directory=args.directory, **handler_kwargs)

    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
