"""Command line entry point for ccm-sim."""

from __future__ import annotations

import argparse
import sys
import threading
import time
from collections.abc import Sequence

from ccm_sim import __version__
from ccm_sim.engine import World, build_world, run_world
from ccm_sim.playlist import load_playlist, run_playlist
from ccm_sim.replay import CsvWriter, MqttRecorder, read_rows, replay
from ccm_sim.scenario import ScenarioError, load_scenario
from ccm_sim.sinks import JsonlSink, MqttSink, Sink
from ccm_sim.timeutil import DEFAULT_START, parse_duration, parse_iso


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccm-sim", description="Crew Context Monitor simulator")
    parser.add_argument("--version", action="version", version=f"ccm-sim {__version__}")
    sub = parser.add_subparsers(dest="command")

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--scenario", default="quiet", help="scenario name (default: quiet)")
        p.add_argument("--playlist", help="run a playlist of scenarios instead (such as demo)")
        p.add_argument("--crew", help="comma-separated crew ids (default: the scenario's crew)")
        p.add_argument("--seed", type=int, default=1)
        p.add_argument("--start", help="start time, ISO 8601 (default: fixed for generate)")
        p.add_argument("--duration", help="simulated duration, such as 2h or 30m")

    run = sub.add_parser("run", help="publish a scenario to a broker or stdout")
    common(run)
    run.add_argument(
        "--speed", help="speed multiplier or 'max' (default: 1, or each playlist step's speed)"
    )
    run.add_argument("--broker", help="host:port of the MQTT broker (default: print JSONL)")

    scen = sub.add_parser("scenarios", help="list scenarios or check their expectations")
    scen.add_argument("action", choices=["list", "check"])
    scen.add_argument("names", nargs="*", help="scenario names (default: all)")

    rec = sub.add_parser("record", help="record ccm/# from a broker to a replay CSV")
    rec.add_argument("--broker", required=True, help="host:port of the MQTT broker")
    rec.add_argument("--out", required=True, help="output CSV path")
    rec.add_argument("--duration", help="stop after this much real time, such as 30m")

    rep = sub.add_parser("replay", help="publish a recorded CSV to a broker or stdout")
    rep.add_argument("--file", required=True, help="replay CSV to publish")
    rep.add_argument("--speed", default="1", help="speed multiplier or 'max'")
    rep.add_argument("--retime", action="store_true", help="shift times so the replay looks live")
    rep.add_argument("--broker", help="host:port of the MQTT broker (default: print JSONL)")

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


def _scenarios(action: str, names: list[str]) -> int:
    from ccm_sim.expectations import check_expectations
    from ccm_sim.scenario import list_scenarios

    names = names or list_scenarios()
    if action == "list":
        for name in names:
            print(name)
        return 0
    failed = 0
    for name in names:
        try:
            world = build_world(load_scenario(name), 1, DEFAULT_START)
            problems = check_expectations(world)
        except ScenarioError as exc:
            problems = [str(exc)]
        if problems:
            failed += 1
            print(f"INCONSISTENT {name}")
            for line in problems:
                print(f"  - {line}")
        else:
            print(f"consistent   {name}")
    return 1 if failed else 0


def _run(
    args: argparse.Namespace, sink: Sink, default_start: float, speed: float | str | None
) -> None:
    """Run the chosen scenario or playlist into ``sink``."""
    if args.playlist:
        try:
            playlist = load_playlist(args.playlist)
        except ScenarioError as exc:
            raise SystemExit(str(exc)) from exc
        crew = [c.strip() for c in args.crew.split(",") if c.strip()] if args.crew else None
        t0 = parse_iso(args.start) if args.start else default_start
        run_playlist(playlist, sink, args.seed, t0, crew, speed)
        return
    run_world(_world(args, default_start), sink, 1.0 if speed is None else speed)


def _record(args: argparse.Namespace) -> int:
    host, port = _broker(args.broker)
    writer = CsvWriter(args.out)
    recorder = MqttRecorder(host, port, writer)
    seconds = parse_duration(args.duration) if args.duration else None
    try:
        if seconds is not None:
            time.sleep(seconds)
        else:
            threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        recorder.stop()
    print(f"recorded {writer.rows} messages to {args.out}", file=sys.stderr)
    return 0


def _replay(args: argparse.Namespace) -> int:
    rows = read_rows(args.file)
    sink: Sink
    if args.broker:
        host, port = _broker(args.broker)
        sink = MqttSink(host, port)
    else:
        sink = JsonlSink("-")
    try:
        replay(rows, sink, _parse_speed(args.speed), retime=args.retime)
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
    finally:
        sink.close()
    return 0


def _parse_speed(text: str) -> float | str:
    return "max" if text == "max" else float(text)


def _broker(text: str) -> tuple[str, int]:
    host, _, port = text.partition(":")
    return host, int(port or 1883)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "scenarios":
        return _scenarios(args.action, args.names)
    if args.command == "record":
        return _record(args)
    if args.command == "replay":
        return _replay(args)
    if args.command == "generate":
        sink: Sink = JsonlSink(args.out)
        try:
            _run(args, sink, DEFAULT_START, "max")
        finally:
            sink.close()
        return 0
    if args.command == "run":
        if args.broker:
            host, port = _broker(args.broker)
            sink = MqttSink(host, port)
        else:
            sink = JsonlSink("-")
        try:
            speed = _parse_speed(args.speed) if args.speed else None
            _run(args, sink, float(int(time.time())), speed)
        except KeyboardInterrupt:
            print("stopped", file=sys.stderr)
        finally:
            sink.close()
        return 0
    parser.print_help()
    return 0
