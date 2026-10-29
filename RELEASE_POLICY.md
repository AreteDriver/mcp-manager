# Release Policy: Solo-Maintainer Governance

## Overview
MCP Manager is maintained by a solo developer. To maintain high security and quality standards while avoiding artificial bottlenecks, this project utilizes an **Evidence-Based Approval** model. 

In the absence of a second human reviewer, the requirement for an "Approving Review" is satisfied by the completion of the **Release Evidence Gate**.

## The Release Evidence Gate
A release candidate is authorized for merge to `main` and publication to PyPI only when the following three gates are closed and evidence is attached to the release PR.

### 1. Technical Gate (Automated)
The candidate must pass all automated quality and security checks:
- **CI Status:** All GitHub Actions (including the OS/Python matrix and package jobs) must be green.
- **Security Audit:** `bandit` and `pip-audit` must return zero unmitigated High or Critical vulnerabilities.
- **Test Coverage:** The candidate must meet or exceed the established coverage baseline ($\ge 88\%$).

### 2. Experience Gate (Empirical)
The author must verify the release candidate in a "Clean Room" environment:
- **Fresh Installation:** The candidate must be installed from the built wheel into a fresh virtual environment.
- **User Journey Validation:** The author must successfully execute the core user journey (e.g., discovery, configuration sync, and tool invocation).
- **Evidence:** A runtime receipt (e.g., `receipt.json` or execution logs) must be attached to the PR.

### 3. Governance Gate (Administrative)
Final consistency checks must be verified:
- **Version Sync:** The version in `__init__.py` must match the proposed GitHub Tag and the `CHANGELOG.md` entry.
- **Documentation:** The `User Guide` and `Release Notes` must accurately reflect the changes in the candidate.
- **Security Review:** A final audit of the `SECURITY.md` policy must confirm that no new high-risk attack vectors were introduced.

## Authorization
Upon attachment of the required evidence for all three gates, the maintainer is authorized to self-approve the PR and proceed with the release. This policy serves as the authoritative record for the bypass of traditional multi-human review requirements.
