# Security Model

MCP Manager handles configuration that can launch local processes and reference
credentials. Its primary security objective is to make operator-authorized
changes predictable, reviewable, and recoverable without claiming that a
third-party MCP server is trustworthy.

## Assets and trust boundaries

Protected assets include client configuration, credential environment-variable
names, stored registry credentials, lockfiles, and the integrity of commands an
operator has chosen to configure.

The trust boundaries are:

1. Local configuration and CLI input supplied by the operator.
2. Remote registries and inherited configs, which are data rather than trusted code.
3. Third-party MCP server processes, which execute with the operator's OS permissions.
4. Client-native config formats, whose capabilities differ and may not translate losslessly.
5. CI and package distribution, which must not publish an unverified artifact.

## Threats and controls

| Threat | Control |
|--------|---------|
| Partial or corrupt writes | Same-directory temp file, flush, `fsync`, atomic replace, and pre-write backup |
| Temp-file race or symlink replacement | Random `mkstemp` names and atomic replacement |
| Credential disclosure in diagnostics | Values are resolved only at runtime and diagnostic errors name variables, not values |
| Credential forwarding through redirects | Authenticated registry requests do not follow redirects |
| Remote config reads local files | Nested remote inheritance rejects relative and `file://` sources |
| Recursive or oversized remote config | Remote cycle tracking and explicit body-size limits |
| Silent policy or transport loss | Capability-aware warnings and rejection of unsupported transports |
| Dependency or source compromise | Strict dependency audit, Bandit, CodeQL, Gitleaks, pinned Actions, SBOM, and checksums |
| Malicious MCP server | Health/protocol operations use argument-vector process creation; server trust remains the operator's responsibility |

## Credential storage

Registry profiles are stored as JSON with mode `0600` and atomic replacement.
They are plaintext to the owning account. Prefer environment-backed credentials
or an OS credential manager when the local-account threat model requires
encryption at rest. CLI token/password flags are retained for compatibility but
can appear in process listings or shell history; `--password-stdin` and OAuth2
device flow are preferred.

## Residual risks

- A configured stdio server is executable code with the user's permissions.
- A compromised client can reinterpret otherwise valid configuration.
- Plaintext credentials remain readable to the owning OS account.
- Network destinations selected by the operator can observe requests made to them.
- Availability and semantic correctness of third-party servers are outside MCP Manager's control.

Report suspected vulnerabilities through the private advisory process described
in the repository `SECURITY.md`.
