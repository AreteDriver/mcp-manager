"""Custom exceptions for mcp-manager."""


class McpManagerError(Exception):
    """Base exception for all mcp-manager errors."""


class DiscoveryError(McpManagerError):
    """Config discovery encountered an unrecoverable error."""


class HealthCheckError(McpManagerError):
    """Health check failed unexpectedly."""


class ProtocolError(McpManagerError):
    """MCP protocol communication failed."""


class RegistryError(McpManagerError):
    """Registry operation failed."""


class ExportError(McpManagerError):
    """Config export or import failed."""


class LicenseError(McpManagerError):
    """Feature requires a higher license tier."""


class WritebackError(McpManagerError):
    """Config write-back to IDE files failed."""
