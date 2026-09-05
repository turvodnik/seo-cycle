"""Guards documentation truthfulness (T-051).

Two invariants:

1. Every relative markdown link inside the top-level docs (README, INSTALL,
   GUIDE, SKILL, docs/*.md) points at a file that actually exists in the repo.
   A broken link is a promise the repo does not keep.
2. No markdown file contains a line shaped like a real secret example — only
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
