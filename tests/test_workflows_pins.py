#!/usr/bin/env python3
"""Every `uses:` in `.github/workflows/` is local or pinned by commit sha (task 9.10).

`scripts/check_action.py` holds `action.yml` to the sha-pin rule, and nothing held the
workflows to it: a pasted `@v4` would get a green pull request and only Scorecard's
`Pinned-Dependencies` would object, after the merge. So this walks every workflow file and
requires each reference to be `./` or `owner/repo@<40 hex> # vX.Y.Z`, the comment being the
only record of which release the sha was read from.

The pattern is `check_action.SHA_PIN`, not a copy: two definitions of a pin drift. Its comment
group is optional because `check_action.py` reports a missing comment separately; here a
missing comment is refused outright. No YAML parser, like the rest of this suite (D-02).

Run: python3 -m unittest discover -s tests -t tests
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
sys.path.insert(0, str(ROOT / "scripts"))

from check_action import SHA_PIN  # noqa: E402

USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(.*?)\s*$")
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1"


def workflow_files(directory: Path) -> list[Path]:
    return sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])


def references(directory: Path) -> list[tuple[Path, int, str]]:
    """(file, line number, value) for every `uses:` key, comment lines skipped."""
    found: list[tuple[Path, int, str]] = []
    for path in workflow_files(directory):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            uses = USES.match(line)
            if uses:
                found.append((path, number, uses.group(1)))
    return found


def pin_problems(directory: Path) -> list[str]:
    """One line per reference that is neither local nor a commented sha pin."""
    problems: list[str] = []
    for path, number, value in references(directory):
        if value.startswith("./"):
            continue
        pinned = SHA_PIN.match(value)
        where = f"{path.name}:{number}"
        if pinned is None:
            problems.append(f"{where}: {value} is not pinned by a full 40-character commit sha")
        elif pinned.group(1) is None:
            problems.append(
                f"{where}: {value} has no '# vX.Y.Z' comment naming the release the sha "
                "resolved from"
            )
    return problems


class WorkflowPins(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = TemporaryDirectory()
        self.tmp = Path(self._directory.name)

    def tearDown(self) -> None:
        self._directory.cleanup()

    def fixture(self, uses: str) -> list[str]:
        (self.tmp / "fixture.yml").write_text(
            "name: fixture\non: push\njobs:\n  one:\n    runs-on: ubuntu-latest\n"
            f"    steps:\n      - uses: {uses}\n",
            encoding="utf-8",
        )
        return pin_problems(self.tmp)

    def test_the_shipped_workflows_hold(self) -> None:
        self.assertEqual(pin_problems(WORKFLOWS), [])

    def test_the_walk_reads_every_workflow(self) -> None:
        # A walk that finds nothing passes everything, so the shipped tree has to yield
        # references from more than one file, and the local `uses: ./` has to be among them.
        found = references(WORKFLOWS)
        self.assertGreater(len({path for path, _, _ in found}), 1)
        self.assertIn("./", {value for _, _, value in found})

    def test_a_local_reference_passes(self) -> None:
        self.assertEqual(self.fixture("./"), [])

    def test_a_commented_sha_pin_passes(self) -> None:
        self.assertEqual(self.fixture(CHECKOUT), [])

    def test_a_floating_tag_fails_with_file_and_line(self) -> None:
        problems = self.fixture("actions/checkout@v4")
        self.assertEqual(
            problems,
            ["fixture.yml:7: actions/checkout@v4 is not pinned by a full 40-character commit sha"],
        )

    def test_an_uncommented_sha_fails_with_file_and_line(self) -> None:
        bare = CHECKOUT.split(" #")[0]
        problems = self.fixture(bare)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith(f"fixture.yml:7: {bare} has no"), problems[0])

    def test_a_short_sha_fails(self) -> None:
        self.assertEqual(len(self.fixture("actions/checkout@3d3c42e # v7.0.1")), 1)

    def test_a_comment_line_is_not_a_reference(self) -> None:
        (self.tmp / "fixture.yml").write_text("# uses: actions/checkout@v4\n", encoding="utf-8")
        self.assertEqual(pin_problems(self.tmp), [])

    def test_a_yaml_extension_is_walked_too(self) -> None:
        (self.tmp / "fixture.yaml").write_text("      - uses: actions/checkout@v4\n", "utf-8")
        self.assertEqual(len(pin_problems(self.tmp)), 1)


if __name__ == "__main__":
    unittest.main()
