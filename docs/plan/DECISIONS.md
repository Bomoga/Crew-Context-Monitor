# Decisions

D1 to D16 are the settled defaults from PLAN.md Section 2. Later decisions append below, numbered from D17.

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

## D17 Plan files committed on the build branch (2026-10-30)

`main` has no commits and the remote repository is empty, so T0.1's premise (plan files committed on `main`) did not hold. The plan files were committed as the first commit on `build/sim-dashboard`. The draft PR in T7.5 needs a `main` on the remote; the team must create it (see OPEN_QUESTIONS.md).

## D18 Windows toolchain (2026-10-30)

The build host is Windows 11 with Git Bash. GNU Make comes from `C:\msys64\usr\bin` (not on PATH by default). The Makefile detects `.venv/Scripts` versus `.venv/bin`. Python 3.11.9 is used; Node v24.14.0.

## D19 Extra API schemas and fixture naming (2026-10-30)

Two schemas beyond the plan's list: `checkin_response` (the `{ok, event_id}` reply in Appendix A.10) and `settings_update` (the PUT body, the `auto_approve` object), so the dashboard has a generated type and a validator for every request and response. Fixture files are named `<kind>.<name>.json`; the plan's state names map to `status.<name>` for the nine status states, `earth_queue.pending` (earth_queue_pending), `history.prv_6h` (history_prv_6h) and `events.mixed` (events_mixed). `status.cards` is enforced as exactly four entries in the fixed order cardio, air, thermal, radiation via `prefixItems`. `source_mode` allows `mock` or `live`; `thresholds_status` allows `provisional` or `final`.

## D20 Beat generator calibration factor (2026-10-30)

Measured on a 1 h quiet run at HR 62 and RMSSD target 45 ms, seeds 1 to 5: mean HR 61.86 to 62.09 bpm; median 5-minute RMSSD 44.6 to 46.1 ms (about 1% above target). No calibration factor is needed; `BeatGenerator(calibration=1.0)` stays the default. Phi 0.3, respiratory amplitude 3 ms, period 4 s.

## D21 Scrubber guard test and truth-vs-measured tolerance (2026-10-30)

T3.2 asks for a test that fails when "red is raised above the ramp peak". Under D6 the ramp peak is defined as 1.3 times the red threshold, so raising red scales the ramp and it still crosses red (a test asserts this). The failure that can actually occur is a threshold file whose yellow value lies above the ramp peak (above 3.9 mmHg at red 3.0); the coupled response then has no excess to follow and `build_world` raises a `ScenarioError` naming thresholds.yaml. A test covers it. Truth channels omit the cabin diurnal term (60 ppm, about 2.5 min of ramp) and noise, so measured threshold crossings are compared to marks with a 5 minute tolerance. Effect sizes are checked against a paired control run with the same seed, which removes circadian terms exactly.

## D22 Sleep debt drift applies to W1 only (2026-10-30)

T3.6 asks to record the crew choice. The `sleep_debt_drift` scenario drifts W1 only (HR +1 bpm/day, RMSSD -3 ms/day for 6 days). Because W2, W3 and the cabin stay flat, attribution can only say individual, as the v2 scenario library expects. The scenario lasts 6 days; the offsets hold at day 6 values (+6 bpm, -18 ms) if a longer duration is requested.

## D23 Averaging window for "HR minus model" checks (2026-10-30)

T3.7 and T3.8 compare message HR with the model's prediction. A single message HR carries about 1 bpm of AR noise plus 1 to 2 bpm of beat-averaging noise, so single-message comparisons would breach any +/-3 bpm limit by chance. Measured maximum |residual| over 5 seeds of the 5 h thermal run: 1-minute means 2.77 to 3.16 bpm (limit 3, so a few breach by noise alone); 5-minute means 1.82 to 2.14 bpm. The tests use 1-minute means for the 30 minute exercise block (maximum 3.76 against a limit of 5) and 5-minute means for the 5 h thermal run. Tolerances are unchanged from the plan.

## D24 Expectation oracle and the scrubber cardio start time (2026-10-30)

`ccm_sim.expectations` checks every `expect:` entry against an oracle derived from the truth channels: Air from the CO2 thresholds, Thermal from the cabin band and a steady skin residual (cabin swing of 2.0 C), Radiation from tumbling 10-minute windows with the Poisson line (yellow after one complete exceeding window, red after two), Cardiovascular from crew offsets (RMSSD change of 8 ms or HR change of 10 bpm, provisional; a 6 bpm resting-HR drift stays below the line so `coincident_trends` is quiet).

