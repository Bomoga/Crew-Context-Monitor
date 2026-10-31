"""Command line entry point for ccm-sim."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from ccm_sim import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccm-sim", description="Crew Context Monitor simulator")
    parser.add_argument("--version", action="version", version=f"ccm-sim {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0
