# Design Spec: P5 — Server Marketplace

**Status:** DRAFT  
**Author:** AreteDriver  
**Date:** 2026-07-20  
**Depends on:** P4 (Version Pinning) ✅  
**Target Version:** v0.4.0

---

## Problem Statement

Developers discover MCP servers through word-of-mouth, Discord, or scattered READMEs. There is no trusted index that answers:

- "Which filesystem MCP server is production-ready?"
- "Does this server actually respond to `tools/list`?"
- "When was it last updated?"
- "Is it safe to run?"

**Goal:** A built-in marketplace that makes discovering and installing MCP servers as easy as `pip install` or `apt search`.

---

## Design Principles

1. **Trust through evidence, not popularity** — Quality scores derived from automated health checks, not GitHub stars.
2. **Static-first, dynamic-later** — MVP is a curated YAML file in the repo. No infrastructure required.
3. **Install is just config generation** — `mcp-manager install <name>` adds an entry to `.mcp-manager.yml`, it does not run `npm install` or clone repos.
4. **Composability** — Marketplace commands reuse existing `HealthChecker`, `Lockfile`, and `project_config` primitives.

---

## Architecture

### Data Model

```yaml
# marketplace/index.yaml (committed in repo)
categories:
  - name: Database
    description: MCP servers for database interaction

servers:
  - name: postgres-mcp
    display_name: PostgreSQL MCP
    description: Query and manage PostgreSQL databases
    repository: https://github.com/modelcontextprotocol/server-postgres
    categories: [Database]
    install_spec:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-postgres"]
      env:
        DATABASE_URL: ${DATABASE_URL}
    quality:
      health_pass_rate: 0.0   # computed by CI
      tool_count: 0           # computed by CI
      last_updated: null      # computed by CI
      license: MIT            # static
      verified: false        # manual gate

  - name: filesystem-mcp
    display_name: Filesystem MCP
    description: Secure filesystem access with configurable roots
    repository: https://github.com/modelcontextprotocol/server-filesystem
    categories: [Filesystem]
    install_spec:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem"]
      env:
        FILESYSTEM_ROOTS: ${FILESYSTEM_ROOTS}
    quality:
      health_pass_rate: 0.0
      tool_count: 0
      last_updated: null
      license: MIT
      verified: false
```

### Schema Definitions

```python
class MarketplaceServer(BaseModel):
    name: str                       # CLI key (kebab-case)
    display_name: str
    description: str
    repository: HttpUrl
    categories: list[str]
    install_spec: StdioConfig | NetworkConfig  # Reuses existing model
    quality: QualityScore

class QualityScore(BaseModel):
    health_pass_rate: float   # 0.0–1.0, from CI deep-check
    tool_count: int           # tools/list count, from CI
    last_updated: str | None # ISO date, from CI
    license: str              # Static, SPDX identifier
    verified: bool             # Manual curation flag
```

---

## CLI Surface

### `mcp-manager search <query>`

Search the marketplace index by name, description, or category.

```bash
$ mcp-manager search postgres

┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┓
┃ Name         ┃ Description                  ┃ Category ┃ Quality  ┃
┣━━━━━━━━━━━━━━╋━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━━━┫
┃ postgres-mcp ┃ Query PostgreSQL databases   ┃ Database ┃ ⬜ 0.0   ┃
┗━━━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┻━━━━━━━━━━┻━━━━━━━━━━┛
```

Flags:
- `--category <name>` — Filter by category
- `--verified-only` — Only show verified servers
- `--json` — JSON output

### `mcp-manager info <name>`

Show detailed info for a single marketplace server.

```bash
$ mcp-manager info postgres-mcp

Name:        postgres-mcp
Display:     PostgreSQL MCP
Repo:        https://github.com/modelcontextprotocol/server-postgres
License:     MIT
Verified:    ⬜
Health:      0.0% (not yet measured)
Tools:       0

Install:
  command: npx
  args: ["-y", "@modelcontextprotocol/server-postgres"]
  env:
    DATABASE_URL: ${DATABASE_URL}
```

### `mcp-manager install <name>`

Add the server's `install_spec` to `.mcp-manager.yml` in the current directory. Creates the file if missing.

```bash
$ mcp-manager install postgres-mcp

Added 'postgres-mcp' to .mcp-manager.yml
Run 'mcp-manager project validate' to verify.
```

Flags:
- `--project <path>` — Target project directory (default: cwd)
- `--dry-run` — Preview changes without writing
- `--to-registry` — Add to global registry instead of project config

