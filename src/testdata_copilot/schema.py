"""Safe JSON Schema subset parsing and synthetic data generation."""

from __future__ import annotations

import json
import math
import random
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse


SUPPORTED_TYPES = {"object", "array", "string", "integer", "number", "boolean"}
MAX_PROPERTIES = 50
MAX_DEPTH = 8
MAX_STRING_LENGTH = 2000
MAX_ARRAY_ITEMS = 100
SUPPORTED_FORMATS = {"email", "date", "date-time", "uuid", "uri"}


def parse_json_schema(text: str) -> dict[str, Any]:
    """Parse a bounded JSON Schema subset suitable for local synthetic data."""

    if not text.strip():
        raise ValueError("Provide a JSON Schema before generating data.")
    try:
        schema = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON Schema: {exc.msg} at line {exc.lineno}, column {exc.colno}.") from exc
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("The root JSON Schema must be an object schema.")
    _validate_schema_shape(schema)
    if not schema.get("properties"):
        raise ValueError("The root schema needs at least one property.")
    return schema


def _validate_schema_shape(schema: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ValueError(f"Schema nesting cannot exceed {MAX_DEPTH} levels.")
    if isinstance(schema, list):
        for value in schema:
            _validate_schema_shape(value, depth)
        return
    if not isinstance(schema, dict):
        return
    if "$ref" in schema:
        raise ValueError("$ref is not supported in this demo; inline the referenced schema.")
    kind = schema.get("type")
    if kind is not None and kind not in SUPPORTED_TYPES:
        raise ValueError(f"Unsupported JSON Schema type: {kind}.")
    if "format" in schema and schema["format"] not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported string format: {schema['format']}.")
    for name in ("minimum", "maximum"):
        if name in schema and (isinstance(schema[name], bool) or not isinstance(schema[name], (int, float))):
            raise ValueError(f"{name} must be numeric.")
    if "minimum" in schema and "maximum" in schema and schema["minimum"] > schema["maximum"]:
        raise ValueError("maximum cannot be less than minimum.")
    for name in ("minLength", "maxLength"):
        if name in schema and (not isinstance(schema[name], int) or schema[name] < 0 or schema[name] > MAX_STRING_LENGTH):
            raise ValueError(f"{name} must be an integer between 0 and {MAX_STRING_LENGTH}.")
    for name in ("minItems", "maxItems"):
        if name in schema and (not isinstance(schema[name], int) or schema[name] < 0 or schema[name] > MAX_ARRAY_ITEMS):
            raise ValueError(f"{name} must be an integer between 0 and {MAX_ARRAY_ITEMS}.")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError("properties must be a JSON object.")
    if len(properties) > MAX_PROPERTIES:
        raise ValueError(f"A schema object cannot have more than {MAX_PROPERTIES} properties.")
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(name, str) for name in required):
        raise ValueError("required must be an array of property names.")
    unknown_required = set(required) - set(properties)
    if unknown_required:
        raise ValueError("required contains unknown properties: " + ", ".join(sorted(unknown_required)))
    for name, child in properties.items():
        if not isinstance(name, str) or not isinstance(child, dict):
            raise ValueError("Each property must have a string name and an object schema.")
        if "type" not in child and "enum" not in child:
            raise ValueError(f"Property `{name}` needs a supported type or enum.")
    _validate_schema_shape(properties, depth + 1)
    _validate_schema_shape(schema.get("items", {}), depth + 1)
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise ValueError("enum must be a non-empty array.")
    if "enum" in schema and kind is not None and any(not _matches_type(kind, value) for value in schema["enum"]):
        raise ValueError(f"enum values do not match the declared type `{kind}`.")
    items = schema.get("items")
    if items is not None and (not isinstance(items, dict) or ("type" not in items and "enum" not in items)):
        raise ValueError("array items must include a supported type or enum.")


def generate_dataset(schema: dict[str, Any], rows_per_scenario: int = 5, seed: int = 2026) -> list[dict[str, Any]]:
    """Generate positive, valid-boundary, and negative synthetic examples."""

    if not isinstance(rows_per_scenario, int) or not 1 <= rows_per_scenario <= 100:
        raise ValueError("Rows per scenario must be between 1 and 100.")
    _validate_schema_shape(schema)
    if schema.get("type") != "object" or not schema.get("properties"):
        raise ValueError("Generation requires an object schema with properties.")

    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    index = 1
    for scenario in ("Positive", "Boundary", "Negative"):
        for scenario_index in range(rows_per_scenario):
            data = _generate_value(schema, "record", index, rng)
            note = "All fields are synthetic and intended for non-production testing."
            if scenario == "Boundary":
                field_path, bound_value, detail = _choose_boundary(schema, scenario_index)
                if field_path:
                    _set_path(data, field_path, bound_value)
                    note = f"Boundary example: {detail}."
                else:
                    note = "No explicit boundary constraint was found; review the schema for additional edge cases."
            elif scenario == "Negative":
                field_path, invalid_value, detail, omit = _choose_negative(schema, scenario_index)
                if field_path:
                    if omit:
                        _remove_path(data, field_path)
                    else:
                        _set_path(data, field_path, invalid_value)
                    note = f"Negative example: {detail}."
            validation_errors = validate_instance(schema, data)
            if scenario in {"Positive", "Boundary"} and validation_errors:
                raise ValueError("Could not create a valid positive/boundary record: " + "; ".join(validation_errors[:3]))
            if scenario == "Negative" and not validation_errors:
                raise ValueError("Could not create a negative record that violates the supplied schema.")
            rows.append({
                "case_id": f"TD-{index:04d}",
                "scenario": scenario,
                "expected_validation": "REJECT" if scenario == "Negative" else "ACCEPT",
                "note": note,
                "data": data,
            })
            index += 1
    return rows


