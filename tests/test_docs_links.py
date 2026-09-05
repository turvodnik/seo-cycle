"""Guards documentation truthfulness (T-051).

Three invariants:

1. Every relative markdown link (``[text](path)``) inside the top-level docs
   (README, INSTALL, GUIDE, SKILL, docs/*.md) points at a file that actually
   exists in the repo. A broken link is a promise the repo does not keep.
2. In the primary onboarding docs (README/INSTALL/GUIDE/SKILL/
   docs/architecture.md — see `BACKTICK_SCAN_FILES`), every backtick-quoted
   path (`` `scripts/foo.py` ``) that is unambiguously a reference into THIS
   repo's own tree (bare `scripts/`, `docs/`, `config/`, `templates/`,
   `prompts/`, `tests/`, `bin/`, `skills/`, a known top-level file, or one of
   those reached through the project-local entrypoint symlinks
   `~/.codex/vendor/seo-cycle/...` / `./.codex/skills/seo-cycle/...` /
   `.claude/...` / `.agents/...`) also resolves. This is the exact shape both
   original T-051 findings had — a non-existent JS-suffixed secret scanner
   referenced from `docs/architecture.md`, and a non-existent NeuronWriter
   diagnostic script referenced from `INSTALL.md` via the project-local
   entrypoint symlink prefix — neither was a markdown-link, both were plain
   backtick-quoted paths, so invariant 1 alone would never have caught them.
   Two things are deliberately excluded:
   paths that describe files created *inside a target project* after install
   (`seo/...`, `blog/...`, `seo-cycle.yaml`, ...) are never resolvable
   against this repo; and brace-expansion shorthand
   (`` `config/region-profiles/{ru,eu,us,global}.yaml` `` meaning four
   files, not one literal path with `{`/`}` in its name) is not a path at
   all. The scan is scoped to onboarding docs rather than the full
   docs/**/*.md tree because planning/historical documents legitimately use
   repo-shaped backtick paths to describe files that live in a *different*
   project or a *not-yet-built* location (e.g. `docs/migration.md` saying a
   helper "currently lives in emwoody" is accurate non-existence, not a
   broken promise) — invariant 1 already covers those files for actual
   `[text](path)` links.
3. No markdown file contains a line shaped like a real secret example — only
   variable *names* belong in docs; values live in the macOS Keychain via
   `ai-secret` (global rules, §5). "Shaped like a real secret" covers three
   cases: a known provider token prefix (`atp_pk_live_`, `sk-`, `ghp_`, ...)
   even truncated with a placeholder ellipsis; the WordPress Application
   Password shape (4 groups of 4 alnum chars — `xxxx xxxx xxxx xxxx` IS this
   shape, not a safe placeholder); or any other >=12-char alnum/`_`/`-` blob
   without an obvious placeholder marker (`your_`, `_here`, `example`, ...).
"""
import pathlib
import re
import unittest
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parent.parent

DOC_FILES = [
    "README.md",
    "INSTALL.md",
    "GUIDE.md",
    "SKILL.md",
]

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
BACKTICK_RE = re.compile(r"`([^`\n]+)`")

# Project-local entrypoint symlinks all point at this repo's own root (shared
# vendor core, or the project-local symlink surface into it) — a path
# reached through one of these prefixes is checkable against ROOT exactly
# like a bare repo-relative path.
ENTRYPOINT_PREFIXES = (
    "~/.codex/vendor/seo-cycle/",
    "./.codex/skills/seo-cycle/",
    ".codex/skills/seo-cycle/",
    "./.claude/skills/seo-cycle/",
    ".claude/skills/seo-cycle/",
    "./.agents/skills/seo-cycle/",
    ".agents/skills/seo-cycle/",
)

# Directories that exist ONLY in this repo, never as a same-named directory
# generated inside a target project after install (project data lives under
# seo/, blog/, categories/, .agents/, .codex/, .claude/ instead) — safe to
# resolve against ROOT without risking false positives on project-future paths.
REPO_DIR_PREFIXES = (
    "scripts/", "docs/", "templates/", "prompts/", "config/",
    "tests/", "bin/", "skills/",
)
REPO_TOP_FILES = {
    "README.md", "INSTALL.md", "GUIDE.md", "SKILL.md", "CHANGELOG.md",
    "VERSION", "LICENSE", "AGENTS.md",
}


# Files where the two original T-051 broken backtick-paths actually lived
# (INSTALL.md, docs/architecture.md) plus the other primary onboarding docs.
# Deliberately NOT the full docs/**/*.md tree used by invariant 1: planning/
# historical documents (docs/migration.md, docs/automated-monthly.md, ...)
# legitimately use repo-shaped backtick paths to describe files that live in
# a *different* project or a *not-yet-built* location ("`scripts/nw.sh`
# сейчас в emwoody" is accurate non-existence, not a broken promise) — the
# markdown-link invariant already covers those files for actual `[text](path)`
# links, so onboarding-doc backtick paths is where this check earns its keep.
BACKTICK_SCAN_FILES = DOC_FILES + ["docs/architecture.md"]


