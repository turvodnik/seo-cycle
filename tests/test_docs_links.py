"""Guards documentation truthfulness (T-051).

Two invariants:

1. Every relative markdown link inside the top-level docs (README, INSTALL,
   GUIDE, SKILL, docs/*.md) points at a file that actually exists in the repo.
   A broken link is a promise the repo does not keep.
2. No markdown file contains a line shaped like a real secret example
   (``NAME=<16+ chars of letters/digits>``) — only variable *names* belong in
   docs; values live in the macOS Keychain via `ai-secret` (global rules, §5).
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

# NAME=VALUE where VALUE looks like a real secret (>=16 chars, letters/digits/
# common token punctuation, no leading placeholder marker).
SECRET_VALUE_RE = re.compile(
    r"^[A-Z][A-Z0-9_]*=([A-Za-z0-9_\-]{16,})\s*$"
)
PLACEHOLDER_VALUES = {
    "your_key_here",
    "example",
    "changeme",
}


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
                m = SECRET_VALUE_RE.match(line.strip())
                if not m:
                    continue
                value = m.group(1)
                if value.lower() in PLACEHOLDER_VALUES:
                    continue
                if set(value) <= {"x", "X"}:
                    continue
                hits.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
        self.assertEqual(
            hits, [], "secret-shaped example value in docs:\n" + "\n".join(hits)
        )


if __name__ == "__main__":
    unittest.main()
