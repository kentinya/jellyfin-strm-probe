#!/usr/bin/env python3
"""Serve synthetic media for the repository's isolated Jellyfin environment."""

from __future__ import annotations

import argparse
import signal
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class IsolatedMediaServer(ThreadingHTTPServer):
    # Do not let an in-flight synthetic media request hold PID 1 past Compose's graceful stop window.
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True


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

    server = IsolatedMediaServer(("0.0.0.0", args.port), handler)

    def stop_server(signum: int, _frame: object) -> None:
        # ``shutdown`` must run off the signal-handler thread because serve_forever owns
        # the loop that it wakes; the following server_close does not wait for requests.
        threading.Thread(target=server.shutdown, name="media-server-shutdown", daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)
    server.serve_forever()
    server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
