# Replay CSV

`ccm-sim record` writes this file from a live broker and `ccm-sim replay` publishes it again. It is
plain CSV (RFC 4180, UTF-8, `\n` line ends) with a header row and one row per MQTT message, in the
order the messages were received.

| Column | Meaning |
|---|---|
| `topic` | MQTT topic, for example `ccm/wearable/telemetry` |
| `t_meas` | Measured time in unix seconds, for ordering and pacing. Taken from the payload: `t_meas` for telemetry and simulator events, `t` for node status. If neither exists, the time the message was received. |
| `retain` | `1` if the message was retained, else `0` |
| `payload_json` | The payload exactly as published, a JSON object on one line (quoted per CSV rules) |

Rules:

- Every payload validates against the schema for its topic in `mqtt/`.
- Rows are published in file order. Replay waits until `t_meas` (relative to the first row, divided
  by the speed) before publishing a row; a row whose `t_meas` is earlier than the last one published
  (a buffered flush after a dropout) is published at once.
- Replay without `--retime` republishes payloads unchanged. With `--retime` it shifts `t_meas`,
  `t_node` (telemetry) and `t` (status) by one constant so spacing is preserved; the shift makes the
  last message land when the replay finishes.
- Statuses are replayed with their recorded `retain` flag and QoS 1; telemetry is QoS 0.
