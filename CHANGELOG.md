# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- MCP 2026-07-28 compatibility probing via `mcp-manager doctor --protocol`,
  including strict-modern enforcement, deterministic list-cache verification,
  official SDK integration fixtures, and cross-instance Streamable HTTP tests.

### Changed

- Migrated the MCP SDK integration to the 2.x API and preserved automatic
  fallback for handshake-era servers.
- HTTP probes now resolve configured credential environment references without
  including secret values in diagnostic output.

## [0.9.0] — 2026-08-17

### Added

- **Target adapter architecture** for client-native MCP configuration dialects
  - Native Codex TOML discovery, preview, write-back, removal, and project scope
  - Claude Code and Cursor project-scoped writes using their official paths
  - Capability inventory via `mcp-manager targets`
  - Static configuration diagnostics via `mcp-manager doctor`
  - Translation warnings for policy, auth, environment-reference, timeout, and extension loss
- **Codex policy coverage** for enabled/required state, tool filters and approvals,
  authentication references, environment forwarding, and timeouts
- **MCP Audit** (`mcp-manager audit` subcommand)
  - `audit list` — list probe specs in a rich table
  - `audit runbook` — generate markdown verification runbook for human-in-the-loop testing
  - `audit serve` — start a benign FastMCP probe server for permission-prompt accuracy testing
  - Built-in Category 3 baseline probe spec (8 probes for tool/parameter misrepresentation)
  - Custom `--probe-spec` YAML support
  - Ported from standalone `mcp-fuzz` project (ADL-20260721-003)

### Changed

- Windsurf discovery now uses the documented `~/.codeium/windsurf/mcp_config.json` path.
- Claude Desktop discovery selects the platform-specific user config path.
- MCP SDK dependency is constrained to `<2.0` until the health/audit code migrates to the 2.x API.
- JSON and TOML writes preserve unrelated target settings and clean up failed atomic-write temp files.
- CI pins the Ruff formatter and validates documentation on pull requests.

### Fixed

- Packaging metadata now follows current setuptools license validation.
- `doctor` reports malformed server entries instead of silently skipping them.
- `mcp-manager init` no longer ignores the team config and lockfile that its sharing workflow requires.
- Built-in templates now launch the official Python Git server with `uvx mcp-server-git`
  instead of referencing the nonexistent `@modelcontextprotocol/server-git` npm package.
- The reusable validation action installs a pinned `uv` runtime so its generated
  Python-server configurations validate consistently on clean CI runners.

## [0.8.0] — 2026-07-20

### Added

- **OAuth2 Device Flow** (mcp-manager registry login --oauth2)
  - RFC 8628 device flow with auto-discovery from MCP manifest or .well-known/oauth-authorization-server
  - Polling loop with authorization_pending, slow_down, access_denied handling
  - Token refresh before expiry on every registry operation
  - --client-id override for enterprise registries
- **Token revocation on logout** — attempts RFC 7009 revocation if endpoint advertised
- **Auth-list expiry column** — shows hours remaining or expired for OAuth2 profiles

## [0.7.1] — 2026-07-20

### Fixed

- **Security**: prevent credential leak via redirect in `_validate_credentials` (`follow_redirects=False`)
- **Security**: add `--password-stdin` TTY guard with clear error message and usage example
- **Dead code**: wire `update_health` into `health_impl` to persist health results to registry
- **UX**: update login error message to reference `--password-stdin` deprecation
- **Architecture**: remove auto-save side effect from `ServerRegistry.update_health()`; callers control persistence
- **Robustness**: lazy `expanduser()` resolution in `ConfigWriteback` to handle `$HOME` changes in tests/containers

## [0.7.0] — 2026-07-20

### Added

- **Persistent registry authentication** (`mcp-manager registry login` / `logout` / `auth-list`)
  - Secure credential storage in `~/.mcp-manager/auth.json` with `0o600` permissions
  - Bearer token and Basic auth profiles, masked in `auth-list` output
  - Credential validation via HEAD request before storing (abort on 401/403, warn on 405)
