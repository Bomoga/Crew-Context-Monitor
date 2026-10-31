import json

import pytest

from ccm_sim import contracts


def test_all_schemas_are_valid_json_schema() -> None:
    kinds = contracts.schema_kinds()
    assert {"wearable_telemetry", "cabin_telemetry", "node_status", "sim_event"} <= set(kinds)
    for kind in kinds:
        contracts.validator(kind)


def test_examples_through_public_loader() -> None:
    assert contracts.check_examples() == []
    for group in contracts.SCHEMA_DIRS:
        for kind, path in contracts.example_files(group, "valid"):
            contracts.validate(kind, json.loads(path.read_text(encoding="utf-8")))
        for kind, path in contracts.example_files(group, "invalid"):
            with pytest.raises(contracts.ContractError):
                contracts.validate(kind, json.loads(path.read_text(encoding="utf-8")))


def test_unknown_kind_raises() -> None:
    with pytest.raises(contracts.ContractError):
        contracts.validate("nope", {})


def test_error_message_names_the_field() -> None:
    bad = {"node": "cabin", "id": "C1", "state": "unknown", "t": 1.0}
    with pytest.raises(contracts.ContractError, match="state"):
        contracts.validate("node_status", bad)
