"""Guards against personal-machine paths leaking into the public repo (T-061).

`seo-cycle` is a public repository. It must never carry, in tracked files,
the owner's macOS username or home-directory structure via an absolute local
path (which in turn would expose which commercial domains are run by the
same owner, once combined with a project path). This test scans every
git-tracked file (``git ls-files`` — the exact set of content a tag/clone/
mirror ships, regardless of what sits untracked or gitignored in a working
tree) for:

- an absolute ``/Users/NAME/...`` path where ``NAME`` is not a generic
  placeholder (``you``, ``username``, ``user``, ``name``);
- an absolute ``/home/NAME/...`` path under the same rule.

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

# Generic placeholders that are fine in a "/Users/NAME/..." docs path,
# plus the one example service-account name used by docs/vps-deployment.md.
PLACEHOLDER_NAMES = {"you", "username", "user", "name", "<you>", "seo"}

HOME_PATH_RE = re.compile(r"/(?:Users|home)/([A-Za-z0-9_.<>-]+)")


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return [line for line in out.stdout.splitlines() if line]


def _iter_findings():
    for rel in _tracked_files():
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable — not a text leak vector
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in HOME_PATH_RE.finditer(line):
                name = m.group(1)
                if name.lower().strip("<>") not in PLACEHOLDER_NAMES:
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