- **Env-var fallback for registry auth**
  - `MCP_MANAGER_REGISTRY_TOKEN` — default Bearer token
  - `MCP_MANAGER_REGISTRY_USER` / `MCP_MANAGER_REGISTRY_PASSWORD` — default Basic auth
  - `MCP_MANAGER_AUTH_FILE` — override auth.json path
- **Auth priority chain**: CLI flag > stored profile > env var > anonymous
- **Release automation**: version guard, CHANGELOG extraction, and GitHub Release notes from `.github/workflows/release.yml`

### Changed

- **Version bumped to 0.7.0**

## [0.6.0] — 2026-07-20

### Added

- **Remote Registry Sync** (`mcp-manager registry diff`, `mcp-manager registry pull`)
  - Fetch server definitions from remote YAML/JSON registries over HTTP
  - Diff preview with Rich table (add / change / remove)
  - Merge strategies: `union` (default) and `replace`
  - Pre-pull verification with `mcp-manager registry pull --verify`
  - Dry-run support on both diff and pull
  - Atomic writes with backups via `write_project_servers`
- **Registry Authentication** — `--token` (Bearer), `--user` + `--password` (Basic), `--header` (repeatable custom headers)
- **One-Command Server Install** (`mcp-manager server install <name>`)
  - Install a single server from local registry into IDE configs
  - Auto-detect existing IDE configs, or target specific IDE with `--ide`
  - `--all` + `--create` to write to all supported IDEs even if config missing
  - `--force` to overwrite existing entries
  - Optional `--verify` health check after install
- **One-Command Server Uninstall** (`mcp-manager server uninstall <name>`)
  - Remove a server from IDE configs by discovery (no registry lookup needed)
  - Health warning before uninstall unless `--force`
  - Target single IDE or all IDEs that have the server
- **ConfigWriteback.remove_servers()** — atomic backup + removal by name, supports wrapper-key and top-level configs

### Changed

- **CLI architecture** — added `server_app` sub-typer under `mcp-manager server` for per-server lifecycle commands

## [0.5.0] — 2026-07-20

### Added

- **Config inheritance** (`extends:`) with circular dependency detection and left-to-right merge
- **Server tags** — filter list/health/sync/monitor with `--tag` and `--exclude-tag`
- **Init wizard** (`mcp-manager init`) — interactive project scaffold with transport selection and env var prompts
- **Project templates** (`mcp-manager template list`, `template use`) — pre-configured server bundles (filesystem, brave-search, playwright, etc.)
- **MkDocs Material documentation site** with GitHub Pages deployment
- **pytest-benchmark suite** — performance baselines for health, sync, and discovery
- **Stress tests** — monitor restart storm backoff and 100-server concurrent health check isolation

### Changed

- **Test coverage pushed from 87% to 90%** — deep stdio/network health paths, monitor OSError/backoff, writeback atomic/backup failures, exporter edge cases
- **README rewritten** with quickstart, feature matrix, and install instructions
- **PyPI package metadata** updated for `arete-mcp`

## [0.4.0] — 2026-07-20

### Added

- **Server Marketplace** (`mcp-manager search`, `info`, `install`)
  - Curated directory of MCP servers with quality metadata
  - Health pass rate, tool count, last updated, license, verified status
  - Auto-lock on install: resolved versions written to `.mcp-manager.lock`
  - Dry-run support: `mcp-manager install <name> --dry-run`
  - SSE transport support in marketplace entries
  - Marketplace quality scores CI gate (B threshold)
  - Marketplace refresh with health check validation
- **CONTRIBUTING.md** — contributor quickstart, preflight checklist, code style, conventional commits, PR process, security reporting
- **Registry durability assessment** (`docs/design/registry-durability.md`) — evaluates JSON/SQLite/YAML choices across registry, telemetry, and lockfile

### Changed

