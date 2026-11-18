#!/usr/bin/env python3
"""The `ci / python` job carries a bounded `timeout-minutes` (task 9.9).

A job with no `timeout-minutes` inherits GitHub's 360-minute default, so a `pip` index that
never answers or a test waiting on a socket holds a runner for six hours before anything goes
red. The bound has to be an integer literal between 10 and 30: an expression or a unit suffix
is something a reader cannot check in the diff, and zero is not a bound at all.

The workflow is read as text, the same way `scripts/check_action.py` reads `action.yml`,
because the runner has no YAML parser and neither does this suite.

Run: python3 -m unittest discover -s tests -t tests
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"

JOB = "checks"
LOWEST = 10
HIGHEST = 30
JOB_HEADER = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
TIMEOUT = re.compile(r"^    timeout-minutes:\s*(.*?)\s*(?:#.*)?$")


def timeout_problems(text: str, name: str = "ci.yml") -> list[str]:
    """Why the `checks` job's timeout is missing or unbounded, each naming file and line."""
    lines = text.splitlines()
    start = None
    for number, line in enumerate(lines, start=1):
        header = JOB_HEADER.match(line)
        if header and header.group(1) == JOB:
            start = number
            break
    if start is None:
        return [f"{name}: no `{JOB}:` job, so there is nothing to bound"]

    for number in range(start + 1, len(lines) + 1):
        line = lines[number - 1]
        if line.strip() and not line.startswith("    "):
            break
        found = TIMEOUT.match(line)
        if not found:
            continue
        value = found.group(1)
        if not re.fullmatch(r"[0-9]+", value):
            return [
                f"{name}:{number}: job `{JOB}` sets timeout-minutes to {value!r}, which is "
                "not an integer literal a reviewer can read"
            ]
        minutes = int(value)
        if not LOWEST <= minutes <= HIGHEST:
            return [
                f"{name}:{number}: job `{JOB}` sets timeout-minutes to {minutes}, outside "
                f"{LOWEST} to {HIGHEST}"
            ]
        return []
    return [
        f"{name}:{start}: job `{JOB}` has no timeout-minutes, so it inherits GitHub's "
        "360-minute default"
    ]


class CiTimeout(unittest.TestCase):
    def setUp(self) -> None:
        self.text = CI.read_text(encoding="utf-8")

    def with_timeout(self, value: str) -> str:
        return re.sub(
            r"^    timeout-minutes:.*$", f"    timeout-minutes: {value}", self.text, flags=re.M
        )

    def test_the_shipped_job_is_bounded(self) -> None:
        self.assertEqual(timeout_problems(self.text), [])

    def test_a_missing_key_names_the_job_and_its_line(self) -> None:
        text = re.sub(r"^    timeout-minutes:.*\n", "", self.text, flags=re.M)
        problems = timeout_problems(text)
        self.assertEqual(len(problems), 1)
        header = text.splitlines().index(f"  {JOB}:") + 1
        self.assertIn(f"ci.yml:{header}: job `{JOB}` has no timeout-minutes", problems[0])

    def test_zero_is_refused(self) -> None:
        problems = timeout_problems(self.with_timeout("0"))
        self.assertEqual(len(problems), 1)
        self.assertIn(f"job `{JOB}` sets timeout-minutes to 0, outside", problems[0])

    def test_a_value_above_the_ceiling_is_refused(self) -> None:
        problems = timeout_problems(self.with_timeout("360"))
        self.assertEqual(len(problems), 1)
        self.assertIn("outside 10 to 30", problems[0])

    def test_non_integers_are_refused(self) -> None:
        for value in ("15.5", "15m", '"15"', "${{ vars.CI_TIMEOUT }}"):
            with self.subTest(value=value):
                problems = timeout_problems(self.with_timeout(value))
                self.assertEqual(len(problems), 1)
                self.assertIn("not an integer literal", problems[0])
                self.assertRegex(problems[0], r"^ci\.yml:\d+: ")

    def test_a_timeout_on_a_step_does_not_count(self) -> None:
        text = re.sub(r"^    timeout-minutes:.*\n", "", self.text, flags=re.M)
        text = text.replace(
            "        run: mypy\n", "        run: mypy\n        timeout-minutes: 15\n"
        )
        self.assertIn("has no timeout-minutes", timeout_problems(text)[0])


if __name__ == "__main__":
    unittest.main()
