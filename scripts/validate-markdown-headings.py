#!/usr/bin/env python3
"""Stop `markdownlint --fix` from turning prose into H1 headings.

WHY THIS EXISTS
---------------
Docs here reference pull requests and issues constantly, and line wrapping
regularly pushes one to the start of a line:

    ... the grouped "argocd ecosystem" PR
    #955 still proposed 10.8.4.

In CommonMark that is prose: an ATX heading needs a space after the `#`, so
`#955` is literal text and renders correctly.

**The problem is our own pre-commit hook.** `markdownlint` runs with `--fix`,
and MD018 (no-missing-space-atx) "helpfully" rewrites the line:

    #955 still proposed 10.8.4.      ->      # 955 still proposed 10.8.4.

which IS a heading. The hook does not fail; it silently edits the file and
passes. The sentence then appears on the rendered page as an H1 reading
"955 still proposed 10.8.4."

In the homelab repo this happened three times before the mechanism was
understood. Each time it was read as "I accidentally wrote a heading", and
each time the fix was to reword the sentence - treating the symptom. The hook
was the cause.

THE TWO-PART FIX
----------------
1. MD018 is disabled, so `--fix` stops rewriting these lines.
2. This script, which:
     a. flags line-initial `#` followed by a non-space, so the pattern is
        surfaced loudly rather than silently rewritten; and
     b. asserts MD018 is *still* disabled, so the protection cannot be
        removed without failing the check.

(b) is the part that matters. Without it, anyone tidying the lint config
reintroduces a silent file-mangler, and the next person spends an afternoon
wondering why their page grew a heading.

PORTED FROM homelab, WITH ONE DIFFERENCE
----------------------------------------
That repo disables MD018 through CLI args on the markdownlint hook. This repo
keeps its rules in `.markdownlint.json`. Both are legitimate, so the guard
accepts **either**, and only fails when `--fix` is in play and MD018 is
disabled in neither place.

NOT A STYLE RULE. Real headings (`# Heading`, `## Heading`) are untouched;
only `#` immediately followed by a non-space, outside code fences, is flagged.
The fix is to rewrap the sentence so the reference is not line-initial -
"PR #955 ..." - or to escape the hash.
"""

from __future__ import annotations

import json
import os
import re
import sys

PRECOMMIT_CONFIG = ".pre-commit-config.yaml"
MARKDOWNLINT_CONFIG = ".markdownlint.json"
RULE = "MD018"

# A line that begins with one or more '#' followed immediately by something
# that is neither whitespace nor another '#'. `# Heading` and `## Heading`
# are fine; `#955` and `#1026` are not.
SUSPECT = re.compile(r"^#+[^#\s]")
FENCE = re.compile(r"^\s*(```|~~~)")


