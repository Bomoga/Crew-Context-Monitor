"""Load the JSON Schemas under ``contracts/`` and validate messages against them.

``validate(kind, obj)`` is the public entry point. ``kind`` is the schema file stem, for example
``"wearable_telemetry"`` or ``"status"``. Run ``python -m ccm_sim.contracts`` to check every
example: valid examples must pass and invalid examples must fail.
"""

from __future__ import annotations

import json
import os
import sys
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_DIRS = ("mqtt", "api")
MIN_INVALID = 3
MIN_VALID = {"mqtt": 2, "api": 1}


class ContractError(ValueError):
    """Raised when an object does not match its schema or a schema is missing."""


def contracts_dir() -> Path:
    """Return the ``contracts/`` directory (override with ``CCM_CONTRACTS_DIR``)."""
    env = os.environ.get("CCM_CONTRACTS_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "contracts"


def schema_kinds() -> dict[str, Path]:
    """Map every schema stem to its file, across the mqtt and api folders."""
    kinds: dict[str, Path] = {}
    for sub in SCHEMA_DIRS:
        for path in sorted((contracts_dir() / sub).glob("*.schema.json")):
            kinds[path.name.removesuffix(".schema.json")] = path
    return kinds


@cache
def _validator(kind: str, root: str) -> Draft202012Validator:
    path = schema_kinds().get(kind)
    if path is None:
        raise ContractError(f"unknown contract kind: {kind!r}")
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validator(kind: str) -> Draft202012Validator:
    return _validator(kind, str(contracts_dir()))


def errors(kind: str, obj: Any) -> list[str]:
    """Return a readable list of schema violations (empty when valid)."""
    found = sorted(validator(kind).iter_errors(obj), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in found]


def validate(kind: str, obj: Any) -> None:
    """Raise ``ContractError`` when ``obj`` does not match the schema for ``kind``."""
    problems = errors(kind, obj)
    if problems:
        raise ContractError(f"{kind} invalid: " + "; ".join(problems))


def is_valid(kind: str, obj: Any) -> bool:
    return not errors(kind, obj)


def example_files(group: str, outcome: str) -> list[tuple[str, Path]]:
    """Return ``(kind, path)`` for each example in ``examples/<group>/<outcome>/``."""
    folder = contracts_dir() / "examples" / group / outcome
    return [(p.name.split(".", 1)[0], p) for p in sorted(folder.glob("*.json"))]


def check_examples() -> list[str]:
    """Check every example; return a list of problems (empty when all is well)."""
    problems: list[str] = []
    kinds = schema_kinds()
    for group in SCHEMA_DIRS:
        counts: dict[str, dict[str, int]] = {}
        for outcome in ("valid", "invalid"):
            for kind, path in example_files(group, outcome):
                if kind not in kinds:
                    problems.append(f"{path.name}: no schema named {kind!r}")
                    continue
                obj = json.loads(path.read_text(encoding="utf-8"))
                ok = is_valid(kind, obj)
                counts.setdefault(kind, {"valid": 0, "invalid": 0})[outcome] += 1
                if outcome == "valid" and not ok:
                    problems.append(f"{path.name}: expected valid, got {errors(kind, obj)}")
                if outcome == "invalid" and ok:
                    problems.append(f"{path.name}: expected invalid, but it passed")
        group_kinds = [k for k, p in kinds.items() if p.parent.name == group]
        for kind in group_kinds:
            have = counts.get(kind, {"valid": 0, "invalid": 0})
            if have["valid"] < MIN_VALID[group]:
                problems.append(
                    f"{kind}: needs {MIN_VALID[group]} valid examples, has {have['valid']}"
                )
            if have["invalid"] < MIN_INVALID:
                problems.append(
                    f"{kind}: needs {MIN_INVALID} invalid examples, has {have['invalid']}"
                )
    return problems


def main() -> int:
    kinds = schema_kinds()
    problems = check_examples()
    n_valid = sum(len(example_files(g, "valid")) for g in SCHEMA_DIRS)
    n_invalid = sum(len(example_files(g, "invalid")) for g in SCHEMA_DIRS)
    for line in problems:
        print(f"FAIL {line}")
    print(
        f"contracts: {len(kinds)} schemas, {n_valid} valid examples passing, "
        f"{n_invalid} invalid examples failing, {len(problems)} problems"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
