---
sidebar_position: 1
title: "Pre-commit Hooks & CI"
description: "Local pre-commit validation and GitHub Actions CI workflow that gate every PR to the homelab repo"
---

# Pre-commit Hooks & CI

Every PR to the [`homelab` repo](https://github.com/imcbeth/homelab) runs through two layers of automated checks: pre-commit hooks locally and a GitHub Actions workflow on the PR. Both run the **same checks** — the CI is the safety net for contributors who haven't installed pre-commit locally.

## Local pre-commit

### Setup (one-time)

```bash
brew install pre-commit kubeconform kustomize
cd /Users/imcbeth/repos/homelab
pre-commit install   # installs the git hook
```

Without `pre-commit install`, the hooks won't run automatically on `git commit`. You can still invoke them manually:

```bash
pre-commit run --all-files            # full sweep
pre-commit run --files <path> ...     # specific files
pre-commit run kustomize-build        # one specific hook
```

### Hook chain

Configured in [`.pre-commit-config.yaml`](https://github.com/imcbeth/homelab/blob/main/.pre-commit-config.yaml):

| Hook | What it does |
|------|--------------|
| `trailing-whitespace` | Strips trailing whitespace |
| `end-of-file-fixer` | Ensures files end with a newline |
| `check-yaml` | YAML syntax validation (with `--unsafe` to allow K8s custom tags) |
| `check-added-large-files` | Rejects files > 1 MB |
| `check-merge-conflict` | Catches unresolved conflict markers |
| `mixed-line-ending` | Normalises to LF |
| `detect-private-key` | Prevents accidental key commits |
| `yamllint` | Style checks (line length 250, indent 2, sequence consistency) |
| `kubeconform` | Validates K8s manifests against schemas (`scripts/validate-manifests.sh`) |
| `kustomize-build` | Builds every `kustomization.yaml` and validates rendered output (`scripts/validate-kustomizations.sh`) |
| `gitleaks` | Scans for committed secrets |
| `markdownlint` | Markdown style (`--fix` enabled for trivial fixes) |
| `check-todos` | Warns on `TODO`/`FIXME` markers (non-blocking) |

### Exclusions for git-crypt'd files

The repository uses `git-crypt` for encrypted-at-rest files matching:

- `secrets/**`
- `*secret*` (anywhere in path)
- `*.key`
- `*-sealed.yaml`

In CI these files are encrypted binary blobs (no key). Every text-mutating hook **must** exclude them or CI fails — either with `UnicodeDecodeError` (yamllint, markdownlint), `control characters not allowed` (kubeconform), or by silently auto-fixing the blob and exiting with a dirty tree.

The shared exclude regex used across hooks:

```regex
(^secrets/|.*secret.*|.*\.key$|.*-sealed\.ya?ml$)
```

### gitleaks: keep the hook and CI pinned together

Secret scanning runs in two places, and they **must run the same version**:

| Gate | Pin |
|---|---|
| `.pre-commit-config.yaml` | `rev: v8.30.1` |
| `.github/workflows/gitleaks.yml` | `version=8.30.1` |

These drifted once — hook on v8.18.1, CI on v8.30.1 — and disagreed on identical input:
v8.18.1 flags AWS's documented sample access key, which v8.30.1 allowlists. A commit could
pass CI and fail the hook, or the reverse. When bumping one, bump the other.

:::warning The hook and CI see different bytes for git-crypt'd files
This is why the `exclude:` list above matters for gitleaks specifically, not just for
text-mutating hooks.

In **CI** those paths are encrypted binary — the runner has no key, so the scan sees exactly
what a stranger cloning the repo sees. On a **developer machine with git-crypt unlocked**,
git decrypts them on read, so the hook would report plaintext that was never committed. The
exclusion keeps the local hook honest.

If you ever run gitleaks by hand against a full checkout, run `git-crypt lock` first or scan
a fresh keyless clone. An unlocked scan audits your keyring, not your repo — it once produced
68 phantom findings. See [Secrets Management](../security/secrets-management.md).
:::

The CI workflow asserts the checkout is locked before scanning, so that failure mode cannot
recur there:

```yaml
- name: Confirm the checkout is git-crypt LOCKED
  run: |
    f=manifests/base/synology-csi/configs/client-info-secret.yml
    if [ -f "$f" ] && ! head -c 9 "$f" | grep -q 'GITCRYPT'; then
      echo "::error::$f is not git-crypt ciphertext in CI"
      exit 1
    fi
```

:::danger Never put "secret" in a workflow filename
`.gitattributes` applies `*secret* filter=git-crypt`, matched on **basename**. A workflow
named `secret-scan.yml` is committed as encrypted binary; GitHub cannot parse it and the run
fails at startup in 0s with no jobs and no logs, listed by filename instead of its `name:`.

This happened. The file is called `gitleaks.yml` for that reason. The same rule is why sealed
secrets are named `*-sealed.yaml`.
:::

## Kustomize build validation

`scripts/validate-kustomizations.sh` is the most powerful hook — it catches errors the per-file `kubeconform` pass misses:

- Missing resources referenced in `kustomization.yaml`
- Patch targets that don't exist
- Generator/transformer misconfig
- Resources that pass YAML lint but fail when assembled

Behaviour:

1. Find every `kustomization.yaml` under `manifests/`.
2. Run `kustomize build` on each — fails the hook if any build errors.
3. Pipe the rendered output through `kubeconform` with `-ignore-missing-schemas -strict`.
4. Skip kustomizations referencing remote git refs (synology-csi, tigera-operator) by default — they need network and add ~30s each. CI sets `VALIDATE_REMOTE=1` to include them.

```bash
# Validate everything locally (fast)
scripts/validate-kustomizations.sh

# Including remote-ref kustomizations (slow, needs network)
VALIDATE_REMOTE=1 scripts/validate-kustomizations.sh
```

## GitHub Actions CI

Workflow: [`.github/workflows/validate.yml`](https://github.com/imcbeth/homelab/blob/main/.github/workflows/validate.yml).

Triggers on:

- `pull_request` touching `manifests/**`, `scripts/**`, `.pre-commit-config.yaml`, or the workflow file itself
- `push` to `main` with the same path filters

What it does:

1. Checkout
2. `actions/setup-python@v5` with Python 3.12
3. Install `kubeconform` v0.6.7 (binary download)
4. Install `kustomize` v5.4.3 (binary download)
5. `pre-commit/action@v3.0.1` runs the full hook chain with `VALIDATE_REMOTE=1` so remote-ref kustomizations are validated too

### Why a CI workflow when pre-commit is already required

Most contributors install pre-commit. Some don't. A few will use `--no-verify` to push past a hook that's blocking on something unrelated to their change. The CI workflow is **non-bypassable** — it runs on every PR push regardless of what happened locally, and the branch protection rule requires it to pass before merge.

## Common failures

### "hook(s) made changes" in CI

A text-mutating hook auto-fixed something (whitespace, EOF, markdown). Pull the auto-fix locally:

```bash
pre-commit run --all-files
git add -A
git commit -m "fix: pre-commit auto-fixes"
git push
```

### `kubeconform` reports "control characters not allowed"

A git-crypt'd file is being parsed as plain YAML. The hook's `exclude:` regex doesn't cover the file path. Add the path pattern to the exclude.

### `kustomize build` fails with "evalsymlink failure" + `hit Ns timeout`

A kustomization references a remote git ref and the fetch timed out. Either the network is slow (try again) or the upstream ref no longer exists (pin to a valid one). Locally these are skipped unless `VALIDATE_REMOTE=1` is set.

### Push rejected with "refusing to allow an OAuth App to create or update workflow"

The git auth token lacks `workflow` scope. Refresh it:

```bash
gh auth refresh -h github.com -s workflow
```

Default `gh auth login` with `repo` scope can't push `.github/workflows/*.yml` changes.

## Adding a new hook

Edit `.pre-commit-config.yaml`. Use upstream hooks where possible:

```yaml
- repo: https://github.com/<org>/<repo>
  rev: v1.0.0
  hooks:
    - id: <hook-id>
      exclude: '(^secrets/|.*secret.*|.*\.key$|.*-sealed\.ya?ml$)'
      # add other exclusions as needed
```

For repo-local hooks (custom scripts under `scripts/`), use the `local` repo:

```yaml
- repo: local
  hooks:
    - id: my-check
      name: My custom check
      entry: scripts/my-check.sh
      language: system
      files: '^manifests/.*\.ya?ml$'
      pass_filenames: false
```

After editing the config, run `pre-commit autoupdate` to pull the latest pinned versions, then re-run `pre-commit run --all-files` to make sure nothing breaks.
