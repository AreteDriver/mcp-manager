# Repository Guide

## Purpose

`mcp-manager` discovers, validates, health-checks, and synchronizes MCP server
configuration across Codex, Claude Code, Claude Desktop, Cursor, and Windsurf.

## Architecture

- `src/mcp_manager/adapters/` owns client-specific parsing, rendering,
  capability declarations, and translation warnings.
- `models.py` is the canonical cross-client representation. Keep target-only
  fields in `McpServer.extensions` so same-target round trips do not erase them.
- `discovery.py` is read-only. `writeback.py` owns backups and atomic writes.
- CLI registration stays in `cli.py`; command behavior belongs in `commands/`.

## Safety Invariants

- Never silently change a transport. Reject unsupported translations.
- Warn before omitting policy, authentication, timeout, or target-extension fields.
- Preserve unrelated config keys and create a backup before changing an existing file.
- Never print credential values. Diagnostics may report only environment-variable names.
- Add user- and project-scope tests for every new target path.

## Verification

```bash
ruff check src tests
ruff format --check src tests
mypy src/mcp_manager
pytest tests -q
python -m build
mkdocs build --strict
```

Use Python 3.11+ and keep public APIs fully typed under strict mypy.
