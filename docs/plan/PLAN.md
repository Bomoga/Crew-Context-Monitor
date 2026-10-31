# Crew Context Monitor: Simulator and Dashboard Implementation Plan

Revision 1, 2026-10-30. Repository: `github.com/Bomoga/Crew-Context-Monitor`.

This file is the spec **and** the task tracker for an autonomous build loop. `docs/plan/LOOP_PROMPT.md` starts the loop. The loop reads this file at the start of every iteration; the files in `docs/plan/` are the loop's memory, not the conversation.

Sources this plan follows, in order of precedence:

1. "Crew Context Monitor: Team Onboarding" (Claude Doc), which merges the Oct 9 Build Plan with the "Build plan v2" slides; the slides win where they disagree.
2. "Crew Context Monitor Build Plan" PDF (Oct 9, 2026).
3. "Wearable Node Assembly Instructions" rev 1 (2026-10-29), for the wearable message details (`finger:false`, null `hr`/`spo2`, 60 s reconnect buffer).

Where those sources leave a choice open, Section 2 sets a default so the loop never has to stop and ask.

---

## 0. How to read and update this file

Status markers on every task:

| Marker | Meaning |
|---|---|
| `[ ]` | not started |
| `[~]` | in progress (at most one at a time) |
| `[x]` | done; acceptance passed; committed |
| `[!]` | blocked; reason in `docs/plan/BLOCKERS.md` |

The loop may edit only: task markers, the `Notes:` line under a task, task splits (Section 7.6), and the Discovered tasks list (Section 12). Any change to spec text goes in `docs/plan/DECISIONS.md` as a new numbered entry, and the spec line gets a `(see D-n)` pointer.

Tracking files (created in T0.2):

| File | Purpose |
|---|---|
| `docs/plan/PROGRESS.md` | one entry per finished or blocked task, newest last; final report; loop sentinel |
| `docs/plan/DECISIONS.md` | defaults D1 to D16 below, then every later decision |
| `docs/plan/BLOCKERS.md` | every `[!]` task: what failed, what was tried, what a human must do |
| `docs/plan/OPEN_QUESTIONS.md` | questions for the team; never waited on |

---

## 1. Scope

**In scope (this loop builds these):**

- `contracts/`: MQTT topics, message JSON Schemas, dashboard API JSON Schemas, provisional thresholds, CO2 unit conversion.
- `sim/`: the simulator (`ccm_sim`), its scenario library, record and replay, and a **mock API** that serves contract-valid dashboard data from a running scenario.
- `dashboard/`: the React dashboard (home, detail, history, events, settings, check-in, Earth queue), built once and served as static files.
- Dev tooling: Makefile, CI workflow, e2e tests, demo runbook, Backend handoff doc.

**Out of scope (other lanes; the loop must not create or edit these):** firmware, BLE bridge, ingest, SQLite, analytics (baseline, residual, CUSUM, correlation, attribution), the real FastAPI service, the real Earth queue, hostapd, systemd units. The loop does not create `firmware/`, `gateway/` or `analytics/` directories.

**Why a mock API.** The build order puts "dashboard home on simulated data" before analytics exists, so the story can be rehearsed early. The mock API runs a scenario in-process and answers `/api/*` with the exact shapes the real API must return, so the real API can replace it later on the same port and paths with no dashboard change. The mock is clearly labeled: every response carries `"source_mode": "mock"`.

---

## 2. Settled defaults (apply without asking)

Copy this table into `DECISIONS.md` in T0.2. Each row names who should confirm it; the loop logs those in `OPEN_QUESTIONS.md` and keeps going.

| # | Decision | Why | Confirm with |
|---|---|---|---|
| D1 | Three crew, W1 W2 W3. Every wearable message carries `crew` (crew member id); `id` stays the device id. | v2 slides: three crew, W1 real, W2 and W3 simulated. | Backend |
| D2 | Add `t_meas` (unix seconds, float, ms precision): the time the reading was measured, on the synced node clock. All analysis uses `t_meas`. `t_node` stays as the raw node clock for debugging. In the simulator, `t_meas` is the simulated clock. | v2: every reading keeps its measured time so buffered data lands in the right minute. Time compression only works if analysis runs on measured time. | Backend, Firmware |
| D3 | MQTT always carries JSON. The wearable's BLE binary packet is decoded by the bridge into the same JSON. The binary layout is Firmware A's concern. | Keeps one MQTT contract; the simulator publishes what the bridge will publish. | Firmware A |
| D4 | MQTT carries CO2 in ppm (`co2`, sensor native). The API returns CO2 in mmHg (`co2_mmhg`). One conversion function: $p_{\text{CO2}}\,[\text{mmHg}] = \text{ppm} \times 10^{-6} \times P_{\text{cabin}}$, with $P_{\text{cabin}} = 760$ mmHg by default (configurable). The dashboard does no unit math. | v2: mmHg everywhere on screen; the open question was where conversion happens. | Backend |
| D5 | Provisional thresholds in `contracts/thresholds.yaml`, marked `status: provisional`: CO2 red at 3.0 mmHg (NASA-STD-3001 Vol 2 Rev D [V2 6004], 1-hour average); CO2 yellow at 2.5 mmHg (provisional choice; the OCHMO CO2 brief cites 2.5 mmHg 7-day average for headache risk below 1%); cabin temperature normal band 18 to 27 C (OCHMO ECLSS brief operating limit); VOC index yellow 250; skin residual yellow 0.5 C, red 1.0 C for 30 min; radiation Poisson test $N > \lambda + 4\sqrt{\lambda}$ per 10-minute window, yellow after one window, red after two in a row. | Pre-kickoff task says to check against NASA-STD-3001 in mmHg. Backend owns the final values. | Backend |
| D6 | The scrubber scenario is defined **relative to the thresholds file**: CO2 ramps from 800 ppm to 1.3 times the red threshold over 3 h (about 5130 ppm at 760 mmHg), and the crew response starts 20 min after CO2 crosses the **yellow** threshold (this replaces "1500 ppm"). A test fails if a threshold change means the ramp no longer crosses red. | The plan's 800 to 2600 ppm ramp peaks near 1.98 mmHg, under the 3 mmHg red line, so the Air card would never turn red. | Backend |
| D7 | All API routes live under `/api` (`/api/status`, `/api/history`, ...). The dashboard owns `/`, `/domain/:name`, `/history`, `/events`, `/settings`. | The plan's API paths `/history` and `/events` collide with the dashboard views of the same name on one FastAPI server. | Backend |
| D8 | Status topics are per device: `ccm/wearable/status/{id}` and `ccm/cabin/status/{id}`, retained, `online`/`offline` via last will. Telemetry topics are unchanged (`ccm/wearable/telemetry`, `ccm/cabin/telemetry`). | One retained `ccm/wearable/status` topic is overwritten when three wearables publish. `ccm/+/telemetry` subscriptions still work. | Backend, Firmware |
| D9 | Messages carry `src`: `"hw"` or `"sim"`. Analytics must ignore it; only the dashboard source badge uses it. | v2 requires a hardware/simulator badge per crew chip, and something has to carry that fact. | Backend |
| D10 | The simulator opens one MQTT client per simulated node (W1, W2, W3, C1), each with its own last will. With hardware W1 live, run `--crew W2,W3`. | Mirrors hardware so status and dropout behave the same. | Backend |
| D11 | Physiology parameters start at the plan's values (HR about 62, RMSSD about 45 ms, SpO2 97, skin 33.4 C; cabin 800 ppm, 22 C, 41% RH, VOC 100, 18 cpm). Every parameter in `sim/params/*.yaml` carries a `source:` field. WESAD/OSDR-derived values replace them later (T2.8, optional). | v2 says ranges come from WESAD and OSDR, but the loop cannot rely on a multi-GB download. | Backend |
| D12 | Physics for scenarios the docs describe only by outcome: **individual_illness**: W2 only, resting HR +12 bpm, RMSSD -15 ms, skin +0.8 C, ramped over 2 h. **coincident_trends**: CO2 800 to 1300 ppm over 3 h (stays under yellow) and, independently, W3 resting HR +6 bpm over 3 h starting 30 min **before** the CO2 rise. | Gives each scenario a concrete, testable shape. | Backend |
| D13 | Daily check-in: two rows of 1 to 5 taps (mood, sleep) plus an optional note; `POST /api/checkin`; shows as context in the events log; never changes a color. | v2: 15-second check-in, context only. | Frontend |
| D14 | Each level shows its word (Green, Yellow, Red) beside the color. Layout and size are identical across levels. | Accessibility; v2 says only color changes and layout never jumps; the word does not move anything. | Frontend |
| D15 | Wearable no-finger state: `hr` and `spo2` are `null` and `"finger": false` is present. | Assembly instructions, firmware hook 7. | Firmware A |
| D16 | Work happens on branch `build/sim-dashboard`; pushes after each phase gate; never to `main`. A draft PR to `main` is opened at the end if `gh` is available. | Lets the team review the whole slice before it lands. | Team |

