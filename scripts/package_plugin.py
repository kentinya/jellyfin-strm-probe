#!/usr/bin/env python3
"""Build the single-version Linux x64 plugin ZIP consumed by package acceptance.

The tool derives the archive payload from the pinned Release publish output and the
committed NuGet lock file, refuses unsafe or incomplete input, and writes a deterministic
ZIP plus a sidecar manifest and SHA-256 digest. It never deploys anything and never touches
a Jellyfin instance; installation is exercised separately by
``scripts/run_isolated_package_integration.py``.

The payload is deliberately minimal: the plugin assembly, its dependency manifest, the
managed and Linux x64 native SQLite runtime assets actually required at run time, the
Jellyfin plugin manifest, and third-party licence notices. Jellyfin core assemblies,
other-platform runtimes, FFmpeg, the SDK, source, tests, runtime state and credentials are
never included.

Consumers (``--verify`` and the package-acceptance deployment) compare the archive against
the sidecar manifest published beside it, so a mutated or fabricated archive is refused
before any valid installation is replaced. The manifest also records the exact source and
build inputs so the artifact can be rebuilt and audited.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "src" / "Jellyfin.Plugin.StrmProbeOptimizer"
PROJECT_FILE = PROJECT / "Jellyfin.Plugin.StrmProbeOptimizer.csproj"
META_SOURCE = PROJECT / "Packaging" / "meta.json"
LOCK_FILE = PROJECT / "packages.lock.json"
DOTNET = ROOT / "scripts" / "dotnet-local"
DOTNET_INVOCATION = ["bash", str(DOTNET)]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "releases"
ARCHIVE_BASENAME = "Jellyfin.Plugin.StrmProbeOptimizer_linux-x64"
SUPPORTED_RUNTIME = "linux-x64"
PLUGIN_GUID = "b061643e-d17d-4c6e-8ba2-6b57e286bd20"
DOTNET_TARGET_FRAMEWORK = "net10.0"
# The fixed, empirically verified combination this first-version archive supports.
SUPPORTED_JELLYFIN_ABI = "12.2.0.0"
SOURCE_SHA = re.compile(r"[0-9a-f]{40}")
EMBEDDED_REVISION = re.compile(rb"0\.1\.0\+([0-9a-f]{40})")
# Tracked inputs that determine the built plugin assembly. Used to record a reproducible
# build-input digest in the sidecar manifest.
BUILD_INPUT_PATHS = ("src", "dev", "global.json", "Jellyfin.Plugin.StrmProbeOptimizer.sln")
# Package id prefixes (NuGet package ids are case-insensitive) mapped to their licence identity.
LICENSE_BY_PREFIX = (
    ("microsoft.data.sqlite", "MIT"),
    ("sqlitepclraw", "Apache-2.0"),
    ("sqlite/", "Public-Domain"),
)


class PackageError(RuntimeError):
    """A packaging precondition failed; no archive may be produced."""


def run(command: list[str], *, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sidecar_manifest_path(archive: Path) -> Path:
    return archive.with_suffix(".manifest.json")


def load_expected_sidecar(archive: Path) -> dict:
    """Read and validate the published sidecar manifest for an archive, if present."""
    manifest_path = sidecar_manifest_path(archive)
    if not manifest_path.is_file():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PackageError(f"The sidecar manifest {manifest_path.name} is unreadable: {error}.") from error
    digest = manifest.get("archiveSha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise PackageError("The sidecar manifest does not record a valid archive SHA-256.")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise PackageError("The sidecar manifest does not record the published per-file digests.")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) \
                or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", ""))):
            raise PackageError("The sidecar manifest has a malformed entry record.")
    return manifest


def expected_from_sidecar(archive: Path) -> tuple[str | None, dict[str, str] | None]:
    """Return (archive digest, per-file digests) from the published sidecar, if any."""
    manifest = load_expected_sidecar(archive)
    if not manifest:
        return None, None
    entries = {entry["path"]: entry["sha256"] for entry in manifest["entries"]}
    return manifest["archiveSha256"], entries


def git_head() -> str:
    result = run(["git", "rev-parse", "HEAD"], timeout=30)
    revision = result.stdout.strip()
    if result.returncode or not SOURCE_SHA.fullmatch(revision):
        raise PackageError("Could not determine the current HEAD commit SHA.")
    return revision


def source_revision(explicit: str | None) -> str:
    """Return the full commit SHA the candidate is built from.

    The revision is no longer a free-form label: it must name a real commit in this
    repository and must equal the current HEAD, because the build embeds it as
    ``SourceRevisionId`` and the package is only reproducible from that tree.
    """
    head = git_head()
    if explicit is None:
        return head
    if not SOURCE_SHA.fullmatch(explicit):
        raise PackageError("The explicit source revision must be a full 40-character commit SHA.")
    exists = run(["git", "cat-file", "-e", explicit + "^{commit}"], timeout=30)
    if exists.returncode:
        raise PackageError(f"The source revision {explicit} is not a reachable commit in this repository.")
    if explicit != head:
        raise PackageError(
            f"The source revision {explicit} does not match the current HEAD {head}; "
            "the candidate must be built from the checked-out commit."
        )
    return explicit


def sdk_version() -> str:
    result = run([*DOTNET_INVOCATION, "--version"], timeout=60)
    version = result.stdout.strip()
    if result.returncode or not version:
        raise PackageError("The pinned local SDK is unavailable; run scripts/development_environment.py sdk first.")
    return version


def build_input_digest() -> str:
    """Hash the tracked build inputs so the sidecar records exactly what was compiled."""
    listing = run(["git", "ls-files", "-z", *BUILD_INPUT_PATHS], timeout=60)
    if listing.returncode:
        raise PackageError("Could not enumerate the tracked build inputs.")
    paths = sorted(name for name in listing.stdout.split("\0") if name)
    if not paths:
        raise PackageError("No tracked build inputs were found; refusing to package an untracked tree.")
    digest = hashlib.sha256()
    for name in paths:
        source = ROOT / name
        if not source.is_file() or source.is_symlink():
            raise PackageError(f"The build input {name!r} is missing or symbolic.")
        digest.update(name.encode("utf-8") + b"\0" + sha256_file(source).encode("ascii") + b"\n")
    return digest.hexdigest()


def worktree_is_clean() -> tuple[bool, str]:
    result = run(["git", "status", "--porcelain", "--untracked-files=no"], timeout=60)
    if result.returncode:
        return False, "Could not determine the worktree state."
    dirty = result.stdout.strip()
    return (not dirty), dirty


def load_plugin_manifest() -> dict:
    if not META_SOURCE.is_file():
        raise PackageError(f"The plugin manifest is missing: {META_SOURCE.relative_to(ROOT)}")
    manifest = json.loads(META_SOURCE.read_text(encoding="utf-8"))
    for field in ("guid", "name", "version", "targetAbi"):
        if not manifest.get(field):
            raise PackageError(f"The plugin manifest is missing the required {field} field.")
    if str(manifest["guid"]).lower() != PLUGIN_GUID:
        raise PackageError("The plugin GUID changed; existing Jellyfin state would be lost.")
    if manifest["targetAbi"] != SUPPORTED_JELLYFIN_ABI:
        raise PackageError(
            f"Unsupported targetAbi {manifest['targetAbi']!r}; this first version supports {SUPPORTED_JELLYFIN_ABI} only."
        )
    return manifest


def publish(configuration: str, runtime: str, source_revision_value: str) -> Path:
    if runtime != SUPPORTED_RUNTIME:
        raise PackageError(f"Unsupported runtime {runtime!r}; this first version packages {SUPPORTED_RUNTIME} only.")
    destination = Path(tempfile.mkdtemp(prefix="strm-package-publish-"))
    result = run([
        *DOTNET_INVOCATION, "publish", str(PROJECT_FILE),
        "--configuration", configuration,
        "--runtime", runtime,
        "--self-contained", "false",
        "--output", str(destination),
        "--nologo",
        f"-p:SourceRevisionId={source_revision_value}",
    ])
    if result.returncode:
        raise PackageError("dotnet publish failed:\n" + (result.stderr.strip() or result.stdout.strip()))
    verify_embedded_revision(destination / (PROJECT.name + ".dll"), source_revision_value)
    return destination


def verify_embedded_revision(assembly: Path, expected_revision: str) -> None:
    """Fail if the published assembly does not embed the requested source revision."""
    if not assembly.is_file():
        raise PackageError(f"The published plugin assembly is missing: {assembly.name}.")
    data = assembly.read_bytes()
    match = EMBEDDED_REVISION.search(data)
    if match is None:
        raise PackageError("The published plugin assembly does not embed a source revision.")
    actual = match.group(1).decode("ascii")
    if actual != expected_revision:
        raise PackageError(
            f"The published plugin assembly embeds build revision {actual}, not the requested {expected_revision}."
        )


def dependency_assets(deps: dict, runtime: str) -> tuple[dict[str, str | None], dict[str, None]]:
    """Return (managed, native) asset maps derived from a dependency manifest.

    ``managed`` maps a file name to its declared assembly version (or ``None`` when the
    manifest does not declare one); ``native`` maps a file name to ``None``.
    """
    runtime_target = deps.get("runtimeTarget", {}).get("name", "")
    libraries = deps.get("targets", {}).get(runtime_target)
    if not libraries:
        raise PackageError("The dependency manifest has no runtime target section.")
    managed: dict[str, str | None] = {}
    native: dict[str, None] = {}
    for metadata in libraries.values():
        for asset, info in metadata.get("runtime", {}).items():
            managed[Path(asset).name] = info.get("assemblyVersion")
        for asset in metadata.get("native", {}):
            native[Path(asset).name] = None
        for asset, info in metadata.get("runtimeTargets", {}).items():
            if info.get("rid") != runtime:
                continue
            if info.get("assetType") == "native":
                native[Path(asset).name] = None
            elif info.get("assetType") == "runtime":
                managed[Path(asset).name] = info.get("assemblyVersion")
    if not managed:
        raise PackageError("The dependency manifest lists no managed runtime assets.")
    if not native:
        raise PackageError(f"The dependency manifest lists no {runtime} native runtime assets.")
    return managed, native


def payload_plan(publish_dir: Path, runtime: str) -> tuple[list[str], list[str], list[str]]:
    """Return (managed, native, all) relative file names required by the dependency manifest."""
    if runtime != SUPPORTED_RUNTIME:
        raise PackageError(f"Unsupported runtime {runtime!r}; this first version packages {SUPPORTED_RUNTIME} only.")
    deps_path = next(publish_dir.glob("*.deps.json"), None)
    if deps_path is None:
        raise PackageError("The publish output has no dependency manifest (*.deps.json).")
    deps = json.loads(deps_path.read_text(encoding="utf-8"))
    managed, native = dependency_assets(deps, runtime)
    return sorted(managed), sorted(native), sorted(set(managed) | set(native))


def resolve_payload(publish_dir: Path, managed: list[str], native: list[str]) -> list[Path]:
    if publish_dir.is_symlink():
        raise PackageError("The publish directory must not be a symbolic link.")
    resolved: list[Path] = []
    seen: set[str] = set()
    for name in [*managed, *native]:
        if name in seen:
            raise PackageError(f"Duplicate payload entry {name!r}.")
        seen.add(name)
        source = publish_dir / name
        if not source.is_file() or source.is_symlink():
            raise PackageError(f"The required payload file {name!r} is missing or symbolic in the publish output.")
        resolved.append(source)
    plugin_dll = publish_dir / (PROJECT.name + ".dll")
    deps = publish_dir / (PROJECT.name + ".deps.json")
    for required in (plugin_dll, deps):
        if not required.is_file() or required.is_symlink():
            raise PackageError(f"The plugin payload {required.name!r} is missing or symbolic in the publish output.")
    return resolved


def shipped_licenses(managed: list[str], native: list[str]) -> list[dict[str, str]]:
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    packages: dict[str, str] = {}
    for section in lock.get("dependencies", {}).values():
        for package_id, metadata in section.items():
            packages.setdefault(package_id.lower(), str(metadata.get("resolved", "")))
    # Only packages that actually contribute a runtime asset are shipped; map each to its licence.
    contributing: set[str] = set()
    for name in [*managed, *native]:
        stem = Path(name).stem.lower()
        if "microsoft.data.sqlite" in stem:
            contributing.add("microsoft.data.sqlite")
            contributing.add("microsoft.data.sqlite.core")
        elif "sqlitepclraw" in stem:
            for package_id in packages:
                if package_id.startswith("sqlitepclraw"):
                    contributing.add(package_id)
        elif stem == "libe_sqlite3":
            contributing.add("sqlite")
    notices: list[dict[str, str]] = []
    for package_id in sorted(contributing):
        licence = None
        for prefix, identity in LICENSE_BY_PREFIX:
            if package_id.startswith(prefix.rstrip("/")):
                licence = identity
                break
        if licence is None:
            raise PackageError(f"No licence identity is recorded for shipped package {package_id!r}.")
        notices.append({"package": package_id, "version": packages.get(package_id, ""), "license": licence})
    if not notices:
        raise PackageError("No shipped runtime dependency was matched to a licence.")
    return notices


def build_archive_layout(
    publish_dir: Path,
    manifest: dict,
    version: str,
    source_sha: str,
    sdk: str,
    runtime: str,
    configuration: str,
    build_inputs_sha256: str | None = None,
    lock_file_sha256: str | None = None,
    build_command: list[str] | None = None,
) -> tuple[dict[str, bytes], dict[str, object]]:
    managed, native, _ = payload_plan(publish_dir, runtime)
    resolve_payload(publish_dir, managed, native)
    plugin_dll = PROJECT.name + ".dll"
    deps_name = PROJECT.name + ".deps.json"
    # The plugin assembly is also listed as its own library's runtime asset; keep one whitelist entry.
    assemblies = sorted({plugin_dll, *managed})
    packaged_manifest = dict(manifest)
    packaged_manifest["assemblies"] = assemblies
    notices = shipped_licenses(managed, native)
    notice_text = "\n".join(
        f"{entry['package']} {entry['version']} - {entry['license']}" for entry in notices
    ) + "\n"

    files: dict[str, bytes] = {}
    for name in [plugin_dll, deps_name, *managed, *native]:
        files[name] = (publish_dir / name).read_bytes()
    files["meta.json"] = (json.dumps(packaged_manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    files["THIRD-PARTY-NOTICES.txt"] = notice_text.encode("utf-8")

    folder = f"{PROJECT.name}_{version}"
    identity = {
        "plugin": PROJECT.name,
        "guid": manifest["guid"],
        "version": version,
        "targetAbi": manifest["targetAbi"],
        "runtime": runtime,
        "configuration": configuration,
        "targetFramework": DOTNET_TARGET_FRAMEWORK,
        "sdk": sdk,
        "sourceRevision": source_sha,
        "buildInputsSha256": build_inputs_sha256 or "",
        "lockFileSha256": lock_file_sha256 or (sha256_file(LOCK_FILE) if LOCK_FILE.is_file() else ""),
        "buildCommand": build_command or [],
        "managed": managed,
        "native": native,
        "assemblies": assemblies,
        "licenses": notices,
    }
    return {f"{folder}/{name}": data for name, data in files.items()}, identity


def write_archive(archive: Path, files: dict[str, bytes]) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in sorted(files):
            if name.startswith("/") or ".." in Path(name).parts or Path(name).is_absolute():
                raise PackageError(f"Refusing an unsafe archive path {name!r}.")
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, files[name])


def _read_archive_manifest(bundle: zipfile.ZipFile, names: list[str], root: str) -> dict:
    required = f"{root}/meta.json"
    if required not in names:
        raise PackageError("The package has no meta.json.")
    return json.loads(bundle.read(required))


def verify_archive(
    archive: Path,
    expected_sha256: str | None = None,
    expected_entries: dict[str, str] | None = None,
) -> dict[str, object]:
    """Validate an existing archive and return its identity; used before any deployment.

    ``expected_sha256`` and ``expected_entries`` are the published expected digest and
    per-file digests. The package-acceptance consumer supplies them from the sidecar
    manifest published beside the archive; ``--verify`` reads that sidecar automatically.
    Structural validation runs independently of the digest comparison, so a mutated archive
    is refused even if the sidecar digest was also rewritten.
    """
    if not archive.is_file() or archive.is_symlink():
        raise PackageError(f"The package {archive} is missing or symbolic.")
    actual_sha256 = sha256_file(archive)
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise PackageError(
            f"The package digest {actual_sha256} does not match the published expected digest {expected_sha256}."
        )
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if not names:
            raise PackageError("The package is empty.")
        roots = {name.split("/", 1)[0] for name in names}
        if len(roots) != 1:
            raise PackageError("The package must contain exactly one top-level plugin folder.")
        root = roots.pop()
        if not re.fullmatch(re.escape(PROJECT.name) + r"_\d+\.\d+\.\d+\.\d+", root):
            raise PackageError(f"Unexpected plugin folder {root!r}.")
        for name in names:
            parts = Path(name).parts
            if name.startswith("/") or ".." in parts or Path(name).is_absolute():
                raise PackageError(f"Unsafe archive path {name!r}.")
            # Every payload entry must sit directly inside the single plugin folder.
            if not name.endswith("/") and (len(parts) != 2 or parts[0] != root):
                raise PackageError(f"The package contains a nested entry outside the plugin folder: {name!r}.")
            info = bundle.getinfo(name)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise PackageError(f"Symbolic link in archive: {name!r}.")
        manifest = _read_archive_manifest(bundle, names, root)
        if str(manifest.get("guid", "")).lower() != PLUGIN_GUID:
            raise PackageError("The package GUID does not match the supported plugin GUID.")
        if manifest.get("targetAbi") != SUPPORTED_JELLYFIN_ABI:
            raise PackageError(f"The package targetAbi {manifest.get('targetAbi')!r} is not supported.")
        version = str(manifest.get("version", ""))
        if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version):
            raise PackageError(f"The package version {version!r} is not a four-part version.")
        if root != f"{PROJECT.name}_{version}":
            raise PackageError(f"The plugin folder {root!r} does not match the manifest version {version!r}.")
        deps_name = PROJECT.name + ".deps.json"
        if f"{root}/{deps_name}" not in names:
            raise PackageError("The package has no dependency manifest.")
        deps = json.loads(bundle.read(f"{root}/{deps_name}"))
        runtime_target = deps.get("runtimeTarget", {}).get("name", "")
        if SUPPORTED_RUNTIME not in runtime_target:
            raise PackageError(f"The package dependency manifest targets {runtime_target!r}, not {SUPPORTED_RUNTIME}.")
        managed, native = dependency_assets(deps, SUPPORTED_RUNTIME)
        plugin_dll = PROJECT.name + ".dll"
        expected_assemblies = {plugin_dll, *managed}
        declared = manifest.get("assemblies")
        if not isinstance(declared, list) or plugin_dll not in declared:
            raise PackageError("The package meta.json does not whitelist the plugin assembly.")
        if set(declared) != expected_assemblies:
            missing = sorted(expected_assemblies - set(declared))
            extra = sorted(set(declared) - expected_assemblies)
            raise PackageError(
                f"The package assembly whitelist does not match its dependencies (missing {missing}, extra {extra})."
            )
        present = {Path(name).name for name in names}
        for name in sorted(managed):
            if name not in present:
                raise PackageError(f"The package is missing its declared managed dependency {name!r}.")
        for name in sorted(native):
            if name not in present:
                raise PackageError(f"The package is missing its declared native asset {name!r}.")
        # No file outside the explicit payload allow-list may ship (e.g. a Jellyfin core DLL).
        allowed = {plugin_dll, deps_name, "meta.json", "THIRD-PARTY-NOTICES.txt", *managed, *native}
        for name in names:
            if name.endswith("/"):
                continue
            leaf = Path(name).name
            if leaf not in allowed:
                raise PackageError(f"The package contains a file outside the allowed payload: {leaf!r}.")
        # The managed assemblies must be the versions the dependency manifest requires.
        for name, expected_version in sorted(managed.items()):
            if not expected_version:
                continue
            actual_version = read_assembly_version(bundle.read(f"{root}/{name}"))
            if actual_version is None:
                raise PackageError(f"The package assembly {name!r} has no readable version.")
            if actual_version != expected_version:
                raise PackageError(
                    f"The package assembly {name!r} is version {actual_version}, not the required {expected_version}."
                )
        entries = []
        for name in sorted(names):
            if name.endswith("/"):
                continue
            data = bundle.read(name)
            entries.append({"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    if expected_entries:
        published = {path: digest for path, digest in expected_entries.items()}
        actual = {entry["path"]: entry["sha256"] for entry in entries}
        if published != actual:
            changed = sorted(
                path for path in set(published) | set(actual) if published.get(path) != actual.get(path)
            )
            raise PackageError(f"The package payload does not match the published per-file digests: {changed}.")
    return {
        "archive": str(archive),
        "archiveSha256": actual_sha256,
        "folder": root,
        "version": version,
        "guid": str(manifest.get("guid")),
        "targetAbi": str(manifest.get("targetAbi")),
        "runtime": SUPPORTED_RUNTIME,
        "assemblies": declared,
        "entries": entries,
    }


def read_assembly_version(data: bytes) -> str | None:
    """Read a .NET assembly's ``AssemblyVersion`` from the CLI metadata.

    Managed assemblies record their version in the metadata ``#~`` stream as
    ``major.minor.build.revision``. Reading it lets the verifier confirm the shipped DLL is
    the exact version the dependency manifest requires rather than trusting a mutable list.
    """
    if len(data) < 0x80 or data[:2] != b"MZ":
        return None
    pe_offset = int.from_bytes(data[0x3C:0x40], "little")
    if data[pe_offset:pe_offset + 4] != b"PE\0\0":
        return None
    sections = int.from_bytes(data[pe_offset + 6:pe_offset + 8], "little")
    optional_size = int.from_bytes(data[pe_offset + 20:pe_offset + 22], "little")
    optional = pe_offset + 24
    magic = int.from_bytes(data[optional:optional + 2], "little")
    directories = optional + (96 if magic == 0x10B else 112)
    section_table = optional + optional_size
    section_ranges = []
    for index in range(sections):
        base = section_table + index * 40
        section_ranges.append((
            int.from_bytes(data[base + 12:base + 16], "little"),
            int.from_bytes(data[base + 8:base + 12], "little"),
            int.from_bytes(data[base + 20:base + 24], "little"),
            int.from_bytes(data[base + 16:base + 20], "little"),
        ))

    def rva_to_offset(rva: int) -> int | None:
        for virtual_address, virtual_size, raw_pointer, raw_size in section_ranges:
            if virtual_address <= rva < virtual_address + max(virtual_size, raw_size):
                return raw_pointer + (rva - virtual_address)
        return None

    cli_rva = int.from_bytes(data[directories + 14 * 8:directories + 14 * 8 + 4], "little")
    cli_offset = rva_to_offset(cli_rva) if cli_rva else None
    if cli_offset is None:
        return None
    metadata_rva = int.from_bytes(data[cli_offset + 8:cli_offset + 12], "little")
    metadata = rva_to_offset(metadata_rva) if metadata_rva else None
    if metadata is None or data[metadata:metadata + 4] != b"BSJB":
        return None
    version_length = int.from_bytes(data[metadata + 12:metadata + 16], "little")
    cursor = metadata + 16 + version_length
    cursor += (-(cursor - metadata)) % 4
    stream_count = int.from_bytes(data[cursor + 2:cursor + 4], "little")
    cursor += 4
    streams: dict[str, int] = {}
    for _ in range(stream_count):
        offset = int.from_bytes(data[cursor:cursor + 4], "little")
        name_start = cursor + 8
        name_end = data.index(b"\0", name_start)
        streams[data[name_start:name_end].decode("ascii", "ignore")] = metadata + offset
        cursor = name_end + 1
        cursor += (-(cursor - metadata)) % 4
    if "#~" not in streams:
        return None
    tables = streams["#~"]
    heap_sizes = data[tables + 6]
    valid = int.from_bytes(data[tables + 8:tables + 16], "little")
    cursor = tables + 24
    row_counts: dict[int, int] = {}
    for table in range(64):
        if valid & (1 << table):
            row_counts[table] = int.from_bytes(data[cursor:cursor + 4], "little")
            cursor += 4
    if 0x20 not in row_counts:
        return None

    def heap_size(flag: int) -> int:
        return 4 if heap_sizes & flag else 2

    def simple_index(table: int) -> int:
        return 4 if row_counts.get(table, 0) >= 0x10000 else 2

    def coded_index(tables_in: tuple[int, ...], bits: int) -> int:
        return 4 if max(row_counts.get(table, 0) for table in tables_in) >= (1 << (16 - bits)) else 2

    sizes = {
        0x00: 2 + heap_size(0x01) + heap_size(0x02) * 3,
        0x01: coded_index((0x00, 0x1A, 0x23, 0x01), 2) + heap_size(0x01) * 2,
        0x02: 4 + heap_size(0x01) * 2 + coded_index((0x02, 0x01, 0x1B), 2) + simple_index(0x04) + simple_index(0x06),
        0x03: simple_index(0x04),
        0x04: 2 + heap_size(0x01) + heap_size(0x02),
        0x05: simple_index(0x06),
        0x06: 4 + 2 + 2 + heap_size(0x01) + heap_size(0x02) + simple_index(0x08),
        0x07: simple_index(0x08),
        0x08: 2 + 2 + heap_size(0x01),
        0x09: simple_index(0x02) + coded_index((0x02, 0x01, 0x1B), 2),
        0x0A: coded_index((0x02, 0x01, 0x1A, 0x06, 0x1B), 3) + heap_size(0x01) + heap_size(0x02),
        0x0B: 2 + coded_index((0x04, 0x08, 0x17), 2) + heap_size(0x02),
        0x0C: coded_index((0x06, 0x04, 0x01, 0x02, 0x08, 0x09, 0x0A, 0x00, 0x0E, 0x17, 0x14, 0x11, 0x1A, 0x1B, 0x20, 0x23, 0x26, 0x27, 0x28, 0x2A, 0x2C), 5)
        + coded_index((0x06, 0x0A), 3) + heap_size(0x02),
        0x0D: coded_index((0x04, 0x08), 1) + heap_size(0x02),
        0x0E: 2 + coded_index((0x02, 0x06, 0x20), 2) + heap_size(0x02),
        0x0F: 2 + 4 + simple_index(0x02),
        0x10: 4 + simple_index(0x04),
        0x11: heap_size(0x02),
        0x12: simple_index(0x02) + simple_index(0x14),
        0x13: simple_index(0x14),
        0x14: 2 + heap_size(0x01) + coded_index((0x02, 0x01, 0x1B), 2),
        0x15: simple_index(0x02) + simple_index(0x17),
        0x16: simple_index(0x17),
        0x17: 2 + heap_size(0x01) + heap_size(0x02),
        0x18: 2 + simple_index(0x06) + coded_index((0x14, 0x17), 1),
        0x19: simple_index(0x02) + coded_index((0x06, 0x0A), 1) * 2,
        0x1A: heap_size(0x01),
        0x1B: heap_size(0x02),
        0x1C: 2 + coded_index((0x04, 0x06), 1) + heap_size(0x01) + simple_index(0x1A),
        0x1D: 4 + simple_index(0x04),
        0x1E: 4 + 4,
        0x1F: 4,
    }
    cursor = tables + 24 + 4 * sum(1 for table in range(64) if valid & (1 << table))
    for table in range(0x20):
        cursor += row_counts.get(table, 0) * sizes[table]
    hash_algorithm = int.from_bytes(data[cursor:cursor + 4], "little")
    major = int.from_bytes(data[cursor + 4:cursor + 6], "little")
    minor = int.from_bytes(data[cursor + 6:cursor + 8], "little")
    build = int.from_bytes(data[cursor + 8:cursor + 10], "little")
    revision = int.from_bytes(data[cursor + 10:cursor + 12], "little")
    if hash_algorithm == 0 and major == 0 and minor == 0 and build == 0 and revision == 0:
        return None
    return f"{major}.{minor}.{build}.{revision}"


def write_sidecars(output_dir: Path, archive: Path, identity: dict[str, object], entries: list[dict[str, object]]) -> tuple[Path, Path]:
    digest = sha256_file(archive)
    manifest_path = sidecar_manifest_path(archive)
    digest_path = output_dir / (archive.name + ".sha256")
    manifest_path.write_text(
        json.dumps({"archive": archive.name, "archiveSha256": digest, **identity, "entries": entries}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    digest_path.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    return manifest_path, digest_path


def package(configuration: str, runtime: str, output_dir: Path, explicit_revision: str | None, keep_publish: Path | None) -> dict[str, object]:
    manifest = load_plugin_manifest()
    version = str(manifest["version"])
    revision = source_revision(explicit_revision)
    clean, dirty = worktree_is_clean()
    if not clean:
        raise PackageError(
            "The worktree has uncommitted tracked changes; the candidate must be built from a committed tree.\n" + dirty
        )
    sdk = sdk_version()
    inputs_digest = build_input_digest()
    lock_digest = sha256_file(LOCK_FILE) if LOCK_FILE.is_file() else ""
    build_command = [
        "dotnet", "publish", str(PROJECT_FILE.relative_to(ROOT)),
        "--configuration", configuration, "--runtime", runtime, "--self-contained", "false",
        f"-p:SourceRevisionId={revision}",
    ]
    publish_dir = keep_publish if keep_publish is not None else publish(configuration, runtime, revision)
    try:
        files, identity = build_archive_layout(
            publish_dir, manifest, version, revision, sdk, runtime, configuration,
            build_inputs_sha256=inputs_digest, lock_file_sha256=lock_digest, build_command=build_command,
        )
        archive = output_dir / f"{ARCHIVE_BASENAME}.zip"
        if archive.exists():
            archive.unlink()
        write_archive(archive, files)
        # Validate the final artifact through the same consumer path that installation uses,
        # first structurally, then against the just-written published digest.
        verification = verify_archive(archive)
        manifest_path, digest_path = write_sidecars(output_dir, archive, identity, verification["entries"])
        expected_sha, expected_entries = expected_from_sidecar(archive)
        verify_archive(archive, expected_sha256=expected_sha, expected_entries=expected_entries)
    finally:
        if keep_publish is None:
            shutil.rmtree(publish_dir, ignore_errors=True)
    return {
        "status": "PASS",
        "archive": str(archive),
        "archiveSha256": verification["archiveSha256"],
        "manifest": str(manifest_path),
        "digest": str(digest_path),
        "pluginVersion": version,
        "guid": manifest["guid"],
        "targetAbi": manifest["targetAbi"],
        "runtime": runtime,
        "configuration": configuration,
        "sdk": sdk,
        "sourceRevision": revision,
        "buildInputsSha256": inputs_digest,
        "lockFileSha256": lock_digest,
        "buildCommand": build_command,
        "entries": verification["entries"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", default="Release")
    parser.add_argument("--runtime", default=SUPPORTED_RUNTIME)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-revision", help="Explicit full source commit SHA; must equal the current HEAD.")
    parser.add_argument("--verify", type=Path, help="Validate an existing archive instead of building one.")
    args = parser.parse_args()
    try:
        if args.verify is not None:
            archive = args.verify.resolve()
            expected_sha, expected_entries = expected_from_sidecar(archive)
            if expected_sha is None:
                raise PackageError(
                    f"The archive {archive} has no published sidecar manifest; cannot verify it against a trusted expected digest."
                )
            print(json.dumps({"status": "PASS", **verify_archive(archive, expected_sha256=expected_sha,
                              expected_entries=expected_entries),
                              "verifiedAgainstSidecar": True}, ensure_ascii=False, indent=2))
            return 0
        result = package(args.configuration, args.runtime, args.output_dir.resolve(), args.source_revision, None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (PackageError, OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
