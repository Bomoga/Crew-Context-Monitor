"""Command line entry point for ccm-sim."""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence

from ccm_sim import __version__
from ccm_sim.engine import World, build_world, run_world
from ccm_sim.scenario import ScenarioError, load_scenario
from ccm_sim.sinks import JsonlSink, MqttSink, Sink
from ccm_sim.timeutil import DEFAULT_START, parse_duration, parse_iso


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccm-sim", description="Crew Context Monitor simulator")
    parser.add_argument("--version", action="version", version=f"ccm-sim {__version__}")
    sub = parser.add_subparsers(dest="command")

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--scenario", default="quiet", help="scenario name (default: quiet)")
        p.add_argument("--crew", help="comma-separated crew ids (default: the scenario's crew)")
        p.add_argument("--seed", type=int, default=1)
        p.add_argument("--start", help="start time, ISO 8601 (default: fixed for generate)")
        p.add_argument("--duration", help="simulated duration, such as 2h or 30m")

    run = sub.add_parser("run", help="publish a scenario to a broker or stdout")
    common(run)
    run.add_argument("--speed", default="1", help="speed multiplier or 'max'")
    run.add_argument("--broker", help="host:port of the MQTT broker (default: print JSONL)")

    gen = sub.add_parser("generate", help="write a scenario to a JSONL file at max speed")
    common(gen)
    gen.add_argument("--out", required=True, help="output JSONL path")
    return parser


def _world(args: argparse.Namespace, default_start: float) -> World:
    try:
        scenario = load_scenario(args.scenario)
    except ScenarioError as exc:
        raise SystemExit(str(exc)) from exc
    crew = [c.strip() for c in args.crew.split(",") if c.strip()] if args.crew else None
    t0 = parse_iso(args.start) if args.start else default_start
    duration = parse_duration(args.duration) if args.duration else None
    try:
        return build_world(scenario, args.seed, t0, crew, duration)
    except ScenarioError as exc:
        raise SystemExit(str(exc)) from exc


def _parse_speed(text: str) -> float | str:
    return "max" if text == "max" else float(text)


def _broker(text: str) -> tuple[str, int]:
    host, _, port = text.partition(":")
    return host, int(port or 1883)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "generate":
        sink: Sink = JsonlSink(args.out)
        try:
            run_world(_world(args, DEFAULT_START), sink, "max")
        finally:
            sink.close()
        return 0
    if args.command == "run":
        world = _world(args, float(int(time.time())))
        if args.broker:
            host, port = _broker(args.broker)
            sink = MqttSink(host, port)
        else:
            sink = JsonlSink("-")
        try:
            run_world(world, sink, _parse_speed(args.speed))
        except KeyboardInterrupt:
            print("stopped", file=sys.stderr)
        finally:
            sink.close()
        return 0
    parser.print_help()
    return 0
