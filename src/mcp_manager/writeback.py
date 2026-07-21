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

from mcp_manager.config import IDE_CONFIG_PATHS
from mcp_manager.exceptions import WritebackError
from mcp_manager.models import McpServer, TransportType

logger = logging.getLogger(__name__)

_BACKUP_SUFFIX = ".mcp-manager-backup"


class ConfigWriteback:
    """Write server configurations back to IDE config files."""

    def __init__(self) -> None:
        self._ide_configs: dict[str, tuple[str, str | None]] = {}
        for tool_name, path_str, wrapper_key in IDE_CONFIG_PATHS:
            self._ide_configs[tool_name] = (path_str, wrapper_key)

    def _resolve(self, ide: str) -> tuple[Path, str | None]:
        """Return the expanded config path and wrapper key for an IDE."""
        path_str, wrapper_key = self._ide_configs[ide]
        return Path(path_str).expanduser(), wrapper_key

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_supported_ides(self) -> list[str]:
        """Return the list of IDE/tool names we can write to."""
        return list(self._ide_configs.keys())

    def get_config_path(self, ide: str) -> Path | None:
        """Return the expected config path for an IDE, or None if unknown."""
        info = self._ide_configs.get(ide)
        if info:
            return Path(info[0]).expanduser()
        return None

    def write_servers(
        self,
        ide: str,
        servers: list[McpServer],
        *,
        create_if_missing: bool = False,
        dry_run: bool = False,
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

        config_path, wrapper_key = self._resolve(ide)

        if not config_path.exists():
            if not create_if_missing and not dry_run:
                raise WritebackError(f"Config file does not exist: {config_path}")
            return self._create_new(config_path, wrapper_key, servers, dry_run=dry_run)

        return self._update_existing(config_path, wrapper_key, servers, dry_run=dry_run)

    def preview(self, ide: str, servers: list[McpServer]) -> dict[str, Any]:
        """Return the JSON dict that would be written without touching disk."""
        if ide not in self._ide_configs:
            raise WritebackError(f"Unknown IDE: {ide}. Supported: {self.get_supported_ides()}")

        config_path, wrapper_key = self._resolve(ide)

        if not config_path.exists():
            return self._build_new_dict(wrapper_key, servers)

        return self._build_updated_dict(config_path, wrapper_key, servers)

    def remove_servers(
        self,
        ide: str,
        server_names: set[str],
        *,
        dry_run: bool = False,
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

        config_path, wrapper_key = self._resolve(ide)

        if not config_path.exists():
            return (config_path, [])

        data = self._build_dict_without_servers(config_path, wrapper_key, server_names)
        removed = self._removed_names

        if dry_run:
            logger.info("[dry-run] Would remove %s from %s", removed, config_path)
            return (config_path, removed)

        if not removed:
            return (config_path, [])

        backup_path = config_path.with_suffix(config_path.suffix + _BACKUP_SUFFIX)
        try:
            shutil.copy2(config_path, backup_path)
        except OSError as exc:
            raise WritebackError(f"Failed to create backup at {backup_path}: {exc}") from exc

        self._atomic_write(config_path, data)
        return (config_path, removed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_new(
        self,
        config_path: Path,
        wrapper_key: str | None,
        servers: list[McpServer],
        *,
        dry_run: bool,
    ) -> Path:
        """Create a brand-new IDE config file."""
        data = self._build_new_dict(wrapper_key, servers)

        if dry_run:
            logger.info("[dry-run] Would create %s", config_path)
            return config_path

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WritebackError(f"Cannot create parent dirs for {config_path}: {exc}") from exc

        self._atomic_write(config_path, data)
        return config_path

    def _update_existing(
        self,
        config_path: Path,
        wrapper_key: str | None,
        servers: list[McpServer],
        *,
        dry_run: bool,
    ) -> Path:
        """Update an existing IDE config file, preserving non-MCP keys."""
        data = self._build_updated_dict(config_path, wrapper_key, servers)

        if dry_run:
            logger.info("[dry-run] Would update %s", config_path)
            return config_path

        # Create backup before touching the file.
        backup_path = config_path.with_suffix(config_path.suffix + _BACKUP_SUFFIX)
        try:
            shutil.copy2(config_path, backup_path)
        except OSError as exc:
            raise WritebackError(f"Failed to create backup at {backup_path}: {exc}") from exc

        self._atomic_write(config_path, data)
        return config_path

    def _build_new_dict(
        self,
        wrapper_key: str | None,
        servers: list[McpServer],
    ) -> dict[str, Any]:
        """Build a fresh IDE config dict."""
        servers_dict = {s.name: _server_to_ide_dict(s) for s in servers}
        if wrapper_key is not None:
            return {wrapper_key: servers_dict}
        return servers_dict

    def _build_updated_dict(
        self,
        config_path: Path,
        wrapper_key: str | None,
        servers: list[McpServer],
    ) -> dict[str, Any]:
        """Merge servers into an existing IDE config dict."""
        try:
            text = config_path.read_text(encoding="utf-8")
            data: dict[str, Any] = json.loads(text)
        except (OSError, json.JSONDecodeError) as exc:
            raise WritebackError(f"Cannot read or parse {config_path}: {exc}") from exc

        if not isinstance(data, dict):
            raise WritebackError(f"Config file {config_path} must contain a JSON object")

        if wrapper_key is not None:
            existing = data.get(wrapper_key, {})
            if not isinstance(existing, dict):
                existing = {}
            merged = {**existing}
            for s in servers:
                merged[s.name] = _server_to_ide_dict(s)
            data[wrapper_key] = merged
        else:
            for s in servers:
                data[s.name] = _server_to_ide_dict(s)

        return data

    def _build_dict_without_servers(
        self,
        config_path: Path,
        wrapper_key: str | None,
        server_names: set[str],
    ) -> dict[str, Any]:
        """Return a copy of the IDE config with specified server names removed."""
        try:
            text = config_path.read_text(encoding="utf-8")
            data: dict[str, Any] = json.loads(text)
        except (OSError, json.JSONDecodeError) as exc:
            raise WritebackError(f"Cannot read or parse {config_path}: {exc}") from exc

        if not isinstance(data, dict):
            raise WritebackError(f"Config file {config_path} must contain a JSON object")

        removed: list[str] = []

        if wrapper_key is not None:
            existing = data.get(wrapper_key, {})
            if isinstance(existing, dict):
                for name in list(existing):
                    if name in server_names:
                        del existing[name]
                        removed.append(name)
        else:
            data = dict(data)
            for name in list(data):
                if name in server_names:
                    del data[name]
                    removed.append(name)

        self._removed_names = removed
        return data

    def _atomic_write(self, path: Path, data: dict[str, Any]) -> None:
        """Write JSON atomically via a temp file."""
        import os

        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=path.parent,
                prefix=f".{path.name}-tmp-",
                suffix=".json",
            )
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp_path, path)
        except OSError as exc:
            raise WritebackError(f"Failed to write {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _server_to_ide_dict(server: McpServer) -> dict[str, Any]:
    """Convert an McpServer to the dict format used by IDE configs."""
    if server.transport == TransportType.STDIO and server.stdio_config:
        result: dict[str, Any] = {
            "command": server.stdio_config.command,
        }
        if server.stdio_config.args:
            result["args"] = server.stdio_config.args
        if server.stdio_config.env:
            result["env"] = server.stdio_config.env
        return result

    if server.network_config:
        result = {
            "type": server.network_config.type,
            "url": server.network_config.url,
        }
        if server.network_config.headers:
            result["headers"] = server.network_config.headers
        return result

    raise WritebackError(f"Server {server.name!r} has no valid transport config")
