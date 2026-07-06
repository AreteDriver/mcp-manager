# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |
| Older   | :x:                |

## Reporting a Vulnerability

Please report security vulnerabilities by opening a **private** security advisory at:
https://github.com/AreteDriver/mcp-manager/security/advisories/new

Do not open public issues for security bugs.

## Disclosure Timeline

- **Day 0–7**: Initial triage and severity assessment
- **Day 7–14**: Patch development (critical: 72h)
- **Day 14–21**: Coordinated disclosure window
- **Day 21+**: Public disclosure if no response

## What We Consider in Scope

- Authentication / authorization bypasses
- Privilege escalation in tool execution
- Data exfiltration via tool parameters
- Supply-chain attacks via dependency poisoning
- SSRF / request forgery in HTTP-based tools

## Out of Scope

- Denial of service via resource exhaustion (handled via rate limiting)
- Social engineering against MCP server operators
- Vulnerabilities in upstream dependencies (report to vendor)

## Security Measures

- `pip-audit` and `bandit` run on every push/PR via GitHub Actions
- Dependencies are pinned and scanned for CVEs
- Tool parameters validated via Pydantic before execution
- No secrets committed to source (enforced via `gitleaks`)
