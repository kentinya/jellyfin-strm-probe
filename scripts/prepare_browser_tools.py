#!/usr/bin/env python3
"""Prepare the pinned headless-browser toolchain used by the configuration-page integration.

The toolchain is a test-only dependency: it is installed under the git-ignored
``artifacts/dev-env/browser-tools`` directory and is never added to the plugin or its production packages. This
script is idempotent and only touches that directory. It never operates on a production server or media library.

Steps:
  1. install the pinned ``playwright`` npm package into ``artifacts/dev-env/browser-tools/node``;
  2. download the pinned Chromium build;
  3. print the system library packages that headless Chromium needs on Debian/Ubuntu (installed separately because
     they require root).

Run it, then ``python3 scripts/run_isolated_configuration_integration.py``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BROWSER_TOOLS = ROOT / "artifacts" / "dev-env" / "browser-tools"
NODE_DIRECTORY = BROWSER_TOOLS / "node"
PLAYWRIGHT_PACKAGE = "playwright@1.55.0"
CHROMIUM_REVISION = "chromium-1187"

SYSTEM_PACKAGES = [
    "libnss3",
    "libatk1.0-0",
    "libatk-bridge2.0-0",
    "libcups2",
    "libxkbcommon0",
    "libatspi2.0-0",
    "libxcomposite1",
    "libxdamage1",
    "libxfixes3",
    "libxrandr2",
    "libgbm1",
    "libcairo2",
    "libpango-1.0-0",
    "libasound2",
]


def run(command: list[str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def ensure_node_project() -> None:
    NODE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    package = NODE_DIRECTORY / "package.json"
    if not package.is_file():
        (NODE_DIRECTORY / "package.json").write_text(
            json.dumps(
                {
                    "name": "strm-probe-browser-tools",
                    "private": True,
                    "description": "Test-only headless browser toolchain for the configuration-page integration.",
                    "dependencies": {"playwright": PLAYWRIGHT_PACKAGE.split("@", 1)[1]},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-system-packages", action="store_true", help="Only print the required system packages and exit.")
    args = parser.parse_args()

    if args.print_system_packages:
        print("sudo apt-get install -y --no-install-recommends " + " ".join(SYSTEM_PACKAGES))
        return 0

    node = shutil.which("node")
    npm = shutil.which("npm")
    if node is None or npm is None:
        print("BLOCKED: Node.js and npm are required to prepare the browser toolchain.", file=sys.stderr)
        return 2

    ensure_node_project()

    install = run(["npm", "install", "--no-save", PLAYWRIGHT_PACKAGE], NODE_DIRECTORY)
    if install.returncode != 0:
        print("BLOCKED: npm install failed:\n" + install.stderr.strip(), file=sys.stderr)
        return 2

    browsers = run(["npx", "playwright", "install", "chromium"], NODE_DIRECTORY)
    if browsers.returncode != 0:
        print("BLOCKED: playwright install failed:\n" + browsers.stderr.strip(), file=sys.stderr)
        return 2

    installed = json.loads((NODE_DIRECTORY / "node_modules" / "playwright" / "package.json").read_text(encoding="utf-8"))
    print(json.dumps({
        "status": "PASS",
        "node": node,
        "playwright": installed.get("version"),
        "chromium_revision": CHROMIUM_REVISION,
        "toolchain_directory": str(NODE_DIRECTORY),
        "system_packages_if_missing": SYSTEM_PACKAGES,
        "next": "python3 scripts/run_isolated_configuration_integration.py",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        raise SystemExit(2)
