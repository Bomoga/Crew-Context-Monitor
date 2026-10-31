"""Every command and file path in the project docs exists or runs (hardware steps excepted)."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import pytest

from ccm_sim.cli import build_parser, main
from ccm_sim.scenario import load_scenario

REPO = Path(__file__).resolve().parents[2]
DOC_NAMES = ["docs/demo.md", "docs/handoff-backend.md", "README.md"]
DOCS = [n for n in DOC_NAMES if (REPO / n).exists()]
FENCE = re.compile(r"```bash\n(.*?)```", re.DOTALL)
BACKTICK = re.compile(r"`([^`\n]+)`")
PATH_ROOTS = ("docs/", "sim/", "contracts/", "dashboard/", ".github/")
# build outputs and caches: absent on a fresh clone, so a doc may name them anywhere in a path
GENERATED = {"data", "dist", "node_modules", ".venv", "test-results", "playwright-report"}


def make_targets() -> set[str]:
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    return set(re.findall(r"^([A-Za-z0-9_.-]+):", text, re.MULTILINE)) - {".PHONY"}


def npm_scripts() -> set[str]:
    pkg = json.loads((REPO / "dashboard" / "package.json").read_text(encoding="utf-8"))
    return set(pkg["scripts"])


def commands(text: str) -> list[str]:
    """Shell commands from the ```bash blocks, one per line (backslash lines joined)."""
    found: list[str] = []
    for block in FENCE.findall(text):
        joined = block.replace("\\\n", " ")
        for line in joined.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                found.append(line)
    return found


def segments(command: str) -> list[list[str]]:
    return [shlex.split(part) for part in re.split(r"\s*&&\s*", command)]


def doc_text(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


def test_at_least_the_demo_runbook_is_checked() -> None:
    assert "docs/demo.md" in DOCS
    assert len(commands(doc_text("docs/demo.md"))) >= 8


@pytest.mark.parametrize("name", DOCS)
def test_make_targets_and_npm_scripts_exist(name: str) -> None:
    targets, scripts = make_targets(), npm_scripts()
    for command in commands(doc_text(name)):
        for argv in segments(command):
            if argv[0] == "make":
                named = [a for a in argv[1:] if "=" not in a and not a.startswith("-")]
                assert named, command
                for target in named:
                    assert target in targets, f"{name}: no make target {target!r} in {command!r}"
            elif argv[:2] == ["npm", "run"]:
                assert argv[2] in scripts, f"{name}: no npm script {argv[2]!r} in {command!r}"
            elif argv[0] == "npm":
                assert argv[1] in {"ci", "install", "test"}, f"{name}: {command!r}"


@pytest.mark.parametrize("name", DOCS)
def test_ccm_sim_commands_parse_and_the_quick_ones_run(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    ran = 0
    for command in commands(doc_text(name)):
        for argv in segments(command):
            if argv[0] != "ccm-sim":
                continue
            args = build_parser().parse_args(argv[1:])  # exits on a bad flag
            if args.command == "generate":
                scenario = load_scenario(args.scenario) if not args.playlist else None
                if scenario is not None and scenario.duration > 86400:
                    continue  # a week of data takes half a minute; the command parsed
                assert main(argv[1:]) == 0
                assert (tmp_path / args.out).stat().st_size > 1000
                ran += 1
    if name == "docs/demo.md":
        assert ran >= 1


@pytest.mark.parametrize("name", DOCS)
def test_file_paths_in_backticks_exist(name: str) -> None:
    for token in BACKTICK.findall(doc_text(name)):
        if " " in token or token.startswith(("/", "http")) or "<" in token or "*" in token:
            continue
        if not token.startswith(PATH_ROOTS) and not token.startswith("scenarios/"):
            continue
        if GENERATED & set(Path(token).parts):
            continue
        candidates = [REPO / token, REPO / "sim" / token]
        assert any(c.exists() for c in candidates), f"{name}: {token!r} does not exist"
