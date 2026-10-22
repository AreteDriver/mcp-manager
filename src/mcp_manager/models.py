"""Pydantic v2 models for all mcp-manager data structures."""

from __future__ import annotations

import time
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TransportType(StrEnum):
    """MCP server transport types."""

    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


class ServerStatus(StrEnum):
    """Health check result statuses."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Transport configs
# ---------------------------------------------------------------------------


class StdioConfig(BaseModel):
    """Configuration for a stdio-based MCP server."""

    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None
    env_vars: list[str | dict[str, str]] = Field(default_factory=list)


class NetworkConfig(BaseModel):
    """Configuration for SSE or HTTP MCP servers."""

    type: Literal["sse", "http"]
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    env_headers: dict[str, str] = Field(default_factory=dict)
    bearer_token_env_var: str | None = None
    auth: str | None = None


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------


class McpServer(BaseModel):
    """A single MCP server with its configuration and discovery metadata."""

    name: str
    transport: TransportType

    # Exactly one of these is populated, depending on transport.
    stdio_config: StdioConfig | None = None
    network_config: NetworkConfig | None = None

    # Where this server was discovered.
    source_tool: str = ""
    source_path: Path | None = None

    # User metadata.
    tags: list[str] = Field(default_factory=list)
    description: str = ""

    # Cross-client policy fields. Targets may support only a subset; adapters
    # expose capabilities so lossy translations can be reported explicitly.
    enabled: bool | None = None
    required: bool | None = None
    enabled_tools: list[str] = Field(default_factory=list)
    disabled_tools: list[str] = Field(default_factory=list)
    default_tools_approval_mode: str | None = None
    tool_approval_modes: dict[str, str] = Field(default_factory=dict)
    startup_timeout_sec: float | None = None
    tool_timeout_sec: float | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)


class HealthResult(BaseModel):
    """Result of a single server health check."""

    server_name: str
    status: ServerStatus
    latency_ms: float | None = None
    transport: TransportType
    protocol_version: str | None = None
    server_info: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    checked_at: float = Field(default_factory=time.time)


class ProtocolProbeResult(BaseModel):
    """Result of a dual-era MCP compatibility probe."""

    server_name: str
    transport: TransportType
    protocol_era: Literal["modern", "legacy"]
    protocol_version: str
    latency_ms: float
    server_info: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)
    list_ttl_ms: int | None = None
    list_cache_scope: Literal["public", "private"] | None = None
    cached_repeat_identical: bool = False
    tool_call_result: dict[str, Any] | None = None


class ServerMapping(BaseModel):
    """Mapping of a server to the IDEs/tools that reference it."""

    server_name: str
    transport: TransportType
    tools: list[str]
    config_paths: list[str]


class RegistryEntry(BaseModel):
    """A server entry in the mcp-manager persistent registry."""

    server: McpServer
    added_at: float = Field(default_factory=time.time)
    last_health: HealthResult | None = None


class ExportConfig(BaseModel):
    """Portable MCP configuration for export/import."""

    version: str = "1"
    servers: dict[str, dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)
