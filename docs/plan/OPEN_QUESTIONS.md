# Open questions

Never waited on. Confirm items come from PLAN.md Section 2.

- Backend: confirm D1 to D12 (crew ids, `t_meas`, JSON-only MQTT, CO2 conversion, thresholds, scrubber scenario, `/api` prefix, per-device status topics, `src` field, per-node MQTT clients, physiology params, scenario physics).
- Firmware A / Firmware: confirm D2 (`t_meas`), D3 (BLE binary decoded by bridge), D8, D15 (`finger:false`, null hr/spo2).
- Frontend: confirm D13 (check-in shape) and D14 (level words).
- Team: confirm D16 (branch and draft PR flow).
- Repository license: none chosen. Which license should the repo carry?
- `main` does not exist locally or on the remote (D17). Who creates it before the T7.5 draft PR?
- Pi OS Bookworm Python version: the plan assumes 3.11+; confirm on the Pi.
- WESAD/OSDR-derived physiology ranges (T2.8) were skipped because the dataset is not present. To enable: extract WESAD, set `CCM_WESAD_DIR`, and add `sim/tools/derive_params.py`.
