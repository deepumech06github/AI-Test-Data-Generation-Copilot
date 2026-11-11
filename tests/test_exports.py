import csv
import io
import json
from pathlib import Path

from testdata_copilot.exports import rows_to_csv, rows_to_json
from testdata_copilot.schema import generate_dataset, parse_json_schema


def test_json_and_csv_exports_include_synthetic_metadata():
    schema_path = Path(__file__).parents[1] / "examples" / "user-profile.schema.json"
    schema = parse_json_schema(schema_path.read_text(encoding="utf-8"))
    rows = generate_dataset(schema, rows_per_scenario=2, seed=5)

    payload = json.loads(rows_to_json(schema, rows, 5))
    csv_rows = list(csv.DictReader(io.StringIO(rows_to_csv(rows))))

    assert payload["synthetic_only"] is True
    assert len(payload["records"]) == 6
    assert len(csv_rows) == 6
    assert "scenario" in csv_rows[0]

