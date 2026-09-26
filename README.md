# mcp-manager

**One CLI to discover, diagnose, health-check, and sync MCP servers across Codex, Claude Code, Cursor, Windsurf, and more.**

[![CI](https://github.com/AreteDriver/mcp-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/AreteDriver/mcp-manager/actions)
[![CodeQL](https://github.com/AreteDriver/mcp-manager/actions/workflows/codeql.yml/badge.svg)](https://github.com/AreteDriver/mcp-manager/actions)
[![Coverage](https://img.shields.io/badge/coverage-88%25-brightgreen.svg)](https://github.com/AreteDriver/mcp-manager/actions)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/arete-mcp.svg)](https://pypi.org/project/arete-mcp/)
[![Downloads](https://img.shields.io/pypi/dm/arete-mcp.svg)](https://pypi.org/project/arete-mcp/)

Think of it as **docker-compose for MCP** — a single `.mcp-manager.yml` in your repo that describes which AI tools your project needs, with one command to sync them to every IDE your team uses.

---

## What this demonstrates

- Translating a fragmented configuration workflow into one documented operating model.
- Safe automation through validation, dry runs, backups, health checks, and rollback-aware writes.
- Practical Python CLI design, cross-tool integration, testing, security guidance, and team onboarding.

## Current status and limitations

This is a production-stable independent project distributed on PyPI. It manages configuration and diagnostics; it does not host MCP servers or guarantee the behavior of third-party servers and clients. See [Status](#status), [Production Readiness](docs/production-readiness.md), and [Security](SECURITY.md) for the supported contract.

## Why mcp-manager?

The Model Context Protocol (MCP) is the open standard for connecting AI agents to external tools — databases, browsers, filesystems, APIs. But every IDE stores MCP configs differently, and there's no way to share them across a team.

**mcp-manager gives you:**

- **One config file** (`.mcp-manager.yml`) committed with your code
- **One command** to sync it to every IDE (`mcp-manager sync --ide cursor`)
- **Health checks** that verify servers actually work, not just "start"
- **Team onboarding** with `mcp-manager init` — detects IDE, imports servers, scaffolds config

No more manual copy-paste. No more "works on my machine" for AI tool configs.

![mcp-manager demo](docs/assets/mcp-manager-demo.gif)

---

## The Problem

You use Codex, Claude Code, Cursor, and Windsurf. Each stores MCP servers in a different location, scope, or dialect.

```
~/.claude.json
~/.cursor/mcp.json
~/.codeium/windsurf/mcp_config.json
~/.codex/config.toml
```

Your team can't share configs via git. Switching projects means manual copy-paste. One IDE has a server the others don't. You have no idea which servers are actually healthy.

**`mcp-manager` gives you one CLI — and one `.mcp-manager.yml` in your repo — to rule them all.**

---

## 30-Second Quickstart

```bash
# Install
pip install arete-mcp

# See every MCP server across every IDE
mcp-manager list

# See supported targets and diagnose stale paths or missing env vars
mcp-manager targets
mcp-manager doctor

# Check if they actually work (not just "starts")
mcp-manager health --deep

# Scaffold a project config
mcp-manager project init

# Sync it to Cursor (dry-run first, then commit)
mcp-manager sync --ide cursor --dry-run
mcp-manager sync --ide cursor
```

---

## What Makes This Different

### vs. Manual IDE Config

| | **mcp-manager** | **Manual Config** |
|---|---|---|
| **Share via git** | ✅ `.mcp-manager.yml` committed with code | ❌ Per-IDE JSON scattered in home dirs |
| **Switch projects** | ✅ One command: `mcp-manager sync --ide cursor` | ❌ Manual copy-paste between configs |
| **Team onboarding** | ✅ `mcp-manager init` detects IDE + imports | ❌ Everyone configures manually |
| **Health verification** | ✅ Deep checks: tools/list, deps on PATH | ❌ "Looks like it started" |
| **Rollback** | ✅ Atomic write + backup | ❌ Direct overwrite |
| **CI gate** | ✅ `mcp-manager validate --strict` | ❌ Nothing |

### vs. Other MCP Managers

| | **mcp-manager** | **Other Managers** |
|---|---|---|
| **Config lives in repo** | ✅ `.mcp-manager.yml` committed with your code | ❌ Global client-native config files |
| **Atomic write-back** | ✅ Backups + dry-run before touching IDE configs | ❌ Direct overwrite, no rollback |
| **Deep health checks** | ✅ Verifies `tools/list` responds, deps on PATH | ❌ "Process started" only |
| **Zero daemon** | ✅ CLI-only, no background services | ❌ Some require persistent gateway/web UI |
| **Python-native** | ✅ `pip install`, works wherever Python 3.11+ does | ❌ Node/Go binaries, extra tooling |
| **Cross-client discovery** | ✅ Reads Codex, Claude, Cursor, Windsurf, and project-scoped configs | ⚠️ Partial coverage |

---

## Features

### 🔍 Discovery
Reads MCP server configs from:
- Claude Code (`~/.claude.json`)
- Claude Desktop (platform-specific user config)
- Cursor (`~/.cursor/mcp.json`)
- Windsurf (`~/.codeium/windsurf/mcp_config.json`)
- Codex (`~/.codex/config.toml`)
- Project-level Claude Code (`.mcp.json`, walks parent dirs)

### 🏥 Health Checks
- **Fast**: Process spawn (stdio) or HTTP ping (SSE) — 10s timeout
- **Deep**: Dependency validation (`node`, `python`, `docker` on PATH) + verify `tools/list` returns non-empty
- **Batch**: Check all servers in parallel with `mcp-manager health`

### 📝 Config Write-Back (Atomic & Safe)
- Writes discovered/merged configs through target-specific JSON or TOML adapters
- **Atomic**: temp file + rename (never corrupts your IDE config)
- **Backups**: `.mcp-manager-backup` created before any modification
- **Dry-run**: Preview changes without touching disk
- **Capability-aware**: rejects unsupported transports and warns about lossy policy/auth translations

### 🏪 Server Marketplace
Discover and install curated MCP servers without hunting through GitHub:

```bash
# Search for servers by name or category
mcp-manager search filesystem
mcp-manager search --category Database

# View details before installing
mcp-manager info postgres

# Add a server to your project config (interactive env var prompts)
mcp-manager install postgres
mcp-manager install slack --no-prompt  # skip prompts, keep ${VAR} placeholders
```

Shipped with 6 official MCP reference servers. Verified servers are shown by default; use `--include-unverified` to browse the full catalog.

### 📁 Project-Scoped Configs
Create `.mcp-manager.yml` in any repo root:

```yaml
project: my-service
servers:
  postgres-local:
    command: node
    args: ["./mcp/postgres-server/dist/index.js"]
    env:
      DATABASE_URL: ${DATABASE_URL}
  stripe-mcp:
    command: npx
    args: ["-y", "@stripe/mcp"]
    env:
      STRIPE_SECRET_KEY: ${STRIPE_SECRET_KEY}
```

- Environment variables (`${VAR}`) resolved at load time
- Validated before write-back (missing env vars or commands caught early)
- Project config wins on merge conflicts with global registry

### 🔐 Version Pinning (Lockfile)
Pin exact MCP server versions for reproducible CI and team consistency:
```bash
mcp-manager lock                    # Resolve and write .mcp-manager.lock
mcp-manager lock --check            # Validate lockfile is current (CI gate)
mcp-manager lock --json             # Output resolved versions as JSON
```

The lockfile records the resolved npm version for each `npx`-based server so every developer and CI runner uses identical tooling.

### 🔄 Export / Import
Portable YAML/JSON for backup, sharing, and CI:
```bash
mcp-manager export servers.yaml
mcp-manager import servers.yaml
```

### 🖥️ Server Monitor (Auto-Restart)
Keep stdio MCP servers alive in development:
```bash
mcp-manager monitor --project .
```
- Watches server processes and restarts on crash
- Exponential backoff (1s → 2s → 4s ... max 30s)
- Graceful shutdown on Ctrl+C / SIGTERM
- JSON status output: `mcp-manager monitor --json`

### 🛡️ MCP Audit (Permission-Prompt Accuracy)
Test whether your IDE's permission prompts faithfully display what MCP tools actually do — the only tool in the ecosystem that tests the **display layer**, not just the protocol layer.

```bash
# List built-in probe specs
mcp-manager audit list

# Generate a markdown runbook for manual verification
mcp-manager audit runbook --output runbook.md

# Start the benign probe MCP server
mcp-manager audit serve
```

Built-in probes cover [HackerOne Category 3](https://hackerone.com/anthropic): tool/parameter misrepresentation in permission prompts. Each probe registers misleading metadata but returns a safe JSON marker — no actual behavior is executed. Supports custom `--probe-spec` YAML files for private threat models.

### 🔒 CI Gate / GitHub Action
Validate `.mcp-manager.yml` on every PR:

```yaml
# .github/workflows/mcp-validate.yml
- uses: AreteDriver/mcp-manager@v1
  with:
    path: "."
    strict: "false"
```

Catches missing env vars, broken commands, and (with `--strict`) failing servers before merge.

---

## Usage

```bash
# List all MCP servers across all IDEs
mcp-manager list

# Filter by IDE
mcp-manager list --tool cursor

# Health check all servers
mcp-manager health

# Probe MCP 2026-07-28 discovery, caching, and legacy fallback
mcp-manager doctor --protocol my-server
mcp-manager doctor --protocol my-server --strict-modern --json

# Deep health check — validate dependencies and verify tools/list
mcp-manager health --deep

# Show server-to-IDE mapping
mcp-manager map

# Search and install from the marketplace
mcp-manager search filesystem
mcp-manager info postgres
mcp-manager install postgres

# Export/import configs (portable YAML/JSON)
mcp-manager export servers.yaml
mcp-manager import servers.yaml

# Add/remove servers from the registry
mcp-manager add my-server --command "node server.js"
mcp-manager remove my-server

# Sync project config to IDE
mcp-manager sync --ide cursor --dry-run
mcp-manager sync --ide cursor
mcp-manager sync --ide codex --dry-run

# Write a client-native project config instead of a user config
mcp-manager sync --ide codex --scope project --project . --create

# Project-level MCP config
mcp-manager project init              # Scaffold .mcp-manager.yml
mcp-manager project validate          # Check env vars, commands on PATH
mcp-manager project export --ide cursor

# Keep stdio servers alive with auto-restart
mcp-manager monitor                   # Foreground monitor, Ctrl+C to stop

# CI gate — validate .mcp-manager.yml in CI
mcp-manager validate                  # Fast validation
mcp-manager validate --strict         # + deep health checks on all servers

# Lockfile — pin exact versions
mcp-manager lock                      # Resolve and write .mcp-manager.lock
mcp-manager lock --check            # Validate lockfile is current (CI gate)

# Permission-prompt security audit
mcp-manager audit list                # Show all built-in audit probes
mcp-manager audit runbook             # Run full permission-prompt audit
mcp-manager audit serve               # Start an MCP server that runs the audit
```

---

## Private Registries & Authentication

Authenticate against private registries so `registry diff` and `registry pull` can fetch server definitions behind HTTP Basic or Bearer auth.

```bash
# Store a Bearer token (validates via HEAD request before saving)
mcp-manager registry login https://reg.example.com/mcp.yaml --token ghp_xxx

# Store Basic auth credentials
mcp-manager registry login https://reg.example.com/mcp.yaml --user alice --password secret

# List stored profiles (credentials are masked)
mcp-manager registry auth-list

# Remove a profile
mcp-manager registry logout https://reg.example.com/mcp.yaml
```

Credentials are stored in `~/.mcp-manager/auth.json` with `0o600` permissions. You can override the path with `MCP_MANAGER_AUTH_FILE`.

**Auth priority chain** (highest wins):
1. CLI flag (`--token`, `--user`)
2. Stored profile for the registry URL
3. Environment variable (`MCP_MANAGER_REGISTRY_TOKEN`, `MCP_MANAGER_REGISTRY_USER` / `PASSWORD`)
4. Anonymous (no auth)

⚠️ **Security note:** passing `--token` on the CLI is insecure — it appears in shell history and `ps` output. Prefer `registry login` (stored credentials) or env vars.

---

## Supported Client Targets

| Target | User Config | Project Config | Format | Write-Back |
|--------|-------------|----------------|--------|------------|
| Codex | `~/.codex/config.toml` | `.codex/config.toml` | TOML | ✅ |
| Claude Code | `~/.claude.json` | `.mcp.json` | JSON | ✅ |
| Claude Desktop | Platform-specific | — | JSON | ✅ |
| Cursor | `~/.cursor/mcp.json` | `.cursor/mcp.json` | JSON | ✅ |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | — | JSON | ✅ |

Run `mcp-manager targets` for the installed version's exact capability matrix.

---

## Transport Types

- **stdio** — local subprocess, JSON-RPC over stdin/stdout
- **sse** — Server-Sent Events over HTTP
- **http** — HTTP POST JSON-RPC

---

## Status

- [x] Read-only config discovery across 5 client targets
- [x] Async health checks with timeout
- [x] JSON registry with add/remove
- [x] YAML/JSON export/import
- [x] Protocol handshake testing
- [x] Config write-back (atomic, with backups)
- [x] Project-scoped `.mcp-manager.yml` support
- [x] Deep health checks (dependency validation + `tools/list` verification)
- [x] Server auto-restart monitor
- [x] CI gate (`mcp-manager validate` + GitHub Action)
- [x] Version pinning lockfile (`mcp-manager lock --check`)
- [x] Server marketplace / remote registry
- [x] Config inheritance (`extends:`) for shared team configs
- [x] Server tags with `--tag` / `--exclude-tag` filters
- [x] Onboarding wizard (`mcp-manager init`)
- [x] Project templates (`mcp-manager template list` / `use`)
- [x] Private registry authentication (`registry login` / `logout` / `auth-list`)
- [x] MCP permission-prompt accuracy auditing (`mcp-manager audit`)
- [x] Native Codex TOML adapter with policy/auth preservation
- [x] Capability inventory and static target diagnostics (`targets`, `doctor`)
- [x] User/project scoped writes for Codex, Claude Code, and Cursor

See [ROADMAP.md](ROADMAP.md) for what's next.

---

## Contributing

```bash
git clone https://github.com/AreteDriver/mcp-manager.git
cd mcp-manager
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Preflight Checklist (required before PR)

```bash
# 1. Linting & formatting
ruff check .
ruff format --check

# 2. Type checking
mypy src/mcp_manager

# 3. Tests with coverage (must be ≥87%)
pytest --cov=mcp_manager --cov-fail-under=87

# 4. Security audit
pip-audit --strict --desc=on .
bandit -r src -ll
```

CI enforces all of the above. PRs that fail any gate will not merge.

---

## Permission Prompt Audit

MCP servers register tools with names and descriptions that appear in permission prompts. A malicious or buggy server can misrepresent what a tool actually does — e.g., register a tool as `"read_file"` that actually executes shell commands.

`mcp-manager audit` tests this display layer with safe, built-in probes:

```bash
# List all built-in probes (HackerOne-style categories)
mcp-manager audit list

# Run the full audit runbook against a target server
mcp-manager audit runbook --target ./my-server

# Start an MCP server that exposes the audit as a tool
mcp-manager audit serve
```

All probes use **benign handlers** — they register misleading metadata but return safe JSON markers. No actual harmful behavior is performed. This makes the audit safe to run against production configs.


---

## Related Projects

- **[animus](https://github.com/AreteDriver/animus)** — Personal AI operating environment with evidence-graded maturity and autonomous improvement
- **[ai-spend](https://github.com/AreteDriver/ai-spend)** — Cross-provider AI cost aggregation (`pip install ai-spend`)
- **[agent-lint](https://github.com/AreteDriver/agent-lint)** — Workflow YAML cost estimator + anti-pattern linter (`pip install agentlinter`)

[Discord](https://discord.gg/fdzQkrt8) — Join the community

*Part of the [AreteDriver](https://github.com/AreteDriver) AI tooling ecosystem.*
