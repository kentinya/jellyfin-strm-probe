#!/usr/bin/env python3
"""Create local Git checkpoints once the normal .git directory is writable."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "Jellyfin STRM Probe Optimizer 完整开发方案 V3.0.md"
SOURCE_SHA256 = "d236cab6b3992636b524f30bbe49a91adb9ef5d6b7010ed5695cae7d65f228ae"


def run(command: list[str]) -> str:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "Command failed")
    return result.stdout


def git(*args: str) -> str:
    return run(["git", "-c", "core.autocrlf=false", "-C", str(ROOT), *args])


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text("utf-8")
    if text.count(old) != 1:
        raise ValueError(f"Expected unchanged bootstrap marker in {path}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def preflight() -> list[str]:
    if any(name in os.environ for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")):
        raise ValueError("Unset custom Git directory/index environment variables before initialization")
    manifest = json.loads((ROOT / "scripts/bootstrap-manifest.json").read_text("utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported bootstrap manifest schema")
    paths: list[str] = []
    for entry in manifest["files"]:
        name = entry["path"]
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name in paths:
            raise ValueError("Invalid or duplicate bootstrap path")
        if relative.parts[0] in {".git", ".aws", ".agents", ".codex"}:
            raise ValueError("Private metadata cannot be staged")
        target = ROOT / relative
        if not target.is_file() or target.is_symlink():
            raise ValueError(f"Required regular file missing: {name}")
        if name != "scripts/bootstrap-manifest.json":
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual != entry["sha256"]:
                raise ValueError(f"Baseline file changed: {name}; review it before manual initialization")
        paths.append(name)
    if SOURCE not in paths or hashlib.sha256((ROOT / SOURCE).read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Original proposal is missing or changed")
    run([sys.executable, "scripts/check_governance.py", "--bootstrap"])
    metadata = ROOT / ".git"
    if metadata.exists() and (not metadata.is_dir() or any(metadata.iterdir())):
        raise ValueError("Existing Git metadata found; initialization will not overwrite it")
    return paths


def initialize(paths: list[str], author_name: str, author_email: str) -> None:
    if not author_name.strip() or not author_email.strip() or any(
        char in author_name + author_email for char in "\r\n"
    ):
        raise ValueError("Provide non-empty, single-line commit author values")

    def commit(message: str) -> str:
        git(
            "-c", f"user.name={author_name}", "-c", f"user.email={author_email}",
            "-c", "commit.gpgsign=false", "commit", "-m", message,
        )
        return git("rev-parse", "HEAD").strip()

    # Fail at the normal Git boundary before changing any planning document.
    git("init", "-b", "main")
    seed = [SOURCE, ".gitignore", ".gitattributes"]
    git("add", "--", *seed)
    baseline = commit("docs: preserve original V3.0 proposal and repository baseline")

    replace_once("SLICE.md", "Status: PLANNED", "Status: ACTIVE")
    replace_once("SLICE.md", "Base SHA: NOT SET", f"Base SHA: {baseline}")
    replace_once(
        "SLICE.md",
        "这是待激活合同。`.git` 只读，尚无合同提交；Git 可写后由初始化脚本使用真实基线 SHA 激活。当前不能把此文档当作实施准入或产品已验收的声明。",
        "合同以原始方案基线提交为 Base 激活。当前尚无实现检查点或产品验收；Task 计划必须在本合同提交后进行。",
    )
    replace_once(
        "docs/roadmap.md", "| PLANNED | 可写 Git 与隔离 Jellyfin 环境 |",
        "| ACTIVE | 已提交原始基线与合同；需要隔离 Jellyfin 环境 |",
    )
    replace_once(
        "docs/roadmap.md",
        "Slice 1 合同已写为规划文件，但 `.git` 只读，尚无合同激活检查点。Git 可写后由初始化脚本提交原始基线、激活 Slice 1，再计划 Task 1.1。",
        "Slice 1 合同已经本地提交并激活；Task 1.1 在合同提交后计划。后续 Slice 保持 PLANNED，未开始产品验收。",
    )
    replace_once(
        "docs/architecture.md",
        "Git 初始化因 `.git` 只读未完成；当前合同未激活。",
        "Git 基线与 Slice 1 合同已本地提交；尚无产品实现。",
    )
    replace_once(
        "docs/scope.md", "没有产品实现，没有活动实施 Task，没有产品验收 PASS。Git 可写并完成合同检查点后，启动 Slice 1 内的 Task 1.1；其余 Slice 保持规划状态。",
        "没有产品实现，没有产品验收 PASS。Slice 1 合同已经激活，随后计划其内的 Task 1.1；其余 Slice 保持规划状态。",
    )
    replace_once(
        "README.md",
        "当前工作区 `.git` 是只读文件系统；已尝试 `git init -b main`，初始化未成功。此时 `SLICE.md` 保持 `PLANNED`，`TASK.md` 保持无活动实施任务。不会通过另一套 Git 目录绕开只读限制。",
        "原规划环境的 `.git` 曾为只读文件系统。正常目录可写后，本地 Git 基线与 Slice 1 合同已初始化，首个 Task 在合同提交后计划；未配置远程或推送。",
    )
    replace_once(
        "docs/progress.md", "- 当前合同：Slice 1，PLANNED，Git 合同激活尚未完成。",
        "- 当前合同：Slice 1，ACTIVE，已提交真实 Base 与激活合同。",
    )
    replace_once(
        "docs/progress.md", "- Git 初始化限制：`.git` 为只读文件系统；初始化工具就绪但未完成提交。",
        "- Git：正常 .git 已创建本地检查点；未配置远程或推送。",
    )
    git("add", "--", *[path for path in paths if path not in seed])
    activation = commit("docs: activate Slice 1 and establish plugin development workflow")
    run([sys.executable, "scripts/check_governance.py"])

    draft = (ROOT / "Task/FIRST_TASK.md").read_text("utf-8")
    draft = draft.replace(
        "这是首次初始化专用草案，尚未激活。初始化脚本将其写入根 TASK.md，并把下列 DRAFT／占位 SHA 改为 PLANNED／真实激活提交。后续任务使用 Task/TEMPLATE.md，不重复激活本草案。",
        "当前 Task 在已提交的 Slice 1 合同内计划。Task Base 是合同激活检查点；插件尚未实施，全部产品测试尚未运行。",
        1,
    ).replace("Status: DRAFT", "Status: PLANNED", 1).replace("{{ACTIVATION_SHA}}", activation)
    (ROOT / "TASK.md").write_text(draft, encoding="utf-8")
    replace_once(
        "docs/progress.md", "- 当前 Task：无活动实施任务；首个 Task 草案见 [模板](../Task/FIRST_TASK.md)。",
        "- 当前 Task：Task 1.1，PLANNED，见 [TASK.md](../TASK.md)。",
    )
    run([sys.executable, "scripts/check_governance.py"])
    git("add", "--", "TASK.md", "docs/progress.md")
    planned = commit("docs: plan Task 1.1 within the committed Slice 1 contract")
    run([sys.executable, "scripts/check_governance.py"])
    print(f"Base: {baseline}\nSlice activation: {activation}\nTask plan: {planned}")
    print("Local checkpoints created; no remote or push; product implementation has not started")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify unchanged baseline files without Git writes")
    parser.add_argument("--author-name", default="Codex")
    parser.add_argument("--author-email", default="codex@localhost")
    args = parser.parse_args()
    try:
        paths = preflight()
        if args.check:
            print("PASS: unchanged bootstrap files; Git writability was not tested")
        else:
            initialize(paths, args.author_name, args.author_email)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        print("No permission workaround or history reset was performed. Inspect any partial checkpoints before retrying.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