---

## 3. Architecture of this slice

```
             scenario YAML + params YAML
                        |
                 ccm_sim engine  (SimClock, seeded RNG, beat-level physiology, cabin model)
                  |             |                         |
          MqttSink |     JsonlSink / MemorySink     mockapi (FastAPI, in-process run)
                  v             v                         |
   mosquitto  ccm/#        data/*.jsonl (eval,             |  /api/status /api/history /api/events
       |                   baseline pre-seed)              |  /api/earth-queue /api/settings /api/checkin
       v                                                   v
 [Backend lane: ingest, analytics, real API]  ---->  dashboard (React, built to dashboard/dist,
                                                     polls /api/status every 5 s, served at /)
```

The real API replaces `mockapi` on port 8000 with the same `/api` paths and the same static mount. Nothing in `dashboard/` knows which one is running except the `source_mode` field.

---

## 4. Repository layout (target)

```
.
├── README.md
├── Makefile
├── .editorconfig  .gitattributes  .gitignore
├── .github/workflows/ci.yml
├── docs/
│   ├── plan/        PLAN.md LOOP_PROMPT.md PROGRESS.md DECISIONS.md BLOCKERS.md OPEN_QUESTIONS.md
│   ├── demo.md
│   └── handoff-backend.md
├── contracts/
│   ├── VERSION  CHANGELOG.md  README.md
│   ├── thresholds.yaml
│   ├── replay_csv.md
│   ├── mqtt/   topics.yaml  wearable_telemetry.schema.json  cabin_telemetry.schema.json
│   │           node_status.schema.json  sim_event.schema.json
│   ├── api/    status  history  events  earth_queue  earth_queue_item  settings
│   │           checkin_request  enroll_request  reset_request  (*.schema.json)
│   └── examples/  mqtt/{valid,invalid}/*.json   api/{valid,invalid}/*.json
├── sim/
│   ├── pyproject.toml
│   ├── params/       physiology.yaml  cabin.yaml
│   ├── scenarios/    scenario.schema.json  *.yaml  demo.yaml
│   ├── src/ccm_sim/  __init__.py cli.py clock.py rng.py beats.py physiology.py cabin.py
│   │                 messages.py sinks.py publisher.py scenario.py effects.py truth.py
│   │                 units.py contracts.py thresholds.py replay.py record.py
│   │                 mockapi/ (app.py state.py templates.py static.py)
│   └── tests/
└── dashboard/
    ├── package.json  package-lock.json  vite.config.ts  tsconfig.json  index.html
    ├── src/  api/ (client.ts types.gen.ts validate.ts)  components/  views/  hooks/  styles/
    ├── test/ (vitest)  e2e/ (playwright)
    └── dist/ (build output, gitignored)
```

`data/` holds generated JSONL and CSV and is gitignored. Small fixtures live under `sim/tests/fixtures/` and `contracts/examples/`.

---

## 5. Toolchain and commands

**Floors:** Python 3.11+ (assumed to match Pi OS Bookworm; confirm on the Pi), Node 20+, npm, git. Optional: `mosquitto` binary, `gh`, `actionlint`. No `sudo`, no global installs; Python in `.venv`, Node in `dashboard/node_modules`.

**Python deps (`sim/pyproject.toml`):** numpy, pyyaml, jsonschema, paho-mqtt `>=2,<3` (use the v2 callback API), fastapi, uvicorn, httpx. Dev: pytest, ruff, mypy, types-PyYAML. Optional dev: amqtt (fallback broker for T2.7 only).

**Dashboard deps:** Vite + React + TypeScript, react-router, Recharts, Tailwind, ajv, Vitest + Testing Library + jsdom, Playwright, @axe-core/playwright, ESLint, Prettier, json-schema-to-typescript. Use the current stable versions at install time; lockfile pins them; record the versions in `DECISIONS.md`.

**Makefile targets (all must exist by the end of T6.1; earlier phases add what they need):**

| Target | Does |
|---|---|
| `make setup` | create `.venv`, `pip install -e "sim[dev]"`, `npm ci` in `dashboard/` (when it exists) |
| `make check` | fast gate, run before every commit: `contracts` + ruff + mypy + pytest (not slow) + dashboard lint, typecheck, vitest, types-fresh |
| `make check-all` | `check` + slow tests + `sim-eval` + dashboard build + Playwright e2e |
| `make contracts` | validate every example in `contracts/examples` (valid must pass, invalid must fail) |
| `make types` | regenerate `dashboard/src/api/types.gen.ts` from `contracts/api` |
| `make sim-eval` | every scenario x 5 seeds through the physics and expectation checks |
| `make serve-mock SCENARIO=... SPEED=...` | mock API plus built dashboard on :8000 |
| `make demo-mock` | mock API running `scenarios/demo.yaml` |
| `make demo-live BROKER=host:1883` | simulator to a real broker for the Backend lane's stack |
| `make dashboard-dev` | Vite dev server proxying `/api` to :8000 |
| `make e2e` | Playwright against the built app and mock API |
| `make fmt`, `make clean` | formatters; remove build output |

---

## 6. Commit and branch conventions

- **Branch:** `build/sim-dashboard`, created from `main` in T0.1. Never commit to `main`, never force-push, never rewrite pushed history.
- **Format:** Conventional Commits 1.0.0. `<type>(<scope>): <subject>`.
  - types: `feat`, `fix`, `test`, `docs`, `build`, `ci`, `refactor`, `perf`, `chore`
  - scopes: `repo`, `plan`, `contracts`, `sim`, `mockapi`, `dashboard`, `e2e`, `ci`, `demo`
  - subject: imperative, lowercase first word, no trailing period, 72 characters or fewer
  - body: what changed and why, wrapped at 72; then a footer line `Refs: T<id>`
  - breaking contract change: `feat(contracts)!: ...` plus a `BREAKING CHANGE:` footer
- **Granularity:** one task, one commit. The plan checkbox and the `PROGRESS.md` entry go in that same commit. A dependency or lockfile addition may land first as its own `build(<scope>): add ...` commit.
- **Green only:** every commit passes `make check`. A commit that marks a task `[!]` contains only tracking-file changes (`chore(plan): mark T<id> blocked`).
- **Push:** `git push -u origin build/sim-dashboard` at each gate (G1 to G4) and at the end. If the push fails (auth, network), note it in `PROGRESS.md` once and continue locally; do not retry in a loop.
- **Never commit:** `.venv/`, `node_modules/`, `dist/`, `data/`, Playwright artifacts, `.env`, credentials, files over 1 MB.

---

## 7. Loop protocol

### 7.1 One iteration

