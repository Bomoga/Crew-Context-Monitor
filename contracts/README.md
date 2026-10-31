# Contracts

Version: see [VERSION](VERSION) (1.0.0). Changes: [CHANGELOG.md](CHANGELOG.md).

These files are the agreement between the simulator, the mock API, the real backend and the dashboard. Times are unix seconds (float). Levels are `green`, `yellow`, `red`. Domains are `cardio`, `air`, `thermal`, `radiation`.

## MQTT

[mqtt/topics.yaml](mqtt/topics.yaml) lists every topic, its publisher, rate, retention and QoS. Payloads are always JSON (D3).

| Topic | Schema | Retained | QoS |
|---|---|---|---|
| `ccm/wearable/telemetry` | `wearable_telemetry` | no | 0 |
| `ccm/cabin/telemetry` | `cabin_telemetry` | no | 0 |
| `ccm/wearable/status/{id}` | `node_status` | yes | 1 |
| `ccm/cabin/status/{id}` | `node_status` | yes | 1 |
| `ccm/sim/event` | `sim_event` | no | 1 |

Key fields:

- `id` is the device id; wearable messages also carry `crew` (crew member id, D1) and `src` (`hw` or `sim`, D9). Analytics ignores `src`.
- `t_meas` is the time the reading was measured on the synced node clock; all analysis uses it (D2). `t_node` is the raw node clock, for debugging.
- With no finger on the sensor, `hr` and `spo2` are `null` and `"finger": false` is present (D15).
- `seq` starts at 1 per node and rises by 1; gaps mean lost messages.

## Units

MQTT carries CO2 in ppm (`co2`). The API returns CO2 in mmHg (`co2_mmhg`). The one conversion is `ppm x 1e-6 x P_cabin` with `P_cabin = 760` mmHg by default (D4), implemented in `ccm_sim.units`. The dashboard does no unit math.

## Dashboard API

All routes live under `/api` (D7). Schemas are in [api/](api/) and every response carries `source_mode` where noted in the schema.

| Route | Request | Response schema |
|---|---|---|
| `GET /api/status` | | `status` |
| `GET /api/history?metric=&crew=&hours=&step=` | | `history` |
| `GET /api/events?since=&limit=` | | `events` |
| `GET /api/earth-queue` | | `earth_queue` |
| `POST /api/earth-queue/{id}/approve` | | `earth_queue_item` |
| `GET /api/settings` | | `settings` |
| `PUT /api/settings` | `settings_update` | `settings` |
| `POST /api/settings/enroll` | `enroll_request` | `settings` |
| `POST /api/settings/reset-baseline` | `reset_request` | `settings` |
| `POST /api/checkin` | `checkin_request` | `checkin_response` |

Fixtures under `examples/api/valid/` are named `<kind>.<name>.json`; the nine `status` fixtures cover the dashboard states, plus `earth_queue.pending`, `history.prv_6h` and `events.mixed`.

## Thresholds

[thresholds.yaml](thresholds.yaml) is the single source of limits. Every value carries a `source` and `status: provisional` until the Backend lane confirms it. Scenarios reference thresholds by dotted path such as `air.co2.red`.

## Validating

```bash
make contracts
```

checks that every valid example passes and every invalid example fails, and that each schema has at least 3 invalid examples. In code: `ccm_sim.contracts.validate(kind, obj)`.

## Change process (after the v1.0.0 freeze)

1. Add a numbered entry to `docs/plan/DECISIONS.md`.
2. Bump [VERSION](VERSION): minor for additive changes, major for breaking ones.
3. Add a line to [CHANGELOG.md](CHANGELOG.md).
4. Update schemas, examples, the simulator, the mock API and the regenerated dashboard types in the same commit.
5. `make check-all` must be green.
6. Commit as `feat(contracts): ...`, or `feat(contracts)!: ...` with a `BREAKING CHANGE:` footer for a breaking change.
