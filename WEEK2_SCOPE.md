# Week 2 Scope: One-Command Server Install

## Goal
Add `mcp-manager server install <name>` — install a single server from the local registry into one or more IDE configs in one command.

## User Story
> As a user, after `mcp-manager add <name>`, I want to type `mcp-manager server install <name>` and have that server appear in my Cursor/Claude Code/Windsurf config files without manually editing JSON.

## CLI Surface

```bash
mcp-manager server install <name> [OPTIONS]
  --ide <ide>         # Target IDE (cursor, claude-code, windsurf). Default: auto-detect.
  --all               # Install to ALL supported IDEs, even if config doesn't exist yet.
  --create            # Create IDE config if missing (requires --ide or --all).
  --dry-run           # Preview what would change without writing.
  --force             # Overwrite if server already exists in target IDE config.
  --verify            # Run health check after install.
  --project <dir>     # Project dir (for context, mainly used with --verify).
```

## Behavior

### 1. Resolve server
- Look up `<name>` in `ServerRegistry`
- Not found → error with suggestion to `mcp-manager add` first

### 2. Determine target IDEs
| Flags | Behavior |
|-------|----------|
| `--ide cursor` | Target only Cursor |
| `--all` | Target all supported IDEs |
| Neither (default) | Auto-detect: IDEs whose config files already exist on disk |

### 3. Per-target install
For each target IDE:
- If config file missing and `--create` not set → skip with warning (unless `--all`)
- If server already exists in that IDE config and `--force` not set → skip with "already installed" note
- Write using `ConfigWriteback.write_servers()` with atomic temp-file + backup
- `--dry-run` uses `ConfigWriteback.preview()` and prints the JSON diff

### 4. Post-install verify (optional)
- If `--verify`, run `HealthChecker.check()` on the installed server
- Report status per IDE

### 5. Output
```
Installing my-server to 2 IDE(s):
  ✅ cursor      — /home/user/.cursor/mcp.json
  ✅ claude-code — /home/user/.config/claude-code/settings.json
  ⚠️  windsurf   — skipped (config missing, use --create)

Verify: HEALTHY (45ms)
```

## Reuses Existing Abstractions
- `ServerRegistry.get(name)` — lookup
- `ConfigDiscovery` — auto-detect existing IDE configs
- `ConfigWriteback` — atomic write with backup
- `HealthChecker` — `--verify`
- `ConfigWriteback.preview()` — `--dry-run`

## Files
- **New:** `src/mcp_manager/commands/install.py` — `install_impl()`
- **New:** `tests/test_install.py` — CLI + impl tests (~18 tests)
- **Modify:** `src/mcp_manager/cli.py` — add `server_app` sub-typer with `install` command

## Test Plan
1. Registry miss → `McpManagerError`
2. `--ide cursor --dry-run` → preview JSON, no disk write
3. `--ide cursor` writes correctly to existing config
4. Default auto-detect: skips IDEs without config, writes to ones with config
5. `--all --create` writes to all supported IDEs, creating missing configs
6. Already exists without `--force` → skip
7. Already exists with `--force` → overwrite
8. `--verify` runs health check and reports
9. Corrupt IDE config → `WritebackError` propagated
10. Unknown `--ide foobar` → error

## Edge Cases
- Server with `network_config` vs `stdio_config` both handled by `_server_to_ide_dict`
- IDE config with wrapper key (e.g. `"mcpServers"`) handled by `ConfigWriteback`
- Missing `--create` when config absent: helpful error suggesting `--create`

## Out of Scope (Week 3+)
- `mcp-manager server uninstall` — Week 3
- Dependency tracking / reverse-mapping — Week 3
- Batch install (`mcp-manager server install --tag <tag>`) — v0.7.0

## Estimate
- Implementation: 2–3 hrs
- Tests: 1–2 hrs
- Lint/type/ruff: 15 min
- Total: ~4 hrs
