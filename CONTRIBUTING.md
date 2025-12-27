# Contributing to k8s-docs-n37

Thank you for contributing to the Kubernetes homelab documentation!

## Prerequisites

- Node.js v20.x or later
- npm
- Python 3.x (for pre-commit hooks)
- Git

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/imcbeth/k8s-docs-n37.git
cd k8s-docs-n37
```

### 2. Install Dependencies

```bash
npm install
```

### 3. Install Pre-commit Hooks

We use pre-commit hooks to ensure code quality and catch errors before they reach CI/CD.

**Install pre-commit:**
```bash
# macOS
brew install pre-commit

# OR using pip
pip install pre-commit
```

**Install the hooks:**
```bash
pre-commit install
```

**Test the hooks:**
```bash
pre-commit run --all-files
```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b docs/update-something
# or
git checkout -b fix/fix-broken-thing
```

### 2. Make Your Changes

Edit documentation files in the `docs/` directory.

### 3. Test Locally

```bash
# Start local development server
npm start

# Open http://localhost:3000 in your browser
```

### 4. Build and Verify

```bash
# Build the site (catches broken links)
npm run build

# Serve the built site
npm run serve
```

### 5. Commit Your Changes

Pre-commit hooks will automatically run when you commit:

```bash
git add .
git commit -m "docs: Your commit message"
```

**What the hooks check:**
- ✅ YAML syntax validation
- ✅ Markdown linting
- ✅ Docusaurus build (catches broken links!)
- ✅ Trailing whitespace removal
- ✅ File ending fixes

**If hooks fail:**
- Fix the reported issues
- Stage the fixes: `git add .`
- Retry the commit: `git commit -m "..."`

### 6. Push and Create PR

```bash
git push -u origin feature/your-feature-name
gh pr create --title "..." --body "..."
```

## Commit Message Format

Use conventional commits:

```
<type>: <description>

[optional body]

[optional footer]
```

**Types:**
- `docs:` - Documentation changes
- `fix:` - Bug fixes
- `feat:` - New features
- `chore:` - Maintenance tasks

**Examples:**
```
docs: Add troubleshooting guide for cert-manager
fix: Correct broken link in metallb documentation
feat: Add new application guide for Velero
```

## Pre-commit Hook Details

### Hooks Configured

1. **Trailing Whitespace** - Removes trailing spaces
2. **End of File Fixer** - Ensures files end with newline
3. **YAML Syntax Check** - Validates YAML frontmatter
4. **Large File Check** - Prevents files > 1MB
5. **Merge Conflict Check** - Detects unresolved conflicts
6. **Markdown Linting** - Enforces markdown style
7. **Docusaurus Build** - **Catches broken links before push!**
8. **YAML Linting** - Advanced YAML validation

### Bypassing Hooks (Not Recommended)

If you absolutely must bypass hooks:

```bash
git commit --no-verify -m "message"
```

**⚠️ Warning:** Only use this for emergencies. Bypassing hooks will bypass critical checks and can cause broken links and failed CI builds.

### Updating Hooks

```bash
pre-commit autoupdate
```

## Troubleshooting

### Pre-commit Hook Fails

**Problem:** Docusaurus build hook fails

**Solution:**
```bash
# Run build manually to see detailed error
npm run build

# Common issues:
# - Broken links: Fix the link or remove it
# - Missing files: Add the referenced file
# - Invalid frontmatter: Check YAML syntax
```

**Problem:** Markdown linting fails

**Solution:**
```bash
# Run markdownlint manually
npx markdownlint-cli docs/**/*.md

# Auto-fix issues
npx markdownlint-cli --fix docs/**/*.md
```

### Node Modules Issues

```bash
# Clean install
rm -rf node_modules package-lock.json
npm install
```

### Pre-commit Not Running

```bash
# Reinstall hooks
pre-commit uninstall
pre-commit install

# Verify installation
pre-commit --version
```

## Documentation Structure

```
docs/
├── intro.md                    # Landing page
├── getting-started/            # Setup guides
├── kubernetes/                 # K8s installation
├── applications/               # Application guides
│   ├── argocd.md
│   ├── cert-manager.md
│   ├── loki.md
│   └── ...
├── monitoring/                 # Monitoring stack
├── storage/                    # Storage guides
├── security/                   # Security docs
└── troubleshooting/           # Common issues
```

## Style Guide

### Markdown

- Use ATX-style headers (`#` not `===`)
- One sentence per line (easier diffs)
- Use fenced code blocks with language specifiers
- Add alt text to images
- Use relative links for internal references

### YAML Frontmatter

All docs should have frontmatter:

```yaml
---
sidebar_position: 1
title: "Page Title"
description: "Brief description for SEO"
---
```

### Code Blocks

Always specify language:

```yaml
# Good
```yaml
apiVersion: v1
kind: Pod
\```

# Bad
\```
apiVersion: v1
kind: Pod
\```
```

## Questions?

- Open an issue: https://github.com/imcbeth/k8s-docs-n37/issues
- Check existing docs: http://localhost:3000 (when running locally)

---

**Happy documenting! 📝**
