# Demo runbook

A decision-support prototype, not a medical device. This runbook takes the eight demo steps from
the v2 plan and maps each to a command. There are two ways to run it:

- **Mock mode** needs no broker and no hardware. The simulator runs inside the mock API
  (`sim/src/ccm_sim/mockapi/`) and serves the dashboard from the same process on port 8000. Every
  crew member is labelled Simulator.
- **Live mode** publishes the simulator's messages to a real MQTT broker for the Backend lane's
  stack. With the real wearable as W1, the simulator runs W2 and W3 only. W1's chip then says
  Hardware.

Steps that need the real wearable or the Backend stack are marked **(hardware)** or **(live)**; every
other command in this file runs on a laptop with the project set up.

## Before the demo

```bash
make setup
make build
```

Build once; `make demo-mock` rebuilds if you forget. The demo playlist is
`sim/scenarios/demo.yaml`: scrubber failure at 60 times real speed, then an individual illness at
120 times, then a solar particle event at 60 times. It lasts 15 simulated hours, which is
about 11 minutes of real time.

## The eight steps

### 1. Start the stack

Mock mode, one command (open http://127.0.0.1:8000):

```bash
make demo-mock
```

Live mode **(live)**: start the Backend stack and its broker first, then publish the demo. With
hardware W1 on, this runs W2 and W3:

```bash
make demo-live BROKER=localhost:1883
```

### 2. A calm home page

Everything is green and every crew chip says where its data comes from. In live mode W1 says
Hardware **(hardware)**; in mock mode all three say Simulator. The footer reads "Decision-support
prototype, not a medical device" on every screen.

### 3. The monitor learns what is normal for each person

The status bar shows how long until alerts start while baselines are being learned. To show this
state in mock mode, start with learning on:

```bash
ccm-sim serve-mock --scenario quiet_day --learning --speed 60 --port 8000
```

For the real stack, pre-seed the baseline with a quiet week of simulated data instead:

```bash
ccm-sim generate --scenario quiet_week --out data/qw.jsonl
```

### 4. The wearable loses the finger **(hardware)**

Lift the finger off the wearable's sensor. The wearable keeps sending messages with `hr` and
`spo2` as null and `"finger": false` (decision D15). What the dashboard shows for that is up to the
Backend lane's analytics; the simulator and the mock do not play this state, so this step needs the
real wearable.

### 5. CO2 scrubber failure (demo step 1)

The playlist starts here. Over about four simulated hours cabin CO2 climbs past the yellow line
(2.5 mmHg) and then the red line (3.0 mmHg). Watch Air quality turn yellow, then red; then
Cardiovascular turn yellow for all three crew with attribution Cabin. The timeline shows CO2 over
pulse-rate variability with dashed markers for the simulated events and the lag label ("Pulse-rate
variability began dropping 20 min after CO2 passed 2.5 mmHg"). Open Air quality for the limit
lines and the detector state.

To run only this scenario, at 60 times real speed:

```bash
make serve-mock SCENARIO=scrubber_failure SPEED=60
```

### 6. One crew member changes (demo step 2)

W2's resting heart rate rises and pulse-rate variability falls while the cabin stays normal. Only
W2's chip turns yellow and the card says "Only W2 changed; cabin within normal". This is the same
signal as step 5 but a different cause.

### 7. Solar particle event (demo step 3)

The radiation proxy steps up for 40 minutes. Radiation (proxy) turns yellow after one 10-minute
window above the expected range, red after two in a row, and green again once a clean window has
passed. Open the Radiation (proxy) page for the Poisson threshold and the one-sentence reason a
fixed threshold would misfire.

### 8. Earth queue and the daily check-in

Red cards queue a summary for Earth. Nothing is sent until a crew member approves it (or turns on
auto-approve for that tier in Settings). Approve one, and note the countdown to the next comms
window. The daily check-in appears at the bottom right; send it in three taps and see that no
level or color changes. It shows up in Events as context.

## If something fails: the replay fallback

Record the demo ahead of time as a replay file, then publish it instead of running the simulator.
The file keeps each message's measured time, and `--retime` shifts the times so the recording looks
live while it plays:

```bash
ccm-sim generate --playlist demo --out data/demo.csv
```

Then, in place of step 1 in live mode **(live)**:

```bash
make demo-live REPLAY=data/demo.csv BROKER=localhost:1883
```

This runs `ccm-sim replay --file data/demo.csv --speed 60 --retime --broker localhost:1883`. To
capture a real run instead, record the broker while it is running:

```bash
ccm-sim record --broker localhost:1883 --out data/live.csv --duration 30m
```

The replay file format is in `contracts/replay_csv.md`.

## Dashboard development

To work on the dashboard against the mock API with hot reload, run the mock API in one terminal
and Vite in another; Vite proxies `/api` to port 8000:

```bash
make dashboard-dev
```
