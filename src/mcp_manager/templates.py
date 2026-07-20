"""Built-in project templates for `mcp-manager template use`."""

from __future__ import annotations

BUILTIN_TEMPLATES: dict[str, str] = {
    "python": """# Python-focused MCP project template
project: {project}

servers:
  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem"]
    env: {{}}
    tags: [core, filesystem]

  git:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-git"]
    env: {{}}
    tags: [core, vcs]
""",
    "node": """# Node.js-focused MCP project template
project: {project}

servers:
  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem"]
    env: {{}}
    tags: [core, filesystem]

  git:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-git"]
    env: {{}}
    tags: [core, vcs]
""",
    "data": """# Data engineering MCP project template
project: {project}

servers:
  postgres:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-postgres"]
    env:
      DATABASE_URL: ${DATABASE_URL}
    tags: [backend, database]

  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem"]
    env: {{}}
    tags: [core, filesystem]

  git:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-git"]
    env: {{}}
    tags: [core, vcs]
""",
    "ai": """# AI tooling MCP project template
project: {project}

servers:
  web-search:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-brave-search"]
    env:
      BRAVE_API_KEY: ${{BRAVE_API_KEY}}
    tags: [ai, search]

  playwright:
    command: npx
    args: ["-y", "@anthropic-ai/playwright-mcp"]
    env: {{}}
    tags: [ai, browser]
""",
}


def list_templates() -> list[str]:
    """Return sorted list of built-in template names."""
    return sorted(BUILTIN_TEMPLATES.keys())


def get_template(name: str, project_name: str = "my-project") -> str:
    """Return the YAML text for a built-in template.

    Args:
        name: Template name (python, node, data, ai).
        project_name: Project name to substitute into the template.

    Returns:
        YAML string ready to write to .mcp-manager.yml.

    Raises:
        KeyError: If template name is unknown.
    """
    template = BUILTIN_TEMPLATES[name]
    return template.format(project=project_name)


def get_template_description(name: str) -> str:
    """Return a one-line description for a template."""
    descriptions: dict[str, str] = {
        "python": "Local Python servers with filesystem + git (mypy + ruff CI gate)",
        "node": "npx-based servers with filesystem + git (npm audit CI gate)",
        "data": "Database + filesystem + git servers for data engineering workflows",
        "ai": "AI tool servers: web search, browser automation",
    }
    return descriptions.get(name, "No description available")