def validate_instance(schema: dict[str, Any], value: Any, path: str = "$", errors: list[str] | None = None) -> list[str]:
    """Validate values against the supported subset of JSON Schema keywords."""

    if errors is None:
        errors = []
    kind = schema.get("type")
    if not _matches_type(kind, value):
        errors.append(f"{path}: expected {kind}, got {_type_name(value)}")
        return errors
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is outside enum")
    if kind == "object":
        properties = schema.get("properties", {}) or {}
        for name in schema.get("required", []) or []:
            if name not in value:
                errors.append(f"{path}.{name}: required property is missing")
        for name, child in properties.items():
            if name in value:
                validate_instance(child, value[name], f"{path}.{name}", errors)
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in properties:
                    errors.append(f"{path}.{name}: additional property is not allowed")
    elif kind == "array":
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: fewer than minItems")
        if len(value) > schema.get("maxItems", MAX_ARRAY_ITEMS):
            errors.append(f"{path}: more than maxItems")
        item_schema = schema.get("items", {})
        for index, item in enumerate(value):
            validate_instance(item_schema, item, f"{path}[{index}]", errors)
    elif kind == "string":
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: shorter than minLength")
        if len(value) > schema.get("maxLength", MAX_STRING_LENGTH):
            errors.append(f"{path}: longer than maxLength")
        fmt = schema.get("format")
        if fmt == "email" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            errors.append(f"{path}: invalid email format")
        if fmt == "date":
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append(f"{path}: invalid date format")
        if fmt == "date-time":
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"{path}: invalid date-time format")
        if fmt == "uuid":
            try:
                uuid.UUID(value)
            except ValueError:
                errors.append(f"{path}: invalid UUID format")
        if fmt == "uri":
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append(f"{path}: invalid URI format")
    elif kind in {"integer", "number"}:
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum")
    return errors


def _generate_value(schema: dict[str, Any], field_name: str, index: int, rng: random.Random) -> Any:
    if schema.get("enum"):
        return rng.choice(schema["enum"])
    kind = schema.get("type")
    normalized = re.sub(r"[^a-z]", "", field_name.lower())
    if kind == "object":
        properties = schema.get("properties", {}) or {}
        return {name: _generate_value(child, name, index, rng) for name, child in properties.items()}
    if kind == "array":
        items = schema.get("items", {"type": "string"})
        count = schema.get("minItems", 1)
        if "maxItems" in schema and schema["maxItems"] < count:
            raise ValueError("maxItems cannot be less than minItems.")
        return [_generate_value(items, field_name, index + item_index, rng) for item_index in range(count)]
    if kind == "string":
        fmt = schema.get("format")
        if fmt == "email" or "email" in normalized:
            value = f"qa.user{index:04d}@example.test"
        elif fmt == "uuid":
            value = str(uuid.uuid5(uuid.NAMESPACE_URL, f"synthetic-{index}-{field_name}"))
        elif fmt == "date":
            value = (date(2026, 1, 1) + timedelta(days=index)).isoformat()
        elif fmt == "date-time":
            value = (datetime(2026, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=index)).isoformat().replace("+00:00", "Z")
        elif fmt == "uri" or "url" in normalized:
            value = f"https://example.test/resource/{index}"
        elif "phone" in normalized or "mobile" in normalized:
            value = f"+1-202-555-{100 + (index - 1) % 100:04d}"
        elif normalized in {"name", "fullname", "firstname", "lastname", "username"}:
            value = f"DemoUser{index:04d}"
        elif "address" in normalized:
            value = f"{100 + index} Example Street"
        elif normalized.endswith("id"):
            value = f"TEST-{index:05d}"
        elif "password" in normalized:
            value = f"DemoOnly!{index:04d}"
        else:
            value = f"sample-{field_name}-{index:04d}"
        return _fit_string(value, schema)
    if kind == "integer":
        minimum = math.ceil(schema.get("minimum", 0))
        maximum = math.floor(schema.get("maximum", minimum + 100))
        if maximum < minimum:
            raise ValueError(f"Maximum is less than minimum for `{field_name}`.")
        return rng.randint(minimum, maximum)
    if kind == "number":
        minimum = float(schema.get("minimum", 0))
        maximum = float(schema.get("maximum", minimum + 100))
        if maximum < minimum:
            raise ValueError(f"Maximum is less than minimum for `{field_name}`.")
        return round(rng.uniform(minimum, maximum), 2)
    if kind == "boolean":
        return bool(rng.getrandbits(1))
    return None