1. **Orient.** Read Sections 0, 2, 6 and 7 of this file (the whole file on the first iteration and after any context reset), the last three entries in `PROGRESS.md`, all of `BLOCKERS.md`, and the latest entries in `DECISIONS.md`. Run `git status` and `git log --oneline -5`.
2. **Recover.** If the tree is dirty and a task is `[~]`, resume that task. If the tree is dirty and no task is `[~]`, inspect the diff: keep it if it clearly belongs to the next task, otherwise `git stash push -m "orphaned <date>"` and log it.
3. **Select.** The first `[ ]` task in document order whose `Depends` are all `[x]`. If a dependency is `[!]`, the dependent task is also `[!]` (log it, commit tracking change, select again).
4. **Start.** Mark it `[~]`.
5. **Build.** Implement only that task's `Do` list. Read existing code before changing it. Write the tests named in `Accept` first where practical.
6. **Verify.** Run every command in `Accept`, then `make check`. Read the output; do not assume.
7. **Finish.** If all green: mark `[x]`, add a `PROGRESS.md` entry (Section 7.3), stage, commit with the task's commit line. If a gate closes with this task, run the gate (Section 9) and push.
8. **Fail.** If red, fix and re-run. After the third failed attempt at the same task, follow 7.4.
9. **Continue.** Go to step 1 without pausing, summarizing to the chat, or waiting for input.

### 7.2 Hard rules

- Never ask the user a question and never wait for input. Use Section 2, then log the question in `OPEN_QUESTIONS.md`.
- Never skip, delete, `xfail` or weaken a test or an assertion to get green. The only allowed skip is the broker-unavailable rule in T2.7, with a `BLOCKERS.md` entry.
- Never change `contracts/` after gate G1 without the change process in Section 9.
- Never touch out-of-scope areas (Section 1). Never add analytics logic to the simulator or the dashboard; the mock API reads scenario expectations, it does not detect anything.
- Never use `sudo`, never install system packages, never call paid APIs, never send data anywhere except package registries and the git remote.
- Never break copy rules (Section 8, P6) in any string the user can see, including mock API templates.
- Keep the repo runnable at every commit: `make setup && make check` on a fresh clone must pass.

### 7.3 PROGRESS.md entry format

```
## T2.3 Physiology model (done | blocked) 2026-10-31 14:05
- What: one or two lines.
- Verify: `make check` green; key numbers (e.g. "median RMSSD 44.1 ms, target 45").
- Commit: <sha short> feat(sim): model crew physiology with activity and cabin coupling
- Notes: anything the next iteration must know (max 3 lines).
```

### 7.4 Blocker protocol

After three failed attempts on one task:

1. `git stash push -m "T<id> attempt"` (keep the work; do not discard it).
2. Mark the task `[!]`, write a `BLOCKERS.md` entry: symptom, the three attempts, the exact failing command and its last 20 output lines, what a human needs to do.
3. Commit `chore(plan): mark T<id> blocked`.
4. Continue with the next selectable task.

### 7.5 Stop conditions

- **Done:** every task is `[x]` or `[!]` and T7.5 has run. Append the final report and the line `LOOP_COMPLETE` to `PROGRESS.md`, commit, push, stop.
- **Hard stop:** toolchain floors not met and not fixable without `sudo`; the git repo is corrupted; three consecutive tasks went `[!]`; or the same task has been `[~]` across five iterations. Append a stop report and the line `LOOP_STOPPED: <reason>` to `PROGRESS.md`, commit, push, stop.

### 7.6 Splitting and discovered work

- If a task cannot finish in one iteration, split it into `T6.6a`, `T6.6b`, ... in place, each with its own `Accept` and commit line, and record the split in `DECISIONS.md`.
- Work found along the way goes in Section 12 as `X<n>` with a one-line reason. Do it in the current phase only if an `Accept` line depends on it; otherwise leave it for the team.

---

## 8. Tasks

Each task lists **Depends**, **Do**, **Accept** (commands and checks that must pass, in addition to `make check`), and **Commit**.

### P0. Bootstrap

- [x] **T0.1 Toolchain probe and branch**
  - Depends: none
  - Do: confirm the plan files are committed on `main`; create and switch to `build/sim-dashboard`. Record `python3 --version`, `node --version`, `npm --version`, `git --version`, and whether `mosquitto`, `gh`, `actionlint` exist, into `PROGRESS.md` (create it). If Python < 3.11 or Node < 20 and no user-level install route works (pyenv, nvm, uv), hard stop (7.5).
  - Accept: `git branch --show-current` prints `build/sim-dashboard`; versions recorded.
  - Commit: `chore(repo): record toolchain and start build branch`

- [x] **T0.2 Repository skeleton and tracking files**
  - Depends: T0.1
  - Do: `README.md` (one paragraph, prototype disclaimer, link to this plan), `.gitignore` (Python, Node, `.venv`, `dist`, `data/`, Playwright reports, `.env`), `.editorconfig`, `.gitattributes` (`* text=auto eol=lf`), `docs/plan/DECISIONS.md` (Section 2 table as D1 to D16), `BLOCKERS.md`, `OPEN_QUESTIONS.md` (seed it with the "Confirm with" column of Section 2 and "repository license"), a `Makefile` whose `check` target exists and passes.
  - Accept: `make check` exits 0; `git check-ignore data/x.jsonl .venv dashboard/dist` lists all three.
  - Commit: `chore(repo): scaffold repository layout and tracking docs`

- [x] **T0.3 Python package skeleton**
  - Depends: T0.2
  - Do: `sim/pyproject.toml` (package `ccm_sim`, src layout, console script `ccm-sim`), deps from Section 5, ruff config (line length 100), mypy strict on `src/`, `ccm_sim/cli.py` with `--version`, one smoke test; Makefile `setup`, `lint`, `test`, `check` wired for Python.
  - Accept: `make setup && make check`; `.venv/bin/ccm-sim --version` prints a version.
  - Commit: `build(sim): add python package skeleton and tooling`

- [x] **T0.4 CI workflow**
  - Depends: T0.3
  - Do: `.github/workflows/ci.yml` with a Python job (3.11, `make setup check`) and a dashboard job guarded by `hashFiles('dashboard/package.json') != ''`.
  - Accept: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"`; `actionlint` passes if installed.
  - Commit: `ci: add check workflow for python and dashboard`

### P1. Contracts (closes gate G1)

- [ ] **T1.1 MQTT topics and message schemas**
  - Depends: T0.3
  - Do: `contracts/mqtt/topics.yaml` (topics, publisher, rate, retained, QoS: telemetry 0, status and sim events 1). JSON Schema 2020-12 files per Appendix A.1 to A.4 with `additionalProperties: false`. Examples: at least 2 valid and 3 invalid per schema (missing required, wrong type, out of range). `make contracts` validates them using `ccm_sim.contracts`.
  - Accept: `make contracts` reports every valid example passing and every invalid one failing.
  - Commit: `feat(contracts): define mqtt topics and telemetry schemas`

- [x] **T1.2 Dashboard API schemas and fixtures**
  - Depends: T1.1
  - Do: schemas per Appendix A.5 to A.10. Valid API fixtures for these states: `all_green`, `learning`, `air_yellow`, `air_red_cabin`, `cardio_yellow_individual`, `radiation_red`, `thermal_red`, `node_offline`, `correlation_active`, `earth_queue_pending`, `history_prv_6h`, `events_mixed`. Invalid fixtures: at least 3 per schema.
  - Accept: `make contracts`.
  - Commit: `feat(contracts): define dashboard api schemas and fixtures`

- [x] **T1.3 Units and provisional thresholds**
  - Depends: T1.1
  - Do: `contracts/thresholds.yaml` per D5, each value with `source:` and `status: provisional`. `ccm_sim/units.py` (`ppm_to_mmhg`, `mmhg_to_ppm`, cabin pressure parameter) and `ccm_sim/thresholds.py` loader.
  - Accept: tests show `ppm_to_mmhg(5000)` equals 3.8 within 1e-9 at 760 mmHg (the OCHMO brief states 0.5% CO2 = 3.8 mmHg; do not use `==` on floats) and the round trip holds within 1e-9; loader rejects a missing key.
  - Commit: `feat(contracts): add co2 unit conversion and provisional thresholds`

