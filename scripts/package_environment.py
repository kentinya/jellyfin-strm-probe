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
# Only the explicitly selected server version is ever used. 12.2 keeps its existing default spec and
# host-provisioned lock; 12.3 has its own committed spec plus an immutable digest lock, so a version
# selection can never silently fall back to the other server.
SERVER_VERSIONS = {
    "12.2": {"spec": "dev/environment-spec.json", "lock": "artifacts/dev-env/images.lock.json"},
    "12.3": {"spec": "dev/environment-spec-12.3.json", "lock": "dev/images-12.3.lock.json"},
}
SERVER_VERSION = "12.2"
SPEC = json.loads((ROOT / SERVER_VERSIONS[SERVER_VERSION]["spec"]).read_text())
# The spec and lock are resolved from ``ROOT`` on every use, so a caller (or a guard test) that
# patches ROOT always gets that root's own files.
LOCK_RELATIVE = SERVER_VERSIONS[SERVER_VERSION]["lock"]


def lock_file() -> Path:
    return ROOT / LOCK_RELATIVE
BASE = ROOT / "artifacts" / "package-env"
WORK = BASE
PROJECT = "jf-strm-probe-package-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:10]
PORT = int(os.environ.get("JF_PROBE_PACKAGE_PORT", "18097"))
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
# Optional per-run limits; other acceptance entries retain their existing defaults.
SERVICE_RESOURCE_LIMITS: dict[str, dict[str, int | float]] = {}
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
STRM_LIBRARY = "Package STRM Fixtures"
# A second real library over the same owned instance, used only where an explicit partial batch scope
# needs two native libraries. Its files are ordinary local media, not STRM.
LOCAL_LIBRARY = "Package Local Fixtures"
LOCAL_LIBRARY_PATH = "/media/local"
# Distinct basenames so Jellyfin never groups them as alternate versions of one another.
MEDIA_MP4 = "package-mp4.mp4"
MEDIA_MKV = "package-mkv.mkv"
# Each acceptance run owns a fresh subdirectory under BASE and writes this marker. The marker
# records this run's unique token; cleanup requires both that this run actually created the
# workspace (module-global ownership) and that the on-disk token matches, so a marker left by a
# previous run can never authorise this run to delete that previous run's data.
RUN_MARKER = ".package-run"

# Set by ``select_workspace`` when this process claims a fresh workspace. Only a workspace this
# run created is eligible for cleanup; a directly patched ``WORK`` (unit tests/tools) is never
# treated as owned.
_OWNED_WORKSPACE: Path | None = None
_RUN_TOKEN: str | None = None

sys.path.insert(0, str(Path(__file__).resolve().parent))


class PackageEnvironmentError(RuntimeError):
    """An isolation or ownership precondition failed."""


def credentials_path() -> Path:
    return WORK / "credentials.local.json"


def generated_at_path() -> Path:
    return WORK / ".media-prepared"


def default_run_workspace() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    return BASE / "runs" / f"run-{stamp}-{uuid.uuid4().hex[:8]}"


def select_workspace(path: Path | None = None) -> Path:
    """Claim a fresh, run-owned workspace and record this run's ownership token.

    Only a directory that does not yet exist, or an existing *empty* directory, may be claimed.
    Any pre-existing non-empty directory is refused before any write — including one that still
    carries an earlier run's ``.package-run`` marker. A marker only proves historical origin, so
    it never grants this run permission to modify or delete that earlier run's data.
    """
    global WORK, _OWNED_WORKSPACE, _RUN_TOKEN
    # A refused selection must never leave a previous selection's ownership behind.
    _OWNED_WORKSPACE = None
    _RUN_TOKEN = None
    candidate = (path if path is not None else default_run_workspace())
    candidate = candidate if candidate.is_absolute() else (ROOT / candidate)
    resolved = candidate.resolve(strict=False)
    base = BASE.resolve()
    if resolved != base and not resolved.is_relative_to(base):
        raise PackageEnvironmentError(
            f"The package workspace {candidate} must live under {BASE}."
        )
    if candidate.is_symlink():
        raise PackageEnvironmentError("The package workspace must not be a symbolic link.")
    if candidate.exists():
        if not candidate.is_dir():
            raise PackageEnvironmentError(f"The package workspace {candidate} is not a directory.")
        if any(candidate.iterdir()):
            raise PackageEnvironmentError(
                f"Refusing to reuse {candidate}: this run may only use a new or empty workspace."
            )
    candidate.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    marker = candidate / RUN_MARKER
    if marker.is_symlink():
        raise PackageEnvironmentError("The package run marker must not be a symbolic link.")
    marker.write_text(token + "\n", encoding="utf-8")
    WORK = candidate
    _OWNED_WORKSPACE = candidate.resolve()
    _RUN_TOKEN = token
    return WORK


