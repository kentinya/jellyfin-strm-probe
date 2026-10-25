#!/usr/bin/env python3
"""Read-only checks for this repository's Slice/Task contracts."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT = re.compile(r"[0-9a-f]{40}")
TASK_STATUSES = {"PLANNED", "IN PROGRESS", "READY FOR B REVIEW", "FIX REQUIRED"}
SLICE_STATUSES = {"PLANNED", "ACTIVE", "FIX REQUIRED", "READY FOR A REVIEW", "PASS / CLOSED"}
WORKFLOW_FILES = (
    "docs/agent-experience/slice-owner-architect-final-reviewer.md",
    "docs/agent-experience/task-planner-reviewer.md",
    "docs/agent-experience/developer-implementation-role.md",
)
# Only maintained governance files are required; retired plans live in Git history.
REQUIRED_FILES = (
    "AGENTS.md", "CLAUDE.md", "README.md", "SLICE.md", "TASK.md",
    "Task/TEMPLATE.md", "docs/scope.md",
    "docs/development-workflow.md", "docs/requirements.md", "docs/architecture.md",
    "docs/product-experience.md", "docs/roadmap.md", "docs/progress.md",
    "docs/compatibility.md", "docs/test-matrix.md", "docs/references.md",
    "scripts/check_governance.py", "tests/test_governance.py",
    ".github/workflows/quality.yml", ".gitignore", ".gitattributes", ".editorconfig",
)


def field(document: str, name: str) -> str:
    matches = re.findall(rf"^{re.escape(name)}: *([^\n]+)$", document, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {name} field")
    return matches[0].strip()


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise ValueError(f"git {args[0]}: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def require_ancestor(ancestor: str, descendant: str, label: str) -> None:
    if not COMMIT.fullmatch(ancestor):
        raise ValueError(f"{label} must be a full commit SHA")
    git("cat-file", "-e", f"{ancestor}^{{commit}}")
    git("merge-base", "--is-ancestor", ancestor, descendant)


def roadmap_rows(document: str) -> dict[int, str]:
    rows: dict[int, str] = {}
    for line in document.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) != 4:
            continue
        match = re.match(r"^(\d+) — ", cells[0])
        if not match:
            continue
        slice_id = int(match[1])
        if slice_id in rows or cells[2] not in {"PLANNED", "ACTIVE", "PASS / CLOSED"}:
            raise ValueError("Duplicate Slice or invalid status in Roadmap")
        rows[slice_id] = cells[2]
    if not rows:
        raise ValueError("Roadmap contains no Slice rows")
    return rows


def check_files() -> None:
    seen: set[str] = set()
    for name in (*REQUIRED_FILES, *WORKFLOW_FILES):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name in seen:
            raise ValueError("Invalid or duplicate governance path")
        if relative.parts[0] in {".git", ".aws", ".agents", ".codex"}:
            raise ValueError("Private metadata cannot be included in governance files")
        seen.add(name)
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            kind = "workflow file" if name in WORKFLOW_FILES else "file"
            raise ValueError(f"Required {kind} missing or symbolic: {name}")


def check(bootstrap: bool) -> None:
    check_files()
    slice_text = (ROOT / "SLICE.md").read_text("utf-8")
    task_text = (ROOT / "TASK.md").read_text("utf-8")
    roadmap_text = (ROOT / "docs/roadmap.md").read_text("utf-8")
    slice_id = int(field(slice_text, "Slice ID"))
    status = field(slice_text, "Status")
    base = field(slice_text, "Base SHA")
    implementation = field(slice_text, "Implementation Head")
    rows = roadmap_rows(roadmap_text)
    no_task = task_text.splitlines()[0] == "# NO ACTIVE IMPLEMENTATION TASK"

    if bootstrap:
        try:
            git("rev-parse", "--verify", "HEAD")
        except ValueError:
            pass
        else:
            raise ValueError("HEAD exists; use the committed governance check instead")
        if status != "PLANNED" or base != "NOT SET" or implementation != "NOT SET":
            raise ValueError("Bootstrap requires a PLANNED Slice with NOT SET SHAs")
        if not no_task or rows.get(slice_id) != "PLANNED" or any(
            row != "PLANNED" for row in rows.values()
        ):
            raise ValueError("Bootstrap cannot authorize an active Task or Slice")
        return

    head = git("rev-parse", "--verify", "HEAD").strip()
    if slice_text != git("show", "HEAD:SLICE.md"):
        raise ValueError("SLICE.md differs from committed HEAD; checkpoint the contract first")
    if roadmap_text != git("show", "HEAD:docs/roadmap.md"):
        raise ValueError("Roadmap differs from committed HEAD; checkpoint the contract first")
    if status not in SLICE_STATUSES:
        raise ValueError("Invalid committed Slice status")
    require_ancestor(base, head, "Slice Base SHA")
    if implementation != "NOT SET":
        require_ancestor(implementation, head, "Implementation Head")
        require_ancestor(base, implementation, "Slice Base SHA")
    if status in {"READY FOR A REVIEW", "PASS / CLOSED"} and implementation == "NOT SET":
        raise ValueError("Final review/closure requires a real Implementation Head")
    expected_row = status if status in {"PLANNED", "PASS / CLOSED"} else "ACTIVE"
    if rows.get(slice_id) != expected_row:
        raise ValueError("Committed Roadmap status does not match the Slice")
    active_rows = [number for number, row in rows.items() if row == "ACTIVE"]
    if active_rows != ([] if status in {"PLANNED", "PASS / CLOSED"} else [slice_id]):
        raise ValueError("Only the current Slice may be ACTIVE")
    if no_task:
        if status == "FIX REQUIRED":
            raise ValueError("FIX REQUIRED needs a corrective Task")
        return
    if status not in {"ACTIVE", "FIX REQUIRED"}:
        raise ValueError("An active Task requires an ACTIVE or FIX REQUIRED Slice")
    if int(field(task_text, "Parent Slice")) != slice_id:
        raise ValueError("Task Parent Slice does not match the committed Slice")
    task_id = field(task_text, "Task ID")
    if not re.fullmatch(rf"{slice_id}\.\d+", task_id):
        raise ValueError("Task ID must belong to its Parent Slice")
    if field(task_text, "Status") not in TASK_STATUSES:
        raise ValueError("Invalid active Task status")
    task_base = field(task_text, "Task Base")
    require_ancestor(task_base, head, "Task Base")
    require_ancestor(base, task_base, "Slice Base SHA")
    if field(task_text, "Difficulty") not in {"Low", "Medium", "High"}:
        raise ValueError("Invalid Task difficulty")
    if field(task_text, "Test Level") not in {"T0", "T1", "T2", "T3", "T4"}:
        raise ValueError("Invalid Task test level")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", action="store_true", help="Check planning only, before Git init")
    args = parser.parse_args()
    try:
        check(args.bootstrap)
    except (ValueError, OSError, KeyError, TypeError, IndexError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    if args.bootstrap:
        print("PASS: planning files only; no Git activation or product acceptance claimed")
    else:
        print("PASS: committed Slice/Task governance; no product test acceptance claimed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
