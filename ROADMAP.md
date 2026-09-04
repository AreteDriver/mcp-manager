# MCP Manager Roadmap

**Current version:** v1.0.0 — production-stable configuration governance

MCP Manager follows a deliberately narrow contract: discover, translate,
diagnose, validate, and safely synchronize MCP configuration. It does not host
MCP servers or assume authority over a client's runtime policy.

## Shipped milestones

| Version | Outcome |
|---------|---------|
| v0.2 | Project-scoped configuration and cross-client write-back |
| v0.3 | Deep health checks, lockfiles, monitor, and CI validation |
| v0.4 | Curated server marketplace |
| v0.5 | Config inheritance, tags, templates, and onboarding |
| v0.6 | Remote registry synchronization |
| v0.7 | Credential profiles and trusted release automation |
| v0.8 | OAuth2 device flow and permission-prompt audit tools |
| v0.9 | Native client adapters, capabilities, and static diagnostics |
| v0.10 | MCP 2026-07-28 discovery, SDK 2.x, and legacy fallback |
| v1.0 | Cross-platform gates, atomic durability, security hardening, and a stable CLI contract |

## v1.0 release gates

- [x] Native adapters preserve unrelated client configuration.
- [x] Unsupported translations warn or reject instead of silently changing transport.
- [x] Config, auth, lockfile, and registry writes use same-directory atomic replacement.
- [x] Remote config inheritance rejects local-file pivots, cycles, and oversized bodies.
- [x] Authenticated registry requests refuse redirects.
- [x] Ruff, formatting, strict mypy, and an 87% coverage floor are required.
- [x] CI defines Linux, macOS, and Windows test jobs on Python 3.11–3.13.
- [x] Bandit, strict project dependency audit, CodeQL, and Gitleaks fail closed.
- [x] Wheel, source distribution, metadata, and fresh-wheel smoke tests are release gates.
- [x] Release artifacts include checksums and a CycloneDX SBOM.
- [x] Confirm the exact v1.0 commit is green on hosted Linux, macOS, and Windows runners.
- [x] Complete the release-candidate dogfood checklist in `docs/production-readiness.md`.
- [ ] Publish and verify the signed-off v1.0.0 tag and PyPI artifacts.

The remaining gate requires merging the approved release candidate and pushing
the signed-off tag. It must complete through the protected release workflow;
local simulation does not replace publication and artifact verification.

## Post-v1 policy

Patch releases are limited to bug fixes, client compatibility updates, and
security work. New targets or configuration semantics require a minor release,
documented capability changes, golden fixtures, and migration guidance.

Claude Code's private project-local state inside `~/.claude.json` remains
client-owned and intentionally outside v1. The supported shared project format
is `.mcp.json`; user-scoped state remains supported separately.

*Last updated: 2026-09-03*
