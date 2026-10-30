# Repository-renaming checklist

This release changes the product brand to **Arete MCP** while keeping the
GitHub repository named `AreteDriver/mcp-manager`. Repository renaming is a
separate, explicitly authorized operation and is not part of this PR.

Before renaming the repository, verify each item independently:

- [ ] Confirm the desired new repository name and owner with the maintainer.
- [ ] Inventory and update repository URLs in PyPI metadata, documentation,
      badges, GitHub Actions, Marketplace listings, and external references.
- [ ] Preserve or configure a redirect from the old repository URL.
- [ ] Update Git remotes for maintainers, CI, release tooling, and automation.
- [ ] Review GitHub Action references (`AreteDriver/mcp-manager@v1`) and decide
      whether the old action path remains supported.
- [ ] Check branch protection, environments, secrets, deploy keys, webhooks,
      Apps, CODEOWNERS, and Pages settings after the rename.
- [ ] Verify release, Marketplace, documentation, and package smoke tests
      against the renamed repository before publishing a release.
- [ ] Announce the repository URL change and document the compatibility window.
