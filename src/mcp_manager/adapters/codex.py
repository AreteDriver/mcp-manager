"""Codex CLI and desktop MCP configuration adapter."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.items import Table

from mcp_manager.adapters.base import PreviewValue, TargetAdapter, TargetCapabilities
from mcp_manager.exceptions import DiscoveryError, WritebackError
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType

_SERVER_KEYS = {
    "command",
    "args",
    "env",
    "env_vars",
    "cwd",
    "url",
    "auth",
    "bearer_token_env_var",
    "http_headers",
    "env_http_headers",
    "enabled",
    "required",
    "enabled_tools",
    "disabled_tools",
    "default_tools_approval_mode",
    "startup_timeout_sec",
    "tool_timeout_sec",
    "tools",
}


class CodexTargetAdapter(TargetAdapter):
    """Read and write Codex's ``[mcp_servers.<name>]`` TOML dialect."""

    def __init__(self, *, user_path: Path, project_path: Path | None = None) -> None:
        super().__init__(
            name="codex",
            user_path=user_path,
            project_path=project_path,
            capabilities=TargetCapabilities(
                format="toml",
                transports=("stdio", "http"),
                project_scope=project_path is not None,
                oauth=True,
                codex_auth_translation=True,
                tool_policy=True,
                approval_policy=True,
                server_controls=True,
                environment_passthrough=True,
                environment_headers=True,
                timeouts=True,
            ),
        )

    def parse(
        self,
        text: str,
        *,
        source_path: Path,
        strict: bool = False,
    ) -> list[McpServer]:
        try:
            document = tomlkit.parse(text)
        except Exception as exc:
            raise DiscoveryError(f"Cannot parse {source_path}: {exc}") from exc

        table = document.get("mcp_servers", {})
        if not isinstance(table, Mapping):
            raise DiscoveryError(f"mcp_servers in {source_path} must be a TOML table")

        results: list[McpServer] = []
        for name, raw_config in table.items():
            if not isinstance(raw_config, Mapping):
                continue
            config = _unwrap(raw_config)
            try:
                results.append(self._build_server(str(name), config, source_path))
            except DiscoveryError:
                if strict:
                    raise
                continue
        return results

    def _build_server(self, name: str, config: dict[str, Any], source_path: Path) -> McpServer:
        if config.get("command") and config.get("url"):
            raise DiscoveryError(f"Codex server {name!r} cannot define both command and url")
        extras = {key: value for key, value in config.items() if key not in _SERVER_KEYS}
        enabled = _optional_bool(config.get("enabled"), field="enabled")
        required = _optional_bool(config.get("required"), field="required")
        enabled_tools = _string_list(config.get("enabled_tools", []), field="enabled_tools")
        disabled_tools = _string_list(config.get("disabled_tools", []), field="disabled_tools")
        approval_mode = _approval_mode(config.get("default_tools_approval_mode"))
        tool_approval_modes = _tool_approval_modes(config.get("tools", {}))
        startup_timeout = _optional_float(
            config.get("startup_timeout_sec"),
            field="startup_timeout_sec",
        )
        tool_timeout = _optional_float(
            config.get("tool_timeout_sec"),
            field="tool_timeout_sec",
        )

        command = config.get("command")
        if command:
            env_vars_raw = config.get("env_vars", [])
            env_vars: list[str | dict[str, str]] = []
            if isinstance(env_vars_raw, list):
                for value in env_vars_raw:
                    if isinstance(value, str):
                        env_vars.append(value)
                    elif isinstance(value, Mapping):
                        env_vars.append({str(key): str(item) for key, item in value.items()})
            return McpServer(
                name=name,
                transport=TransportType.STDIO,
                stdio_config=StdioConfig(
                    command=str(command),
                    args=_string_list(config.get("args", []), field="args"),
                    env=_string_dict(config.get("env", {})),
                    cwd=_optional_str(config.get("cwd")),
                    env_vars=env_vars,
                ),
                source_tool=self.name,
                source_path=source_path,
                enabled=enabled,
                required=required,
                enabled_tools=enabled_tools,
                disabled_tools=disabled_tools,
                default_tools_approval_mode=approval_mode,
                tool_approval_modes=tool_approval_modes,
                startup_timeout_sec=startup_timeout,
                tool_timeout_sec=tool_timeout,
                extensions={"codex": extras},
            )

        url = config.get("url")
        if not url:
            raise DiscoveryError(f"Codex server {name!r} has neither command nor url")
        return McpServer(
            name=name,
            transport=TransportType.HTTP,
            network_config=NetworkConfig(
                type="http",
                url=str(url),
                headers=_string_dict(config.get("http_headers", {})),
                env_headers=_string_dict(config.get("env_http_headers", {})),
                bearer_token_env_var=_optional_str(config.get("bearer_token_env_var")),
                auth=_optional_choice(
                    config.get("auth"), field="auth", values={"oauth", "chatgpt"}
                ),
            ),
            source_tool=self.name,
            source_path=source_path,
            enabled=enabled,
            required=required,
            enabled_tools=enabled_tools,
            disabled_tools=disabled_tools,
            default_tools_approval_mode=approval_mode,
            tool_approval_modes=tool_approval_modes,
            startup_timeout_sec=startup_timeout,
            tool_timeout_sec=tool_timeout,
            extensions={"codex": extras},
        )

    def render(self, existing_text: str | None, servers: list[McpServer]) -> str:
        document = self._load_for_write(existing_text)
        mcp_servers = document.get("mcp_servers")
        if not isinstance(mcp_servers, Table):
            mcp_servers = tomlkit.table()
            document["mcp_servers"] = mcp_servers

        for server in servers:
            existing = mcp_servers.get(server.name)
            section = existing if isinstance(existing, Table) else tomlkit.table()
            for key in _SERVER_KEYS:
                section.pop(key, None)
            for key, value in _server_to_codex_mapping(server).items():
                section[key] = value
            mcp_servers[server.name] = section
        return tomlkit.dumps(document)

    def remove(self, existing_text: str, server_names: set[str]) -> tuple[str, list[str]]:
        document = self._load_for_write(existing_text)
        mcp_servers = document.get("mcp_servers")
        if not isinstance(mcp_servers, Table):
            return tomlkit.dumps(document), []
        removed: list[str] = []
        for name in list(mcp_servers):
            if name in server_names:
                del mcp_servers[name]
                removed.append(name)
        return tomlkit.dumps(document), removed

    def preview(self, existing_text: str | None, servers: list[McpServer]) -> PreviewValue:
        return self.render(existing_text, servers)

    @staticmethod
    def _load_for_write(existing_text: str | None) -> tomlkit.TOMLDocument:
        if existing_text is None:
            return tomlkit.document()
        try:
            return tomlkit.parse(existing_text)
        except Exception as exc:
            raise WritebackError(f"Cannot parse TOML config: {exc}") from exc


