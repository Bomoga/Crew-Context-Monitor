# Contract changelog

Versioning: minor bump for additive changes, major bump for breaking ones.

## 1.1.0 (2026-10-30)

- Additive: `replay_csv.md` defines the record and replay file format (`topic,t_meas,retain,payload_json`). No schema changes.

## 1.0.0 (2026-10-30)

- Initial frozen contract: MQTT topics and four message schemas (wearable telemetry, cabin telemetry, node status, simulator event), eleven dashboard API schemas, provisional thresholds, CO2 ppm to mmHg conversion.