def run(*args: str, timeout: int = 120, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PackageEnvironmentError(message)


def require_owned_path(path: Path, *, label: str | None = None) -> Path:
    """Return ``path`` only when it and every parent stay inside the owned workspace.

    The original lexical path is validated component by component before any resolution, so a
    symbolic link anywhere in the chain — including the final file and a link that points back
    inside the workspace — is rejected rather than silently followed. The resolved path is then
    required to stay inside the workspace as a second, independent guard.
    """
    workspace_root = WORK.resolve()
    candidate = path if path.is_absolute() else (WORK / path)
    lexical = Path(os.path.abspath(candidate))
    if lexical != workspace_root and not lexical.is_relative_to(workspace_root):
        raise PackageEnvironmentError(
            f"Refusing to write outside the package workspace: {label or candidate}."
        )
    if workspace_root.is_symlink():
        raise PackageEnvironmentError("The package workspace must not be a symbolic link.")
    current = workspace_root
    for part in lexical.relative_to(workspace_root).parts:
        current = current / part
        if current.is_symlink():
            raise PackageEnvironmentError(
                f"Refusing to write through a symbolic link: {label or current}."
            )
    resolved = candidate.resolve(strict=False)
    if resolved != workspace_root and not resolved.is_relative_to(workspace_root):
        raise PackageEnvironmentError(
            f"Refusing to write outside the package workspace: {label or candidate}."
        )
    return candidate


def workspace_owned_root() -> Path:
    workspace()
    return WORK.resolve()


def workspace() -> None:
    for path in (ROOT / "artifacts", BASE, WORK):
        if path.is_symlink():
            raise PackageEnvironmentError("The package environment directory must not be a symlink.")
    WORK.mkdir(parents=True, exist_ok=True)
    marker = WORK / RUN_MARKER
    if marker.is_symlink():
        raise PackageEnvironmentError("The package run marker must not be a symbolic link.")
    owned = _OWNED_WORKSPACE is not None and _OWNED_WORKSPACE == WORK.resolve()
    if marker.is_file():
        # A marker that this run did not write means another run owns the directory; refuse to
        # touch it rather than silently reusing or overwriting its data.
        if not owned or marker.read_text(encoding="utf-8").strip() != (_RUN_TOKEN or ""):
            raise PackageEnvironmentError(
                "Refusing to write into a package workspace owned by a different run."
            )
    elif owned:
        marker.write_text((_RUN_TOKEN or "") + "\n", encoding="utf-8")
    for name in ("config", "cache", "strm", "media", "media-server"):
        path = WORK / name
        if path.is_symlink():
            raise PackageEnvironmentError(f"The package environment subdirectory {name!r} is a symlink.")
        path.mkdir(exist_ok=True)


def write_owned_bytes(target: Path, data: bytes, *, label: str) -> Path:
    """Write bytes to a validated path, refusing a symlinked target or parent.

    The final component is validated (not just its directory), so a pre-existing file that is a
    symbolic link to a foreign sentinel is refused instead of being followed and overwritten.
    """
    owned = require_owned_path(target, label=label)
    owned.parent.mkdir(parents=True, exist_ok=True)
    if owned.is_symlink():
        raise PackageEnvironmentError(f"Refusing to write through a symbolic link: {label}.")
    owned.write_bytes(data)
    return owned


def copy_owned(source: Path, target: Path, *, label: str) -> Path:
    """Copy a file to a validated target, refusing a symlinked destination."""
    owned = require_owned_path(target, label=label)
    owned.parent.mkdir(parents=True, exist_ok=True)
    if owned.is_symlink():
        raise PackageEnvironmentError(f"Refusing to write through a symbolic link: {label}.")
    shutil.copy2(source, owned)
    return owned


def select_server_version(version: str) -> dict:
    """Select exactly one server version and its own spec plus immutable lock.

    Unknown versions are refused before anything is measured, and the previous selection's spec/lock
    is never used as a fallback.
    """
    global SPEC, LOCK_RELATIVE, SERVER_VERSION
    require(version in SERVER_VERSIONS, f"Unknown server version {version!r}; supported: {sorted(SERVER_VERSIONS)}.")
    spec_path = ROOT / SERVER_VERSIONS[version]["spec"]
    require(spec_path.is_file(), f"The server version {version} specification is missing: {spec_path}")
    candidate = json.loads(spec_path.read_text())
    require(str(candidate.get("server", {}).get("version")) == version,
            f"The environment specification {spec_path.name} does not declare server version {version}.")
    SERVER_VERSION = version
    SPEC = candidate
    LOCK_RELATIVE = SERVER_VERSIONS[version]["lock"]
    return server_identity()


def server_public_version() -> str:
    """The exact ``/System/Info/Public`` version the selected server must report."""
    server = SPEC["server"]
    return str(server.get("public_version") or str(server["version"]) + ".0")


def server_identity() -> dict:
    """The selected server's fixed identity, recorded in every run index."""
    server = SPEC["server"]
    return {"version": SERVER_VERSION, "publicVersion": server_public_version(),
            "image": server.get("image"), "source": server.get("source"),
            "sourceSha": server.get("source_sha"),
            "imageIndexDigest": server.get("image_index_digest"),
            "lockFile": LOCK_RELATIVE, "specFile": SERVER_VERSIONS[SERVER_VERSION]["spec"]}


def load_image_lock() -> dict[str, str]:
    lock_path = lock_file()
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


def verify_server_image(images: dict[str, str] | None = None) -> dict:
    """Prove the locked server digest is present locally as a Linux amd64 image.

    The measurement must run on the digest the contract fixed, not on whatever a mutable tag now
    resolves to, so a missing or foreign image stops the run before any instance starts.
    """
    images = images or load_image_lock()
    server = images["server"]
    inspected = run(*DOCKER, "image", "inspect", server,
                    "--format", "{{.Os}}/{{.Architecture}} {{.Id}} {{json .RepoDigests}}")
    require(inspected.returncode == 0,
            f"The pinned server image {server} is not present locally; pull that digest before measuring.")
    fields = inspected.stdout.strip().split(maxsplit=2)
    require(len(fields) >= 2, "The pinned server image inspection returned no platform identity.")
    require(fields[0] == "linux/amd64",
            f"The pinned server image is {fields[0]!r}, not the required linux/amd64 platform.")
    digests = json.loads(fields[2]) if len(fields) > 2 and fields[2].startswith("[") else []
    expected_digest = server.split("@", 1)[1]
    require(server in digests or fields[1] == expected_digest,
            f"The locally present image does not match the locked digest {server} (repo digests {digests}).")
    identity = server_identity()
    identity.update({"imageId": fields[1], "repoDigests": digests, "platform": fields[0]})
    return identity


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
    for service, limits in SERVICE_RESOURCE_LIMITS.items():
        require(service in compose["services"], "Resource limits name an unknown service.")
        require(set(limits) == {"cpus", "mem_limit"}, "Resource limits require CPU and memory bounds.")
        require(all(isinstance(value, (int, float)) and not isinstance(value, bool)
                    and 0 < value < float("inf") for value in limits.values()),
                "Resource limits must be finite positive numbers.")
        compose["services"][service].update(limits)
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
    write_owned_bytes(path, ("\n".join(lines) + "\n").encode("utf-8"), label="compose file")
    return path


def guard_containers() -> None:
    listed = run(*DOCKER, "ps", "-aq", "--filter", "label=com.docker.compose.project=" + PROJECT)
    require(listed.returncode == 0,
            f"Could not query the package-environment containers: {listed.stderr.strip() or listed.stdout.strip()}")
    ids = listed.stdout
    if not ids.strip():
        return
    inspected = run(*DOCKER, "inspect", *ids.split())
    require(inspected.returncode == 0, "Could not inspect existing package-environment containers.")
    base = BASE.resolve()
    for container in json.loads(inspected.stdout):
        mounts = container.get("Mounts", [])
        require(mounts, "An existing package-environment container has no mounts; refusing to touch it.")
        for mount in mounts:
            # Any run directory under the package environment root belongs to this project, so a
            # previous run's containers may be recreated. A mount outside that root is foreign.
            require(mount["Type"] == "bind" and Path(mount["Source"]).resolve().is_relative_to(base),
                    "An existing package-environment container has foreign mounts; refusing to change it.")


def compose(action: str, *, timeout: int = 180) -> None:
    workspace()
    stage_media_server()
    require(run(*DOCKER, "info", "--format", "{{.ServerVersion}}").returncode == 0, "The Docker daemon is unavailable.")
    guard_containers()
    if action == "up":
        # A start must use the selected version's own locked digest on the required platform.
        verify_server_image()
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
        write_owned_bytes(destination, source_bytes, label="isolated media server")


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
    if generated_at_path().is_file() and all((media / name).is_file() for name in targets):
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
    copy_owned(media / MEDIA_MP4, media / "package-mp4-alt.mp4", label="alternate MP4 fixture")
    copy_owned(media / MEDIA_MKV, media / "package-mkv-alt.mkv", label="alternate MKV fixture")
    write_owned_bytes(generated_at_path(), b"prepared\n", label="media-prepared marker")


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
    return write_owned_bytes(path, ("\n".join(lines) + "\n").encode("utf-8"), label=f"STRM fixture {name}")


def wait_healthy(timeout: int = 150) -> str:
    container = container_name("jellyfin")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        health = run(*DOCKER, "inspect", "--format", "{{.State.Health.Status}}", container)
        if health.returncode == 0 and health.stdout.strip() == "healthy":
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/System/Info/Public", timeout=10) as response:
                    info = json.load(response)
                if info.get("Version") == server_public_version():
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


def write_credentials(base_url: str, username: str, password: str) -> None:
    credentials = write_owned_bytes(
        credentials_path(),
        json.dumps({"base_url": base_url, "username": username, "password": password}).encode("utf-8"),
        label="credentials file",
    )
    credentials.chmod(0o600)


def prepare_clean_instance(libraries: list[tuple[str, list[str]]] | None = None) -> dict:
    """Start a fresh instance, complete setup, add the given libraries and record credentials."""
    workspace()
    ensure_media()
    compose("stop")
    for name in ("config", "cache"):
        target = require_owned_path(WORK / name, label=f"fresh-instance {name}")
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)
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
    for name, paths in (libraries or [(STRM_LIBRARY, ["/media/strm"])]):
        add_library_authenticated(token, name, paths)
    return {"container": container, "port": PORT, "credentials": str(credentials_path()),
            "libraries": [name for name, _ in (libraries or [(STRM_LIBRARY, ["/media/strm"])])],
            "server": server_identity()}


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


