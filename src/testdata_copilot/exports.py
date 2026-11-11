"""JSON and CSV exports for generated synthetic examples."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Iterable


def rows_to_json(schema: dict[str, Any], rows: Iterable[dict[str, Any]], seed: int) -> str:
    return json.dumps({
        "schema_version": "1.0",
        "project": "AI-Test-Data-Generation-Copilot",
        "synthetic_only": True,
        "seed": seed,
        "schema": schema,
        "records": list(rows),
    }, indent=2, ensure_ascii=False)


def rows_to_csv(rows: Iterable[dict[str, Any]]) -> str:
    materialized = list(rows)
    field_names = ["case_id", "scenario", "expected_validation", "note"]
    data_fields = sorted({key for row in materialized for key in row.get("data", {})})
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=field_names + data_fields)
    writer.writeheader()
    for row in materialized:
        flattened = {key: row.get(key, "") for key in field_names}
        for key in data_fields:
            value = row.get("data", {}).get(key, "")
            flattened[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
        writer.writerow(flattened)
    return output.getvalue()