def _fit_string(value: str, schema: dict[str, Any]) -> str:
    minimum = schema.get("minLength", 0)
    maximum = schema.get("maxLength", MAX_STRING_LENGTH)
    if maximum < minimum:
        raise ValueError("maxLength cannot be less than minLength.")
    if len(value) < minimum:
        if schema.get("format") in {"email", "date", "date-time", "uuid"}:
            raise ValueError("String length constraints conflict with the requested format in this demo.")
        value += "x" * (minimum - len(value))
    return value[:maximum]


def _boundary_candidates(schema: dict[str, Any]) -> list[tuple[list[str], list[Any], str]]:
    candidates = []
    for name, child in (schema.get("properties", {}) or {}).items():
        kind = child.get("type")
        path = [name]
        if kind in {"integer", "number"}:
            if kind == "integer":
                values = [math.ceil(child["minimum"]) if key == "minimum" else math.floor(child["maximum"]) for key in ("minimum", "maximum") if key in child]
            else:
                values = [child[key] for key in ("minimum", "maximum") if key in child]
            if values:
                candidates.append((path, values, f"`{name}` at its declared numeric bound"))
        elif child.get("enum") and len(child["enum"]) > 1:
            candidates.append((path, [child["enum"][0], child["enum"][-1]], f"`{name}` at the first or last enum value"))
        elif kind == "string" and child.get("format") not in {"email", "date", "date-time", "uuid"} and ("minLength" in child or "maxLength" in child):
            base = _generate_value(child, name, 1, random.Random(1))
            values = []
            if "minLength" in child:
                values.append("x" * child["minLength"])
            if "maxLength" in child:
                values.append((base + "x" * child["maxLength"])[:child["maxLength"]])
            if values:
                candidates.append((path, values, f"`{name}` at its declared length bound"))
        elif kind == "array" and ("minItems" in child or "maxItems" in child):
            item_schema = child.get("items", {"type": "string"})
            values = []
            if "minItems" in child:
                values.append([_generate_value(item_schema, name, i + 1, random.Random(i + 1)) for i in range(child["minItems"])])
            if "maxItems" in child:
                values.append([_generate_value(item_schema, name, i + 1, random.Random(i + 1)) for i in range(child["maxItems"])])
            if values:
                candidates.append((path, values, f"`{name}` at its declared item-count bound"))
    return candidates


def _choose_boundary(schema: dict[str, Any], index: int) -> tuple[list[str] | None, Any, str]:
    candidates = _boundary_candidates(schema)
    if not candidates:
        return None, None, "no explicit boundary constraint"
    path, values, detail = candidates[index % len(candidates)]
    value = values[index % len(values)]
    return path, value, detail


def _choose_negative(schema: dict[str, Any], index: int) -> tuple[list[str] | None, Any, str, bool]:
    properties = schema.get("properties", {}) or {}
    required = [name for name in schema.get("required", []) if name in properties]
    if required:
        field = required[index % len(required)]
        return [field], None, f"required field `{field}` is omitted", True
    fields = list(properties)
    if not fields:
        return None, None, "no property was available for negative mutation", False
    field = fields[index % len(fields)]
    detail = properties[field]
    kind = detail.get("type")
    if kind in {"integer", "number"}:
        if "maximum" in detail:
            invalid = math.floor(detail["maximum"]) + 1 if kind == "integer" else detail["maximum"] + 1
            return [field], invalid, f"`{field}` is above its maximum", False
        if "minimum" in detail:
            invalid = math.ceil(detail["minimum"]) - 1 if kind == "integer" else detail["minimum"] - 1
            return [field], invalid, f"`{field}` is below its minimum", False
    if kind == "string" and (detail.get("format") == "email" or "email" in field.lower()):
        return [field], "not-an-email", f"`{field}` has an invalid email format", False
    if detail.get("enum"):
        return [field], "__invalid_enum_value__", f"`{field}` is outside its enum", False
    wrong_type = {"string": 7, "integer": "not-an-integer", "number": "not-a-number", "boolean": "not-a-boolean", "object": "not-an-object", "array": "not-an-array"}.get(kind, "invalid")
    return [field], wrong_type, f"`{field}` has the wrong data type", False


def _set_path(target: dict[str, Any], path: list[str], value: Any) -> None:
    current = target
    for segment in path[:-1]:
        current = current[segment]
    current[path[-1]] = value


def _remove_path(target: dict[str, Any], path: list[str]) -> None:
    current = target
    for segment in path[:-1]:
        current = current[segment]
    current.pop(path[-1], None)


def _matches_type(kind: str | None, value: Any) -> bool:
    return {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda: isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": lambda: isinstance(value, bool),
        None: lambda: True,
    }.get(kind, lambda: False)()


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    return "array" if isinstance(value, list) else "object" if isinstance(value, dict) else "string"

