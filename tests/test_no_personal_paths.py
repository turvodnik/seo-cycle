"""Guards against personal-machine paths leaking into the public repo (T-061).

`seo-cycle` is a public repository. It must never carry, in tracked files,
the owner's macOS username or home-directory structure via an absolute local
path (which in turn would expose which commercial domains are run by the
same owner, once combined with a project path). This test scans every
git-tracked file (``git ls-files`` — the exact set of content a tag/clone/
mirror ships, regardless of what sits untracked or gitignored in a working
tree) for:

- an absolute ``/Users/NAME/...`` path where ``NAME`` is not a generic
  placeholder (``you``, ``username``, ``user``, ``name``) — ``NAME`` is any
  non-slash, non-whitespace run, Unicode included, so a Cyrillic (or other
  non-ASCII) account name is caught, not just `[A-Za-z0-9]` ones (gate
  review, T-061 fix-up: the first version of this test used an ASCII-only
  character class and missed exactly that case);
- an absolute ``/home/NAME/...`` path under the same rule.

Files are read UTF-8 first, then latin-1 as a fallback that never raises
(gate review, T-061 fix-up: the first version silently skipped any file
that failed UTF-8 decoding, which is a blind spot for a real leak sitting
in a non-UTF-8 text file, not just for genuinely binary ones) — a short
extension skip-list still short-circuits the obviously-binary files for
speed, but that list is a performance optimisation, not the correctness
mechanism.

Generic docs placeholders like ``/Users/<you>/...`` or ``/Users/username/...``
are the sanctioned way to show an example path and are explicitly allowed,
and so is a generic example account name in a ``/home/<name>/...`` systemd
unit example (``docs/vps-deployment.md`` uses ``seo`` — a service-account
name the doc itself invents, not a real person's username) — the risk this
test guards against is a REAL machine path leaking, not every string that
happens to follow ``/home/``.

Deliberately NOT checked: a bare mention of ``turvodnik`` with no leading
``/Users/`` or ``/home/``. That string is also the project's public GitHub
org/account (``github.com/turvodnik``, `_tools/AGENTS.md` §6) and appears
throughout install docs and scripts in `github.com/turvodnik/...` and
`raw.githubusercontent.com/turvodnik/...` URLs — already-public identity,
not a personal-machine-path leak, and flagging it would just be noise on
every install doc. Same reasoning for a bare ``pifagor`` inside a public
product User-Agent string or the ``pifagorlab.com`` domain name quoted in a
changelog entry — those are public identifiers already, not filesystem
structure. What actually leaked (T-059, T-061) was always the combination
``/Users/<name>/<dir>/<project>`` — that is exactly what ``HOME_PATH_RE``
below catches, machine-name-agnostic (works for any future personal path,
not just the two usernames already found), and it is exactly the shape of
this ticket's acceptance-criteria grep
(``grep -rnE "/Users/(pifagor|turvodnik)"``), generalised to any name.

## Exceptions (narrow, justified)

- ``.git/**`` — history is intentionally not rewritten (SPEC "что не
  делаем"); this test guards the working tree that ships in a fresh clone/
  tag, not the object database. ``git ls-files`` never returns anything
  under ``.git/`` anyway, but the exclusion is kept explicit for clarity.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# This file's own docstring/comments discuss "/Users/..." and "/home/..."
# shapes in prose (including grep syntax and markdown backticks around
# them), which is not itself a personal-path leak — exclude it from the
# scan rather than contort the regex or the prose around a self-reference.
SELF = "tests/test_no_personal_paths.py"

# Generic placeholders that are fine in a "/Users/NAME/..." docs path,
# plus the one example service-account name used by docs/vps-deployment.md.
PLACEHOLDER_NAMES = {"you", "username", "user", "name", "<you>", "seo"}

# A macOS/Linux account name is not restricted to ASCII (a Cyrillic or other
# Unicode login name is valid and this machine's owner could plausibly have
# one) — the character class has to be "anything that isn't a path separator
# or whitespace", not "[A-Za-z0-9...]", or a non-ASCII username sails through
# unmatched. ``\S`` already excludes newlines, so this only ever inspects one
# line at a time regardless.
HOME_PATH_RE = re.compile(r"/(?:Users|home)/([^\s/]+)")

# Extensions that are never personal-path-shaped text, skipped for speed —
# NOT for correctness: unlike secret-scan.py, we still fall back to a
# byte-preserving decode (see below) for anything not on this list, so an
# actual text file in a non-UTF-8 encoding (Windows-1251 Cyrillic docs, for
# instance) is still scanned rather than silently skipped.
_SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".woff", ".woff2", ".mp4", ".mov", ".db", ".sqlite", ".sqlite3",
}


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return [line for line in out.stdout.splitlines() if line]


def _read_text_best_effort(path: pathlib.Path) -> str | None:
    """UTF-8 first; a non-UTF-8 text file (legacy Windows-1251 doc, say)
    must still be scanned, not skipped — decode as latin-1 instead, which
    never raises (every byte 0-255 has a code point) and preserves the
    ASCII byte values a "/Users/NAME" leak is made of either way. Only a
    genuine read failure (permissions, dangling symlink) is skipped."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1")
        except OSError:
            return None
    except OSError:
        return None


def _iter_findings():
    for rel in _tracked_files():
        if rel == SELF:
            continue
        path = ROOT / rel
        if not path.is_file() or path.suffix.lower() in _SKIP_SUFFIXES:
            continue
        text = _read_text_best_effort(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in HOME_PATH_RE.finditer(line):
                name = m.group(1)
                # Strip trailing prose punctuation a "/Users/<you>," style
                # sentence leaves stuck to the captured name (the char
                # class has no better way to know a path ended).
                normalized = name.lower().strip("<>.,;:)\"'")
                if normalized not in PLACEHOLDER_NAMES:
                    yield rel, lineno, m.group(0)


class NoPersonalPathsTest(unittest.TestCase):
    def test_no_personal_paths_in_tracked_tree(self) -> None:
        findings = list(_iter_findings())
        self.assertFalse(
            findings,
            "Личные пути найдены в публичном (git-tracked) дереве:\n"
            + "\n".join(f"  {f}:{ln}: {snippet!r}" for f, ln, snippet in findings),
        )


if __name__ == "__main__":
    unittest.main()
