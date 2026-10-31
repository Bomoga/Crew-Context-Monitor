# Backend lane handoff

What the simulator, mock API and dashboard lane built, and what the Backend lane needs from it.
Everything here is a decision-support prototype, not a medical device. Commands run from the
repository root after `make setup`.

## What is here

| Piece | Where | What it is for |
|---|---|---|
| Contract v1 | `contracts/` | MQTT topics and message schemas, dashboard API schemas, provisional thresholds, the replay file format |
| Simulator | `sim/src/ccm_sim/` | Three crew and a cabin node publishing schema-valid messages, 11 scenarios |
| Mock API | `sim/src/ccm_sim/mockapi/` | The dashboard's `/api` routes served from a running scenario |
| Dashboard | `dashboard/` | React app built to `dashboard/dist` and served as static files |

## 1. The contract

The contract is the agreement between the lanes. Read `contracts/README.md` first. It lists every
topic, field and unit, and the API routes with their schemas in `contracts/api/`. The version is in
`contracts/VERSION` (1.1.0) and the history in `contracts/CHANGELOG.md`.

- MQTT carries JSON only (D3). Topics, QoS and retention are in `contracts/mqtt/topics.yaml`;
  schemas are `contracts/mqtt/*.schema.json`.
- Every reading carries `t_meas`, the measured time on the synced node clock. Analysis should use it
  and ignore `t_node` (D2). Messages carry `src` (`hw` or `sim`), which analytics must ignore (D9).
- Validate against the schemas in code with `ccm_sim.contracts.validate(kind, obj)`, or check the
  examples with:

```bash
make contracts
```

**Changing the contract after v1.0.0** follows the process in `contracts/README.md`: a numbered entry
in `docs/plan/DECISIONS.md`, a version bump (minor if additive, major if breaking), a changelog line,
and schemas, examples, simulator, mock API and the regenerated dashboard types updated in the same
commit. Regenerate the dashboard's TypeScript types from the schemas with:

```bash
make types
```

## 2. The `/api` prefix and the static mount

All API routes live under `/api` (D7), so the dashboard can own `/`, `/domain/:name`, `/history`,
`/events` and `/settings` on the same server. The routes and their response schemas:

| Route | Response schema |
|---|---|
| `GET /api/status` | `status` |
| `GET /api/history?metric=&crew=&hours=&step=` | `history` |
| `GET /api/events?since=&limit=` | `events` (oldest first, `limit` 1 to 1000, default 200) |
| `GET /api/earth-queue`, `POST /api/earth-queue/{id}/approve` | `earth_queue`, `earth_queue_item` |
| `GET` and `PUT /api/settings` | `settings` (PUT takes `settings_update`) |
| `POST /api/settings/enroll`, `POST /api/settings/reset-baseline` | `settings` |
| `POST /api/checkin` | `checkin_response` |

The mock follows these behaviors, which the dashboard relies on: approving a queue item twice returns
the same item; a check-in adds a `checkin` event and never changes a level; unknown crew ids are 404
and bad bodies are 422; unknown paths under `/api` are a JSON 404, never the app.

The mock serves the built dashboard with the code in `sim/src/ccm_sim/mockapi/static.py`. The real
FastAPI service can use it unchanged: include the API routers first, then mount the dashboard last
so its catch-all never shadows an API route.

```python
from pathlib import Path

from fastapi import FastAPI

from ccm_sim.mockapi.static import mount_dashboard

app = FastAPI()
# ... include the /api routers here ...
mount_dashboard(app, Path("dashboard/dist"))
```

Real files in `dist` are served as they are, every other non-`/api` path returns `index.html` so a
reload on `/history` works, and the app is a plain static build with no Node process. Build it with:

```bash
make build
```

The real API replaces the mock on port 8000 with the same paths. The only field that tells them
apart is `source_mode` (`mock` or `live`). Routes under `/api/_mock` exist only in the mock.

## 3. CO2 units

