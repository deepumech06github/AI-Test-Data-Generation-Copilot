"""Streamlit app for privacy-conscious synthetic test data generation."""

from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st

from testdata_copilot.exports import rows_to_csv, rows_to_json
from testdata_copilot.llm import infer_schema_from_description
from testdata_copilot.schema import generate_dataset, parse_json_schema, validate_instance


def _api_key() -> str | None:
    key = os.getenv("OPENAI_API_KEY", "")
    try:
        key = key or st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        pass
    return key or None


SAMPLE_SCHEMA = (Path(__file__).parent / "examples" / "user-profile.schema.json").read_text(encoding="utf-8")

st.set_page_config(page_title="AI Test Data Generation Copilot", page_icon="🧬", layout="wide")
st.title("🧬 AI Test Data Generation Copilot")
st.caption("Generate repeatable synthetic test records from JSON Schema, with positive, boundary, and negative scenarios.")

generate_tab, about_tab = st.tabs(["Generate test data", "About & architecture"])

with generate_tab:
    source = st.radio("Schema source", ["Edit JSON Schema", "Draft schema with AI"], horizontal=True)
    active_schema = None
    schema_text = None
    if source == "Edit JSON Schema":
        schema_text = st.text_area("JSON Schema", value=SAMPLE_SCHEMA, height=320, key="schema_input")
        try:
            active_schema = parse_json_schema(schema_text)
        except ValueError as exc:
            st.warning(str(exc))
    else:
        prompt = st.text_area("Describe the data shape and constraints", value="Generate test records for user profiles with a UUID, email, age from 18 to 120, status active/pending/locked, creation timestamp, and optional phone number.", height=130)
        st.caption("The description is sent to OpenAI only when you click the schema drafting button. Do not include real customer data, secrets, or credentials.")
        if st.button("Draft JSON Schema with AI", type="secondary"):
            try:
                inferred = infer_schema_from_description(prompt, api_key=_api_key())
                st.session_state["inferred_schema"] = inferred
                st.session_state["inferred_schema_editor"] = json.dumps(inferred, indent=2)
                st.session_state.pop("generated_rows", None)
            except Exception as exc:
                st.error(str(exc))
        active_schema = st.session_state.get("inferred_schema")
        if active_schema:
            if "inferred_schema_editor" not in st.session_state:
                st.session_state["inferred_schema_editor"] = json.dumps(active_schema, indent=2)
            inferred_text = st.text_area("Review and edit the inferred JSON Schema", key="inferred_schema_editor", height=320)
            try:
                active_schema = parse_json_schema(inferred_text)
            except ValueError as exc:
                active_schema = None
                st.warning(str(exc))

    controls = st.columns(2)
    rows_per_scenario = controls[0].number_input("Rows per scenario", min_value=1, max_value=100, value=5, step=1)
    seed = controls[1].number_input("Random seed", min_value=0, max_value=2_147_483_647, value=2026, step=1)
    if st.button("Generate synthetic test data", type="primary", disabled=active_schema is None):
        try:
            rows = generate_dataset(active_schema, int(rows_per_scenario), int(seed))
            st.session_state["generated_rows"] = rows
            st.session_state["generated_schema"] = active_schema
            st.session_state["generated_seed"] = int(seed)
            st.session_state["generated_rows_per_scenario"] = int(rows_per_scenario)
        except Exception as exc:
            st.error(str(exc))

    rows = st.session_state.get("generated_rows", [])
    generated_schema = st.session_state.get("generated_schema")
    if (rows and generated_schema and active_schema == generated_schema
            and st.session_state.get("generated_seed") == int(seed)
            and st.session_state.get("generated_rows_per_scenario") == int(rows_per_scenario)):
        st.divider()
        counts = {scenario: sum(row["scenario"] == scenario for row in rows) for scenario in ("Positive", "Boundary", "Negative")}
        metrics = st.columns(4)
        metrics[0].metric("Total records", len(rows))
        metrics[1].metric("Positive", counts["Positive"])
        metrics[2].metric("Boundary", counts["Boundary"])
        metrics[3].metric("Negative", counts["Negative"])
        st.caption("Generated locally from the schema. Every value is synthetic and intended for non-production testing.")
        table = []
        for row in rows:
            validation_errors = validate_instance(generated_schema, row["data"])
            table.append({
                "Case ID": row["case_id"],
                "Scenario": row["scenario"],
                "Expected": row["expected_validation"],
                "Validation check": "Valid" if not validation_errors else f"{len(validation_errors)} issue(s) expected",
                **row["data"],
            })
        st.dataframe(table, use_container_width=True, hide_index=True)
        for row in rows:
            with st.expander(f"{row['case_id']} · {row['scenario']} · expected {row['expected_validation']}"):
                st.caption(row["note"])
                st.json(row["data"])
                errors = validate_instance(generated_schema, row["data"])
                if errors:
                    st.write("Expected validation findings:")
                    for error in errors:
                        st.markdown(f"- {error}")
        st.download_button("Download JSON", rows_to_json(generated_schema, rows, st.session_state.get("generated_seed", int(seed))), "synthetic-test-data.json", "application/json")
        st.download_button("Download CSV", rows_to_csv(rows), "synthetic-test-data.csv", "text/csv")

with about_tab:
    st.subheader("Useful test data without production records")
    st.markdown("""
    This project shows a schema-driven approach to safe, repeatable test data:

    - Generate positive, valid-boundary, and intentionally negative records.
    - Preserve a seed so a test run can be reproduced.
    - Use reserved fictional values such as `example.test` for email data.
    - Validate generated records against a documented JSON Schema subset.
    - Optionally use an LLM to draft the schema from a plain-language description; record generation stays local and deterministic.

    The generator does not connect to production systems or databases. Review generated values and constraints before using them in a test environment.
    """)
    st.markdown("**Architecture:** JSON Schema or optional AI schema draft → local deterministic generator → validation checks → JSON/CSV exports. See `docs/architecture.md`.")

