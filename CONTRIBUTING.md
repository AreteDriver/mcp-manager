# Contributing to mcp-manager

Thank you for considering a contribution! This project is a developer-tooling CLI — we value correctness, safety, and clear error messages over cleverness.

## Quickstart

```bash
git clone https://github.com/AreteDriver/mcp-manager.git
cd mcp-manager
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Preflight Checklist

Run these locally before opening a PR. The CI will run the same checks and fail if any step breaks.

```bash
# 1. Lint & format
ruff check src/ tests/
ruff format --check src/ tests/

# 2. Type check (strict)
mypy src/mcp_manager

# 3. Test suite (≥ 80 % coverage gate)
pytest tests/ -v --cov=mcp_manager --cov-fail-under=80

# 4. Security scan (optional but recommended)
bandit -r src/ -ll
pip-audit --desc
```

## What to Contribute

- **Bug fixes** — especially for edge cases in config parsing, health checks, or IDE write-back.
- **New IDE adapters** — add support for a new tool by implementing the write-back logic in `writeback.py`.
- **Marketplace entries** — validated, well-documented MCP servers with install specs.
- **Docs improvements** — README, `--help` text, or this file.

## Code Style

- Python 3.11+ features are encouraged (`str | None`, `match`, `tomllib`).
- All public functions and methods need type annotations; `mypy --strict` must pass.
- Prefer specific exception types over `except Exception`.
- Keep CLI command logic thin — business logic belongs in module functions, not `cli.py`.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `fix:` — bug fix
- `feat:` — new feature
- `docs:` — documentation only
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `test:` — test-only change
- `chore:` — tooling, dependencies, CI

## Pull Request Process

1. Open a PR against `main`.
2. Ensure the preflight checklist above is green.
3. If the change touches the marketplace index, run the marketplace refresh workflow locally and include the updated `index.yaml`.
4. A maintainer will review within 48 hours. We may ask for tests or narrower exception handling.

## Security

- Never commit API keys, tokens, or credentials.
- Subprocess execution is a sensitive surface; validate commands and avoid `shell=True`.
- If you find a vulnerability, email `security@aretedriver.com` (or open a private security advisory on GitHub) rather than filing a public issue.
