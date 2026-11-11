"""Optional OpenAI helper that drafts a schema from a data-shape description."""

from __future__ import annotations

import json
import os
from typing import Any

from .schema import parse_json_schema


SYSTEM_PROMPT = """Convert a short test-data requirement into a compact JSON Schema. Return only a JSON object with a `schema` property. The schema root must have type object and properties. Use only types object, array, string, integer, number, and boolean. Include required, enum, format (email/date/date-time/uuid), minimum/maximum, minLength/maxLength, and minItems/maxItems only when useful. Do not include example/default data values, real personal data, credentials, secrets, $ref, or arbitrary code. Use generic fictional field constraints."""


def infer_schema_from_description(description: str, api_key: str | None = None) -> dict[str, Any]:
    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("Set OPENAI_API_KEY to use AI schema drafting.")
    if not description.strip():
        raise ValueError("Describe the test data shape first.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError('Install the optional dependency with: pip install -e ".[llm]"') from exc
    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": description},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("The model returned an empty schema.")
    payload = json.loads(content)
    schema = payload.get("schema")
    if not isinstance(schema, dict):
        raise ValueError("The model response must contain a JSON Schema object under `schema`.")
    _remove_examples_and_defaults(schema)
    parse_json_schema(json.dumps(schema))
    return schema


def _remove_examples_and_defaults(value: Any) -> None:
    if isinstance(value, dict):
        value.pop("example", None)
        value.pop("default", None)
        for child in value.values():
            _remove_examples_and_defaults(child)
    elif isinstance(value, list):
        for child in value:
            _remove_examples_and_defaults(child)