PLAN Appendix B.1 gives the scrubber cardio expectation as `mark:co2_passes_yellow + 25m`. With the coupling proportional to CO2 excess, the crew response is only 0.8 ms at that time, so no detector could flag it. The oracle first reaches the line 71 minutes after the yellow crossing, and the scenario ends 106 minutes after, so `scrubber_failure.yaml` now says `+ 75m`. Spec text is otherwise unchanged. The Backend lane should confirm both the detectability line and the time (OPEN_QUESTIONS.md).

A coupled effect's peak excess is taken over the scenario's own duration, not a shortened run, so `--duration 1h` on `scrubber_failure` keeps the full-scale response.

## D25 Replay file format added to the contract; what `--retime` means (2026-10-30)

T4.1 asks for `contracts/replay_csv.md`. It is an additive document, so the Section 9 process was followed: this entry, `contracts/VERSION` 1.0.0 to 1.1.0, a CHANGELOG line, and the README pointer. No schema, example, simulator or type changes were needed.

`--retime` shifts every time field (`t_meas`, `t_node`, status `t`) by one constant, so spacing is preserved. The constant is chosen so the recording's last message lands at the moment the replay finishes: `now + duration / speed - last_t`. At `--speed max` that is exactly "the recording ends now"; at real speed each message carries about the wall time at which it is published, so the dashboard sees live-looking data rather than a constant lag of the whole recording length.

## D26 Dashboard toolchain versions (2026-10-30)

Installed at T6.1 with npm 11.9 on Node v24.14 (Node 20+ is the floor); the lockfile pins them. Runtime: react 19.3.1, react-dom 19.3.1, react-router 8.5.1, recharts 3.10.1, ajv 8.20. Dev: vite 8.3.5, @vitejs/plugin-react 6.1.2, typescript 6.0.3, tailwindcss 4.3.3 with @tailwindcss/vite, vitest 5.0.5, jsdom 29.1.1, @testing-library/react 16.3.3, @playwright/test 1.64.1, @axe-core/playwright 4.14, eslint 10.14 with typescript-eslint 8.72 and eslint-plugin-react-hooks 7.1, prettier 3.9.10, json-schema-to-typescript 16.

`dashboard/src/api/types.gen.ts` is generated from `contracts/api/*.schema.json` by `scripts/gen-types.mjs`. json-schema-to-typescript turns the status `cards` schema (prefixItems plus `items: false`) into `never[]`, so for the TypeScript type only the generator rewrites it to a tuple of four `Card`. The JSON Schema, which also fixes the domain order, is unchanged and is what ajv validates against.

## D27 Tracking files were repaired from git history (2026-10-31)

At close-out, `docs/plan/PROGRESS.md` held only 15 of its entries and `docs/plan/DECISIONS.md` had lost the first rows of the defaults table. Several appends made with shell redirection (`cat >> file`) had landed at the start of the file and overwritten earlier text, intermittently and only for some commits; plain Python appends and the `echo >>` lines in OPEN_QUESTIONS.md were unaffected. The checkout is under OneDrive, which is the likely cause but was not confirmed. Each entry was intact in the commit that added it, so both files were rebuilt from git history without losing content: PROGRESS.md from the last intact version plus each later commit's entry, DECISIONS.md from the scaffold commit's header and table plus the surviving entries (D21 moved back into order). `sim/tests/test_tracking_docs.py` guards against a repeat. The close-out text itself was written with Python in append mode and checked afterwards.

## D28 One CI job, no hashFiles guard (2026-10-31)

PLAN T0.4 asked for a dashboard job guarded by `hashFiles('dashboard/package.json') != ''`. Every GitHub Actions run of that workflow failed at 0 seconds with "likely failed because of a workflow file issue", and the pull request showed no checks. The job-level `if` using `hashFiles` is the likely cause (from memory of GitHub's rules, not confirmed from an error message, which the API did not expose); `actionlint` was not installed to catch it. The dashboard exists now, so the guard is unnecessary: `.github/workflows/ci.yml` has one job that sets up Python 3.11 and Node 20 and runs `make setup check`, which already covers both halves.
