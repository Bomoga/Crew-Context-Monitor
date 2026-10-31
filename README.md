# Crew Context Monitor

Simulator, mock API and dashboard for the Crew Context Monitor. **A decision-support prototype, not
a medical device.**

The simulator publishes what the wearable and cabin nodes will publish, so the rest of the system can
be built and rehearsed before the hardware is ready. The mock API serves the dashboard's `/api`
routes from a running scenario, and the dashboard is a React app built once and served as static
files. The real API is meant to replace the mock on the same port and paths with no dashboard
change.

The build spec and task tracker is [docs/plan/PLAN.md](docs/plan/PLAN.md). Firmware, the BLE
bridge, ingest, analytics and the real API are other lanes and are not in this repository.

## Requirements

Python 3.11 or newer, Node 20 or newer with npm, GNU Make and git. A `mosquitto` broker is optional:
the broker tests fall back to an in-process broker. On Windows, run `make` from Git Bash with GNU
Make on the path.

## Quickstart

Set up (creates `.venv`, installs the simulator, runs `npm ci` for the dashboard) and check that
everything works:

```bash
make setup
make check
```

The `ccm-sim` command lives in the virtual environment: `.venv/bin` on macOS and Linux,
`.venv/Scripts` on Windows. Activate it or call it by path.

### Run the simulator

List the scenarios, write one to a file at full speed, or publish it to an MQTT broker in real
time or faster:

```bash
ccm-sim scenarios list
ccm-sim generate --scenario scrubber_failure --out data/scrubber.jsonl
ccm-sim run --scenario scrubber_failure --speed 60 --broker localhost:1883
```

Without `--broker`, `ccm-sim run` prints the messages as JSON lines. The scenarios are
`quiet_day`, `quiet_week`, `scrubber_failure`, `individual_illness`, `coincident_trends`,
`solar_particle_event`, `sleep_debt_drift`, `exercise_block`, `thermal_fault`, `wifi_dropout` and
`ble_dropout`. Record a live broker and replay it later with `ccm-sim record` and
`ccm-sim replay`; the file format is in [contracts/replay_csv.md](contracts/replay_csv.md).

### Run the mock API and the dashboard

This builds the dashboard and serves it, with the mock API, from one Python process on
http://127.0.0.1:8000. No Node process runs:

```bash
make serve-mock
```

Pick a scenario and speed (simulated seconds per real second), or run the three-step demo:

```bash
make serve-mock SCENARIO=individual_illness SPEED=120
make demo-mock
```

The demo, including the live-broker and replay-fallback variants, is in [docs/demo.md](docs/demo.md).

### Work on the dashboard

Run the mock API in one terminal, and Vite with hot reload in another. Vite proxies `/api` to
port 8000:

```bash
make serve-mock
make dashboard-dev
```

### Run the tests

```bash
make check
make sim-eval
make e2e
make check-all
```

`make check` is the fast gate to run before every commit: contract examples, ruff, mypy, pytest and
the dashboard's lint, type check and unit tests. `make sim-eval` runs every scenario's physics tests
on five seeds, which takes several minutes. `make e2e` builds the dashboard and runs the Playwright
suite against the mock API; install the browser once first. `make check-all` runs everything:

```bash
cd dashboard && npx playwright install chromium
```

## Repository map

```text
contracts/   MQTT topics and message schemas, dashboard API schemas, thresholds, replay format
sim/         the simulator (ccm_sim), its scenarios and parameters, and the mock API
dashboard/   the React dashboard, its unit tests (test/) and end-to-end tests (e2e/)
docs/        demo runbook, Backend handoff, and the plan with its progress, decisions and blockers
Makefile     every command above
```

Where to read next:

- [contracts/README.md](contracts/README.md) for topics, fields, units and the contract change process.
- [docs/handoff-backend.md](docs/handoff-backend.md) for what the Backend lane needs.
- [docs/plan/DECISIONS.md](docs/plan/DECISIONS.md) and [docs/plan/OPEN_QUESTIONS.md](docs/plan/OPEN_QUESTIONS.md) for the choices made and the questions still open.

## Conventions

- **Commits** follow Conventional Commits: `<type>(<scope>): <subject>`, one task per commit, every
  commit passing `make check`. Types are `feat`, `fix`, `test`, `docs`, `build`, `ci`, `refactor`,
  `perf` and `chore`.
- **The contract** in `contracts/` changes only through the process in
  [contracts/README.md](contracts/README.md): a numbered decision, a version bump, and the schemas,
  examples, simulator, mock API and generated types updated together.
- **Copy rules** for everything a person reads: one plain sentence per reason with a number and a
  baseline comparison; no raw z-scores; pulse-rate variability is never "HRV"; radiation is always a
  "proxy"; "consistent with", never "caused by"; the footer on every screen; a Hardware or Simulator
  badge on every crew chip. Tests enforce them in both the mock API and the dashboard.
- **No detection logic** lives in the simulator, the mock API or the dashboard. Thresholds are
  provisional and live in `contracts/thresholds.yaml`.
- **Generated files** (`dashboard/src/api/types.gen.ts`, `dashboard/dist`, `data/`) are not edited by
  hand. Regenerate the types with `make types`.