def _server_to_codex_mapping(server: McpServer) -> dict[str, Any]:
    extras = server.extensions.get("codex", {})
    result = dict(extras) if isinstance(extras, dict) else {}

    if server.transport == TransportType.STDIO and server.stdio_config:
        result["command"] = server.stdio_config.command
        if server.stdio_config.args:
            result["args"] = server.stdio_config.args
        if server.stdio_config.env:
            result["env"] = server.stdio_config.env
        if server.stdio_config.env_vars:
            result["env_vars"] = server.stdio_config.env_vars
        if server.stdio_config.cwd:
            result["cwd"] = server.stdio_config.cwd
    elif server.network_config:
        result["url"] = server.network_config.url
        if server.network_config.auth:
            result["auth"] = server.network_config.auth
        if server.network_config.bearer_token_env_var:
            result["bearer_token_env_var"] = server.network_config.bearer_token_env_var
        if server.network_config.headers:
            result["http_headers"] = server.network_config.headers
        if server.network_config.env_headers:
            result["env_http_headers"] = server.network_config.env_headers
    else:
        raise WritebackError(f"Server {server.name!r} has no valid transport config")

    if server.enabled is not None:
        result["enabled"] = server.enabled
    if server.required is not None:
        result["required"] = server.required
    if server.enabled_tools:
        result["enabled_tools"] = server.enabled_tools
    if server.disabled_tools:
        result["disabled_tools"] = server.disabled_tools
    if server.default_tools_approval_mode:
        result["default_tools_approval_mode"] = server.default_tools_approval_mode
    if server.tool_approval_modes:
        result["tools"] = {
            name: {"approval_mode": mode}
            for name, mode in sorted(server.tool_approval_modes.items())
        }
    if server.startup_timeout_sec is not None:
        result["startup_timeout_sec"] = server.startup_timeout_sec
    if server.tool_timeout_sec is not None:
        result["tool_timeout_sec"] = server.tool_timeout_sec
    return result


def _unwrap(value: Any) -> dict[str, Any]:
    unwrapped = value.unwrap() if hasattr(value, "unwrap") else value
    return dict(unwrapped) if isinstance(unwrapped, Mapping) else {}


def _string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise DiscoveryError(f"Codex field {field!r} must be an array")
    return [str(item) for item in value]


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_bool(value: Any, *, field: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise DiscoveryError(f"Codex field {field!r} must be a boolean")
    return value


def _optional_float(value: Any, *, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        raise DiscoveryError(f"Codex field {field!r} must be a positive number")
    return float(value)


def _approval_mode(value: Any) -> str | None:
    return _optional_choice(
        value,
        field="default_tools_approval_mode",
        values={"auto", "prompt", "writes", "approve"},
    )


def _optional_choice(value: Any, *, field: str, values: set[str]) -> str | None:
    if value is None:
        return None
    choice = str(value)
    if choice not in values:
        raise DiscoveryError(f"Codex field {field!r} must be one of: {', '.join(sorted(values))}")
    return choice


def _tool_approval_modes(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    modes: dict[str, str] = {}
    for tool_name, config in value.items():
        if isinstance(config, Mapping) and config.get("approval_mode") is not None:
            mode = _optional_choice(
                config["approval_mode"],
                field=f"tools.{tool_name}.approval_mode",
                values={"auto", "prompt", "writes", "approve"},
            )
            assert mode is not None
            modes[str(tool_name)] = mode
    return modes
