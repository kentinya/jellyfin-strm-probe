#!/usr/bin/env python3
"""Check the Jellyfin catalog against the accepted, already published v0.1.0 ZIP.

This is a delivery check, not a builder or installer. It never contacts a Jellyfin
instance. The native catalog's MD5 is checked alongside our accepted SHA-256 and
the existing archive validator; the Release ZIP remains unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import package_plugin as package

ROOT = Path(__file__).resolve().parents[1]
APPROVED_SHA256 = "9641fe917cc8db8d36ec32c841fb968b0149890f39094adce5338a0f28dd9e37"
APPROVED_SOURCE = "3a7de052bf089141f76e2f60921de285bd5184c4"
RELEASE_URL = (
    "https://github.com/kentinya/jellyfin-strm-probe/releases/download/v0.1.0/"
    "Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip"
)


def check(manifest: Path, archive: Path) -> dict:
    catalog = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(catalog, list) or len(catalog) != 1:
        raise ValueError("The first-release catalog must contain exactly one plugin.")
    plugin = catalog[0]
    identity = package.verify_archive(archive, expected_sha256=APPROVED_SHA256)
    with zipfile.ZipFile(archive) as bundle:
        meta = json.loads(bundle.read(identity["folder"] + "/meta.json"))
    for field in ("guid", "name", "category"):
        if plugin.get(field) != meta[field]:
            raise ValueError(f"Catalog {field} differs from the accepted plugin identity.")
    versions = plugin.get("versions")
    if not isinstance(versions, list) or len(versions) != 1:
        raise ValueError("Only the accepted first release is approved for this catalog.")
    version = versions[0]
    for field in ("version", "targetAbi"):
        if version.get(field) != meta[field]:
            raise ValueError(f"Catalog {field} differs from the accepted package.")
    if version.get("sourceUrl") != RELEASE_URL:
        raise ValueError("Catalog download must use the approved, versioned Release asset.")
    data = archive.read_bytes()
    # Jellyfin 12.2's InstallationManager consumes MD5, not the SHA-256 sidecar.
    if version.get("checksum") != hashlib.md5(data, usedforsecurity=False).hexdigest():
        raise ValueError("Catalog MD5 does not match the downloaded Release ZIP.")
    return {
        "status": "PASS",
        "guid": identity["guid"],
        "version": identity["version"],
        "targetAbi": identity["targetAbi"],
        "archiveSha256": APPROVED_SHA256,
        "sourceRevision": APPROVED_SOURCE,
        "nativeChecksum": version["checksum"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "manifest.json")
    parser.add_argument("--package", type=Path, help="Use an already downloaded Release ZIP.")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="strm-plugin-repository-") as directory:
        archive = args.package
        if archive is None:
            archive = Path(directory) / "release.zip"
            with urllib.request.urlopen(RELEASE_URL, timeout=60) as response:
                archive.write_bytes(response.read())
        print(json.dumps(check(args.manifest, archive), indent=2))


if __name__ == "__main__":
    main()
