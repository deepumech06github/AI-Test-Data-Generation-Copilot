# AI-Test-Data-Generation-Copilot

A privacy-conscious, schema-driven test data generator for quality engineering teams. It creates repeatable synthetic **positive**, **boundary**, and **negative** records from a JSON Schema, checks them against a supported schema subset, and exports JSON or CSV. Optional AI assistance drafts a JSON Schema from a plain-language description; record generation itself stays local.

## What it demonstrates

- JSON Schema-driven synthetic data design
- Reproducible records using a seed
- Positive, boundary, and intentionally invalid scenarios
- Local validation and JSON/CSV exports
- Optional LLM-assisted schema drafting
- Unit tests and GitHub Actions CI

## Run locally

Requires Python 3.10 or newer.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
streamlit run app.py
```

The sample user-profile schema loads by default. The generator works offline and requires no account or API key.

## Optional AI schema drafting

Install the optional OpenAI integration and configure `OPENAI_API_KEY` through an environment variable or Streamlit secrets:

```bash
pip install -e ".[llm]"
# macOS / Linux:
export OPENAI_API_KEY="your-key"
# Windows PowerShell:
$env:OPENAI_API_KEY = "your-key"
streamlit run app.py
```

The data-shape description is sent to the model only when you click **Draft JSON Schema with AI**. Do not enter real customer data, credentials, or secrets. Generated records are created locally after schema review.

## Supported JSON Schema subset

The demo supports object, array, string, integer, number, and boolean types; required properties; enums; email/date/date-time/UUID/URI formats; numeric min/max; string min/max length; and array min/max items. It does not resolve `$ref` or implement the full JSON Schema standard. Schema `example` and `default` values are not copied into generated records. Constraints are intentionally bounded to keep generation predictable.

Negative records omit a required property when available, otherwise introduce a type, enum, format, or numeric constraint violation. Boundary records target supported min/max or enum edges. Every exported record includes its scenario and expected acceptance/rejection behavior.

## Run unit tests

```bash
python -m pip install -e ".[dev]"
pytest
```

## Upload to GitHub

1. Extract the project ZIP.
2. Create a repository named `AI-Test-Data-Generation-Copilot`.
3. Upload the extracted folder contents, including `.github/workflows/ci.yml`.
4. Commit with a message such as `Add AI test data generation copilot`.

## Safety and use guidance

All sample values are synthetic. Email addresses use the reserved `example.test` domain. Do not use generated records in production systems. Generated values should still be reviewed for the constraints and behaviors your test environment expects.

## Repository map

```text
app.py                              Streamlit app
src/testdata_copilot/schema.py      Schema validation and local generator
src/testdata_copilot/llm.py         Optional AI schema drafting
src/testdata_copilot/exports.py     JSON and CSV outputs
examples/user-profile.schema.json  Sample JSON Schema
tests/                              Unit tests
docs/architecture.md               Architecture and production evolution
.github/workflows/ci.yml            GitHub Actions checks
```

## License

MIT. See [LICENSE](LICENSE).