- [x] **T1.4 Contract loader, version and freeze**
  - Depends: T1.2, T1.3
  - Do: `ccm_sim.contracts.validate(kind, obj)` with cached validators; `contracts/VERSION` = `1.0.0`; `contracts/CHANGELOG.md`; `contracts/README.md` (topics, fields, units, the change process from Section 9). Run gate G1.
  - Accept: `make contracts`; a test validates every example through the public loader.
  - Commit: `feat(contracts): freeze contract v1.0.0`

### P2. Simulator core

- [x] **T2.1 Clock and random streams**
  - Depends: T1.4
  - Do: `SimClock(start, speed)` where `speed` is a float or `"max"`; `now()`, `sleep_until(t_sim)`; an injectable real-time source for tests. `rng.py`: per-stream generators derived from `(seed, stream_name)` so adding a crew member does not change another member's numbers.
  - Accept: tests: at speed 60 one fake real second advances 60 sim seconds; `max` never sleeps; same seed gives byte-identical output; adding W3 leaves W1's stream identical.
  - Commit: `feat(sim): add simulation clock and seeded random streams`

- [x] **T2.2 Beat-level inter-beat intervals**
  - Depends: T2.1
  - Do: `beats.py` per Appendix C: RR from target HR(t) and target RMSSD(t), AR(1) beat-to-beat term, small respiratory term; produce beat times and integer-ms intervals.
  - Accept (5 seeds, 1 h quiet): mean HR within 1 bpm of target; median 5-minute RMSSD within 15% of target; when target RMSSD drops by 15 ms, the measured 5-minute RMSSD reaches within 15% of the new target within 10 minutes; beat times strictly increasing; every RR in [300, 2000] ms.
  - Commit: `feat(sim): generate beat-level inter-beat intervals`

- [x] **T2.3 Crew physiology model**
  - Depends: T2.2
  - Do: `physiology.py`: $HR(t) = HR_0 + c_{HR}(t) + \beta_1\,\text{act}(t) + \beta_2\,(T_{\text{cabin}}(t) - 22) + \Delta_{\text{scenario}}(t) + \text{noise}$; RMSSD with circadian term; SpO2 (integer, clamp 90 to 100, noisier under motion); skin temperature as a first-order lag (tau 20 min) toward a cabin-coupled target plus circadian; activity process (rest about 0.06, exercise about 1.2, std of acceleration magnitude in g); `motion = act > 0.3`; battery slow discharge from 4.15 V. Per-crew variation (W2 base HR 66, W3 base HR 58). All values in `sim/params/physiology.yaml` with `source:` (D11).
  - Accept: tests: quiet-day means match params within tolerance; a +3 C cabin step raises HR by `beta2 * 3` within 1 bpm after settling; a rest-to-exercise step raises HR by `beta1 * delta_act` within 3 bpm; skin temperature reaches 63% of a step in 20 +/- 3 min.
  - Commit: `feat(sim): model crew physiology with activity and cabin coupling`

- [x] **T2.4 Cabin environment and radiation counts**
  - Depends: T2.1
  - Do: `cabin.py`: CO2 ppm baseline with noise and a crew-metabolic diurnal term; temperature, RH, VOC index, PM1/PM2.5/PM10 as integers; Geiger counts as Poisson per 10 s (`c10s`) at rate cpm/6, and `cpm` as the rolling 60 s sum. Params in `sim/params/cabin.yaml`.
  - Accept (5 seeds, 6 h): mean cpm within 1 of 18; `c10s` variance/mean between 0.8 and 1.2; all fields inside schema ranges.
  - Commit: `feat(sim): model cabin environment and radiation counts`

- [x] **T2.5 Message builders**
  - Depends: T2.3, T2.4
  - Do: `messages.py`: wearable message every 5 s of sim time (ibi = beats in the window, `hr = round(60000 / mean(ibi))`), cabin message every 10 s; `seq` per node from 1, step 1; `t_meas` = window end; `t_node` = `t_meas` plus a per-node offset (within 2 s) and 30 ppm drift; `src`, `crew`; `finger` handling per D15.
  - Accept: 10,000 generated messages all pass `contracts.validate`; `seq` strictly +1 per node; `t_meas` spacing exactly 5 s and 10 s.
  - Commit: `feat(sim): build schema-valid wearable and cabin messages`

