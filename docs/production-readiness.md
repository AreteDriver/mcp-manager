# Production Readiness

This document is the release contract for MCP Manager 1.x. A release is ready
only when every automated gate is green on the exact tag candidate and the
manual dogfood evidence below is complete.

## Supported contract

| Surface | Supported |
|---------|-----------|
| Python | 3.11, 3.12, and 3.13 |
| Operating systems | Linux, macOS, and Windows |
| Clients | Codex, Claude Code, Claude Desktop, Cursor, and Windsurf |
| Transports | stdio, Streamable HTTP, and legacy SSE where the target supports it |
| Scopes | User scope; shared project scope for Codex, Claude Code, and Cursor |
| Stability | CLI command names, documented exit behavior, and project config schema follow SemVer |

Client-private or undocumented state is not part of the contract. In
particular, MCP Manager does not edit Claude Code's private per-project entries
inside `~/.claude.json`.

## Automated release gates

Run the canonical local verification:

```bash
ruff check src tests
ruff format --check src tests
mypy src/mcp_manager
pytest tests -q --cov=mcp_manager --cov-fail-under=87
python -m build
twine check dist/*
mkdocs build --strict
pip-audit --strict --desc=on .
bandit -r src -ll
```

GitHub Actions additionally runs the tests on all supported operating systems,
scans repository history with Gitleaks, runs CodeQL, exercises the public root
Action against valid and invalid configs, and installs the built wheel into a
fresh environment.

## Candidate evidence and acceptance

The integrated candidate combines production hardening (PR #20), bounded
marketplace refresh (PR #21), and architecture/Pages repairs (PR #22). Its
source version is 1.0.0; that version string does not establish publication.
Every release receipt must record the full commit SHA, artifact SHA-256,
platform/Python and client versions, commands, results and unresolved items.
Do not carry a passing result from a parent branch forward as final-candidate
qualification. The candidate remains held until the gates below are met.

### Automated and isolated qualification

Run these against the final candidate and retain the corresponding CI run or
local receipt. They establish tested behavior, not installed-client acceptance:

- Run the complete quality/security contract above and all nine OS/Python jobs.
- Run `scripts/rc_dogfood.py --wheel PATH_TO_CANDIDATE_WHEEL`: five native format
  round trips, repeat-write idempotence, unrelated-field preservation, backup
  restoration, forced-write cleanup and fresh-wheel CLI smoke.
- Exercise CLI import, preview, sync, health, remove and recovery using isolated
  temporary HOME/project directories and benign local protocol servers.
- Run the public Action against valid and invalid configurations.
- Install the final artifact with pip, pipx and uv; inspect its version and
  import path. Test upgrade from the preceding published version and recovery
  without editing the operator's real configuration.
- Record security scan results and reproduce any unresolved high-severity issue.

### Installed-client acceptance — still required

A rendered configuration and an SDK session are different evidence from a
client loading that configuration and using its tools. Record actual client
versions and supported transports/scopes. Use an isolated profile or approved
project with a benign test server; preserve the original config and stop on
unexpected changes. Do not copy credentials into evidence.

| Client | Candidate format coverage | Final-candidate client loads config and calls a tool |
|--------|---------------------------|----------------------------------------------------|
| Codex | Automated TOML fixtures | Pending |
| Claude Code | Automated JSON fixtures | Pending |
| Claude Desktop | Automated JSON fixtures | Pending |
| Cursor | Automated JSON fixtures | Pending |
| Windsurf | Automated JSON fixtures | Pending |

For each claimed target, preview/apply the change, invoke a harmless tool from
that client, repeat sync without changes, remove the test server and restore
the baseline. Confirm unrelated settings survive and failure recovery works.
Unsupported or unavailable combinations stay explicitly unverified; narrow
release claims if they cannot be demonstrated. A passing CI matrix is not a
claim that all five GUI/CLI clients were exercised on every OS.

### Release decision

- [ ] Final integrated commit has passing required hosted checks.
- [ ] Installed-client acceptance above is recorded, or support claims are explicitly narrowed.
- [ ] Required review is satisfied under an explicitly agreed repository policy.
- [ ] No unresolved release-blocking safety defect remains.
- [ ] Protected release publishes the approved tag and matching PyPI/GitHub artifacts.
- [ ] Downloaded artifacts match release checksums; install/upgrade and hosted documentation are verified.

The local static review agent is advisory and does not create a separate GitHub
approving identity. Its result does not authorize policy changes or publication.

### Historical evidence — not final-candidate sign-off

On September 3, 2026, existing Codex, Claude Code and Claude Desktop configs
were imported read-only on macOS. Cursor and Windsurf were not installed.
Five-format temporary fixtures, fresh pip/pipx/uv installs and 627 tests at
88.08% coverage were recorded then; these were not live acceptance of all clients.

PR #20 at `6fd5c0af08efc82f2254f5655c2eb3efc5ea2ae2` subsequently recorded
697 tests and 88.56% coverage, with successful hosted matrix checks and
fresh-wheel format fixtures. That evidence belongs to the parent candidate,
not automatically to this integrated branch. See the exact-commit Actions runs
and the integration PR for subsequent validation receipts.

## Rollback

Every existing client config is copied to a sibling
`.mcp-manager-backup` file before replacement. To recover, stop any active
monitor, copy that backup over the client config, and rerun `mcp-manager doctor`
before attempting another sync. A failed release is yanked from PyPI only when
installation itself is unsafe; otherwise publish a patch release so existing
environments have a normal upgrade path.

## Support and compatibility

After publication, the latest 1.x release will receive security and compatibility fixes. Translation
loss is surfaced as a warning, and unsupported transports are rejected. Changes
to documented output schemas or config semantics require SemVer treatment and
migration notes.