MQTT carries CO2 in ppm (`co2`, the sensor's own unit). The API returns mmHg (`co2_mmhg`). The one
conversion is `ppm x 1e-6 x cabin pressure`, with the cabin pressure 760 mmHg unless changed (D4). It
is `ppm_to_mmhg` and `mmhg_to_ppm` in `sim/src/ccm_sim/units.py`, and the pressure is the
`cabin.pressure_mmhg` entry in `contracts/thresholds.yaml`. The dashboard does no unit math, so the
conversion belongs in the API layer, once.

## 4. Thresholds

`contracts/thresholds.yaml` is the source of every limit. Each value has a `source` and
`status: provisional`, and `/api/status` repeats the status as `thresholds_status`. The values come
from D5: CO2 yellow 2.5 mmHg and red 3.0 mmHg, cabin temperature band 18 to 27 C, skin residual
yellow 0.5 C and red 1.0 C for 30 minutes, and the radiation Poisson test on 10-minute windows
(count above the baseline plus 4 standard deviations: yellow after one window, red after two in a
row). The Backend lane owns the final values. Load them with `ccm_sim.thresholds.load_thresholds`.

The scrubber scenario is defined relative to this file (D6): the CO2 ramp peaks at 1.3 times the red
threshold, so editing the thresholds moves the scenario with them, and a threshold set that the ramp
cannot reach fails with a clear message.

## 5. Scenario expectations as the evaluation oracle

Every scenario file in `sim/scenarios/` has an `expect:` block that says what a correct pipeline
should show. Use them as the oracle for the Backend lane's `make eval`. The scenarios are:
`quiet_day`, `quiet_week`, `scrubber_failure`, `individual_illness`, `coincident_trends`,
`solar_particle_event`, `sleep_debt_drift`, `exercise_block`, `thermal_fault`, `wifi_dropout` and
`ble_dropout`.

- `ccm-sim scenarios check` lists each scenario as consistent: the expectations agree with the
  scenario's own ground truth and with the thresholds.
- `ccm-sim scenarios expected` prints, as JSON, checkpoint times for every scenario with the card
  levels, attribution, crew, correlation and offline nodes a correct pipeline should show at each.
  The grammar and the oracle are documented at the top of `sim/src/ccm_sim/expectations.py`.

```bash
ccm-sim scenarios check
ccm-sim scenarios expected
```

To run a scenario through a pipeline, publish it to a broker or write it to a file. Use a fixed seed
for repeatable numbers:

```bash
ccm-sim run --scenario scrubber_failure --speed 60 --seed 1 --broker localhost:1883
ccm-sim generate --scenario scrubber_failure --seed 1 --out data/scrubber.jsonl
```

Two things to know about the expectations (both are in `docs/plan/OPEN_QUESTIONS.md`):

- The cardiovascular detectability line is provisional (D24): a change of 8 ms in pulse-rate
  variability or 10 bpm in resting heart rate. A slow 6 bpm resting-heart-rate drift is deliberately
  below it, so `coincident_trends` expects nothing.
- `scrubber_failure` expects Cardiovascular yellow 75 minutes after CO2 passes yellow. The plan said
  25 minutes, which the proportional coupling cannot make detectable.

Randomness: each crew member and the cabin use their own named random stream, so adding a crew
member does not change anyone else's numbers, and the same seed gives byte-identical output.

## 6. Pre-seeding baselines

A quiet week of three crew and the cabin is the baseline pre-seed. It is 7 days of messages
(362,880 wearable and 60,480 cabin records), generated in about half a minute at maximum speed:

```bash
ccm-sim generate --scenario quiet_week --out data/qw.jsonl
```

The file has one `{"topic", "payload", "retain"}` JSON object per line, in order of measured time,
with the node status records first and last. To publish it to a broker instead of reading the
file, write a replay CSV (`contracts/replay_csv.md`) and replay it at full speed:

```bash
ccm-sim generate --scenario quiet_week --out data/qw.csv
ccm-sim replay --file data/qw.csv --speed max --broker localhost:1883
```

## 7. Publishing to your stack

`ccm-sim run` opens one MQTT client per node (D10), each with its own last will on its retained
status topic (D8), so a dropped node shows `offline` the way real hardware does. With the real
wearable as W1, run only the simulated crew:

```bash
ccm-sim run --scenario scrubber_failure --crew W2,W3 --speed 60 --broker localhost:1883
```

The `wifi_dropout` and `ble_dropout` scenarios drop a node's connection, buffer its readings, and
flush them in order on return with their original `seq` and `t_meas`, so analysis should place them
by measured time. The demo playlist and the replay fallback are in `docs/demo.md`.

## 8. What the mock does not do

The mock API detects nothing. Card levels, attribution and the correlation come from the scenario
expectations; the numbers are the generated data against the parameter baselines; the sentences come
from templates that follow the copy rules. The CUSUM curve in `/api/history` and the correlation `r`
are illustrative. All mock crew report `src: "sim"`. Real analytics (baselines, residuals, CUSUM,
correlation and attribution) and the real Earth queue are the Backend lane's.

## 9. Open items for the Backend lane

These are the questions the build loop logged without waiting. The full list is in
`docs/plan/OPEN_QUESTIONS.md`; the decisions behind them are in `docs/plan/DECISIONS.md`.

- Confirm D1 to D12 and D24: crew ids, `t_meas`, JSON-only MQTT, the CO2 conversion, the provisional
  thresholds, the scrubber scenario, the `/api` prefix, per-device status topics, the `src` field,
  one MQTT client per node, the physiology parameters, the scenario physics, and the cardiovascular
  detectability line.
- Physiology parameters are the plan's values, not fitted to WESAD or OSDR data (that step was
  skipped because the dataset is not present).
- There is no `main` branch yet on the remote (D17), and no repository license has been chosen.
