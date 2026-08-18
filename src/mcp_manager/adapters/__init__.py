"""Target-specific MCP client configuration adapters."""

from mcp_manager.adapters.base import ConfigScope, TargetAdapter, TargetCapabilities
from mcp_manager.adapters.registry import build_target_adapters

__all__ = [
    "ConfigScope",
    "TargetAdapter",
    "TargetCapabilities",
    "build_target_adapters",
]
