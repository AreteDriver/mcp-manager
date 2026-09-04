# Production Readiness

This document is the release contract for MCP Manager 1.x. A release is ready
only when every automated gate is green on the exact tag candidate and the
manual dogfood evidence below is complete.

## Supported contract

| Surface | Supported |
|---------|-----------|
| Python | 3.11, 3.12, and 3.13 |
| Operating systems | Linux, macOS, and Windows |
| Clients | Codex, Claude Code, Claude Desktop, Cursor, and Windsurf |
| Transports | stdio, Streamable HTTP, and legacy SSE where the target supports it |
| Scopes | User scope; shared project scope for Codex, Claude Code, and Cursor |
| Stability | CLI command names, documented exit behavior, and project config schema follow SemVer |

Client-private or undocumented state is not part of the contract. In
particular, MCP Manager does not edit Claude Code's private per-project entries
inside `~/.claude.json`.

## Automated release gates

Run the canonical local verification:

```bash
ruff check src tests
ruff format --check src tests
mypy src/mcp_manager
pytest tests -q --cov=mcp_manager --cov-fail-under=87
python -m build
twine check dist/*
mkdocs build --strict
pip-audit --strict --desc=on .
bandit -r src -ll
```

GitHub Actions additionally runs the tests on all supported operating systems,
scans repository history with Gitleaks, runs CodeQL, exercises the public root
Action against valid and invalid configs, and installs the built wheel into a
fresh environment.

## Release-candidate dogfood

Record evidence for all of the following on the proposed release commit:

- [ ] Import existing configs from every supported client without exposing credential values.
- [ ] Preview and apply a no-op sync twice; the second run produces no change.
- [ ] Add and remove one stdio and one network server per writable target.
- [ ] Confirm unrelated JSON and TOML keys and comments survive round trips.
- [ ] Interrupt or force a failed write and restore from `.mcp-manager-backup`.
- [ ] Exercise missing commands, missing environment variables, timeouts, malformed configs, and unavailable servers.
- [ ] Run the public Action against one valid config and one intentionally invalid config.
- [ ] Install with pip, pipx, and uv from the release-candidate artifact.
- [ ] Complete one smoke pass on Linux, macOS, and Windows.
- [ ] Confirm there are no unresolved P0/P1 defects or undocumented data-loss paths.

## Rollback

Every existing client config is copied to a sibling
`.mcp-manager-backup` file before replacement. To recover, stop any active
monitor, copy that backup over the client config, and rerun `mcp-manager doctor`
before attempting another sync. A failed release is yanked from PyPI only when
installation itself is unsafe; otherwise publish a patch release so existing
environments have a normal upgrade path.

## Support and compatibility

The latest 1.x release receives security and compatibility fixes. Translation
loss is surfaced as a warning, and unsupported transports are rejected. Changes
to documented output schemas or config semantics require SemVer treatment and
migration notes.
