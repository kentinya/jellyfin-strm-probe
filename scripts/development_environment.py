#!/usr/bin/env python3
"""Prepare Task 1.1 tools; never operate on a production Docker endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "artifacts/dev-env"
SPEC = json.loads((ROOT / "dev/environment-spec.json").read_text())
PROJECT = "jf-strm-probe-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:10]
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def run(*args: str, timeout: int = 60, cwd: Path = ROOT) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{args[0]} exit {result.returncode}: {result.stderr.strip()}")
    return result.stdout.strip()


def workspace() -> None:
    for path in (ROOT / "artifacts", WORK):
        if path.is_symlink():
            raise RuntimeError("Environment directory must not be a symlink")
    WORK.mkdir(parents=True, exist_ok=True)
    for name in ("sdk", "downloads", "config", "cache", "media", "strm", "cli", "nuget"):
        path = WORK / name
        if path.is_symlink():
            raise RuntimeError(f"Environment subdirectory is a symlink: {name}")
        path.mkdir(exist_ok=True)


def sdk_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        DOTNET_ROOT=str(WORK / "sdk"),
        DOTNET_CLI_HOME=str(WORK / "cli"),
        DOTNET_CLI_TELEMETRY_OPTOUT="1",
        DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1",
        NUGET_PACKAGES=str(WORK / "nuget"),
    )
    return env


def sdk_version() -> str:
    executable = WORK / "sdk/dotnet"
    if not executable.is_file():
        raise RuntimeError("Pinned local SDK is not installed")
    return subprocess.check_output(
        [str(executable), "--version"], cwd=ROOT, env=sdk_env(), text=True, timeout=30
    ).strip()


def verify_archive(path: Path) -> None:
    digest = hashlib.sha512()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != SPEC["sdk"]["sha512"]:
        raise RuntimeError("SDK archive SHA-512 mismatch; nothing will be extracted")


def install_sdk(archive: Path | None) -> None:
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise RuntimeError("This environment is pinned to Linux x64")
    workspace()
    if (WORK / "sdk/dotnet").exists():
        if sdk_version() != SPEC["sdk"]["version"]:
            raise RuntimeError("Installed local SDK does not match the pin")
        print("PASS: existing pinned SDK")
        return
    if any((WORK / "sdk").iterdir()):
        raise RuntimeError("SDK directory is nonempty; refusing to overwrite it")
    if archive is None:
        archive = WORK / "downloads/sdk.tar.gz"
        partial = WORK / "downloads/sdk.partial"
        print("Downloading the pinned official SDK", flush=True)
        run("curl", "--fail", "--location", "--proto", "=https", "--proto-redir", "=https",
            "--connect-timeout", "15", "--max-time", "600", "--output", str(partial),
            SPEC["sdk"]["url"], timeout=610)
        verify_archive(partial)
        partial.replace(archive)
    else:
        verify_archive(archive)
    # Only the archive with the checked official checksum reaches extraction.
    run("tar", "-xzf", str(archive), "-C", str(WORK / "sdk"), timeout=180)
    if sdk_version() != SPEC["sdk"]["version"]:
        raise RuntimeError("Extracted SDK does not match the pin")
    print("PASS: SDK " + sdk_version())


def image_digest(image: str) -> str:
    data = json.loads(run(*DOCKER, "image", "inspect", image))[0]
    repository = image.split(":")[0]
    matches = [d for d in data.get("RepoDigests", [])
               if d.startswith(repository + "@") and DIGEST.fullmatch(d.split("@", 1)[1])]
    if not matches:
        raise RuntimeError(f"No immutable repository digest available for {image}")
    return sorted(matches)[0]


def provision_images() -> None:
    workspace()
    lock_path = WORK / "images.lock.json"
    if lock_path.exists():
        load_lock()
        print("PASS: existing immutable image lock; refusing to re-resolve tags")
        return
    run(*DOCKER, "info", "--format", "{{.ServerVersion}}")
    images = {}
    for name, tag in (("server", SPEC["server"]["image"]), ("media", SPEC["media_image"])):
        print("Pulling " + tag, flush=True)
        run(*DOCKER, "pull", "--platform", "linux/amd64", tag, timeout=600)
        images[name] = image_digest(tag)
    lock_path.write_text(json.dumps({"spec": SPEC, "images": images}, indent=2) + "\n")
    print("PASS: image digests recorded in artifacts/dev-env/images.lock.json")


def load_lock() -> dict[str, str]:
    data = json.loads((WORK / "images.lock.json").read_text())
    if data["spec"] != SPEC:
        raise RuntimeError("Image lock belongs to a different environment specification")
    images = data["images"]
    for name, repository in (("server", "jellyfin/jellyfin"), ("media", "python")):
        value = images.get(name, "")
        prefix = repository + "@"
        if not value.startswith(prefix) or not DIGEST.fullmatch(value[len(prefix):]):
            raise RuntimeError("Invalid immutable image lock")
    return images


def compose_args() -> tuple[list[str], dict[str, str]]:
    images = load_lock()
    env = os.environ.copy()
    env.update(JF_PROBE_SERVER_IMAGE=images["server"], JF_PROBE_MEDIA_IMAGE=images["media"],
               JF_PROBE_WORK=str(WORK), JF_PROBE_UID=str(os.getuid()), JF_PROBE_GID=str(os.getgid()))
    return [*DOCKER, "compose", "--project-name", PROJECT,
            "--file", str(ROOT / "dev/compose.yaml")], env


def guard_containers() -> None:
    ids = run(*DOCKER, "ps", "-aq", "--filter", "label=com.docker.compose.project=" + PROJECT)
    if not ids:
        return
    for container in json.loads(run(*DOCKER, "inspect", *ids.splitlines())):
        mounts = container["Mounts"]
        if not mounts or any(m["Type"] != "bind" or
                             not Path(m["Source"]).resolve().is_relative_to(WORK.resolve())
                             for m in mounts):
            raise RuntimeError("Existing project container has foreign mounts; refusing to change it")


def compose(action: str) -> None:
    workspace()
    run(*DOCKER, "info", "--format", "{{.ServerVersion}}")
    args, env = compose_args()
    guard_containers()
    if action == "up":
        if sdk_version() != SPEC["sdk"]["version"]:
            raise RuntimeError("Pinned SDK is required before starting")
        tail = ["up", "-d", "--pull", "never"]
    elif action == "stop":
        tail = ["stop", "--timeout", "20"]
    else:
        tail = ["ps"]
    subprocess.run([*args, *tail], cwd=ROOT, env=env, check=True, timeout=60)


def doctor() -> int:
    checks = []
    def check(name, operation):
        try:
            detail = operation()
            checks.append({"check": name, "result": "PASS", "detail": str(detail or "available")})
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            checks.append({"check": name, "result": "BLOCKED", "detail": str(error)})

    def listener():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))

    def https():
        with urllib.request.urlopen("https://api.nuget.org/v3/index.json", timeout=15) as response:
            return response.status

    def pinned_sdk():
        version = sdk_version()
        if version != SPEC["sdk"]["version"]:
            raise RuntimeError("SDK does not match global.json")
        return version

    check("pinned-sdk", pinned_sdk)
    check("docker-daemon", lambda: run(*DOCKER, "info", "--format", "{{.ServerVersion}}"))
    check("docker-compose", lambda: run(*DOCKER, "compose", "version"))
    check("local-listener", listener)
    for host in ("builds.dotnet.microsoft.com", "github.com", "registry-1.docker.io", "api.nuget.org"):
        check("dns:" + host, lambda host=host: socket.getaddrinfo(host, 443)[0][4][0])
    check("nuget-https", https)
    check("image-lock", lambda: json.dumps(load_lock(), sort_keys=True))
    print(json.dumps({"spec": SPEC, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if all(c["result"] == "PASS" for c in checks) else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("doctor", "sdk", "images", "provision", "up", "stop", "status"))
    parser.add_argument("--sdk-archive", type=Path, help="Offline official SDK archive; checksum still required")
    args = parser.parse_args()
    try:
        if args.action == "doctor":
            return doctor()
        if args.action in ("sdk", "provision"):
            install_sdk(args.sdk_archive.resolve() if args.sdk_archive else None)
        if args.action in ("images", "provision"):
            provision_images()
        if args.action in ("up", "stop", "status"):
            compose(args.action)
    except (OSError, RuntimeError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print("BLOCKED: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
