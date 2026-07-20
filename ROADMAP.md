# MCP Manager Roadmap

**Current version:** v0.4.0 — Server marketplace, version pinning, CI gates, atomic write-back
**Target:** v0.5.0 — Team adoption, PyPI growth, marketplace quality scores

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

### ✅ P4: Version Pinning / Lockfile

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

**Shipped:** v0.3.1

---

## v0.3.0 — "Team-Ready" ✅ Shipped

**Theme:** MCP at team/enterprise scale.

### ✅ Server Auto-Restart Monitor

`mcp-manager monitor` keeps stdio servers alive with exponential backoff restart.

### ✅ CI Gate / GitHub Action

`mcp-manager validate` for fast config validation. Composite action published at `.github/actions/mcp-manager-validate`.

### ✅ P5: Server Marketplace

Curated directory of MCP servers with quality scores (health pass rate, tool count, last updated).

**Commands shipped:**
- `mcp-manager search <query>` — search by name/description/category
- `mcp-manager info <name>` — detailed server info
- `mcp-manager install <name>` — add server to `.mcp-manager.yml`

**Shipped:** v0.4.0

---

## Success Metrics

### v0.2.0 (Shipped)

| Metric | Status | Target | Measurement |
|--------|--------|--------|-------------|
| Config write-back with backups | ✅ Complete | 4+ IDEs | Integration tests |
| Project-scoped config parsing | ✅ Complete | Stable YAML + env resolution | Unit tests |
| Deep health checks | ✅ Complete | >95% true-positive | Unit tests |
| PyPI package published | 🔄 Next | `arete-mcp` | PyPI listing |

### v0.3.0 (Shipped)

| Metric | Status | Target | Measurement |
|--------|--------|--------|-------------|
| Server auto-restart monitor | ✅ Complete | Foreground + exponential backoff | Unit tests |
| CI gate GitHub Action | ✅ Complete | Composite action in repo | Workflow tests |
| PyPI package published | 🔄 Next | `arete-mcp` | PyPI listing |

### v0.4.0 (Target)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Project-scoped config adoption | 5+ real projects using `.mcp-manager.yml` | GitHub search for `.mcp-manager.yml` |
| Server marketplace | Curated directory with quality scores | Community submissions |
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

*Last updated: 2026-07-19*
