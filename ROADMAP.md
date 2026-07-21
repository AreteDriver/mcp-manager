# MCP Manager Roadmap

**Current version:** v0.7.1 — Auth hardening + review debt closure
**Target:** v0.8.0 — OAuth2 device flow, token refresh, team RBAC

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

### v0.4.0 (Shipped)

| Metric | Status | Target | Measurement |
|--------|--------|--------|-------------|
| Server marketplace | ✅ Complete | Curated directory with quality scores | Community submissions |
| Project-scoped config adoption | ✅ Complete | 5+ real projects using `.mcp-manager.yml` | GitHub search |
| PyPI downloads | 🔄 Next | 200+/mo | pypistats |

### v0.5.0 (Shipped)

| Metric | Status | Target | Measurement |
|--------|--------|--------|-------------|
| Config inheritance (`extends:`) | ✅ Complete | Circular detection, left-to-right merge | Unit tests |
| Server tags | ✅ Complete | `--tag` / `--exclude-tag` filters | Unit tests |
| Project templates | ✅ Complete | 4+ built-in templates | Integration tests |
| Init wizard | ✅ Complete | Interactive scaffold | Manual QA |
| Documentation site | ✅ Complete | MkDocs Material on GitHub Pages | Live URL |
| Test coverage | ✅ Complete | ≥90% | pytest-cov |
| PyPI downloads | 🔄 Next | 200+/mo | pypistats |

### v0.6.0 — "Registry Sync" ✅ Shipped

**Theme:** Pull server definitions from remote registries.

| Metric | Status | Target | Measurement |
|--------|--------|--------|-------------|
| Remote registry sync | ✅ Complete | `mcp-manager registry diff` / `pull` | Integration tests |
| Registry authentication | ✅ Complete | `--token`, `--user`, `--password` | Unit tests |
| PyPI downloads | 🔄 Next | 200+/mo | pypistats |

### v0.7.0 — "Auth Hardening" ✅ Shipped

**Theme:** Production-grade credential management.

| Metric | Status | Target | Measurement |
|--------|--------|--------|-------------|
| Auth profiles (stored credentials) | ✅ Complete | `registry login` / `logout` / `auth-list` | Unit tests |
| Env-var fallback | ✅ Complete | `MCP_MANAGER_REGISTRY_TOKEN` / `_USER` / `_PASSWORD` | Unit tests |
| Credential validation | ✅ Complete | HEAD request before storing | Unit tests |
| Release automation | ✅ Complete | Version guard + CHANGELOG extraction + PyPI publish | Workflow tests |
| Test coverage | ✅ Complete | ≥90% | pytest-cov |

### v0.7.1 — "Review Debt Closure" ✅ Shipped

**Theme:** Zero review findings, clean CI, zero warnings.

| Metric | Status | Target | Measurement |
|--------|--------|--------|-------------|
| Senior review findings closed | ✅ Complete | 16/16 resolved | Commit log |
| CI green (release workflow) | ✅ Complete | Tests + build + publish pass | GitHub Actions |
| Zero test warnings | ✅ Complete | No RuntimeWarning or PytestUnknownMarkWarning | pytest |

### v0.8.0 (Target)

**Theme:** Enterprise auth and team governance.

| Metric | Target | Measurement |
|--------|--------|-------------|
| OAuth2 device flow | `mcp-manager registry login --oauth2` | Design doc |
| Token refresh | Auto-refresh before expiry | Prototype |
| Team RBAC | Read-only vs admin registry roles | Design doc |

---

## Why Now?

The MCP market window is open and closing:
- Anthropic pushed MCP as an open standard (2024–2025)
- Cursor and Windsurf adopted it for tool integration (2025)
- GitHub Copilot is evaluating MCP support (rumored 2025 H2)
- **No dominant player** exists in MCP server management

The team that makes MCP configs as portable as `docker-compose.yml` wins this layer.

---

*Last updated: 2026-07-20*