def unpack_archive(archive: Path, destination: Path, *, expected_sha256: str | None = None,
                   expected_entries: dict[str, str] | None = None) -> dict:
    """Validate an archive fully, then swap it into place; a rejected archive never disturbs the target.

    The consumer reads the archive's published sidecar manifest by default and refuses to
    replace a valid installation unless the archive and every file match it.
    """
    import package_plugin

    require(archive.is_file() and not archive.is_symlink(), f"The package {archive} is missing or symbolic.")
    if expected_sha256 is None and expected_entries is None:
        expected_sha256, expected_entries = package_plugin.expected_from_sidecar(archive)
    require(expected_sha256 is not None,
            "Refusing to install an archive without its published sidecar manifest (archive + per-file digests).")
    # Ownership is checked before any delete/replace so a foreign directory is never touched.
    owned_destination = require_owned_path(destination, label=f"plugin folder {destination.name}")
    owned_parent = require_owned_path(destination.parent, label="plugins directory")
    verification = package_plugin.verify_archive(
        archive, expected_sha256=expected_sha256, expected_entries=expected_entries)
    root = verification["folder"]
    staging = owned_parent / (".staging-" + uuid.uuid4().hex[:12])
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
        if owned_destination.exists():
            require(not owned_destination.is_symlink(), f"Refusing to replace a symlinked plugin folder {root!r}.")
            shutil.rmtree(owned_destination)
        staging.replace(owned_destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return {"folder": root, "extracted": extracted, "archiveSha256": verification["archiveSha256"]}


def deploy_archive(archive: Path) -> dict:
    """Install the archive into the package instance's plugin directory (no dev deployment)."""
    import package_plugin

    owned_plugins = require_owned_path(WORK / "config" / "plugins", label="package plugins directory")
    owned_plugins.mkdir(parents=True, exist_ok=True)
    expected_sha, expected_entries = package_plugin.expected_from_sidecar(archive)
    require(expected_sha is not None,
            "Refusing to deploy an archive without its published sidecar manifest (archive + per-file digests).")
    verification = package_plugin.verify_archive(
        archive, expected_sha256=expected_sha, expected_entries=expected_entries)
    folder = verification["folder"]
    require(folder == "Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0",
            f"Unexpected plugin folder {folder!r}; expected the supported versioned folder.")
    return unpack_archive(archive, owned_plugins / folder,
                          expected_sha256=expected_sha, expected_entries=expected_entries)


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
    target = require_owned_path(plugin_directory(), label="deployed plugin folder")
    if target.is_symlink():
        raise PackageEnvironmentError("Refusing to remove a symlinked plugin folder.")
    shutil.rmtree(target, ignore_errors=True)


def backup_state(destination: Path) -> dict:
    """Copy the configuration and fingerprint database into an owned backup directory.

    The server must be stopped by the caller first, per the delivery instructions.
    """
    owned_destination = require_owned_path(destination, label="backup directory")
    owned_destination.mkdir(parents=True, exist_ok=True)
    sources = {
        "configuration": WORK / "config" / "plugins" / "configurations" / "Jellyfin.Plugin.StrmProbeOptimizer.xml",
        "fingerprint": WORK / "config" / "data" / "plugins" / "b061643ed17d4c6e8ba26b57e286bd20" / "strm-fingerprints.db",
    }
    copied: dict[str, dict[str, str]] = {}
    for label, source in sources.items():
        require(source.is_file(), f"The package instance has no {label} to back up: {source}.")
        # The individual destination file is validated, not only the directory, so a symlinked
        # backup leaf cannot redirect the copy to a foreign sentinel.
        target = copy_owned(source, owned_destination / source.name, label=f"backup {label}")
        copied[label] = {"path": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    return copied


def restore_state(backup: Path) -> dict:
    """Restore the configuration and fingerprint database from a backup and return read-back hashes."""
    owned_backup = require_owned_path(backup, label="backup directory")
    require(owned_backup.is_dir(), f"The backup directory {owned_backup} does not exist.")
    sources = {
        "configuration": (owned_backup / "Jellyfin.Plugin.StrmProbeOptimizer.xml",
                          WORK / "config" / "plugins" / "configurations" / "Jellyfin.Plugin.StrmProbeOptimizer.xml"),
        "fingerprint": (owned_backup / "strm-fingerprints.db",
                        WORK / "config" / "data" / "plugins" / "b061643ed17d4c6e8ba26b57e286bd20" / "strm-fingerprints.db"),
    }
    restored: dict[str, dict[str, str]] = {}
    for label, (source, target) in sources.items():
        require(source.is_file(), f"The backup has no {label}: {source}.")
        owned_target = copy_owned(source, target, label=f"{label} target")
        restored[label] = {"path": str(owned_target), "sha256": hashlib.sha256(owned_target.read_bytes()).hexdigest()}
    return restored


def _tree_fingerprint(root: Path) -> dict[str, str]:
    """Return {relative path: sha256} for the regular files under a workspace subdirectory."""
    result: dict[str, str] = {}
    if not root.is_dir():
        return result
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def capture_instance_state() -> dict[str, object]:
    """Snapshot every owned instance input that a run may read or write.

    Besides the plugin configuration, fingerprint database, media and STRM files, this records
    the native scheduled-task state (all triggers) and the library entries under ``config/root``
    so a run cannot silently leave a trigger or library change behind.
    """
    workspace()
    state: dict[str, object] = {
        "configuration": _tree_fingerprint(WORK / "config" / "plugins" / "configurations"),
        "fingerprint_database": _tree_fingerprint(
            WORK / "config" / "data" / "plugins" / "b061643ed17d4c6e8ba26b57e286bd20"),
        "media": _tree_fingerprint(WORK / "media"),
        "strm": _tree_fingerprint(WORK / "strm"),
        "scheduled_tasks": _tree_fingerprint(WORK / "config" / "data" / "ScheduledTasks"),
        "libraries": _tree_fingerprint(WORK / "config" / "root"),
    }
    return state


STATE_AREAS = ("configuration", "fingerprint_database", "media", "strm", "scheduled_tasks", "libraries")


def reconcile_instance_state(before: dict[str, object]) -> dict[str, object]:
    """Compare the owned inputs with the pre-run snapshot and refuse any disturbed input.

    The run always uses a fresh, marker-owned workspace, so every file it creates is
    run-owned and every file it removes is a pre-existing input it must not have touched. A
    removed or modified pre-existing input makes the whole run FAIL rather than being reported
    and forgotten.
    """
    after = capture_instance_state()
    areas: dict[str, object] = {}
    disturbed: list[str] = []
    for area in STATE_AREAS:
        previous = dict(before.get(area, {}))
        current = dict(after.get(area, {}))
        added = sorted(set(current) - set(previous))
        removed = sorted(set(previous) - set(current))
        changed = sorted(path for path in set(previous) & set(current) if previous[path] != current[path])
        areas[area] = {"added": added, "removed": removed, "changed": changed}
        if removed or changed:
            disturbed.append(area)
    result = {"status": "CLEAN" if not disturbed else "MISMATCH", "areas": areas, "disturbed": disturbed}
    if disturbed:
        raise PackageEnvironmentError(
            "The run disturbed pre-existing instance inputs in: " + ", ".join(disturbed) + "."
        )
    return result


def cleanup_instance(*, required_services: tuple[str, ...] = ()) -> dict[str, object]:
    """Stop the instance and remove only the workspace this run actually created.

    Cleanup requires both this run's module-global ownership and the on-disk token to match.
    A marker left behind by a previous run therefore never authorises deletion of that run's
    data, and a directly patched ``WORK`` is never treated as owned.
    """
    if _OWNED_WORKSPACE is None or _OWNED_WORKSPACE != WORK.resolve():
        raise PackageEnvironmentError("Refusing to clean a workspace this run did not create.")
    marker = WORK / RUN_MARKER
    if marker.is_symlink() or not marker.is_file():
        raise PackageEnvironmentError("Refusing to clean a workspace without this run's marker.")
    if marker.read_text(encoding="utf-8").strip() != (_RUN_TOKEN or ""):
        raise PackageEnvironmentError("Refusing to clean a workspace owned by a different run.")
    workspace()
    root = require_owned_path(WORK, label="run workspace")
    compose("stop")
    container_states = inspect_owned_container_states()
    if required_services:
        observed_services = [state.get("service") for state in container_states]
        require(sorted(observed_services, key=str) == sorted(required_services),
                "Missing or unexpected owned-service exit evidence; preserving workspace.")
    invalid = [state for state in container_states
               if state.get("status") != "exited" or type(state.get("exit_code")) is not int
               or state["exit_code"] != 0 or state.get("oom_killed") is not False
               or state.get("error") != "" or not state.get("finished_at")
               or str(state["finished_at"]).startswith("0001-")]
    require(not invalid,
            "Owned package containers did not terminate cleanly: "
            + json.dumps(invalid, sort_keys=True))
    removed = sorted(path.name for path in root.iterdir())
    shutil.rmtree(root)
    return {"status": "CLEANED", "removed": removed, "workspace": str(root),
            "container_states": container_states}


def inspect_owned_container_states() -> list[dict[str, object]]:
    """Return final state for this Compose project without following foreign containers."""
    listed = run(*DOCKER, "ps", "-aq", "--filter", "label=com.docker.compose.project=" + PROJECT)
    require(listed.returncode == 0,
            "Could not query package-environment containers after stopping the instance.")
    ids = listed.stdout.split()
    if not ids:
        return []
    inspected = run(*DOCKER, "inspect", *ids)
    require(inspected.returncode == 0,
            "Could not inspect package-environment containers after stopping the instance.")
    states: list[dict[str, object]] = []
    for item in json.loads(inspected.stdout):
        state = item.get("State", {})
        states.append({
            "name": str(item.get("Name", "")).lstrip("/"),
            "service": item.get("Config", {}).get("Labels", {}).get("com.docker.compose.service"),
            "status": state.get("Status"),
            "exit_code": state.get("ExitCode"),
            "oom_killed": state.get("OOMKilled"),
            "error": state.get("Error", ""),
            "finished_at": state.get("FinishedAt"),
        })
    return states