def repo_relative_candidate(raw):
    """Return a ROOT-relative path string if `raw` unambiguously names a file
    in this repo's own tree, else None (not a path / not checkable here)."""
    if not raw or any(ch in raw for ch in " \t<>*$|&;=\"'{}"):
        return None
    if raw.startswith(("http://", "https://", "mailto:", "#", "-")):
        return None
    stripped = raw
    for prefix in ENTRYPOINT_PREFIXES:
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):]
            break
    if stripped.startswith("./"):
        stripped = stripped[2:]
    if stripped in REPO_TOP_FILES:
        return stripped
    if stripped.startswith(REPO_DIR_PREFIXES):
        return stripped
    return None

# NAME=VALUE line — VALUE is whatever follows "=" to end of line (may contain
# spaces, e.g. a WordPress Application Password).
NAME_VALUE_RE = re.compile(r"^[A-Z][A-Z0-9_]*=(.+)$")

# Known provider token prefixes — any of these appearing in a value marks it
# as secret-shaped regardless of length (catches e.g. `atp_pk_live_...`,
# where the trailing dots are a placeholder but the prefix itself is real).
PROVIDER_PREFIX_RE = re.compile(
    r"(atp_pk_live_|atp_sk_live_|sk-|sk_live_|pk_live_|ck_[a-z0-9]|cs_[a-z0-9]|"
    r"ghp_|gho_|ghu_|ghs_|AKIA|xox[baprs]-|eyJ)",
    re.IGNORECASE,
)

# WordPress Application Password shape: 4 groups of 4 alnum chars separated
# by single spaces (`xxxx xxxx xxxx xxxx` is this shape, not a safe
# "obviously fake" placeholder — it is exactly what a real one looks like).
WP_APP_PASSWORD_RE = re.compile(r"^[A-Za-z0-9]{4}(?: [A-Za-z0-9]{4}){3}$")

PLACEHOLDER_MARKERS = ("your_", "_here", "example", "changeme", "placeholder")


def is_secret_shaped(value):
    value = value.strip()
    # NAME="value" / NAME='value' — unwrap the quotes before analysis, same
    # as any shell would when the line is sourced.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    if not value:
        return False
    # strip a trailing ellipsis placeholder before checking prefixes
    bare = re.sub(r"[.…]+$", "", value)
    if PROVIDER_PREFIX_RE.search(bare):
        return True
    if WP_APP_PASSWORD_RE.match(value):
        return True
    compact = value.replace(" ", "")
    if len(compact) < 12:
        return False
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", compact):
        return False
    low = compact.lower()
    if any(marker in low for marker in PLACEHOLDER_MARKERS):
        return False
    if set(low) <= {"x"}:
        return False
    return True


def iter_doc_files():
    for name in DOC_FILES:
        path = ROOT / name
        if path.exists():
            yield path
    for path in sorted((ROOT / "docs").rglob("*.md")):
        yield path


def resolve_link(doc_path, target):
    # strip markdown link title (`url "title"`) and anchor
    target = target.split(" ", 1)[0].strip("<>")
    if not target:
        return None
    parsed = urlsplit(target)
    if parsed.scheme:  # http(s)://, mailto:, etc — not a repo-relative link
        return None
    if target.startswith("#"):
        return None
    file_part = parsed.path
    if not file_part:
        return None
    return (doc_path.parent / file_part).resolve()


class TestDocsLinks(unittest.TestCase):
    def test_relative_links_resolve(self):
        broken = []
        for doc_path in iter_doc_files():
            text = doc_path.read_text(encoding="utf-8")
            rel_doc = doc_path.relative_to(ROOT)
            for match in LINK_RE.finditer(text):
                target_path = resolve_link(doc_path, match.group(1))
                if target_path is None:
                    continue
                if not target_path.exists():
                    broken.append(f"{rel_doc}: -> {match.group(1)}")
        self.assertEqual(broken, [], "broken relative links:\n" + "\n".join(broken))

    def test_backtick_repo_paths_resolve(self):
        broken = []
        for name in BACKTICK_SCAN_FILES:
            doc_path = ROOT / name
            if not doc_path.exists():
                continue
            text = doc_path.read_text(encoding="utf-8")
            rel_doc = doc_path.relative_to(ROOT)
            for match in BACKTICK_RE.finditer(text):
                candidate = repo_relative_candidate(match.group(1))
                if candidate is None:
                    continue
                if not (ROOT / candidate).exists():
                    broken.append(f"{rel_doc}: `{match.group(1)}` -> {candidate}")
        self.assertEqual(
            broken, [], "broken backtick-quoted repo path:\n" + "\n".join(broken)
        )

    def test_no_secret_shaped_values(self):
        hits = []
        for path in sorted(ROOT.rglob("*.md")):
            if ".git" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                m = NAME_VALUE_RE.match(line.strip())
                if not m:
                    continue
                if is_secret_shaped(m.group(1)):
                    hits.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
        self.assertEqual(
            hits, [], "secret-shaped example value in docs:\n" + "\n".join(hits)
        )


if __name__ == "__main__":
    unittest.main()
