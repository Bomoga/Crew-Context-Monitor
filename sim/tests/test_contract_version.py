import re

from ccm_sim import contracts


def test_version_file_is_semver() -> None:
    text = (contracts.contracts_dir() / "VERSION").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", text)


def test_changelog_mentions_current_version() -> None:
    root = contracts.contracts_dir()
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    assert f"## {version}" in (root / "CHANGELOG.md").read_text(encoding="utf-8")
