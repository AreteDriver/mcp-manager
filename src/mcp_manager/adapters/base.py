"""Adapter contracts for MCP client configuration dialects."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from mcp_manager.exceptions import WritebackError
from mcp_manager.models import McpServer

ConfigScope = Literal["user", "project"]
PreviewValue = dict[str, Any] | str


@dataclass(frozen=True)
class TargetCapabilities:
    """Configuration features supported by a target client."""

    format: Literal["json", "toml"]
    transports: tuple[str, ...] = ("stdio", "http", "sse")
    project_scope: bool = False
    oauth: bool = False
    codex_auth_translation: bool = False
    tool_policy: bool = False
    approval_policy: bool = False
    server_controls: bool = False
    environment_passthrough: bool = False
    environment_headers: bool = False
    timeouts: bool = False


class TargetAdapter(ABC):
    """Translate one client configuration dialect to and from ``McpServer``."""

    def __init__(
        self,
        *,
        name: str,
        user_path: Path,
        capabilities: TargetCapabilities,
        project_path: Path | None = None,
    ) -> None:
        self.name = name
        self.user_path = user_path.expanduser()
        self.project_path = project_path
        self.capabilities = capabilities

    def resolve_path(
        self,
        *,
        scope: ConfigScope = "user",
        project_dir: Path | None = None,
    ) -> Path:
        """Resolve a user- or project-scoped configuration path."""
        if scope == "user":
            return self.user_path
        if self.project_path is None:
            raise WritebackError(f"Target {self.name!r} does not support project-scoped config")
        root = (project_dir or Path.cwd()).resolve()
        return root / self.project_path

    def validate_servers(self, servers: list[McpServer]) -> None:
        """Reject translations that would change the transport semantics."""
        unsupported = sorted(
            {
                server.transport.value
                for server in servers
                if server.transport.value not in self.capabilities.transports
            }
        )
        if unsupported:
            raise WritebackError(
                f"Target {self.name!r} does not support transport(s): " + ", ".join(unsupported)
            )

    def translation_warnings(self, servers: list[McpServer]) -> list[str]:
        """Describe policy fields that the target cannot represent exactly."""
        warnings: list[str] = []
        if not self.capabilities.tool_policy and any(
            server.enabled_tools or server.disabled_tools for server in servers
        ):
            warnings.append("tool allow/deny lists are not supported and will be omitted")
        if not self.capabilities.approval_policy and any(
            server.default_tools_approval_mode or server.tool_approval_modes for server in servers
        ):
            warnings.append("tool approval policies are not supported and will be omitted")
        if not self.capabilities.codex_auth_translation and any(
            server.network_config
            and (server.network_config.auth or server.network_config.bearer_token_env_var)
            for server in servers
        ):
            warnings.append("Codex-style OAuth settings are not supported and will be omitted")
        if not self.capabilities.server_controls and any(
            server.enabled is not None or server.required is not None for server in servers
        ):
            warnings.append(
                "enabled/required server controls are not supported and will be omitted"
            )
        if not self.capabilities.environment_passthrough and any(
            server.stdio_config and server.stdio_config.env_vars for server in servers
        ):
            warnings.append(
                "inherited environment-variable references are not supported and will be omitted"
            )
        if not self.capabilities.environment_headers and any(
            server.network_config and server.network_config.env_headers for server in servers
        ):
            warnings.append("environment-backed HTTP headers are not supported and will be omitted")
        if not self.capabilities.timeouts and any(
            server.startup_timeout_sec is not None or server.tool_timeout_sec is not None
            for server in servers
        ):
            warnings.append("server timeout settings are not supported and will be omitted")
        foreign_extensions = sorted(
            {
                source
                for server in servers
                for source, fields in server.extensions.items()
                if source != self.name and fields
            }
        )
        if foreign_extensions:
            warnings.append(
                "target-specific extension fields from "
                + ", ".join(foreign_extensions)
                + " may be omitted"
            )
        return warnings

    @abstractmethod
    def parse(
        self,
        text: str,
        *,
        source_path: Path,
        strict: bool = False,
    ) -> list[McpServer]:
        """Parse target-native configuration text."""

    @abstractmethod
    def render(self, existing_text: str | None, servers: list[McpServer]) -> str:
        """Merge servers and return target-native configuration text."""

    @abstractmethod
    def remove(self, existing_text: str, server_names: set[str]) -> tuple[str, list[str]]:
        """Remove named servers and return new text plus removed names."""

    @abstractmethod
    def preview(self, existing_text: str | None, servers: list[McpServer]) -> PreviewValue:
        """Return a human-readable native preview."""