def check_markdown(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return []  # binary or unreadable; not ours to judge

    failures = []
    in_fence = False
    for num, line in enumerate(text.split("\n"), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if SUSPECT.match(line):
            # Tailor the advice. A bare "#123" is almost always a PR or issue
            # reference pushed to the line start by wrapping; anything else
            # (a run of social hashtags, say) needs escaping instead, and
            # suggesting "PR #Kubernetes" would be nonsense.
            if re.match(r"^#\d", line):
                advice = "Rewrap so the reference is not line-initial, or write 'PR #<n>'."
            else:
                advice = "Rewrap, or escape the leading hash as '\\#'."
            failures.append(
                f"{path}:{num}: line starts with '#' and no space\n"
                f"    {line[:88]}\n"
                f"    markdownlint --fix would rewrite this into a heading.\n"
                f"    {advice}"
            )
    return failures


# --------------------------------------------------------------------------
# Config guard — MD018 must stay disabled somewhere, or --fix mangles prose.
# --------------------------------------------------------------------------

def _md018_disabled_in_markdownlint_config(path: str = MARKDOWNLINT_CONFIG) -> bool:
    """True when .markdownlint.json explicitly switches MD018 off."""
    try:
        with open(path, encoding="utf-8") as fh:
            config = json.load(fh)
    except (OSError, ValueError):
        return False
    if not isinstance(config, dict):
        return False
    # markdownlint accepts the rule name or its alias.
    for key in (RULE, "no-missing-space-atx"):
        if config.get(key) is False:
            return True
    return False


def _markdownlint_hook_args(path: str = PRECOMMIT_CONFIG):
    """Return the markdownlint hook's args, or None when there is no such hook."""
    try:
        import yaml
    except ImportError:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return None
    for repo in (config or {}).get("repos", []):
        for hook in repo.get("hooks", []):
            if "markdownlint" in (hook.get("id") or ""):
                return hook.get("args") or []
    return None


def check_hook_config(
    precommit: str = PRECOMMIT_CONFIG, mdconfig: str = MARKDOWNLINT_CONFIG
) -> list[str]:
    args = _markdownlint_hook_args(precommit)

    if args is None:
        # Either PyYAML is missing or there is no markdownlint hook. If the
        # rule is switched off in the lint config we are safe regardless, so
        # only complain when it is not.
        if _md018_disabled_in_markdownlint_config(mdconfig):
            return []
        if not os.path.exists(precommit):
            return []
        return [
            f"{precommit}: cannot confirm {RULE} is disabled (no markdownlint hook "
            f"found, or PyYAML unavailable) and {mdconfig} does not disable it either."
        ]

    if "--fix" not in args:
        return []  # nothing rewrites files, so nothing to protect against

    if RULE in args or _md018_disabled_in_markdownlint_config(mdconfig):
        return []

    return [
        f"{precommit}: the markdownlint hook runs --fix without disabling {RULE}, "
        f"and {mdconfig} does not disable it either.\n"
        f"    {RULE}'s autofix rewrites '#955 text' into '# 955 text', turning a\n"
        f"    sentence into an H1. It edits the file and still passes.\n"
        f'    Add "{RULE}": false to {mdconfig} (preferred here), or add {RULE}\n'
        f"    to the hook's --disable list."
    ]


# --------------------------------------------------------------------------
# Self-test. Fixtures assert the check CAN fail, so a regression to
# "always passes" is caught here rather than on a rendered page.
# --------------------------------------------------------------------------

def self_test() -> int:
    import tempfile

    failures: list[str] = []

    def check(label, cond, detail=""):
        try:
            ok = cond() if callable(cond) else cond
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {label} (raised {type(exc).__name__}: {exc})")
            failures.append(label)
            return
        print(("  PASS  " if ok else "  FAIL  ") + label + ("" if ok else f"  {detail}"))
        if not ok:
            failures.append(label)

    def run(content):
        fd, path = tempfile.mkstemp(suffix=".md")
        os.write(fd, content.encode())
        os.close(fd)
        try:
            return check_markdown(path)
        finally:
            os.unlink(path)

    def tmp(name, body):
        d = tempfile.mkdtemp()
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
        return p

    # --- the real-world case, and the regression that must fail ---
    check("flags a line-initial PR reference",
          lambda: len(run("text wrapping to\n#955 still proposed 10.8.4.\n")) == 1)
    check("flags a multi-hash case", lambda: len(run("##1026 was merged\n")) == 1)

    # --- real headings must NOT be flagged ---
    check("a real H1 is not flagged", lambda: run("# Heading\n") == [])
    check("a real H3 is not flagged", lambda: run("### Heading\n") == [])
    check("a setext-ish line is not flagged", lambda: run("Heading\n=======\n") == [])
    check("an HTTP status heading is not flagged", lambda: run("### 404 Not Found\n") == [])

    # --- code fences are prose-exempt: shell comments start with '#' ---
    check("'#!/bin/bash' inside a fence is not flagged",
          lambda: run("```bash\n#!/bin/bash\n#comment\n```\n") == [])
    check("tilde fences are honoured", lambda: run("~~~\n#1026\n~~~\n") == [])
    check("a violation AFTER a closed fence is still caught",
          lambda: len(run("```\n#ok\n```\n#1026 bad\n")) == 1)

    # --- config guard: both disabling mechanisms, and the unsafe case ---
    pc_fix = tmp("pc.yaml",
                 "repos:\n  - repo: https://x\n    rev: v1\n    hooks:\n"
                 "      - id: markdownlint\n        args: ['--fix']\n")
    pc_fix_disabled = tmp("pc.yaml",
                          "repos:\n  - repo: https://x\n    rev: v1\n    hooks:\n"
                          "      - id: markdownlint\n        args: ['--fix', '--disable', 'MD018']\n")
    pc_nofix = tmp("pc.yaml",
                   "repos:\n  - repo: https://x\n    rev: v1\n    hooks:\n"
                   "      - id: markdownlint\n        args: []\n")
    md_off = tmp("ml.json", '{"default": true, "MD018": false}')
    md_alias_off = tmp("ml.json", '{"default": true, "no-missing-space-atx": false}')
    md_on = tmp("ml.json", '{"default": true}')

    check("UNSAFE: --fix, rule enabled in both places -> fails",
          lambda: len(check_hook_config(pc_fix, md_on)) == 1)
    check("safe: disabled in .markdownlint.json",
          lambda: check_hook_config(pc_fix, md_off) == [])
    check("safe: disabled by its alias in .markdownlint.json",
          lambda: check_hook_config(pc_fix, md_alias_off) == [])
    check("safe: disabled via hook args",
          lambda: check_hook_config(pc_fix_disabled, md_on) == [])
    check("safe: no --fix at all, so nothing rewrites files",
          lambda: check_hook_config(pc_nofix, md_on) == [])

    # --- and the live repo must itself be configured safely ---
    cfg = check_hook_config()
    check("this repo is configured safely", cfg == [], f"got {cfg}")

    print()
    if failures:
        print(f"SELF-TEST FAILED: {len(failures)}: {', '.join(failures)}")
        return 1
    print("SELF-TEST PASSED")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()

    paths = [a for a in argv[1:] if not a.startswith("-")]
    failures: list[str] = []
    for path in paths:
        if path.endswith(".md"):
            failures.extend(check_markdown(path))
    failures.extend(check_hook_config())

    if failures:
        print("Markdown heading hazards:\n", file=sys.stderr)
        for f in failures:
            print(f"  {f}\n", file=sys.stderr)
        print(
            "  A '#' at the start of a line with no space is prose in CommonMark, but\n"
            "  markdownlint --fix rewrites it into a heading WITHOUT failing. That is why\n"
            f"  {RULE} is disabled in {MARKDOWNLINT_CONFIG}.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
