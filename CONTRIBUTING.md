# Contributing to nthlayer-override-adapter

Thank you for considering contributing to **nthlayer-override-adapter** — a
standalone HTTP sidecar that accepts override events (canonical/batch JSON or
webhook payloads), emits each as one unparented `gen_ai.override` OTel span,
and binds each accepted override to the verdict store via HTTP POST to
`nthlayer-core`. We're in active v1.5 development and welcome feedback from
the SRE/DevOps community.

## Ways to Contribute

- **Report bugs / request features** — [open an issue](https://github.com/rsionnach/nthlayer-override-adapter/issues).
- **Discuss** — [GitHub Discussions](https://github.com/rsionnach/nthlayer/discussions) for the wider ecosystem.
- **Code & docs** — pull requests welcome (see below).

## Development Setup

```bash
# Install uv (https://docs.astral.sh/uv/)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone alongside nthlayer-common (the adapter depends on it via a sibling path)
git clone https://github.com/rsionnach/nthlayer-common.git
git clone https://github.com/rsionnach/nthlayer-override-adapter.git
cd nthlayer-override-adapter
uv sync --extra dev                  # creates .venv with test/lint tools

# Run the sidecar locally
cp override-adapter-config.yaml.example override-adapter-config.yaml
uv run nthlayer-override-adapter serve --config override-adapter-config.yaml

# Run the test suite
uv run pytest -q                     # full suite
uv run pytest tests/test_<name>.py -v  # a single file
uv run pytest -k "<expr>" -v         # by name

# Lint
uv run ruff check src/ tests/
```

> **Sibling dependency & Python.** `pyproject.toml` declares
> `nthlayer-common = { path = "../nthlayer-common", editable = true }`, so
> `nthlayer-common` must sit next to this repo on disk or `uv sync` fails to
> resolve it. Requires Python 3.11+ (`uv` will provision it via
> `uv python install` if needed).

A clean clone to a green `uv run pytest -q` should take well under five
minutes. CI runs ruff then pytest on a py3.11/3.12/3.13 matrix for every push
and PR to `main`.

## Pull Request Process

1. Fork the repository and create a feature branch off `main`
   (`git checkout -b feat/your-change`).
2. Make your change with tests.
3. Ensure tests pass: `uv run pytest -q`.
4. Ensure lint passes: `uv run ruff check src/ tests/`.
5. Commit using Conventional Commits (see below).
6. Push to your fork and open a PR against `main`.

Commits land on `main`; `release-please` maintains the release PR and cuts
`v*` tags. The release publish flow is `uv build` → `uvx twine check dist/*`
→ Docker smoke gate (`tests/smoke/`) → trusted PyPI publish.

## Development Guidelines

### Code Style

- Python 3.11+, type hints encouraged.
- Ruff lint config: `select = ["E","F","I","W","UP","B"]`.
  Run `uv run ruff check src/ tests/`.

### Load-bearing invariants

- **`apply_privacy` is the single privacy boundary.** The sidecar is the only
  PII-redaction point; routes call `apply_privacy` once and pass the masked
  event to both `emit_override` and `bind_to_core`. Never apply privacy twice,
  and never inside `emit_override`.
- **Unparented spans.** `gen_ai.override` is emitted with an empty OTel
  `Context()` — overrides are operator decisions, not bound to a service
  trace. Do not "fix" this to inherit a current trace context.
- **Fail-open.** OTel export and core-binding errors still return HTTP 201;
  the relevant counters increment. Preserve that posture.

(See `CLAUDE.md` for the full numbered invariant list.)

### Commit Messages

```
<type>: <description>

<optional body>
```

`feat` / `fix` / `perf` / `deps` / `refactor` / `docs` surface in the
changelog; `chore` / `test` / `ci` / `build` / `style` are hidden.

### Testing

- Add tests for new behaviour.
- Run a single file with `-v` while iterating; run the full `-q` suite before
  opening a PR.

## Finding Something to Work On

Browse [open issues](https://github.com/rsionnach/nthlayer-override-adapter/issues)
and look for `good-first-issue` / `help-wanted` labels. Maintainers track
detailed work in **Beads**, a Dolt-backed board in the `opensrm` repo
(`cd ../opensrm && bd ready --json`) — you don't need it to contribute.

## Code of Conduct

Be respectful and constructive — we're all here to build better reliability
tooling.

## Security

Please report security vulnerabilities privately — use GitHub's "Report a
vulnerability" (the repo's **Security** tab) rather than a public issue. This
sidecar handles override events and PII redaction, so responsible disclosure
matters.

## Questions?

- [GitHub Issues](https://github.com/rsionnach/nthlayer-override-adapter/issues) — bugs and features.
- [GitHub Discussions](https://github.com/rsionnach/nthlayer/discussions) — general questions.

## License

By contributing, you agree that your contributions will be licensed under
this repository's license (see `LICENSE`).

---

**Thank you for helping make NthLayer better!**
