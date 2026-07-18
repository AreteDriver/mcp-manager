# MCP Manager Roadmap

**Current version:** v0.2.0 — Project-scoped configs, atomic write-back, deep health checks
**Target:** v0.3.0 — Server lifecycle management, CI gates, marketplace

---

## v0.2.0 — "Works Everywhere" ✅ Shipped

**Theme:** MCP configs should live in the repo, not in IDE settings.

### ✅ P1: Project-Scoped MCP Configuration

`.mcp-manager.yml` in repo root with env var resolution and validation.

**Commands shipped:**
- `mcp-manager project init`
- `mcp-manager project validate`
- `mcp-manager project export --ide <name>`
- `mcp-manager sync --ide <name> --dry-run`

### ✅ P2: Cross-IDE Config Portability (Write-Back)

Atomic IDE config writes with backups and dry-run.

| IDE | Config File | Read | Write |
|-----|-------------|------|-------|
| Claude Code | `~/.claude.json` | ✅ | ✅ |
| Claude Desktop | `~/.config/Claude/claude_desktop_config.json` | ✅ | ✅ |
| Cursor | `~/.cursor/mcp.json` | ✅ | ✅ |
| Windsurf | `~/.windsurf/mcp_config.json` | ✅ | ✅ |
| Project-level | `.mcp.json` | ✅ | ✅ |

### ✅ P3: Server Health Checking (Enhanced)

Deep health checks with dependency validation and `tools/list` verification.

**Commands shipped:**
- `mcp-manager health --deep`

### P4: Version Pinning (Planned)

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

## Success Metrics

### v0.2.0 (Shipped)

| Metric | Status | Target | Measurement |
|--------|--------|--------|-------------|
| Config write-back with backups | ✅ Complete | 4+ IDEs | Integration tests |
| Project-scoped config parsing | ✅ Complete | Stable YAML + env resolution | Unit tests |
| Deep health checks | ✅ Complete | >95% true-positive | Unit tests |
| PyPI package published | 🔄 Next | `arete-mcp` | PyPI listing |

### v0.3.0 (Target)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Project-scoped config adoption | 5+ real projects using `.mcp-manager.yml` | GitHub search for `.mcp-manager.yml` |
| Server auto-restart | Stable daemon mode | Integration tests |
| CI gate GitHub Action | Published to Marketplace | Action installs |
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
