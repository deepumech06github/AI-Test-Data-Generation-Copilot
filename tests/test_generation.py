import json
from pathlib import Path

import pytest

from testdata_copilot.schema import generate_dataset, parse_json_schema, validate_instance


def _sample_schema():
    path = Path(__file__).parents[1] / "examples" / "user-profile.schema.json"
    return parse_json_schema(path.read_text(encoding="utf-8"))


def test_generator_returns_three_scenarios_and_seed_is_repeatable():
    schema = _sample_schema()
    first = generate_dataset(schema, rows_per_scenario=3, seed=15)
    second = generate_dataset(schema, rows_per_scenario=3, seed=15)

    assert first == second
    assert len(first) == 9
    assert {row["scenario"] for row in first} == {"Positive", "Boundary", "Negative"}


def test_positive_and_boundary_are_valid_while_negative_data_is_invalid():
    schema = _sample_schema()
    rows = generate_dataset(schema, rows_per_scenario=4, seed=7)

    for row in rows:
        errors = validate_instance(schema, row["data"])
        if row["scenario"] in {"Positive", "Boundary"}:
            assert errors == []
        else:
            assert errors


def test_schema_parser_rejects_refs_and_non_object_roots():
    with pytest.raises(ValueError, match="root JSON Schema"):
        parse_json_schema(json.dumps({"type": "array"}))
    with pytest.raises(ValueError, match="\$ref"):
        parse_json_schema(json.dumps({"type": "object", "properties": {"id": {"$ref": "#/definitions/Id"}}}))


def test_row_count_is_bounded():
    with pytest.raises(ValueError, match="between 1 and 100"):
        generate_dataset(_sample_schema(), rows_per_scenario=101)