- **CLI architecture refactored** — `cli.py` reduced from 1,070 lines to 319 lines (70% reduction)
  - Extracted command implementations into `commands/` subpackage:
    - `commands/common.py` — shared console, discovery, registry helpers
    - `commands/servers.py` — list, map, health, add, remove, test, export, import, status
    - `commands/ops.py` — sync, validate, monitor, stats, lock
    - `commands/project.py` — project init, validate, export
    - `commands/marketplace.py` — search, info, install, refresh
  - Zero breaking changes — all `@app.command()` registrations preserved
- **Project config env var syntax expanded**
  - `${VAR:-default}` — falls back to `default` if `VAR` is unset
  - `${VAR:?required}` — raises `WritebackError` if `VAR` is unset
  - Validation skips `:-` vars (explicit default) but flags bare `$VAR` and `:?` vars
- **Exception handling narrowed** across 6 modules:
  - `health.py` — specific types: `OSError`, `TimeoutError`, `ProtocolError`, `json.JSONDecodeError`, `ValidationError`
  - `registry.py` — `ValidationError`, `TypeError`, `KeyError`
  - `lockfile.py` — `URLError`, `HTTPError`, `json.JSONDecodeError`, `TimeoutError`
  - `exporters.py` — `ValidationError`, `KeyError`, `TypeError`
  - `marketplace.py` — `yaml.YAMLError`, `OSError`, `TimeoutError`, `ValueError`
  - `monitor.py` — `OSError` (timeout already handled upstream)
- **Stdio handshake deduplicated** in `health.py` — extracted `_stdio_spawn()`, `_stdio_init_sequence()`, `_stdio_cleanup()`, `_stdio_ping_handshake()` shared between shallow and deep health checks

### Fixed

- `ruff` and `mypy` now clean across entire codebase (no outstanding lint)
- `TimeoutError` standardized to builtin (replaced `asyncio.TimeoutError` per UP041)
- Test patch targets updated to match new `commands/` module paths
- Unawaited coroutine warning suppressed in marketplace refresh tests

## [0.3.0] — 2026-07-17

### Added

- **Server auto-restart monitor** (`mcp-manager monitor`) — keeps stdio servers alive with exponential backoff restart
- **CI gate / GitHub Action** (`mcp-manager validate`) — fast config validation as composite action at `.github/actions/mcp-manager-validate`
- Telemetry store with SQLite WAL mode for append-only event logging

### Changed

- `setuptools` deprecation warnings resolved
- GitHub Actions bumped to SHA-pinned v7

## [0.2.0] — 2026-07-14

### Added

- **Project-scoped MCP configuration** — `.mcp-manager.yml` in repo root with env var resolution and validation
- **Cross-IDE config portability (write-back)** — atomic IDE config writes with backups and dry-run
  - Claude Code (`~/.claude.json`)
  - Claude Desktop (`~/.config/Claude/claude_desktop_config.json`)
  - Cursor (`~/.cursor/mcp.json`)
  - Windsurf (`~/.windsurf/mcp_config.json`)
  - Project-level (`.mcp.json`)
- **Deep health checks** — dependency validation and `tools/list` verification (`mcp-manager health --deep`)
- **Version pinning / lockfile** — `mcp-manager lock` writes `.mcp-manager.lock` with resolved versions; `mcp-manager lock --check` for CI gate

### Security

- Added `SECURITY.md`
- Pinned GitHub Actions to SHA commits
- Added `.env` and credential patterns to `.gitignore`
- Security workflow: `pip-audit` + `bandit` on push/PR

[Unreleased]: https://github.com/AreteDriver/mcp-manager/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/AreteDriver/mcp-manager/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/AreteDriver/mcp-manager/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/AreteDriver/mcp-manager/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/AreteDriver/mcp-manager/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/AreteDriver/mcp-manager/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/AreteDriver/mcp-manager/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/AreteDriver/mcp-manager/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/AreteDriver/mcp-manager/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/AreteDriver/mcp-manager/releases/tag/v0.2.0
