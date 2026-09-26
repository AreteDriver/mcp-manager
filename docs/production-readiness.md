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

- [x] Import existing configs from every supported client without exposing credential values.
- [x] Preview and apply a no-op sync twice; the second run produces no change.
- [x] Add and remove one stdio and one network server per writable target.
- [x] Confirm unrelated JSON and TOML keys and comments survive round trips.
- [x] Interrupt or force a failed write and restore from `.mcp-manager-backup`.
- [x] Exercise missing commands, missing environment variables, timeouts, malformed configs, and unavailable servers.
- [x] Run the public Action against one valid config and one intentionally invalid config.
- [x] Install with pip, pipx, and uv from the release-candidate artifact.
- [x] Complete one smoke pass on Linux, macOS, and Windows.
- [x] Confirm there are no unresolved P0/P1 defects or undocumented data-loss paths.

### v1.0.0 evidence — 2026-09-03

The evidence applies to the release-candidate head of
[PR #20](https://github.com/AreteDriver/mcp-manager/pull/20). The pull request's
exact-commit checks are the authoritative hosted record.

- Existing Codex, Claude Code, and Claude Desktop configuration was imported
  read-only on macOS. Output was reviewed for structure and diagnostics only;
  credential values were not recorded. Cursor and Windsurf were not installed
  on that workstation, so no nonexistent user configuration was fabricated.
- `scripts/rc_dogfood.py` exercises all five native target formats in isolated
  temporary directories. It previews, applies, repeats, parses, removes,
  preserves unrelated data, restores a backup byte-for-byte, and verifies that
  a forced atomic-replacement failure retains the original and cleans its
  temporary file.
- The test suite covers missing commands and environment variables, network and
  subprocess timeouts, malformed configuration, and unavailable servers. The
  public Action workflow covers both valid and intentionally invalid input.
- The candidate wheel was installed and invoked in fresh pip, pipx, and uv tool
  environments. The package matrix repeats the wheel test on hosted Linux,
  macOS, and Windows runners.
- The local candidate suite passed 627 tests at 88.08% coverage, together with
  Ruff, format, strict mypy, strict MkDocs, Bandit, dependency audit, package
  metadata, and source-archive checks. GitHub reported no open issues when the
  candidate was signed off.

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
