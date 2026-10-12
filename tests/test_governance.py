"""Exercise committed governance states in disposable Git repositories."""

from __future__ import annotations

import hashlib
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NO_TASK = "# NO ACTIVE IMPLEMENTATION TASK\n\nNo implementation is authorized.\n"


def replace_field(path: Path, name: str, value: str) -> None:
    document, count = re.subn(
        rf"^{re.escape(name)}: [^\n]+$", f"{name}: {value}",
        path.read_text("utf-8"), flags=re.MULTILINE,
    )
    if count != 1:
        raise AssertionError(f"Expected one {name} in {path.name}")
    path.write_text(document, encoding="utf-8")


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Governance fixture",
         "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
         "-c", "core.hooksPath=/dev/null", *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


class GovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.shared = tempfile.TemporaryDirectory(prefix="jf-governance-seed-")
        cls.addClassCleanup(cls.shared.cleanup)
        cls.seed = Path(cls.shared.name) / "seed"
        cls.seed.mkdir()
        checker = runpy.run_path(str(ROOT / "scripts/check_governance.py"))
        paths = [*checker["REQUIRED_FILES"], *checker["WORKFLOW_FILES"]]
        cls.source = checker["SOURCE"]
        cls.source_sha256 = checker["SOURCE_SHA256"]
        for name in paths:
            target = cls.seed / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        # Fixture contracts are independent of future product Slice/Task IDs.
        (cls.seed / "SLICE.md").write_text(
            "# Fixture Slice\n\nSlice ID: 1\nStatus: PLANNED\n"
            "Base SHA: NOT SET\nImplementation Head: NOT SET\n",
            encoding="utf-8",
        )
        cls.task = (
            "# Fixture Task\n\nTask ID: 1.1\nParent Slice: 1\n"
            "Status: PLANNED\nTask Base: NOT SET\n"
            "Difficulty: High\nTest Level: T4\nPlanner / Reviewer: B\n"
        )
        (cls.seed / "TASK.md").write_text(NO_TASK, encoding="utf-8")
        roadmap = cls.seed / "docs/roadmap.md"
        roadmap.write_text(
            "| Slice | Goal | Status | Dependency |\n"
            "|---|---|---|---|\n"
            "| 1 — First | Fixture | PLANNED | None |\n"
            "| 2 — Second | Fixture | PLANNED | First |\n"
            "| 3 — Third | Fixture | PLANNED | Second |\n",
            encoding="utf-8",
        )
        git(cls.seed, "init", "-b", "main")
        git(cls.seed, "add", "--", *paths)
        git(cls.seed, "commit", "-m", "fixture: seed")
        cls.base = git(cls.seed, "rev-parse", "HEAD")
        replace_field(cls.seed / "SLICE.md", "Status", "ACTIVE")
        replace_field(cls.seed / "SLICE.md", "Base SHA", cls.base)
        roadmap.write_text(
            roadmap.read_text("utf-8").replace("| PLANNED |", "| ACTIVE |", 1),
            encoding="utf-8",
        )
        git(cls.seed, "add", "--", "SLICE.md", "docs/roadmap.md")
        git(cls.seed, "commit", "-m", "fixture: activation")
        cls.activation = git(cls.seed, "rev-parse", "HEAD")
        (cls.seed / "TASK.md").write_text(cls.task, encoding="utf-8")
        replace_field(cls.seed / "TASK.md", "Task Base", cls.activation)
        git(cls.seed, "add", "--", "TASK.md")
        git(cls.seed, "commit", "-m", "fixture: Task plan")

    def setUp(self) -> None:
        sandbox = tempfile.TemporaryDirectory(prefix="jf-governance-case-")
        self.addCleanup(sandbox.cleanup)
        self.repo = Path(sandbox.name) / "repo"
        shutil.copytree(self.seed, self.repo)

    def checkpoint(self) -> None:
        git(self.repo, "add", "--", "SLICE.md", "docs/roadmap.md", "TASK.md")
        git(self.repo, "commit", "-m", "fixture: state change")

    def planned(self, *, no_task: bool = True) -> None:
        replace_field(self.repo / "SLICE.md", "Status", "PLANNED")
        roadmap = self.repo / "docs/roadmap.md"
        roadmap.write_text(
            roadmap.read_text("utf-8").replace("| ACTIVE |", "| PLANNED |"),
            encoding="utf-8",
        )
        if no_task:
            (self.repo / "TASK.md").write_text(NO_TASK, encoding="utf-8")

    def assert_guard(self, success: bool, message: str = "", *args: str) -> None:
        # The checker must remain read-only even when a contract is invalid.
        before = git(self.repo, "status", "--porcelain")
        result = subprocess.run(
            [sys.executable, "scripts/check_governance.py", *args],
            cwd=self.repo, capture_output=True, text=True, check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0 if success else 1, output)
        self.assertIn(message, output)
        self.assertEqual(git(self.repo, "status", "--porcelain"), before)

    def test_active_task_accepts_ancestor_bases(self) -> None:
        self.assert_guard(True, "PASS: committed")

    def test_committed_planned_without_task(self) -> None:
        self.planned()
        self.checkpoint()
        self.assert_guard(True)

    def test_frozen_snapshot_keeps_real_implementation_head(self) -> None:
        implementation = git(self.repo, "rev-parse", "HEAD")
        self.planned()
        replace_field(self.repo / "SLICE.md", "Implementation Head", implementation)
        with (self.repo / "SLICE.md").open("a", encoding="utf-8") as document:
            document.write("\nDevelopment Hold: FROZEN BY USER\n")
        self.checkpoint()
        self.assert_guard(True)

    def test_planned_rejects_active_task(self) -> None:
        self.planned(no_task=False)
        self.checkpoint()
        self.assert_guard(False, "An active Task requires")

    def test_planned_rejects_unset_base(self) -> None:
        self.planned()
        replace_field(self.repo / "SLICE.md", "Base SHA", "NOT SET")
        self.checkpoint()
        self.assert_guard(False, "Slice Base SHA must be a full")

    def test_planned_rejects_active_roadmap(self) -> None:
        replace_field(self.repo / "SLICE.md", "Status", "PLANNED")
        (self.repo / "TASK.md").write_text(NO_TASK, encoding="utf-8")
        self.checkpoint()
        self.assert_guard(False, "Roadmap status does not match")

    def test_planned_rejects_another_active_slice(self) -> None:
        self.planned()
        roadmap = self.repo / "docs/roadmap.md"
        roadmap.write_text(
            roadmap.read_text("utf-8")
            .replace("| PLANNED |", "| ACTIVE |", 2)
            .replace("| ACTIVE |", "| PLANNED |", 1),
            encoding="utf-8",
        )
        self.checkpoint()
        self.assert_guard(False, "Only the current Slice")

    def test_uncommitted_contract_is_rejected(self) -> None:
        replace_field(self.repo / "SLICE.md", "Status", "PLANNED")
        self.assert_guard(False, "SLICE.md differs from committed")

    def test_uncommitted_roadmap_is_rejected(self) -> None:
        roadmap = self.repo / "docs/roadmap.md"
        with roadmap.open("a", encoding="utf-8") as document:
            document.write("\nDraft priority change.\n")
        self.assert_guard(False, "Roadmap differs from committed")

    def test_task_parent_must_match(self) -> None:
        replace_field(self.repo / "TASK.md", "Parent Slice", "2")
        self.assert_guard(False, "Task Parent Slice does not match")

    def test_task_id_must_match(self) -> None:
        replace_field(self.repo / "TASK.md", "Task ID", "2.1")
        self.assert_guard(False, "Task ID must belong")

    def test_fabricated_base_is_rejected(self) -> None:
        replace_field(self.repo / "TASK.md", "Task Base", "f" * 40)
        self.assert_guard(False, "git cat-file")

    def test_nonancestor_base_is_rejected(self) -> None:
        tree = git(self.repo, "rev-parse", "HEAD^{tree}")
        disconnected = git(self.repo, "commit-tree", tree, "-m", "fixture: disconnected")
        replace_field(self.repo / "TASK.md", "Task Base", disconnected)
        self.assert_guard(False, "git merge-base")

    def test_bootstrap_cannot_bypass_committed_head(self) -> None:
        self.assert_guard(False, "HEAD exists", "--bootstrap")

    def test_bootstrap_only_accepts_unactivated_planning(self) -> None:
        self.planned()
        replace_field(self.repo / "SLICE.md", "Base SHA", "NOT SET")
        # Only this disposable fixture's metadata is removed, never workspace Git.
        shutil.rmtree(self.repo / ".git")
        result = subprocess.run(
            [sys.executable, "scripts/check_governance.py", "--bootstrap"],
            cwd=self.repo, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("planning files only", result.stdout)
        self.assertFalse((self.repo / ".git").exists())

    def test_missing_role_document_is_rejected(self) -> None:
        (self.repo / "docs/agent-experience/task-planner-reviewer.md").unlink()
        self.assert_guard(False, "Required workflow file missing")

    def test_current_proposal_is_immutable(self) -> None:
        digest = hashlib.sha256((self.repo / self.source).read_bytes()).hexdigest()
        self.assertEqual(digest, self.source_sha256)
        with (self.repo / self.source).open("a", encoding="utf-8") as document:
            document.write("\nUnauthorized edit.\n")
        self.assert_guard(False, "current V4.2 proposal was changed")

    def test_legacy_proposal_is_not_required(self) -> None:
        self.assertFalse(
            (self.repo / "Jellyfin STRM Probe Optimizer 完整开发方案 V3.0.md").exists()
        )
        self.assert_guard(True)

    def test_missing_current_proposal_is_rejected(self) -> None:
        (self.repo / self.source).unlink()
        self.assert_guard(False, "Required file missing or symbolic")

    def test_symbolic_current_proposal_is_rejected(self) -> None:
        source = self.repo / self.source
        copy = self.repo / "proposal-copy.md"
        source.rename(copy)
        source.symlink_to(copy.name)
        self.assert_guard(False, "Required file missing or symbolic")

    def test_missing_current_requirements_is_rejected(self) -> None:
        (self.repo / "docs/requirements.md").unlink()
        self.assert_guard(False, "Required file missing or symbolic")

    def test_review_requires_implementation(self) -> None:
        replace_field(self.repo / "SLICE.md", "Status", "READY FOR A REVIEW")
        (self.repo / "TASK.md").write_text(NO_TASK, encoding="utf-8")
        self.checkpoint()
        self.assert_guard(False, "requires a real Implementation Head")

    def test_corrective_slice_requires_task(self) -> None:
        replace_field(self.repo / "SLICE.md", "Status", "FIX REQUIRED")
        (self.repo / "TASK.md").write_text(NO_TASK, encoding="utf-8")
        self.checkpoint()
        self.assert_guard(False, "FIX REQUIRED needs a corrective Task")

    def test_closed_slice_without_task(self) -> None:
        replace_field(self.repo / "SLICE.md", "Status", "PASS / CLOSED")
        replace_field(
            self.repo / "SLICE.md", "Implementation Head",
            git(self.repo, "rev-parse", "HEAD"),
        )
        roadmap = self.repo / "docs/roadmap.md"
        roadmap.write_text(
            roadmap.read_text("utf-8").replace("| ACTIVE |", "| PASS / CLOSED |"),
            encoding="utf-8",
        )
        (self.repo / "TASK.md").write_text(NO_TASK, encoding="utf-8")
        self.checkpoint()
        self.assert_guard(True)


if __name__ == "__main__":
    unittest.main()
