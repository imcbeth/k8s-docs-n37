# k8s-docs-n37 — Claude Instructions

## What This Repo Is

Docusaurus documentation site for the homelab Kubernetes cluster. Mirrors the deployed state of the homelab repo (`~/homelab`). Every significant homelab change should be reflected here.

## Repository Structure

```
docs/
  applications/   # Per-application guides (one .md per app)
  monitoring/     # Monitoring stack docs
  security/       # Security and policy docs
sidebars.ts       # Docusaurus sidebar navigation (update when adding new guides)
```

## Active Branch

`docs/april-2026-updates` — long-running feature branch for all 2026 updates. **Always work on this branch**, not `main` directly.

PR: `github.com/imcbeth/k8s-docs-n37/pull/78`

## Key Rules

### Pre-Commit Hooks

Every commit runs a **Docusaurus production build**. The commit will be rejected if the build fails. This catches broken links, invalid frontmatter, and syntax errors. Fix build errors before committing.

### Adding a New Application Guide

1. Create `docs/applications/<appname>.md` with frontmatter:

   ```md
   ---
   title: "App Name"
   description: "One-line description"
   ---
   ```

2. Add the doc ID to `sidebars.ts` under the Applications section — without this the page won't appear in the nav.

### Conflict Resolution

Use `git rebase origin/main` (not merge) when conflicts arise, then `git push --force-with-lease`. No confirmation needed before the force-push.

### Copilot Review Comments

To fetch all Copilot comments on a PR:

```bash
gh api repos/imcbeth/k8s-docs-n37/pulls/<NNN>/comments \
  --jq '.[] | {path, line, body}'
gh api repos/imcbeth/k8s-docs-n37/pulls/<NNN>/reviews \
  --jq '.[] | {state, body, user: .user.login}'
```

Fix all actionable items and commit. If a comment reflects a misunderstanding, explain in a PR reply.

## Doc Update Checklist

When updating an application guide after a homelab change:

- [ ] Version numbers (chart version, app version, image tag)
- [ ] Overview table (namespace, chart, image, ArgoCD app, wave)
- [ ] Any new gotchas or operational notes discovered
- [ ] Resource usage table if limits changed
- [ ] Last Updated date at bottom of file
- [ ] Cross-links to related guides if new integrations were added

## Companion Repo

The homelab infrastructure lives at `~/homelab`. Use cluster state (via MCP tools) to validate documentation accuracy before committing — don't document what you think is true, verify it.
