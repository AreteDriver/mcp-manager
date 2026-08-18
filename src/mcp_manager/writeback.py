"""Write MCP server configs back to IDE-specific JSON files.

All operations are atomic (write to temp, then rename) and create backups
before modifying existing files.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from mcp_manager.adapters import ConfigScope, build_target_adapters
from mcp_manager.adapters.base import PreviewValue, TargetAdapter
from mcp_manager.adapters.json_target import JsonTargetAdapter
from mcp_manager.config import IDE_CONFIG_PATHS, TARGET_FORMATS, TARGET_PROJECT_PATHS
from mcp_manager.exceptions import WritebackError
from mcp_manager.models import McpServer

logger = logging.getLogger(__name__)

_BACKUP_SUFFIX = ".mcp-manager-backup"


class ConfigWriteback:
    """Write server configurations back to IDE config files."""

    def __init__(self) -> None:
        self._ide_configs: dict[str, tuple[str, str | None]] = {}
        for tool_name, path_str, wrapper_key in IDE_CONFIG_PATHS:
            self._ide_configs[tool_name] = (path_str, wrapper_key)
        self._target_adapters = build_target_adapters(IDE_CONFIG_PATHS)

    def _resolve(
        self,
        ide: str,
        *,
        scope: ConfigScope = "user",
        project_dir: Path | None = None,
    ) -> tuple[Path, str | None]:
        """Return the expanded config path and wrapper key for an IDE."""
        path_str, wrapper_key = self._ide_configs[ide]
        if scope == "project":
            relative = TARGET_PROJECT_PATHS.get(ide)
            if relative is None:
                raise WritebackError(f"Target {ide!r} does not support project-scoped config")
            return (project_dir or Path.cwd()).resolve() / relative, wrapper_key
        return Path(path_str).expanduser(), wrapper_key

    def _adapter_for(self, ide: str) -> TargetAdapter:
        """Return an adapter while honoring test/user path overrides."""
        if ide not in self._ide_configs:
            raise WritebackError(f"Unknown IDE: {ide}. Supported: {self.get_supported_ides()}")
        path_value, wrapper_key = self._ide_configs[ide]
        configured = self._target_adapters.get(ide)
        if configured is not None and TARGET_FORMATS.get(ide) == "toml":
            return configured
        return JsonTargetAdapter(
            name=ide,
            user_path=Path(path_value),
            wrapper_key=wrapper_key,
            project_path=(Path(TARGET_PROJECT_PATHS[ide]) if ide in TARGET_PROJECT_PATHS else None),
            oauth=configured.capabilities.oauth if configured else False,
            implicit_url_transport=(
                getattr(configured, "implicit_url_transport", None) if configured else None
            ),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_supported_ides(self) -> list[str]:
        """Return the list of IDE/tool names we can write to."""
        return list(self._ide_configs.keys())

    def get_config_path(
        self,
        ide: str,
        *,
        scope: ConfigScope = "user",
        project_dir: Path | None = None,
    ) -> Path | None:
        """Return the expected config path for an IDE, or None if unknown."""
        info = self._ide_configs.get(ide)
        if info:
            return self._resolve(ide, scope=scope, project_dir=project_dir)[0]
        return None

    def supports_scope(self, ide: str, scope: ConfigScope) -> bool:
        """Return whether a target supports the requested config scope."""
        adapter = self._adapter_for(ide)
        return scope == "user" or adapter.capabilities.project_scope

    def write_servers(
        self,
        ide: str,
        servers: list[McpServer],
        *,
        create_if_missing: bool = False,
        dry_run: bool = False,
        scope: ConfigScope = "user",
        project_dir: Path | None = None,
    ) -> Path:
        """Write servers to an IDE config file.

        Args:
            ide: IDE/tool name (e.g. "cursor", "claude-code").
            servers: Servers to write. Replaces existing entries with the same name.
            create_if_missing: If True, create the file (and parent dirs) if absent.
            dry_run: If True, compute the result but do not write anything.

        Returns:
            Path to the config file that would be / was written.

        Raises:
            WritebackError: If the IDE is unknown or writing fails.
        """
        if ide not in self._ide_configs:
            raise WritebackError(f"Unknown IDE: {ide}. Supported: {self.get_supported_ides()}")

        config_path, _wrapper_key = self._resolve(ide, scope=scope, project_dir=project_dir)
        adapter = self._adapter_for(ide)
        adapter.validate_servers(servers)

        if not config_path.exists():
            if not create_if_missing and not dry_run:
                raise WritebackError(f"Config file does not exist: {config_path}")
            existing_text = None
        else:
            try:
                existing_text = config_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise WritebackError(f"Cannot read {config_path}: {exc}") from exc

        rendered = adapter.render(existing_text, servers)
        if dry_run:
            logger.info("[dry-run] Would update %s", config_path)
            return config_path

        if not config_path.exists():
            try:
                config_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise WritebackError(f"Cannot create parent dirs for {config_path}: {exc}") from exc
        else:
            self._backup(config_path)
        self._atomic_write(config_path, rendered)
        return config_path

    def preview(
        self,
        ide: str,
        servers: list[McpServer],
        *,
        scope: ConfigScope = "user",
        project_dir: Path | None = None,
    ) -> PreviewValue:
        """Return the native target config that would be written."""
        if ide not in self._ide_configs:
            raise WritebackError(f"Unknown IDE: {ide}. Supported: {self.get_supported_ides()}")

        config_path, _wrapper_key = self._resolve(ide, scope=scope, project_dir=project_dir)
        adapter = self._adapter_for(ide)
        adapter.validate_servers(servers)
        existing_text = None
        if config_path.exists():
            try:
                existing_text = config_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise WritebackError(f"Cannot read {config_path}: {exc}") from exc
        return adapter.preview(existing_text, servers)

    def translation_warnings(self, ide: str, servers: list[McpServer]) -> list[str]:
        """Return non-fatal warnings for a target translation."""
        return self._adapter_for(ide).translation_warnings(servers)

    def remove_servers(
        self,
        ide: str,
        server_names: set[str],
        *,
        dry_run: bool = False,
        scope: ConfigScope = "user",
        project_dir: Path | None = None,
    ) -> tuple[Path, list[str]]:
        """Remove servers from an IDE config by name.

        Args:
            ide: IDE/tool name.
            server_names: Set of server names to remove.
            dry_run: If True, compute result but do not write.

        Returns:
            Tuple of (config_path, list of actually removed names).

        Raises:
            WritebackError: If the IDE is unknown or writing fails.
        """
        if ide not in self._ide_configs:
            raise WritebackError(f"Unknown IDE: {ide}. Supported: {self.get_supported_ides()}")

        config_path, _wrapper_key = self._resolve(ide, scope=scope, project_dir=project_dir)

        if not config_path.exists():
            return (config_path, [])

        try:
            existing_text = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WritebackError(f"Cannot read {config_path}: {exc}") from exc
        data, removed = self._adapter_for(ide).remove(existing_text, server_names)

        if dry_run:
            logger.info("[dry-run] Would remove %s from %s", removed, config_path)
            return (config_path, removed)

        if not removed:
            return (config_path, [])

        self._backup(config_path)
        self._atomic_write(config_path, data)
        return (config_path, removed)

    @staticmethod
    def _backup(config_path: Path) -> None:
        backup_path = config_path.with_suffix(config_path.suffix + _BACKUP_SUFFIX)
        try:
            shutil.copy2(config_path, backup_path)
        except OSError as exc:
            raise WritebackError(f"Failed to create backup at {backup_path}: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _atomic_write(self, path: Path, data: dict[str, Any] | str) -> None:
        """Write target-native config atomically via a temp file."""
        import os

        tmp_path: str | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=path.parent,
                prefix=f".{path.name}-tmp-",
                suffix=path.suffix or ".tmp",
            )
            with open(fd, "w", encoding="utf-8") as fh:
                if isinstance(data, str):
                    fh.write(data)
                    if data and not data.endswith("\n"):
                        fh.write("\n")
                else:
                    json.dump(data, fh, indent=2, ensure_ascii=False)
                    fh.write("\n")
            os.replace(tmp_path, path)
        except OSError as exc:
            if tmp_path is not None:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except OSError:
                    logger.warning("Failed to clean up temporary config file %s", tmp_path)
            raise WritebackError(f"Failed to write {path}: {exc}") from exc
