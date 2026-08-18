"""Built-in target adapter registry."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from mcp_manager.adapters.base import TargetAdapter
from mcp_manager.adapters.codex import CodexTargetAdapter
from mcp_manager.adapters.json_target import JsonTargetAdapter
from mcp_manager.config import TARGET_FORMATS, TARGET_PROJECT_PATHS


def build_target_adapters(
    config_paths: Iterable[tuple[str, str | Path, str | None]],
) -> dict[str, TargetAdapter]:
    """Build adapters from the configurable target path registry."""
    adapters: dict[str, TargetAdapter] = {}
    for name, path_value, wrapper_key in config_paths:
        path = Path(path_value).expanduser()
        project_value = TARGET_PROJECT_PATHS.get(name)
        project_path = Path(project_value) if project_value else None
        if TARGET_FORMATS.get(name, "json") == "toml":
            adapters[name] = CodexTargetAdapter(user_path=path, project_path=project_path)
        else:
            adapters[name] = JsonTargetAdapter(
                name=name,
                user_path=path,
                wrapper_key=wrapper_key,
                project_path=project_path,
                oauth=name in {"claude-code", "claude-desktop", "cursor", "windsurf"},
                implicit_url_transport=("http" if name in {"cursor", "windsurf"} else None),
            )
    return adapters
