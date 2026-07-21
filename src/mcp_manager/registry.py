"""Persistent server registry for mcp-manager."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from pydantic import ValidationError

from mcp_manager.config import MANAGER_REGISTRY_FILE
from mcp_manager.exceptions import RegistryError
from mcp_manager.models import HealthResult, McpServer, RegistryEntry

logger = logging.getLogger(__name__)


class ServerRegistry:
    """Persistent JSON-backed registry of MCP servers."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or MANAGER_REGISTRY_FILE
        self._entries: dict[str, RegistryEntry] = {}

    def load(self) -> None:
        """Load registry from disk. No-op if file doesn't exist."""
        self._entries.clear()
        if not self._path.is_file():
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RegistryError(f"Failed to load registry: {exc}") from exc

        if not isinstance(raw, dict):
            raise RegistryError("Registry file is not a JSON object")

        for name, entry_data in raw.items():
            try:
                self._entries[name] = RegistryEntry.model_validate(entry_data)
            except (ValidationError, TypeError, KeyError) as exc:
                logger.warning("Skipping invalid registry entry %r: %s", name, exc)

    def save(self) -> None:
        """Persist registry to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            name: entry.model_dump(mode="json", exclude_none=True)
            for name, entry in self._entries.items()
        }
        try:
            self._path.write_text(
                json.dumps(data, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise RegistryError(f"Failed to save registry: {exc}") from exc

    def add(self, server: McpServer) -> None:
        """Add or update a server entry."""
        existing = self._entries.get(server.name)
        self._entries[server.name] = RegistryEntry(
            server=server,
            added_at=existing.added_at if existing else time.time(),
            last_health=existing.last_health if existing else None,
        )

    def remove(self, name: str) -> bool:
        """Remove a server by name. Returns True if found and removed."""
        if name in self._entries:
            del self._entries[name]
            return True
        return False

    def get(self, name: str) -> RegistryEntry | None:
        """Get a single entry by name."""
        return self._entries.get(name)

    def list_all(self) -> list[RegistryEntry]:
        """Return all registry entries sorted by name."""
        return [self._entries[k] for k in sorted(self._entries)]

    def update_health(self, name: str, result: HealthResult) -> None:
        """Update the last health check for a server and persist."""
        entry = self._entries.get(name)
        if entry:
            entry.last_health = result
            self.save()

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, name: str) -> bool:
        return name in self._entries
