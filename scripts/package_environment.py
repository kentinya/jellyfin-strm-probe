#!/usr/bin/env python3
"""Isolated Jellyfin instance used only for package (ZIP) acceptance.

This module deliberately owns a separate workspace, Compose project and host port from the
shared development instance in ``scripts/development_environment.py`` so an archive
installation never depends on, mutates or is confused with the development deployment. The
server container mounts no source, SDK, NuGet cache or build output: the only plugin payload
it can see is the one unpacked from the archive under test.

It also owns synthetic-media preparation (generated with the pinned Jellyfin FFmpeg, so no
host ffmpeg is required) and the fresh-instance bootstrap (startup wizard + two libraries).
Nothing here talks to a production Jellyfin, media library or proxy.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = ROOT / "scripts" / "development_environment.py"
SPEC = json.loads((ROOT / "dev" / "environment-spec.json").read_text())
WORK = ROOT / "artifacts" / "package-env"
PROJECT = "jf-strm-probe-package-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:10]
PORT = int(os.environ.get("JF_PROBE_PACKAGE_PORT", "18097"))
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
STRM_LIBRARY = "Package STRM Fixtures"
# Distinct basenames so Jellyfin never groups them as alternate versions of one another.
MEDIA_MP4 = "package-mp4.mp4"
MEDIA_MKV = "package-mkv.mkv"
CREDENTIALS = WORK / "credentials.local.json"
GENERATED_AT = WORK / ".media-prepared"

sys.path.insert(0, str(Path(__file__).resolve().parent))


class PackageEnvironmentError(RuntimeError):
    """An isolation or ownership precondition failed."""


def run(*args: str, timeout: int = 120, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PackageEnvironmentError(message)


def workspace() -> None:
    for path in (ROOT / "artifacts", WORK):
        if path.is_symlink():
            raise PackageEnvironmentError("The package environment directory must not be a symlink.")
    WORK.mkdir(parents=True, exist_ok=True)
    for name in ("config", "cache", "strm", "media", "media-server"):
        path = WORK / name
        if path.is_symlink():
            raise PackageEnvironmentError(f"The package environment subdirectory {name!r} is a symlink.")
        path.mkdir(exist_ok=True)


def load_image_lock() -> dict[str, str]:
    lock_path = ROOT / "artifacts" / "dev-env" / "images.lock.json"
    require(lock_path.is_file(), "The immutable image lock is missing; provision the environment first.")
    data = json.loads(lock_path.read_text())
    require(data.get("spec") == SPEC, "The image lock belongs to a different environment specification.")
    images = data.get("images", {})
    for name, repository in (("server", "jellyfin/jellyfin"), ("media", "python")):
        value = images.get(name, "")
        prefix = repository + "@"
        require(value.startswith(prefix) and DIGEST.fullmatch(value[len(prefix):]),
                f"The image lock has no immutable {name} digest.")
    return images


def write_compose() -> Path:
    images = load_image_lock()
    compose = {
        "services": {
            "jellyfin": {
                "image": images["server"],
                "platform": "linux/amd64",
                "user": f"{os.getuid()}:{os.getgid()}",
                "restart": "no",
                "ports": [f"127.0.0.1:{PORT}:8096"],
                "volumes": [
                    f"{WORK}/config:/config",
                    f"{WORK}/cache:/cache",
                    f"{WORK}/strm:/media/strm:ro",
                    f"{WORK}/media:/media/local:ro",
                ],
                "networks": ["acceptance", "frontend"],
            },
            "media": {
                "image": images["media"],
                "platform": "linux/amd64",
                "user": f"{os.getuid()}:{os.getgid()}",
                "restart": "no",
                "read_only": True,
                "command": ["python", "/server/isolated_media_server.py", "--directory", "/media", "--port", "8080"],
                "volumes": [f"{WORK}/media:/media:ro", f"{WORK}/media-server:/server:ro"],
                "networks": ["acceptance"],
            },
        },
        "networks": {
            "acceptance": {"internal": True},
            "frontend": {"driver": "bridge"},
        },
    }
    path = WORK / "compose.yaml"
    # A tiny YAML writer keeps the file self-contained without a PyYAML dependency.
    lines: list[str] = ["services:"]
    for service, body in compose["services"].items():
        lines.append(f"  {service}:")
        for key, value in body.items():
            if key in {"volumes", "networks", "ports"}:
                lines.append(f"    {key}:")
                for item in value:
                    lines.append(f'      - "{item}"' if key != "networks" else f"      - {item}")
            elif key == "command":
                rendered = ", ".join(json.dumps(part) for part in value)
                lines.append(f"    command: [{rendered}]")
            elif isinstance(value, bool):
                lines.append(f"    {key}: {str(value).lower()}")
            elif isinstance(value, int):
                lines.append(f"    {key}: {value}")
            else:
                lines.append(f'    {key}: "{value}"')
    lines.append("networks:")
    for network, body in compose["networks"].items():
        lines.append(f"  {network}:")
        for key, value in body.items():
            if isinstance(value, bool):
                lines.append(f"    {key}: {str(value).lower()}")
            else:
                lines.append(f'    {key}: "{value}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def guard_containers() -> None:
    ids = run(*DOCKER, "ps", "-aq", "--filter", "label=com.docker.compose.project=" + PROJECT).stdout
    if not ids.strip():
        return
    inspected = run(*DOCKER, "inspect", *ids.split())
    require(inspected.returncode == 0, "Could not inspect existing package-environment containers.")
    for container in json.loads(inspected.stdout):
        mounts = container.get("Mounts", [])
        require(mounts, "An existing package-environment container has no mounts; refusing to touch it.")
        for mount in mounts:
            require(mount["Type"] == "bind" and Path(mount["Source"]).resolve().is_relative_to(WORK.resolve()),
                    "An existing package-environment container has foreign mounts; refusing to change it.")


def compose(action: str, *, timeout: int = 180) -> None:
    workspace()
    stage_media_server()
    require(run(*DOCKER, "info", "--format", "{{.ServerVersion}}").returncode == 0, "The Docker daemon is unavailable.")
    guard_containers()
    path = write_compose()
    base = [*DOCKER, "compose", "--project-name", PROJECT, "--file", str(path)]
    if action == "up":
        tail = ["up", "-d", "--pull", "never"]
    elif action == "stop":
        tail = ["stop", "--timeout", "20"]
    elif action == "down":
        tail = ["down", "--volumes", "--remove-orphans"]
    else:
        tail = ["ps"]
    result = run(*base, *tail, timeout=timeout)
    require(result.returncode == 0, f"docker compose {action} failed: {result.stderr.strip() or result.stdout.strip()}")


def stage_media_server() -> None:
    source = ROOT / "scripts" / "isolated_media_server.py"
    destination = WORK / "media-server" / source.name
    source_bytes = source.read_bytes()
    if not destination.is_file() or destination.read_bytes() != source_bytes:
        destination.write_bytes(source_bytes)


def container_name(service: str) -> str:
    result = run(*DOCKER, "ps", "--filter", "label=com.docker.compose.project=" + PROJECT,
                 "--format", '{{.Names}} {{.Label "com.docker.compose.service"}}')
    require(result.returncode == 0, "Could not inspect package-environment containers.")
    matches = [line.split()[0] for line in result.stdout.splitlines() if line.split()[-1:] == [service]]
    require(len(matches) == 1, f"Expected exactly one package-environment {service} container.")
    return matches[0]


def ensure_media() -> None:
    """Generate the synthetic MP4/MKV fixtures with the pinned Jellyfin FFmpeg if absent."""
    workspace()
    media = WORK / "media"
    targets = {
        MEDIA_MP4: ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"],
        MEDIA_MKV: ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"],
    }
    if GENERATED_AT.is_file() and all((media / name).is_file() for name in targets):
        return
    images = load_image_lock()
    # `python:...` base image has no ffmpeg; the pinned Jellyfin server image ships the pinned ffmpeg.
    for name, codecs in targets.items():
        command = [
            *DOCKER, "run", "--rm", "--entrypoint", "/usr/lib/jellyfin-ffmpeg/ffmpeg",
            "-v", f"{media}:/out", images["server"],
            "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x90:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            *codecs, "-shortest", f"/out/{name}",
        ]
        result = run(*command, timeout=180)
        require(result.returncode == 0, f"Could not generate the synthetic {name} fixture: {result.stderr.strip()[-300:]}")
    # Alternate fixtures must be byte-identical so a same-SHA-1 URL change is meaningful.
    shutil.copy2(media / MEDIA_MP4, media / "package-mp4-alt.mp4")
    shutil.copy2(media / MEDIA_MKV, media / "package-mkv-alt.mkv")
    GENERATED_AT.write_text("prepared\n", encoding="utf-8")


def media_sha1(name: str) -> tuple[str, int]:
    data = (WORK / "media" / name).read_bytes()
    return hashlib.sha1(data).hexdigest(), len(data)


def write_strm(name: str, url: str, sha1: str | None, size: int | None) -> Path:
    workspace()
    path = WORK / "strm" / (name + ".strm")
    lines = ["# strm-probe-version:1"]
    if sha1 is not None:
        lines.append(f"# strm-probe-sha1:{sha1}")
    if size is not None:
        lines.append(f"# strm-probe-size:{size}")
    lines.append(url)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def wait_healthy(timeout: int = 150) -> str:
    container = container_name("jellyfin")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        health = run(*DOCKER, "inspect", "--format", "{{.State.Health.Status}}", container)
        if health.returncode == 0 and health.stdout.strip() == "healthy":
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/System/Info/Public", timeout=10) as response:
                    info = json.load(response)
                if info.get("Version") == "12.2.0":
                    return container
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                pass
        time.sleep(1)
    raise PackageEnvironmentError("The package-environment Jellyfin container did not become healthy.")


def public_info() -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/System/Info/Public", timeout=15) as response:
        return json.load(response)


def request_json(method: str, path: str, *, headers: dict[str, str] | None = None,
                 body: dict | None = None, timeout: int = 20) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, method=method,
                                     headers={**(headers or {}), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as error:
        return error.code, {}


def bootstrap_fresh_instance(username: str, password: str) -> None:
    """Complete the startup wizard and create the two package libraries on a fresh instance."""
    status, info = request_json("GET", "/System/Info/Public")
    require(status == 200, "The fresh instance public info was unavailable.")
    if info.get("StartupWizardCompleted"):
        return
    for path, body in (
        ("/Startup/Configuration", {"ServerName": "Package Acceptance", "UICulture": "en-US",
                                    "MetadataCountryCode": "US", "PreferredMetadataLanguage": "en"}),
        ("/Startup/RemoteAccess", {"EnableRemoteAccess": False}),
    ):
        status, _ = request_json("POST", path, body=body)
        require(status in (200, 204), f"The startup step {path} failed with HTTP {status}.")
    # The first user is created lazily; reading it forces initialization before it can be renamed/passworded.
    status, _ = request_json("GET", "/Startup/User")
    require(status in (200, 204), f"The startup first-user probe failed with HTTP {status}.")
    status, _ = request_json("POST", "/Startup/User", body={"Name": username, "Password": password})
    require(status in (200, 204), f"The startup user creation failed with HTTP {status}.")
    status, _ = request_json("POST", "/Startup/Complete")
    require(status in (200, 204), f"Completing the startup wizard failed with HTTP {status}.")


def add_library(name: str, paths: list[str]) -> None:
    body = {"LibraryOptions": {"EnableInternetProviders": False, "EnableRealtimeMonitor": False,
                               "SaveLocalMetadata": False, "PathInfos": [{"Path": p} for p in paths]}}
    query = urllib.parse.urlencode({"name": name, "collectionType": "movies", "refreshLibrary": "true"})
    query += "".join(f"&paths={urllib.parse.quote(p)}" for p in paths)
    status, _ = request_json("POST", "/Library/VirtualFolders?" + query, body=body)
    require(status in (200, 204), f"Adding the library {name!r} failed with HTTP {status}.")


def write_credentials(base_url: str, username: str, password: str) -> None:
    CREDENTIALS.write_text(json.dumps({"base_url": base_url, "username": username, "password": password}),
                           encoding="utf-8")
    CREDENTIALS.chmod(0o600)


def prepare_clean_instance() -> dict:
    """Start a fresh instance, complete setup, add the two libraries and record credentials."""
    workspace()
    ensure_media()
    compose("stop")
    for name in ("config", "cache"):
        shutil.rmtree(WORK / name, ignore_errors=True)
        (WORK / name).mkdir(parents=True, exist_ok=True)
    compose("up")
    container = wait_healthy()
    username = "package-admin"
    password = uuid.uuid4().hex + "Aa1!"
    bootstrap_fresh_instance(username, password)
    # After the wizard the public info must report completion before libraries can be added.
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and not public_info().get("StartupWizardCompleted"):
        time.sleep(1)
    require(public_info().get("StartupWizardCompleted"), "The fresh instance did not complete its startup wizard.")
    write_credentials(f"http://127.0.0.1:{PORT}", username, password)
    # The library is created through the authenticated API, so authenticate first.
    token = login(username, password)
    add_library_authenticated(token, STRM_LIBRARY, ["/media/strm"])
    return {"container": container, "port": PORT, "credentials": str(CREDENTIALS)}


def login(username: str, password: str) -> str:
    identity = 'MediaBrowser Client="STRM Probe Optimizer package acceptance", Device="local-test", DeviceId="strm-probe-package", Version="0.1.0"'
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/Users/AuthenticateByName",
        data=json.dumps({"Username": username, "Pw": password}).encode(),
        headers={"Content-Type": "application/json", "Authorization": identity},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        auth = json.load(response)
    return f'{identity}, Token="{auth["AccessToken"]}"'


def add_library_authenticated(auth_header: str, name: str, paths: list[str]) -> None:
    body = {"LibraryOptions": {"EnableInternetProviders": False, "EnableRealtimeMonitor": False,
                               "SaveLocalMetadata": False, "PathInfos": [{"Path": p} for p in paths]}}
    query = urllib.parse.urlencode({"name": name, "collectionType": "movies", "refreshLibrary": "true"})
    query += "".join(f"&paths={urllib.parse.quote(p)}" for p in paths)
    status, _ = request_json("POST", "/Library/VirtualFolders?" + query, body=body, headers={"Authorization": auth_header})
    require(status in (200, 204), f"Adding the library {name!r} failed with HTTP {status}.")


def unpack_archive(archive: Path, destination: Path) -> dict:
    """Validate an archive fully, then swap it into place; a rejected archive never disturbs the target."""
    import package_plugin

    require(archive.is_file() and not archive.is_symlink(), f"The package {archive} is missing or symbolic.")
    verification = package_plugin.verify_archive(archive)
    root = verification["folder"]
    staging = destination.parent / (".staging-" + uuid.uuid4().hex[:12])
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive) as bundle:
            extracted: list[dict[str, object]] = []
            for name in bundle.namelist():
                parts = Path(name).parts
                require(not name.startswith("/") and ".." not in parts and not Path(name).is_absolute(),
                        f"Unsafe archive path {name!r}.")
                info = bundle.getinfo(name)
                require((info.external_attr >> 16) & 0o170000 != 0o120000, f"Symbolic link in archive: {name!r}.")
                relative = Path(*parts[1:])
                if not relative.parts:
                    continue
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                data = bundle.read(name)
                target.write_bytes(data)
                extracted.append({"path": relative.as_posix(), "sha256": hashlib.sha256(data).hexdigest()})
        # Only after the whole archive is validated and staged is the previous install replaced.
        if destination.exists():
            shutil.rmtree(destination)
        staging.replace(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return {"folder": root, "extracted": extracted, "archiveSha256": verification["archiveSha256"]}


def deploy_archive(archive: Path) -> dict:
    """Install the archive into the package instance's plugin directory (no dev deployment)."""
    plugins = WORK / "config" / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    import package_plugin

    verification = package_plugin.verify_archive(archive)
    folder = verification["folder"]
    require(folder == "Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0",
            f"Unexpected plugin folder {folder!r}; expected the supported versioned folder.")
    return unpack_archive(archive, plugins / folder)


def plugin_directory() -> Path:
    return WORK / "config" / "plugins" / "Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0"


def deployed_payload() -> dict[str, str]:
    """Return {relative path: sha256} for every file currently deployed, ignoring runtime state."""
    root = plugin_directory()
    hashes: dict[str, str] = {}
    if not root.is_dir():
        return hashes
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def remove_deployed_plugin() -> None:
    """Remove the plugin payload entirely (used for the uninstall/native-recovery scenario)."""
    shutil.rmtree(plugin_directory(), ignore_errors=True)


def cleanup() -> None:
    try:
        compose("down")
    except (PackageEnvironmentError, OSError, subprocess.SubprocessError):
        pass
