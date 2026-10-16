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


def source_revision(explicit: str | None) -> str:
    if explicit:
        if not SOURCE_SHA.fullmatch(explicit):
            raise PackageError("The explicit source revision must be a full 40-character commit SHA.")
        return explicit
    result = run(["git", "rev-parse", "HEAD"], timeout=30)
    revision = result.stdout.strip()
    if result.returncode or not SOURCE_SHA.fullmatch(revision):
        raise PackageError("Could not determine a full source commit SHA; pass --source-revision explicitly.")
    return revision


def sdk_version() -> str:
    result = run([*DOTNET_INVOCATION, "--version"], timeout=60)
    version = result.stdout.strip()
    if result.returncode or not version:
        raise PackageError("The pinned local SDK is unavailable; run scripts/development_environment.py sdk first.")
    return version


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


def publish(configuration: str, runtime: str) -> Path:
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
    ])
    if result.returncode:
        raise PackageError("dotnet publish failed:\n" + (result.stderr.strip() or result.stdout.strip()))
    return destination


def payload_plan(publish_dir: Path, runtime: str) -> tuple[list[str], list[str], list[str]]:
    """Return (managed, native, all) relative file names required by the dependency manifest."""
    if runtime != SUPPORTED_RUNTIME:
        raise PackageError(f"Unsupported runtime {runtime!r}; this first version packages {SUPPORTED_RUNTIME} only.")
    deps_path = next(publish_dir.glob("*.deps.json"), None)
    if deps_path is None:
        raise PackageError("The publish output has no dependency manifest (*.deps.json).")
    deps = json.loads(deps_path.read_text(encoding="utf-8"))
    runtime_target = deps.get("runtimeTarget", {}).get("name")
    libraries = deps.get("targets", {}).get(runtime_target)
    if not libraries:
        raise PackageError("The dependency manifest has no runtime target section.")
    managed: set[str] = set()
    native: set[str] = set()
    for library, metadata in libraries.items():
        for asset in metadata.get("runtime", {}):
            managed.add(Path(asset).name)
        # A RID-specific publish target resolves native assets into a flat `native` section; the
        # framework-dependent target uses `runtimeTargets` with an explicit RID. Handle both shapes.
        for asset in metadata.get("native", {}):
            native.add(Path(asset).name)
        for asset, asset_metadata in metadata.get("runtimeTargets", {}).items():
            if asset_metadata.get("rid") != runtime or asset_metadata.get("assetType") != "native":
                continue
            native.add(Path(asset).name)
    if not managed:
        raise PackageError("The dependency manifest lists no managed runtime assets.")
    if not native:
        raise PackageError(f"The dependency manifest lists no {runtime} native runtime assets.")
    return sorted(managed), sorted(native), sorted(managed | native)


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


def verify_archive(archive: Path) -> dict[str, object]:
    """Validate an existing archive and return its identity; used before any deployment."""
    if not archive.is_file() or archive.is_symlink():
        raise PackageError(f"The package {archive} is missing or symbolic.")
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
            info = bundle.getinfo(name)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise PackageError(f"Symbolic link in archive: {name!r}.")
        required = f"{root}/meta.json"
        if required not in names:
            raise PackageError("The package has no meta.json.")
        manifest = json.loads(bundle.read(required))
        if str(manifest.get("guid", "")).lower() != PLUGIN_GUID:
            raise PackageError("The package GUID does not match the supported plugin GUID.")
        if manifest.get("targetAbi") != SUPPORTED_JELLYFIN_ABI:
            raise PackageError(f"The package targetAbi {manifest.get('targetAbi')!r} is not supported.")
        version = str(manifest.get("version", ""))
        if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version):
            raise PackageError(f"The package version {version!r} is not a four-part version.")
        assemblies = manifest.get("assemblies")
        if not isinstance(assemblies, list) or PROJECT.name + ".dll" not in assemblies:
            raise PackageError("The package meta.json does not whitelist the plugin assembly.")
        present = {Path(name).name for name in names}
        for assembly in assemblies:
            if Path(assembly).name not in present:
                raise PackageError(f"The package meta.json whitelists a missing assembly {assembly!r}.")
        deps_name = PROJECT.name + ".deps.json"
        if deps_name not in present:
            raise PackageError("The package has no dependency manifest.")
        deps = json.loads(bundle.read(f"{root}/{deps_name}"))
        runtime_target = deps.get("runtimeTarget", {}).get("name", "")
        if SUPPORTED_RUNTIME not in runtime_target:
            raise PackageError(f"The package dependency manifest targets {runtime_target!r}, not {SUPPORTED_RUNTIME}.")
        libraries = deps.get("targets", {}).get(runtime_target, {})
        native = [
            Path(asset).name
            for metadata in libraries.values()
            for asset in metadata.get("native", {})
        ]
        native.extend(
            Path(asset).name
            for metadata in libraries.values()
            for asset, info in metadata.get("runtimeTargets", {}).items()
            if info.get("rid") == SUPPORTED_RUNTIME and info.get("assetType") == "native"
        )
        if not native:
            raise PackageError("The package dependency manifest declares no Linux x64 native asset.")
        for name in native:
            if name not in present:
                raise PackageError(f"The package is missing its declared native asset {name!r}.")
        entries = []
        for name in sorted(names):
            if name.endswith("/"):
                continue
            data = bundle.read(name)
            entries.append({"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return {
        "archive": str(archive),
        "archiveSha256": sha256_file(archive),
        "folder": root,
        "version": version,
        "guid": str(manifest.get("guid")),
        "targetAbi": str(manifest.get("targetAbi")),
        "runtime": SUPPORTED_RUNTIME,
        "assemblies": assemblies,
        "entries": entries,
    }


def write_sidecars(output_dir: Path, archive: Path, identity: dict[str, object], entries: list[dict[str, object]]) -> tuple[Path, Path]:
    digest = sha256_file(archive)
    manifest_path = output_dir / (archive.stem + ".manifest.json")
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
    sdk = sdk_version()
    publish_dir = keep_publish if keep_publish is not None else publish(configuration, runtime)
    try:
        files, identity = build_archive_layout(publish_dir, manifest, version, revision, sdk, runtime, configuration)
        archive = output_dir / f"{ARCHIVE_BASENAME}.zip"
        if archive.exists():
            archive.unlink()
        write_archive(archive, files)
        verification = verify_archive(archive)
        manifest_path, digest_path = write_sidecars(output_dir, archive, identity, verification["entries"])
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
        "entries": verification["entries"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", default="Release")
    parser.add_argument("--runtime", default=SUPPORTED_RUNTIME)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-revision", help="Explicit full source commit SHA; defaults to git HEAD.")
    parser.add_argument("--verify", type=Path, help="Validate an existing archive instead of building one.")
    args = parser.parse_args()
    try:
        if args.verify is not None:
            print(json.dumps({"status": "PASS", **verify_archive(args.verify)}, ensure_ascii=False, indent=2))
            return 0
        result = package(args.configuration, args.runtime, args.output_dir.resolve(), args.source_revision, None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (PackageError, OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