### `mcp-manager marketplace refresh`

(Re)-run deep health checks against all marketplace servers and update `index.yaml` with computed quality scores.

- Runs in CI nightly
- Writes results back to `marketplace/index.yaml`
- Creates `.mcp-manager-marketplace.lock` (lockfile for marketplace servers themselves)

---

## Quality Score Computation (CI Pipeline)

```yaml
# .github/workflows/marketplace-refresh.yml
name: Marketplace Refresh

on:
  schedule:
    - cron: '0 6 * * *'  # 6 AM UTC daily
  workflow_dispatch:

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v6
        with:
          python-version: '3.12'
      - run: pip install -e ".[dev]"
      - run: mcp-manager marketplace refresh --output marketplace/index.yaml
      - run: |
          git config user.name "github-actions"
          git config user.email "github-actions@github.com"
          git add marketplace/index.yaml
          git diff --cached --quiet || git commit -m "chore: refresh marketplace quality scores"
          git push
```

**Scoring algorithm (v1):**
1. For each server, run `mcp-manager health --deep`
2. `health_pass_rate` = 1.0 if deep check passes, 0.0 if not
3. `tool_count` = length of `tools/list` result
4. `last_updated` = `npm view <pkg> time.modified` or GitHub API `pushed_at`
5. Never overwrite static fields (`license`, `verified`)

**Trust levels:**
| Score | Badge | Meaning |
|---|---|---|
| ≥0.9 | 🟢 Verified | Deep check passes, >5 tools, updated within 30 days |
| ≥0.5 | 🟡 Functional | Deep check passes, may be stale |
| <0.5 | 🔴 Unstable | Fails deep check or no response |
| Unmeasured | ⬜ Unknown | Not yet evaluated by CI |

---

## File Layout

```
marketplace/
├── index.yaml          # Curated server list + computed scores
├── schemas/
│   └── index.v1.json   # JSON Schema for validation
└── .gitignore          # Ignore local test artifacts
```

---

## Security & Trust Model

1. **Curated, not crowdsourced** — Only maintainers can add entries to `index.yaml` via PR.
2. **No arbitrary code execution on install** — `install` writes YAML, it does not run `npm install`.
3. **Sandboxed health checks** — CI runs health checks in ephemeral containers; no network egress beyond npm registry.
4. **Transparent scoring** — All quality data is in the repo; anyone can audit the CI logs.

---

## MVP Scope (v0.4.0)

**In scope:**
- Static `marketplace/index.yaml` with 5–10 hand-curated servers (official MCP reference servers)
- `search`, `info`, `install` CLI commands
- Basic quality score display in search output
- CI job stub (runs manually, not yet scheduled)

**Out of scope (post-v0.4.0):**
- Remote registry API
- Community submissions / PR template
- Automated `verified` flag promotion
- Category browsing (TUI or web UI)
- Version conflict resolution on install
- Dependency pre-flight (`node --version`, etc.)

---

## Success Metrics

| Metric | Target | Measurement |
|---|---|---|
| Marketplace servers indexed | ≥5 official MCP servers | `marketplace/index.yaml` |
| `search` command works | No crashes, sorted results | CLI test |
| `install` command works | Adds valid entry to `.mcp-manager.yml` | Integration test |
| CI refresh job exists | Workflow file committed | `.github/workflows/` |
| Quality scores displayed | Visible in `search` / `info` output | Manual test |

---

## Open Questions

1. Should `install` prompt for required env vars (`DATABASE_URL`) or leave them as `${VAR}` placeholders?
2. Should we cache npm registry responses during refresh to avoid rate limits?
3. Should unverified servers be hidden by default in `search`?
4. How do we handle network-based MCP servers (SSE/HTTP) in the marketplace?

---

## Decision Log

| ID | Decision | Rationale |
|---|---|---|
| DS-20260720-001 | Static YAML over remote API | Zero infra, zero auth, works offline, PR-reviewable |
| DS-20260720-002 | `install` writes config, does not run commands | Security: never execute arbitrary npm packages during install |
| DS-20260720-003 | Quality scores computed in CI, not client-side | Deterministic, auditable, avoids rate-limiting client machines |
| DS-20260720-004 | Start with official MCP reference servers | Maximum trust, well-documented, health checks likely to pass |

---

*Next step: Approve spec → scaffold `marketplace/index.yaml` + CLI commands → write tests → integrate CI refresh job.*
