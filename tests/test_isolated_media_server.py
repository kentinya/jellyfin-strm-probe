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


if __name__ == "__main__":
    unittest.main()
