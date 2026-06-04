# nthlayer-override-adapter — agent-facing commands

Standalone HTTP sidecar that accepts override events and emits
`gen_ai.override` OTel spans, plus binds each accepted override to the
verdict store via HTTP POST to nthlayer-core.

## Stack

- Python ≥3.11, managed via `uv`.
- Runtime: Starlette + Uvicorn (ASGI).
- Tests: `pytest`, `pytest-asyncio`, `httpx` (Starlette `TestClient`).
- Lint: `ruff`.
- Typecheck: **not configured** (no `mypy.ini`, no `pyrightconfig.json`,
  no `[tool.mypy]`/`[tool.pyright]` in `pyproject.toml`). TODO: wire
  one when the rest of the ecosystem standardises.

## Build / test / lint / run commands

```bash
uv sync --extra dev
uv run pytest -q                                # full suite (89 tests)
uv run pytest tests/test_<name>.py -v           # single file
uv run pytest -k "<expr>" -v                    # single test by name
uv run ruff check src/ tests/                   # lint
uv run nthlayer-override-adapter serve --config <path>   # run the sidecar
```

Example config:

```bash
cp override-adapter-config.yaml.example override-adapter-config.yaml
```

## CI / release

- CI matrix: Python 3.11 / 3.12 / 3.13 (`.github/workflows/test.yml`).
  Runs `ruff` then `pytest`.
- Release: push to `main` runs `release-please-action@v4` (config in
  `release-please-config.json` + `.release-please-manifest.json`) to
  maintain the release PR and cut `v*` tags from conventional commits.
  Tag push or `workflow_dispatch` triggers the publish job:
  `uv build` → `uvx twine check dist/*` → Docker smoke gate
  (`python:3.11-slim` installs the built `.whl` + runs `tests/smoke/`)
  → trusted PyPI publish via `pypa/gh-action-pypi-publish`.