- [x] **T2.6 Sinks, publisher and CLI**
  - Depends: T2.5
  - Do: `Sink` protocol; `MemorySink`, `JsonlSink` (one `{"topic":..., "payload":..., "retain":...}` per line), `MqttSink` (paho v2, one client per node per D10, last will on the node's status topic, retained `online` on connect). Publisher merges node streams by `t_meas` and paces by the clock. CLI: `ccm-sim run --scenario NAME [--speed N|max] [--crew W1,W2,W3] [--broker host:port] [--seed N] [--start ISO]` and `ccm-sim generate --scenario NAME --out FILE.jsonl [--seed N]` (max speed, no broker). Until P3 exists, `--scenario quiet` is built in.
  - Accept: `ccm-sim generate --scenario quiet --duration 2h --out data/q.jsonl` writes 1440 wearable messages per crew and 720 cabin messages, plus status records; JSONL round trip test; output order is non-decreasing in `t_meas`.
  - Commit: `feat(sim): publish to mqtt, jsonl and memory sinks`

- [x] **T2.7 Broker integration test**
  - Depends: T2.6
  - Do: pytest fixture starts `mosquitto -p <free port>` if on PATH; otherwise tries `amqtt` in-process. Test: subscribe `ccm/#`, run 10 sim minutes at max speed, assert message counts, retained `online` on each status topic, and that killing one node's client delivers its `offline` last will. If neither broker works after 2 attempts, mark the test `skip(reason=...)`, add a `BLOCKERS.md` entry (non-fatal, task still `[x]`), and note it in `OPEN_QUESTIONS.md`.
  - Accept: test passes, or the documented skip path is followed exactly.
  - Commit: `test(sim): add mqtt broker integration test`

- [x] **T2.8 (optional) WESAD/OSDR-derived parameters**
  - Depends: T2.3
  - Do: only if `CCM_WESAD_DIR` is set and points at an extracted WESAD copy: a script `sim/tools/derive_params.py` that computes resting HR and RMSSD ranges and writes `sim/params/physiology.derived.yaml` with `source: WESAD`. Otherwise mark `[x]` with the note "skipped, dataset not present" and add an `OPEN_QUESTIONS.md` line.
  - Accept: script runs on the dataset, or the skip note exists.
  - Commit: `feat(sim): derive physiology ranges from wesad` (or `chore(plan): skip optional wesad derivation`)
  - Notes: skipped, dataset not present (`CCM_WESAD_DIR` unset).

### P3. Scenarios (closes gate G2)

- [x] **T3.1 Scenario engine and quiet baselines**
  - Depends: T2.6
  - Do: `scenario.py` + `effects.py` per Appendix B: YAML loader validated by `sim/scenarios/scenario.schema.json`; duration parsing; effect ops `set`, `step`, `ramp`, `drift_per_day`, `coupled`, `exercise`, `rate`, `silence`; truth channels (`truth.py`) recording every applied offset per target per minute; sim events published to `ccm/sim/event` at each event's start and end. Scenarios `quiet_day` (24 h) and `quiet_week` (7 d, 3 crew).
  - Accept: one unit test per op; `ccm-sim generate --scenario quiet_week --out data/qw.jsonl` finishes in under 120 s and contains 3 crew x 7 days of wearable messages.
  - Commit: `feat(sim): add scenario engine and quiet baselines`

- [x] **T3.2 scrubber_failure**
  - Depends: T3.1, T1.3
  - Do: per D6. CO2 ramp start at +30 min; all three crew: RMSSD falls (up to -12 ms at peak) and HR rises (up to +6 bpm at peak), coupled to CO2 above yellow with a 20 min lag; sim events "Scrubber fault begins", "CO2 passes yellow", "CO2 passes red".
  - Accept (5 seeds): CO2 crosses yellow and red per `thresholds.yaml`; each crew's 5-minute RMSSD starts falling 20 +/- 3 min after the yellow crossing; a test that loads a modified thresholds file with red raised above the ramp peak fails with a clear message.
  - Commit: `feat(sim): add scrubber failure scenario`

- [x] **T3.3 individual_illness**
  - Depends: T3.1
  - Do: per D12.
  - Accept (5 seeds): W2 shifts as specified within 10%; W1 and W3 means stay within 1 bpm / 3 ms of their quiet values; CO2 and cabin temperature stay inside normal.
  - Commit: `feat(sim): add individual illness scenario`

- [x] **T3.4 coincident_trends**
  - Depends: T3.1
  - Do: per D12, with the two trends driven by independent random streams.
  - Accept: CO2 stays below yellow; W3 HR trend starts 30 min before the CO2 trend; the truth channels show no coupling between them.
  - Commit: `feat(sim): add coincident trends scenario`

- [x] **T3.5 solar_particle_event**
  - Depends: T3.1
  - Do: cpm rate steps 18 to 240 for 40 min, then back to 18.
  - Accept (5 seeds): every 10-minute window fully inside the step has $N > \lambda + 4\sqrt{\lambda}$ against the 18 cpm baseline; windows before and after do not (allow at most one exceedance across all quiet windows of all seeds).
  - Commit: `feat(sim): add solar particle event scenario`

- [x] **T3.6 sleep_debt_drift**
  - Depends: T3.1
  - Do: resting HR +1 bpm per day and RMSSD -3 ms per day for 6 days, applied to W1 only so attribution says individual (record this choice in `DECISIONS.md`).
  - Accept: slopes measured on rest windows within 20% of target over 5 seeds; no single 5-minute window departs from the drifting mean by more than the quiet-day spread (the drift is slow, not spiky).
  - Commit: `feat(sim): add sleep debt drift scenario`

- [x] **T3.7 exercise_block**
  - Depends: T3.1
  - Do: activity high for 30 min, HR toward 150 through the model's `beta1` term, exponential recovery (tau 3 min); `motion: true` throughout the block.
  - Accept: HR peaks at 150 +/- 8; HR minus the model's prediction stays within +/- 5 bpm (the model explains it); motion flag true for at least 95% of block windows.
  - Commit: `feat(sim): add exercise block scenario`

- [x] **T3.8 thermal_fault**
  - Depends: T3.1
  - Do: cabin temperature 22 to 29 C over 2 h; skin temperature follows through the lag; HR change only through the `beta2` term.
  - Accept: cabin leaves the 18 to 27 C band at the expected time; skin follows within the lag tolerance; HR minus model prediction within +/- 3 bpm.
  - Commit: `feat(sim): add thermal fault scenario`

- [x] **T3.9 wifi_dropout and ble_dropout**
  - Depends: T3.1
  - Do: `wifi_dropout`: C1 goes silent for 8 min (MqttSink drops the connection without a clean disconnect so the broker fires the last will; other sinks emit an `offline` status record), buffers messages, then reconnects (`online`) and flushes the buffer in order with original `seq` and `t_meas`. `ble_dropout`: W1 silent 60 s then resends its last 60 s.
  - Accept: after the flush, `seq` has no gaps; flushed messages carry `t_meas` inside the silent window; every sim minute of the scenario has at least one cabin message by `t_meas`.
  - Commit: `feat(sim): add wifi and ble dropout scenarios`

- [x] **T3.10 Scenario expectations and sim-eval**
  - Depends: T3.2 to T3.9
  - Do: an `expect:` block in every scenario per Appendix B.3 (encoding the "what the pipeline should show" column of the v2 scenario library). `ccm-sim scenarios check` verifies each expectation is consistent with the truth channels and thresholds (for example, an Air red window lies where CO2 is at or above red). `make sim-eval` runs every scenario x 5 seeds through its physics tests and the consistency check (pytest marker `slow`).
  - Accept: `make sim-eval` green; `ccm-sim scenarios check` lists every scenario as consistent.
  - Commit: `feat(sim): encode scenario expectations and sim-eval`

- [x] **T3.11 Demo playlist**
  - Depends: T3.10
  - Do: `sim/scenarios/demo.yaml`: the simulator-driven demo steps in order (scrubber_failure at 60x, individual_illness, solar_particle_event), each with a label; `ccm-sim run --playlist demo`. Run gate G2.
  - Accept: `ccm-sim generate --playlist demo --out data/demo.jsonl` succeeds and its sim events appear in order.
  - Commit: `feat(sim): add demo playlist`

### P4. Record and replay

- [x] **T4.1 Record and replay modes**
  - Depends: T3.11
  - Do: `contracts/replay_csv.md` (columns `topic,t_meas,retain,payload_json`, one row per message). `ccm-sim record --broker H:P --out FILE.csv [--duration 30m]`; `ccm-sim replay --file FILE.csv [--speed N] [--retime]` (`--retime` shifts `t_meas` and `t_node` so the recording ends now, for the live fallback; off for eval).
  - Accept: generate, record through MemorySink, replay, compare: identical messages without `--retime`; with `--retime` only time fields differ and spacing is preserved; replay payloads validate.
  - Commit: `feat(sim): add record and replay modes`

### P5. Mock API

- [x] **T5.1 Status, history and events**
  - Depends: T4.1
  - Do: `ccm_sim.mockapi` FastAPI app. Runs the selected scenario in a background thread on a SimClock; keeps 1-minute rollups in memory. `GET /api/status`: card levels and attribution from the active `expect` entries, numbers from the generated data and params baseline, reasons from templates (T5.3). `GET /api/history` and `GET /api/events` per Appendix A. `POST /api/_mock/scenario {name, speed}` switches scenario (dev only, documented as such). CLI `ccm-sim serve-mock --scenario NAME --speed N --port 8000 [--fast-forward] [--learning]`.
  - Accept: TestClient tests: for every scenario, at five sim times spread over its duration, every endpoint response passes `contracts.validate`; card levels at those times equal the expectations.
  - Commit: `feat(mockapi): serve status, history and events from scenarios`

- [x] **T5.2 Earth queue, settings and check-in**
  - Depends: T5.1
  - Do: in-memory Earth queue seeded with one item per tier, plus a generated summary each time a card turns red (payload compact, `bytes` = UTF-8 length); `POST /api/earth-queue/{id}/approve`; settings get/put, enroll, reset-baseline (resets the mock's learning timer for that crew); `POST /api/checkin` adds a `checkin` event and never changes a level.
  - Accept: schema-valid responses; approving twice is idempotent; auto-approve on a tier approves new items of that tier; a check-in leaves every card level unchanged.
  - Commit: `feat(mockapi): add earth queue, settings and check-in`

- [x] **T5.3 Copy templates and copy-rule tests**
  - Depends: T5.1
  - Do: `templates.py` with one sentence per domain and state, each with a number and a baseline comparison ("resting HR 71, baseline 65"), attribution phrasing ("3 of 3 crew show lower pulse-rate variability since 09:10; cabin CO2 up 2.1 mmHg", "Only W2 changed; cabin within normal", "Not enough data to attribute"), and the correlation sentence ("Pulse-rate variability began dropping 20 min after CO2 passed 2.5 mmHg").
  - Accept: a test renders every template for every scenario state and asserts: no "caused by"; no "z-score" or raw z values; "HRV" never appears without "pulse-rate variability"; radiation text includes "proxy"; every reason contains a digit.
  - Commit: `feat(mockapi): add plain-language reason templates`

- [x] **T5.4 Static dashboard hosting**
  - Depends: T5.1
  - Do: if `dashboard/dist` exists, mount it at `/` with SPA fallback (unknown non-`/api` paths return `index.html`); `/api/*` 404s stay JSON.
  - Accept: TestClient: `/history` and `/domain/air` return `index.html` when a fake dist exists; `/api/nope` returns JSON 404.
  - Commit: `feat(mockapi): serve built dashboard with spa fallback`

### P6. Dashboard (closes gate G3)

Copy rules apply to every view (from the onboarding doc): one plain sentence per reason with a number and a baseline comparison; no raw z-scores on home; HRV is always "pulse-rate variability"; radiation is always a "proxy"; "consistent with", never "caused by"; footer "Decision-support prototype, not a medical device" on every screen; source badge (Hardware or Simulator) on every crew chip; the check-in never changes a color.

- [x] **T6.1 Scaffold and generated types**
  - Depends: T1.4
  - Do: Vite React TS app in `dashboard/` with the deps from Section 5; Vite proxy `/api` to `127.0.0.1:8000`; scripts `lint`, `typecheck`, `test`, `build`, `gen:types`, `check:types-fresh` (regenerate then `git diff --exit-code`), `e2e`. Wire into `make setup`, `make check`, `make types`. Two commits.
  - Accept: `make check` runs the dashboard steps green; `npm run gen:types` output is committed and fresh.
  - Commit 1: `build(dashboard): scaffold vite react app with tooling`
  - Commit 2: `feat(dashboard): generate api types from contracts`

- [ ] **T6.2 API client and polling**
  - Depends: T6.1
  - Do: typed client for every endpoint; `useStatus` polls every 5 s with abort on unmount; stale when the last success is older than 15 s; error state keeps the last data; in dev builds ajv validates every response and logs contract violations.
  - Accept: Vitest with fake timers: polls at 5 s, marks stale at 15 s, recovers; a malformed fixture logs a violation in dev mode.
  - Commit: `feat(dashboard): add typed api client with status polling`

- [x] **T6.3 App shell**
  - Depends: T6.2
  - Do: router with `/`, `/domain/:name`, `/history`, `/events`, `/settings`; nav; footer on every route; a reserved banner slot for stale or offline state so nothing shifts; level color tokens (Tailwind) and the level word (D14).
  - Accept: test renders every route and finds the footer text; banner slot height is constant with and without a banner.
  - Commit: `feat(dashboard): add app shell, routes and footer`

- [x] **T6.4 Status bar and crew strip**
  - Depends: T6.3
  - Do: status bar shows the worst card's sentence, attribution and action in one line; learning state shows the time until alerts start; crew strip with one chip per crew (level, online, source badge), clicking a chip selects the crew for the timeline.
  - Accept: tests over the `all_green`, `air_yellow`, `air_red_cabin`, `learning` fixtures; the status bar bounding box is identical across them; each chip shows Hardware or Simulator.
  - Commit: `feat(dashboard): add status bar and crew strip`

- [x] **T6.5 Risk cards**
  - Depends: T6.4
  - Do: four cards in fixed order (Cardiovascular, Air quality, Thermal, Radiation (proxy)), each with level, two or three numbers against baseline, the reason; whole card links to `/domain/:name`.
  - Accept: tests for each level fixture; card positions do not change between fixtures; no z values rendered.
  - Commit: `feat(dashboard): add risk cards`

- [x] **T6.6 Fused timeline**
  - Depends: T6.5
  - Do: Recharts chart: cabin CO2 (mmHg, left axis) over the selected crew's pulse-rate variability (ms, right axis), toggle to HR residual; last 6 h; vertical markers for events, with simulated events drawn distinctly; when `correlation` is present, both markers and the lag label appear.
  - Accept: tests with `history_prv_6h`, `events_mixed`, `correlation_active` fixtures: markers count equals events in range; lag label text matches the fixture sentence; toggle switches series.
  - Commit: `feat(dashboard): add fused co2 and pulse-rate variability timeline`

- [x] **T6.7 Earth queue panel**
  - Depends: T6.5
  - Do: pending items with tier, approval state, size in bytes, countdown to the next comms window, payload preview, Approve button (optimistic update, rollback on error).
  - Accept: tests: approve calls the endpoint once, updates state, rolls back on a 500; countdown renders from `next_window_t`.
  - Commit: `feat(dashboard): add earth queue panel`

- [x] **T6.8 Domain detail view**
  - Depends: T6.6
  - Do: `/domain/:name`: raw series with baseline band, limit lines, detector state, model coefficients for Cardiovascular; Radiation shows the Poisson threshold line and one sentence on why a fixed threshold misfires.
  - Accept: tests for each domain fixture; unknown domain shows a not-found message inside the shell.
  - Commit: `feat(dashboard): add domain detail view`

- [x] **T6.9 History view**
  - Depends: T6.8
  - Do: metric and crew selectors; 7-day trend; CUSUM panel with the alarm line.
  - Accept: tests switch metric and crew and assert the requested query parameters.
  - Commit: `feat(dashboard): add history view`

- [ ] **T6.10 Events view**
  - Depends: T6.3
  - Do: chronological log, newest first, kind filter, "Simulated" badge on simulator events, check-ins shown as context.
  - Accept: tests with `events_mixed`.
  - Commit: `feat(dashboard): add events view`

- [ ] **T6.11 Settings view**
  - Depends: T6.3
  - Do: enroll crew, reset baseline (in-app confirm dialog; no browser `confirm()`), auto-approve toggles per tier.
  - Accept: tests assert request bodies; reset requires confirmation.
  - Commit: `feat(dashboard): add settings view`

- [ ] **T6.12 Daily check-in**
  - Depends: T6.4
  - Do: per D13; shown when `checkin_due`; completes in three taps; posts and dismisses.
  - Accept: tests: three taps submit; no level or color changes after submit.
  - Commit: `feat(dashboard): add daily check-in`

- [ ] **T6.13 Responsive layout and accessibility**
  - Depends: T6.5 to T6.12
  - Do: tablet first at 1280 x 800; phone at 390 x 844 stacks the cards in one column; visible focus states; level words present.
  - Accept: Playwright against the mock API: at phone width the four cards are vertically stacked (each card's top below the previous card's bottom); axe reports no serious or critical violations on any route.
  - Commit: `feat(dashboard): add responsive layout and accessibility fixes`

- [ ] **T6.14 Copy-rule tests**
  - Depends: T6.13
  - Do: one Vitest suite that renders every route with every fixture and scans visible text for the copy rules listed at the top of P6.
  - Accept: suite green; deliberately breaking a fixture string makes it fail (prove once, then revert).
  - Commit: `test(dashboard): enforce copy rules on every view`

- [ ] **T6.15 Production build served without Node**
  - Depends: T6.14, T5.4
  - Do: `npm run build` to `dashboard/dist`; JS bundle budget: warn above 400 kB gzip; `make serve-mock` serves it from the Python process. Run gate G3.
  - Accept: Playwright smoke against `make serve-mock` (no Vite running): home renders, cards visible, footer present.
  - Commit: `build(dashboard): serve production build from mock api`

### P7. End-to-end, demo and handoff (closes gate G4)

- [ ] **T7.1 End-to-end per scenario**
  - Depends: T6.15, T3.10
  - Do: Playwright suite that, for each scenario, starts `serve-mock` at high speed (choose the speed so each run takes under 60 s), waits for each expected state, and asserts card levels, attribution text and timeline markers; saves screenshots to the gitignored report folder.
  - Accept: `make e2e` green for every scenario.
  - Commit: `test(e2e): verify dashboard states for every scenario`

- [ ] **T7.2 Demo runbook and targets**
  - Depends: T7.1
  - Do: `make demo-mock`, `make demo-live`; `docs/demo.md` maps the 8-step v2 demo script to commands, marks which steps need hardware, and documents the `--replay` fallback line.
  - Accept: every command in `docs/demo.md` runs (hardware steps excepted, marked as such).
  - Commit: `docs(demo): add simulator and dashboard demo runbook`

- [ ] **T7.3 Backend handoff**
  - Depends: T7.1
  - Do: `docs/handoff-backend.md`: contract v1 and the change process; `/api` prefix and static mount code; the CO2 conversion location; `thresholds.yaml` as the source of limits; scenario `expect` blocks as the eval oracle for `make eval`; `quiet_week` JSONL for baseline pre-seeding; open items from `OPEN_QUESTIONS.md`.
  - Accept: every file path and command in the doc exists or runs.
  - Commit: `docs: add backend lane handoff`

- [ ] **T7.4 README quickstart**
  - Depends: T7.2
  - Do: setup, run the simulator, run the mock API, run the dashboard in dev, run tests, repo map, conventions, prototype disclaimer.
  - Accept: commands in the README run on a fresh clone.
  - Commit: `docs(repo): write readme quickstart`

- [ ] **T7.5 Final verification and close-out**
  - Depends: T7.1 to T7.4
  - Do: fresh clone into a temp directory; `make setup && make check-all`; record timings; grep for `TODO`/`FIXME` without a task or blocker reference; write the final report in `PROGRESS.md` (tasks done, blocked, open questions, how to run) and the line `LOOP_COMPLETE`; push; if `gh` is available and authenticated, open a draft PR from `build/sim-dashboard` to `main` titled "Simulator, mock API and dashboard". Run gate G4.
  - Accept: `check-all` green on the fresh clone.
  - Commit: `chore(plan): close out simulator and dashboard plan`

---

## 9. Gates

| Gate | Closes after | Must be true | Then |
|---|---|---|---|
| G1 Contract frozen | T1.4 | `make contracts` green; `contracts/VERSION` is 1.0.0 | push |
| G2 Simulator publishing three crew | T3.11 | `make sim-eval` green on 5 seeds; T2.7 passing or skip-documented; `quiet_week` generation under 120 s | push |
| G3 Dashboard on simulated data | T6.15 | `make check-all` green except e2e; production build served by the mock API | push |
| G4 Done | T7.5 | `make check-all` green on a fresh clone | push, draft PR |

**Contract change process after G1:** a numbered `DECISIONS.md` entry; bump `contracts/VERSION` (minor for additive, major for breaking); `CHANGELOG.md` line; update schemas, examples, simulator, mock API and regenerated types **in the same commit**; `make check-all` green; commit as `feat(contracts): ...` (or `feat(contracts)!:` for breaking).

---

## 10. Definition of done (whole plan)

- A fresh clone runs `make setup && make check-all` green.
- `ccm-sim run` publishes three crew plus the cabin to a broker with schema-valid messages; every v2 scenario plus the quiet runs and dropouts exist, pass `make sim-eval` on 5 seeds, and carry `expect` blocks.
- `ccm-sim record` and `ccm-sim replay` round-trip.
- `make serve-mock` serves every dashboard view with no Node process running, and every scenario's expected states appear in the e2e suite.
- Every screen follows the copy rules; the footer is everywhere; the source badge is on every crew chip.
- `docs/demo.md` and `docs/handoff-backend.md` exist and their commands run.
- `PROGRESS.md` ends with the final report and `LOOP_COMPLETE`.

---

## 11. Risks the loop should expect

| Risk | Handling |
|---|---|
| No MQTT broker on the machine | T2.7 skip path; everything else uses MemorySink and JSONL |
| Statistical tests flaky | fixed seeds; tolerances in the task text; never widen a tolerance without a `DECISIONS.md` entry explaining the measured spread |
| Long slow tests | `slow` marker; `make check` stays under about 3 minutes, `check-all` carries the rest |
| Playwright browsers missing | `npx playwright install chromium` (user level); if that fails, block T6.13, T6.15, T7.1 per 7.4 and continue |
| Threshold values change later | D6 test fails loudly and points at `thresholds.yaml` |
| Scope creep (more sensors, LLM features, analytics in the mock) | Section 1 and rule 7.2; log ideas in `OPEN_QUESTIONS.md` |

---

## 12. Discovered tasks

(The loop appends `X<n>` items here.)

---

## Appendix A. Contract sketches

Field names, types and ranges below are the starting point for the JSON Schemas. Times are unix seconds (float). Levels are `"green" | "yellow" | "red"`. Domains are `"cardio" | "air" | "thermal" | "radiation"`.

**A.1 Wearable telemetry** (`ccm/wearable/telemetry`)

```json
{"node":"wearable","id":"W1","crew":"W1","src":"sim","seq":1842,
 "t_node":1760000001.8,"t_meas":1760000000.0,
 "hr":62,"spo2":97,"skin_c":33.4,"act":0.12,"motion":false,
 "ibi":[968,975,960,982,971],"batt":3.91}
```

`hr` int 25 to 250 or null; `spo2` int 50 to 100 or null; `skin_c` 20 to 45; `act` >= 0; `ibi` 0 to 20 ints in [300, 2000]; `batt` 3.0 to 4.3; optional `finger` (false only, D15). Required: everything except `finger`.

**A.2 Cabin telemetry** (`ccm/cabin/telemetry`)

```json
{"node":"cabin","id":"C1","src":"sim","seq":902,"t_node":1760000000.4,"t_meas":1760000000.0,
 "co2":812,"temp_c":22.1,"rh":41,"voc":105,"pm1":2,"pm25":4,"pm10":6,"cpm":18,"c10s":3}
```

`co2` ppm int 0 to 40000; `cpm` and `c10s` optional (no Geiger module); `voc` 0 to 500.

**A.3 Node status** (`ccm/wearable/status/{id}`, `ccm/cabin/status/{id}`, retained)

```json
{"node":"cabin","id":"C1","state":"offline","t":1760000480.0}
```

**A.4 Sim event** (`ccm/sim/event`)

```json
{"scenario":"scrubber_failure","name":"co2_passes_yellow","label":"CO2 passes 2.5 mmHg",
 "phase":"mark","t_meas":1760007200.0,"crew":null}
```

`phase`: `start | end | mark`; `crew`: crew id or null.

**A.5 `GET /api/status`**

```json
{
  "t": 1760010000.0,
  "source_mode": "mock",
  "thresholds_status": "provisional",
  "crew_status": {"level":"red","domain":"air",
    "sentence":"Cabin CO2 3.1 mmHg, baseline 0.6; 3 of 3 crew show lower pulse-rate variability; consistent with a cabin cause.",
    "attribution":"cabin","action":"Check scrubber, increase ventilation, retest in 30 min"},
  "crew": [{"id":"W1","name":"W1","src":"hw","online":true,"level":"yellow",
            "baseline":"ready","learning_ends_t":null,"last_seen_t":1760009995.0}],
  "cards": [{"domain":"air","level":"red","reason":"Cabin CO2 3.1 mmHg, baseline 0.6.",
             "action":"Check scrubber, increase ventilation, retest in 30 min",
             "attribution":"cabin","crew":["W1","W2","W3"],
             "numbers":[{"label":"CO2","value":3.1,"unit":"mmHg","baseline":0.6}],
             "detector":{"name":"threshold","state":"red","detail":"above 3.0 mmHg for 12 min"},
             "model":null}],
  "nodes": [{"node":"cabin","id":"C1","state":"online","last_seen_t":1760009998.0}],
  "correlation": {"x":"co2_mmhg","y":"prv","crew":"W1","lag_min":20,"r":-0.71,
                  "sentence":"Pulse-rate variability began dropping 20 min after CO2 passed 2.5 mmHg."},
  "checkin_due": false
}
```

`cards` always has exactly four entries, one per domain. `model` (Cardiovascular only) is `{"beta0":..,"beta1":..,"beta2":..,"fitted_t":..}`. `attribution`: `"cabin" | "individual" | "unclear" | null`.

**A.6 `GET /api/history?metric=&crew=&hours=6&step=60`**

```json
{"metric":"prv","unit":"ms","crew":"W1",
 "points":[{"t":1760000000.0,"mean":44.0,"min":39.0,"max":51.0}],
 "baseline":[{"t":1760000000.0,"mean":45.0,"lo":38.0,"hi":52.0}],
 "cusum":[{"t":1760000000.0,"pos":0.4,"neg":0.0,"h":5.0}],
 "limits":{"yellow":null,"red":null}}
```

Metrics: `hr`, `hr_resid`, `prv`, `spo2`, `skin_c`, `act`, `co2_mmhg`, `temp_c`, `rh`, `voc`, `pm25`, `cpm`. `crew` is null for cabin metrics. `baseline`, `cusum`, `limits` may be null.

**A.7 `GET /api/events?since=&limit=`**

```json
{"events":[{"id":"e-120","t":1760007200.0,"kind":"sim_event","domain":"air","metric":"co2_mmhg",
            "crew":null,"score":null,"sentence":"Simulated: CO2 passes 2.5 mmHg","simulated":true}]}
```

`kind`: `spike | drift | correlation | sim_event | checkin | node`.

**A.8 Earth queue.** `GET /api/earth-queue` returns `{"next_window_t":..., "items":[item]}`; item is `{"id","t","tier":"crew_only|flight_surgeon|urgent","approved":bool,"sent":bool,"bytes":int,"summary":str,"payload":object}`. `POST /api/earth-queue/{id}/approve` returns the item.

**A.9 Settings.** `GET /api/settings` returns `{"crew":[{"id","name","enrolled_t"}],"auto_approve":{"crew_only":bool,"flight_surgeon":bool,"urgent":bool}}`; `PUT /api/settings` takes the `auto_approve` object; `POST /api/settings/enroll {"id","name"}`; `POST /api/settings/reset-baseline {"crew","metric":null|str}`.

**A.10 Check-in.** `POST /api/checkin {"crew":"W1","mood":1..5,"sleep":1..5,"note":str|null}` returns `{"ok":true,"event_id":"e-..."}`.

## Appendix B. Scenario file format

**B.1 Shape**

```yaml
name: scrubber_failure
title: CO2 scrubber failure
duration: 4h
crew: [W1, W2, W3]
events:
  - at: 30m
    name: scrubber_fault
    label: Scrubber fault begins
    effects:
      - {target: cabin.co2, op: ramp, to: {threshold: air.co2.red, factor: 1.3}, over: 3h}
      - {target: crew.*.rmssd, op: coupled, driver: cabin.co2,
         start: {above_threshold: air.co2.yellow, lag: 20m}, gain_at_peak: -12}
      - {target: crew.*.hr, op: coupled, driver: cabin.co2,
         start: {above_threshold: air.co2.yellow, lag: 20m}, gain_at_peak: 6}
marks:
  - {when: "cabin.co2 >= air.co2.yellow", name: co2_passes_yellow, label: "CO2 passes {air.co2.yellow} mmHg"}
  - {when: "cabin.co2 >= air.co2.red", name: co2_passes_red, label: "CO2 passes {air.co2.red} mmHg"}
expect:
  - {card: air, level: yellow, from: "cabin.co2 >= air.co2.yellow", until: "cabin.co2 >= air.co2.red"}
  - {card: air, level: red, from: "cabin.co2 >= air.co2.red"}
  - {card: cardio, level: yellow, from: "mark:co2_passes_yellow + 25m", attribution: cabin, crew: "*"}
  - {correlation: {x: co2_mmhg, y: prv, lag_min: [15, 25]}}
```

**B.2 Effect ops**

| op | Fields | Meaning |
|---|---|---|
| `set` | `value` | hold a target at a value |
| `step` | `delta`, `for` | add `delta` for a duration |
| `ramp` | `to` (number or threshold ref), `over` | linear ramp from current value |
| `drift_per_day` | `delta`, `days` | slow linear drift |
| `coupled` | `driver`, `start`, `gain_at_peak` | target offset proportional to the driver's excess over the start threshold, delayed by `lag` |
| `exercise` | `act`, `for`, `recovery_tau` | activity block; HR follows the model |
| `rate` | `cpm`, `for` | Poisson rate change for Geiger counts |
| `silence` | `node`, `for`, `buffer` | node goes offline; `buffer: true` flushes on return |

Thresholds are referenced by path into `contracts/thresholds.yaml` and converted to ppm through `units.py` when the target is in ppm.

**B.3 Expectations.** Each entry names a `card` and `level` (with optional `attribution`, `crew`), or a `correlation`, or `quiet: [domains]` (nothing may fire, used by `exercise_block` and `coincident_trends`), with `from`/`until` as a truth-channel condition, a mark reference plus offset, or a duration offset from scenario start. The mock API uses them to build `/api/status`; the Backend lane's `make eval` uses them as the oracle.

Expected outcomes to encode (v2 scenario library):

| Scenario | Expect |
|---|---|
| scrubber_failure | Air yellow then red; Cardiovascular yellow for all crew with attribution cabin; correlation lag 15 to 25 min |
| individual_illness | Cardiovascular yellow for W2 only, attribution individual; Air green |
| coincident_trends | `quiet: [cardio, air]`; no correlation |
| solar_particle_event | Radiation yellow after one window, red after two in a row, green after the step ends |
| sleep_debt_drift | no spike events; Cardiovascular yellow from day 4 with a drift reason, attribution individual |
| exercise_block | `quiet: [cardio]` |
| thermal_fault | Thermal yellow then red; Cardiovascular stays green |
| wifi_dropout | C1 offline then online; no gap in 1-minute coverage |
| ble_dropout | W1 offline then online; no gap |
| quiet_day, quiet_week | `quiet` on all domains (false-alarm baseline) |

## Appendix C. Beat generator

Per beat $n$: $RR_n = \overline{RR}(t_n) + x_n + r_n$, where $\overline{RR}(t) = 60000 / HR(t)$ ms, $r_n$ is a small respiratory sinus term (period about 4 s, amplitude a few ms), and $x_n$ is AR(1):

$$x_n = \phi\,x_{n-1} + \varepsilon_n,\qquad \varepsilon_n \sim \mathcal{N}(0, \sigma_\varepsilon^2).$$

For a stationary AR(1), $\mathbb{E}[(x_{n+1}-x_n)^2] = \dfrac{2\sigma_\varepsilon^2}{1+\phi}$, so to hit a target RMSSD set

$$\sigma_\varepsilon = \text{RMSSD}_{\text{target}}\sqrt{\frac{1+\phi}{2}},\qquad \phi = 0.3 \text{ (default)}.$$

Slow changes in $\overline{RR}$ and the respiratory term add a little to the measured RMSSD; T2.2's 15% tolerance covers that, and the generator may subtract a calibration factor measured on a quiet run (record it in `DECISIONS.md`). The gateway's metric is

$$\text{RMSSD} = \sqrt{\frac{1}{N-1}\sum_{i=1}^{N-1}\left(RR_{i+1}-RR_i\right)^2}.$$

## Appendix D. Running the loop headless (optional)

Interactive: paste `LOOP_PROMPT.md` into a Claude Code session started in the repo root. Headless alternative, from the repo root, one fresh session per iteration until a sentinel appears (check `claude --help` for the exact non-interactive and permission flags on your install):

```bash
until grep -qE '^LOOP_(COMPLETE|STOPPED)' docs/plan/PROGRESS.md 2>/dev/null; do
  claude -p "$(cat docs/plan/LOOP_PROMPT.md)"
  sleep 5
done
```
