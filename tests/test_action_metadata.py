"""Contract tests for the distributable root GitHub Action."""

from __future__ import annotations

from pathlib import Path

import yaml


def _metadata() -> dict[str, object]:
    return yaml.safe_load(Path("action.yml").read_text(encoding="utf-8"))


def test_root_action_is_marketplace_discoverable() -> None:
    metadata = _metadata()

    assert metadata["name"] == "MCP Manager Validate"
    assert metadata["description"]
    assert metadata["branding"] == {"icon": "check-circle", "color": "green"}


def test_root_action_installs_its_tagged_source() -> None:
    metadata = _metadata()
    steps = metadata["runs"]["steps"]  # type: ignore[index]
    install_step = next(
        step for step in steps if step["name"] == "Install mcp-manager from this release"
    )

    assert '"$GITHUB_ACTION_PATH"' in install_step["run"]


def test_shell_steps_do_not_interpolate_inputs_directly() -> None:
    metadata = _metadata()
    steps = metadata["runs"]["steps"]  # type: ignore[index]

    for step in steps:
        if "run" in step:
            assert "${{ inputs." not in step["run"]
