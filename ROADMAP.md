# MCP Manager Roadmap

**Current version:** v0.9.0 — Native multi-client adapters and diagnostics
**Target:** v0.10.0 — Runtime diagnostics and MCP SDK 2.x migration

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
| Codex | `~/.codex/config.toml` | ✅ | ✅ |
| Claude Code | `~/.claude.json` | ✅ | ✅ |
| Claude Desktop | Platform-specific user config | ✅ | ✅ |
| Cursor | `~/.cursor/mcp.json` | ✅ | ✅ |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | ✅ | ✅ |
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

### v0.8.0 — "OAuth2 + MCP Audit" ✅ Shipped

**Theme:** OAuth2 registry auth and MCP permission-prompt auditing.

| Metric | Status | Measurement |
|--------|--------|-------------|
| OAuth2 device flow | ✅ Complete | `registry login --oauth2` tests |
| Token refresh | ✅ Complete | Auth regression tests |
| Permission-prompt audit | ✅ Complete | Built-in probe tests |

### v0.9.0 — "Native Client Adapters" ✅ Shipped

| Metric | Target | Measurement |
|--------|--------|-------------|
| Native Codex TOML | Lossless settings/comments round trip | Adapter tests |
| Target capabilities | Machine-readable `targets --json` | CLI tests |
| Static diagnostics | JSON/TOML, path, and env checks | Doctor tests |
| Project scope | Codex, Claude Code, Cursor | Integration tests |

### v0.10.0 — "Runtime Diagnostics"

| Metric | Target | Measurement |
|--------|--------|-------------|
| Deep target doctor | Optional native client/runtime verification | Integration tests |
| Claude local scope | Private project-local config in `~/.claude.json` | Scope tests |
| MCP SDK 2.x | Remove the temporary `<2.0` constraint | Full compatibility suite |

---

## Next Design Priorities

- Add optional runtime client verification to `doctor` without coupling it to serialization.
- Model Claude Code's private local scope separately from shared project scope.
- Add fixture-based conformance tests against each client's published examples.
- Migrate health and audit integrations to MCP SDK 2.x before relaxing the `<2.0` constraint.

---

*Last updated: 2026-08-17*
