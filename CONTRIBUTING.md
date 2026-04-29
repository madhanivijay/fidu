# Contributing

Thanks for opening a PR. This guide covers what we expect: stack, dev loop,
tests, and the rules around versioned contracts.

## Stack

- **Python 3.10+** (CI runs on 3.11). The codebase targets `py310` for ruff
  syntax features.
- **Pandas / DuckDB / PyArrow** for the native pandas + SQL engines.
- **Optional**: Pydantic 2 (input schema), jsonschema (output schema tests),
  Soda Core / Great Expectations / PyDeequ (tool adapters), PySpark (Spark
  engine), Streamlit + Plotly (UI).
- **Style**: `ruff` with `E,F,I,B,UP,SIM` selectors. No formatter beyond what
  `ruff format` would do -- keep the diff small.

## Local dev loop

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest -q
```

Optional, when touching engine perf:

```bash
pip install -e ".[dev]"
python benchmarks/run.py --rows 50000 --rules benchmarks/rules.yaml
```

## PR checklist

Before requesting review:

- [ ] `ruff check .` is clean.
- [ ] `pytest -q` is green (full suite, not just the file you changed).
- [ ] If you touched the JSON output, `pytest tests/test_output_schema.py` still
      passes against `schemas/dq_results.schema.json`. If it doesn't, see the
      schema-bump rules below.
- [ ] If you added or renamed a connector / engine / tool adapter, the registry
      table in [docs/EXTENDING.md](docs/EXTENDING.md) is up to date.
- [ ] If you added a new dependency, it's optional unless it's truly required
      for the lite path. Heavy deps go behind an extras group in
      `pyproject.toml`.
- [ ] If the change is user-visible (config field, CLI flag, output field),
      `README.md` and `CHANGELOG.md` are updated.

## Tests

- Tests live in `tests/`. Reach for `pytest` directly -- there are no fixtures
  outside what each test file defines.
- Plugin-registry tests register stubs with leading-underscore names
  (`_test_*`) so they don't collide with real adapters.
- For executor-level resilience (timeouts, partial-result mode), see
  `tests/test_resilience.py` for the patterns we already use.
- Don't introduce a test that hits the network. Network-style failures are
  simulated by stub connectors (see `_ExplodingConnector` in
  `tests/test_resilience.py`).

## Schema-bump rules

The kit ships **two** versioned contracts. Bump them deliberately.

### Output JSON schema -- `schemas/dq_results.schema.json` + `OUTPUT_SCHEMA_VERSION`

Semver. Anything that downstream BI / catalogue / contract consumers might
parse counts.

| Change                                                | Bump  |
| ----------------------------------------------------- | ----- |
| Add a new optional field on an existing object        | minor |
| Add a new top-level optional field                    | minor |
| Add a new value to an existing `enum`                 | minor |
| Tighten an existing field (e.g. add `required`)       | major |
| Rename, remove, or change the type of a field         | major |
| Change the meaning of an existing field               | major |
| Documentation / comment-only edits                    | patch |

When bumping:

1. Update `OUTPUT_SCHEMA_VERSION` in `core/constants.py`.
2. Update the schema in `schemas/dq_results.schema.json`.
3. Add an entry to `CHANGELOG.md` under the new version.
4. Re-run `pytest tests/test_output_schema.py`.

### Input YAML schema -- `INPUT_SCHEMA_VERSION`

Single integer (currently `1`). Each rule file and config file declares
`schema_version: 1` at the top level. The validator warns on missing and
errors on unknown.

Bump only when introducing a **breaking** rename or removal in the input
contract. Additive fields don't require a bump -- existing v1 YAMLs keep
working.

When bumping:

1. Update `INPUT_SCHEMA_VERSION` in `core/constants.py`.
2. Update every YAML in `configs/`, `rules/`, `benchmarks/`, and
   `examples/` to declare the new version.
3. Decide whether the validator should accept the *old* version too. If
   yes, replace the equality check in
   `core.config_validator._validate_input_schema_version` with set
   membership and document the supported range.
4. Add a `CHANGELOG.md` entry.

## Adding a connector / engine / tool adapter

See [docs/EXTENDING.md](docs/EXTENDING.md) for the registry contract and the
JSONL connector walkthrough. The short version:

1. Subclass `BaseConnector` / `BaseDQEngine` / `BaseToolAdapter`.
2. Register at import time via `register_connector` / `register_engine` /
   `register_tool_adapter`.
3. Add a unit test that exercises a small end-to-end run through your new
   plugin (mirror `tests/test_custom_connector_example.py`).

## What we *don't* want in PRs

- `print()` statements outside `main.py` -- use `core.logging.get_logger`.
- New top-level dependencies without a clear case for being non-optional.
- Comment paragraphs explaining *what* the code does. The code says that. If
  the *why* is non-obvious (a hidden constraint, a bug-driven workaround),
  one short comment is fine.
- Backwards-compatibility shims for code that doesn't yet have external
  consumers. Prefer renaming cleanly over adding aliases.

## Release

Releases are tagged on `main`. Before tagging:

1. `pyproject.toml` -- bump `version`.
2. `CHANGELOG.md` -- move "Unreleased" entries under the new version.
3. Full `pytest -q` + `ruff check .` clean.
4. Tag: `git tag -s vX.Y.Z -m "vX.Y.Z"` and push.

Questions? Open an issue or start a draft PR with the question in the
description -- both work.
