# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |
| < 1.0   | :x:                |

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

- Resource exhaustion caused by an operator-selected third-party MCP server
- Social engineering against MCP server operators
- Vulnerabilities in upstream dependencies (report to vendor)

## Security Measures

- `pip-audit` and `bandit` run on every push/PR via GitHub Actions
- Project dependencies are resolved and scanned in strict mode for CVEs
- Tool parameters validated via Pydantic before execution
- Repository history is scanned for secrets with `gitleaks`
- Authenticated registry requests refuse redirects to prevent credential forwarding
- Remote inherited configs cannot read local files and are size-bounded
- Config and credential writes use same-directory atomic replacement
