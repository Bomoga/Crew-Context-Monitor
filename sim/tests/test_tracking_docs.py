"""The plan's memory files must not lose entries (they were once overwritten by shell appends)."""

from __future__ import annotations

import re
from pathlib import Path

PLAN_DIR = Path(__file__).resolve().parents[2] / "docs" / "plan"


def read(name: str) -> str:
    return (PLAN_DIR / name).read_text(encoding="utf-8")


def tasks_by_marker() -> dict[str, str]:
    return {
        m.group(2): m.group(1)
        for m in re.finditer(r"^- \[(.)\] \*\*(T\d+\.\d+) ", read("PLAN.md"), re.MULTILINE)
    }


def test_every_finished_task_has_a_progress_entry() -> None:
    headings = set(re.findall(r"^## (T\d+\.\d+) ", read("PROGRESS.md"), re.MULTILINE))
    done = {t for t, marker in tasks_by_marker().items() if marker == "x"}
    assert done, "no finished tasks found in PLAN.md"
    assert done <= headings, f"tasks without a PROGRESS entry: {sorted(done - headings)}"


def test_progress_entries_are_whole() -> None:
    blocks = re.split(r"\n(?=## T\d+\.\d+ )", read("PROGRESS.md"))[1:]
    assert len(blocks) >= 40
    for block in blocks:
        title = block.splitlines()[0]
        body = block.splitlines()[1:]
        assert any(line.startswith("- What:") for line in body), title
        assert any(line.startswith("- Verify:") for line in body), title
        assert any(line.startswith(("- Commit:", "- Commits:")) for line in body), title


def test_decisions_keep_the_defaults_table_and_numbered_entries() -> None:
    text = read("DECISIONS.md")
    rows = [int(n) for n in re.findall(r"^\| D(\d+) \|", text, re.MULTILINE)]
    assert rows == list(range(1, 17))
    numbered = [int(n) for n in re.findall(r"^## D(\d+) ", text, re.MULTILINE)]
    assert numbered == list(range(17, 17 + len(numbered))) and len(numbered) >= 10


def test_the_loop_sentinel_is_the_last_line_once_every_task_is_done() -> None:
    markers = set(tasks_by_marker().values())
    lines = [line for line in read("PROGRESS.md").splitlines() if line.strip()]
    if markers == {"x"}:
        assert lines[-1] == "LOOP_COMPLETE"
    else:
        assert not any(line.startswith(("LOOP_COMPLETE", "LOOP_STOPPED")) for line in lines)
