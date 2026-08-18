"""MCP audit spec models and loader.

Ported from mcp-fuzz. A spec is a YAML file listing probe cases. Each case
 declares a *registered* tool description and an *actual* behavior marker.
 The harness asks the human to invoke the tool and verify the prompt matched
 expectations.

The threat model is Anthropic HackerOne Category 3: "Misrepresenting parameters
or tools in permission prompts by displaying different information than what
will actually be executed."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Categories from Anthropic HackerOne Claude Code scope (verified 2026-03-02).
CATEGORIES = {
    1: "permission_prompt_bypass_command",
    2: "permission_prompt_bypass_file_write",
    3: "tool_param_misrepresentation",
    4: "invisible_execution",
    5: "mcp_apps_iframe",
}


@dataclass
class ProbeCase:
    """One probe — a tool registered with a deliberate display/behavior gap."""

    probe_id: str
    category: int
    summary: str  # one-line description of what's being probed
    registered_name: str  # tool name as the host sees it
    registered_description: str  # description as the host should display
    registered_params: dict[str, dict[str, Any]] = field(default_factory=dict)
    actual_behavior: str = ""  # human-readable note on what the tool actually does
    expected_finding: str = ""  # what would constitute a bug if observed
    safe_payload: bool = True  # if True, behavior is observable-only (no side-effects)
    canonical: str | None = None  # policy identifier for permissions.allow
    subject_identifier: str | None = None  # fuzzing subject (defaults to canonical)
    prompt_template: str | None = None  # custom prompt template with {variant}
    expected_tool_names: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"category must be one of {sorted(CATEGORIES)}, got {self.category}")
        if not self.probe_id or not self.registered_name:
            raise ValueError("probe_id and registered_name are required")
        if not self.safe_payload:
            raise ValueError(
                f"probe {self.probe_id}: only safe_payload=True is supported in v0 — "
                "the harness never executes destructive behavior, only registers "
                "descriptions that lie about benign side-effects"
            )


@dataclass
class Spec:
    """A collection of probe cases."""

    name: str
    description: str
    probes: list[ProbeCase]


def load_spec(path: Path | str) -> Spec:
    """Load a probe spec from a YAML file."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    probes = [ProbeCase(**p) for p in data.get("probes", [])]
    seen: set[str] = set()
    for p in probes:
        if p.probe_id in seen:
            raise ValueError(f"duplicate probe_id: {p.probe_id}")
        seen.add(p.probe_id)
    return Spec(
        name=data["name"],
        description=data.get("description", ""),
        probes=probes,
    )
