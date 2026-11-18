#!/usr/bin/env python3
"""`ci.yml` cancels a superseded pull request run, never one in progress on `main` (task 9.8).

Every push to a pull request pays for a full install, `check_action.py`, the suite, `ruff` and
`mypy`, and without a concurrency group the newest required check queues behind runs whose
commit nobody will merge. Cancelling is safe in this workflow because it never calls the
action and never writes anything, which `watch.yml` does: there a cancel can land between the
read and the write of the tracking issue, so that group keeps `cancel-in-progress: false`.

A run in progress on `main` must never be cancelled, because the push run on `main` is the
evidence for gate G1, so the cancel is keyed on the event rather than set to true.

The workflow is read as text, like `scripts/check_action.py` reads `action.yml`.

Run: python3 -m unittest discover -s tests -t tests
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"

GROUP = "${{ github.workflow }}-${{ github.ref }}"
CANCEL = "${{ github.event_name == 'pull_request' }}"


def top_level_block(lines: list[str], key: str) -> tuple[int, dict[str, str]] | None:
    """(line number, {child: value}) for a top-level mapping such as `concurrency:`."""
    for number, line in enumerate(lines, start=1):
        if line.rstrip() != f"{key}:":
            continue
        children: dict[str, str] = {}
        for child in lines[number:]:
            if child.strip().startswith("#"):
                continue
            found = re.fullmatch(r"  ([a-z-]+):\s*(.*?)\s*", child)
            if not found:
                break
            children[found.group(1)] = found.group(2)
        return number, children
    return None


class CiConcurrency(unittest.TestCase):
    def setUp(self) -> None:
        self.lines = CI.read_text(encoding="utf-8").splitlines()

    def concurrency(self) -> tuple[int, dict[str, str]]:
        block = top_level_block(self.lines, "concurrency")
        self.assertIsNotNone(block, "ci.yml has no top-level concurrency: block")
        assert block is not None
        return block

    def test_the_block_sits_before_jobs(self) -> None:
        number, _ = self.concurrency()
        jobs = self.lines.index("jobs:") + 1
        self.assertLess(number, jobs, f"ci.yml:{number}: concurrency: belongs before jobs:")

    def test_the_group_is_keyed_on_workflow_and_ref(self) -> None:
        number, children = self.concurrency()
        self.assertEqual(children.get("group"), GROUP, f"ci.yml:{number}: wrong group")

    def test_only_pull_request_runs_are_cancelled(self) -> None:
        number, children = self.concurrency()
        self.assertEqual(
            children.get("cancel-in-progress"),
            CANCEL,
            f"ci.yml:{number}: cancel-in-progress must be keyed on pull_request so a main run "
            "in progress is never cancelled",
        )

    def test_the_workflow_never_calls_the_action(self) -> None:
        # The reason a cancel is safe here. If ci.yml ever runs the action or gains a write
        # permission, a cancelled run can leave a half-written issue, and this group has to be
        # argued again rather than inherited.
        for number, line in enumerate(self.lines, start=1):
            if line.lstrip().startswith("#"):
                continue
            self.assertNotRegex(line, r"uses:\s*\./", f"ci.yml:{number}: calls the action")
            self.assertNotRegex(line, r":\s*write\b", f"ci.yml:{number}: grants a write")


if __name__ == "__main__":
    unittest.main()
