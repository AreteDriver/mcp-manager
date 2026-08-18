"""Adapter for JSON MCP client configurations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp_manager.adapters.base import PreviewValue, TargetAdapter, TargetCapabilities
from mcp_manager.adapters.common import server_from_json_mapping, server_to_json_mapping
from mcp_manager.exceptions import DiscoveryError, WritebackError
from mcp_manager.models import McpServer


class JsonTargetAdapter(TargetAdapter):
    """Read and write the common ``mcpServers`` JSON dialect."""

    def __init__(
        self,
        *,
        name: str,
        user_path: Path,
        wrapper_key: str | None,
        project_path: Path | None = None,
        oauth: bool = False,
        implicit_url_transport: str | None = None,
    ) -> None:
        super().__init__(
            name=name,
            user_path=user_path,
            project_path=project_path,
            capabilities=TargetCapabilities(
                format="json",
                project_scope=project_path is not None,
                oauth=oauth,
            ),
        )
        self.wrapper_key = wrapper_key
        self.implicit_url_transport = implicit_url_transport

    def parse(
        self,
        text: str,
        *,
        source_path: Path,
        strict: bool = False,
    ) -> list[McpServer]:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DiscoveryError(f"Cannot parse {source_path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise DiscoveryError(f"Config file {source_path} must contain a JSON object")

        servers: Any = raw
        if self.wrapper_key is not None:
            servers = raw.get(self.wrapper_key, {})
        if not isinstance(servers, dict):
            raise DiscoveryError(f"Server table in {source_path} must be a JSON object")

        results: list[McpServer] = []
        for name, config in servers.items():
            if not isinstance(config, dict):
                continue
            normalized = dict(config)
            if (
                self.implicit_url_transport
                and "url" in normalized
                and "type" not in normalized
                and "command" not in normalized
            ):
                normalized["type"] = self.implicit_url_transport
            try:
                results.append(
                    server_from_json_mapping(
                        str(name),
                        normalized,
                        source_tool=self.name,
                        source_path=source_path,
                    )
                )
            except DiscoveryError:
                if strict:
                    raise
                continue
        return results

    def render(self, existing_text: str | None, servers: list[McpServer]) -> str:
        data = self._load_for_write(existing_text)
        if self.wrapper_key is None:
            target = data
        else:
            existing = data.get(self.wrapper_key, {})
            target = existing if isinstance(existing, dict) else {}
            data[self.wrapper_key] = target

        for server in servers:
            target[server.name] = server_to_json_mapping(server, target_name=self.name)
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    def remove(self, existing_text: str, server_names: set[str]) -> tuple[str, list[str]]:
        data = self._load_for_write(existing_text)
        target: dict[str, Any]
        if self.wrapper_key is None:
            target = data
        else:
            existing = data.get(self.wrapper_key, {})
            if not isinstance(existing, dict):
                return json.dumps(data, indent=2, ensure_ascii=False) + "\n", []
            target = existing

        removed: list[str] = []
        for name in list(target):
            if name in server_names:
                del target[name]
                removed.append(name)
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n", removed

    def preview(self, existing_text: str | None, servers: list[McpServer]) -> PreviewValue:
        rendered = self.render(existing_text, servers)
        value = json.loads(rendered)
        assert isinstance(value, dict)
        return value

    @staticmethod
    def _load_for_write(existing_text: str | None) -> dict[str, Any]:
        if existing_text is None:
            return {}
        try:
            data = json.loads(existing_text)
        except json.JSONDecodeError as exc:
            raise WritebackError(f"Cannot parse JSON config: {exc}") from exc
        if not isinstance(data, dict):
            raise WritebackError("Config file must contain a JSON object")
        return data
