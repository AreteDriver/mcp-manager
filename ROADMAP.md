# MCP Manager Roadmap

**Current version:** v0.1.x — Basic registry, health checks, export/import
**Target:** v0.2.0 — Project-scoped configs, cross-IDE portability, server lifecycle management

---

## v0.2.0 — "Works Everywhere"

**Theme:** MCP configs should live in the repo, not in IDE settings.

### P1: Project-Scoped MCP Configuration

**Problem:** MCP servers are configured globally per IDE. Switching projects means manual enable/disable. Team members can't share server configs via git.

**Solution:** `.mcp-manager.yml` in repo root. When `mcp-manager` runs inside a project, it:
1. Reads `.mcp-manager.yml` for project-specific servers
2. Merges with global registry (project wins on conflicts)
3. Exports active config to the IDE(s) the user actually uses

```yaml
# .mcp-manager.yml
project: my-service
servers:
  postgres-local:
    command: node
    args: ["./mcp/postgres-server/dist/index.js"]
    env:
      DATABASE_URL: ${DATABASE_URL}  # resolved from shell env
    auto_start: true
    health_check:
      timeout: 5
      retry: 3
  stripe-mcp:
    command: npx
    args: ["-y", "@stripe/mcp"]
    env:
      STRIPE_SECRET_KEY: ${STRIPE_SECRET_KEY}  # resolved from shell env
```

**Commands:**
- `mcp-manager project init` — scaffold `.mcp-manager.yml`
- `mcp-manager project validate` — lint config, check env vars present, test commands exist
- `mcp-manager project export --ide cursor` — write merged config to `.cursor/mcp.json`
- `mcp-manager project export --ide claude-code` — update `~/.claude/mcp.json` with project servers

### P2: Cross-IDE Config Portability

**Problem:** Claude Code, Cursor, and Windsurf each use different JSON schemas for MCP server configs. Keeping them in sync is manual and error-prone.

**Solution:** One canonical representation (`mcp-manager`'s internal model) → export adapters for each IDE format.

| IDE | Config File | Status |
|-----|-------------|--------|
| Claude Code | `~/.claude/mcp.json` | Supported |
| Cursor | `.cursor/mcp.json` | Planned |
| Windsurf | `~/.windsurf/mcp.json` | Planned |
| Zed | `~/.config/zed/settings.json` (mcp_servers key) | Planned |
| VS Code | `.vscode/mcp.json` | Planned |

**Command:** `mcp-manager export --ide <name> --format <json|yaml>`

### P3: Server Health Checking (Enhanced)

**Problem:** Current `mcp-manager health` only checks if the server process starts. It doesn't verify the server actually responds to MCP protocol `initialize` or serves useful tools.

**Solution:** Deep health checks:
- **Process health:** Server starts and stays up for 5s (current behavior)
- **Protocol health:** Server responds to `initialize` with valid JSON-RPC
- **Tool health:** Server returns a non-empty `tools/list`
- **Dependency health:** Required binaries (`node`, `python`, `docker`) are on `$PATH`

**Commands:**
- `mcp-manager health --deep` — run all check levels
- `mcp-manager health --watch` — continuous monitoring (for CI or pre-commit hooks)

### P4: Version Pinning

**Problem:** `npx -y @some-org/mcp-server` runs the latest version. A breaking change in the server breaks every team member's IDE at a different time.

**Solution:** Lockfile pattern.

```yaml
# .mcp-manager.yml
servers:
  my-server:
    command: npx
    args: ["-y", "@some-org/mcp-server@1.2.3"]  # explicit version
```

`mcp-manager lock` → writes `.mcp-manager.lock` with resolved versions (like `package-lock.json`).
`mcp-manager lock --check` → CI gate ensuring lockfile matches resolved versions.

---

## v0.3.0 — "Team-Ready" (Future)

**Theme:** MCP at team/enterprise scale.

- **Remote server registry** — Share vetted MCP servers across an organization (internal npm registry / GitHub packages integration)
- **Secret injection** — Integrate with 1Password, Doppler, or HashiCorp Vault for `env` resolution
- **Server marketplace** — Curated directory of MCP servers with quality scores (health pass rate, tool count, last updated)
- **CI gate** — `mcp-manager validate` as a GitHub Action ensuring `.mcp-manager.yml` is valid before merge

---

## Success Metrics for v0.2.0

| Metric | Target | Measurement |
|--------|--------|-------------|
| Project-scoped config adoption | 5+ real projects using `.mcp-manager.yml` | GitHub search for `.mcp-manager.yml` |
| Cross-IDE export coverage | 3+ IDEs supported | Release notes + docs verification |
| Deep health check accuracy | >95% true-positive rate on broken servers | Manual test against 20 known-good + 10 known-bad servers |
| PyPI downloads | 200+/mo | pypistats (deflated for bot noise) |

---

## Why Now?

The MCP market window is open and closing:
- Anthropic pushed MCP as an open standard (2024–2025)
- Cursor and Windsurf adopted it for tool integration (2025)
- GitHub Copilot is evaluating MCP support (rumored 2025 H2)
- **No dominant player** exists in MCP server management

The team that makes MCP configs as portable as `docker-compose.yml` wins this layer.

---

*Last updated: 2026-07-17*
