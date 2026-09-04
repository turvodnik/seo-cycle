"""Guards the path/CLI convention (T-050).

The legacy global install path is not created by the installer and must not be
printed anywhere: instrumental packages never live in ``~/.codex/skills`` (only
universal ones do). Commands are published in CLI form (``seo-cycle ...``);
plain file paths use the project-relative surface ``./.codex/skills/seo-cycle``.

The needle is assembled from fragments so this test never matches itself.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

LEGACY = "~/.codex" + "/skills/seo-cycle"
PROJECT_SURFACE = "." + "/.codex/skills/seo-cycle"
BARE_SURFACE = ".codex" + "/skills/seo-cycle"

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "workspace"}
# CHANGELOG records what past releases actually did; rewriting it would falsify
# history. Its mentions are historical statements, not instructions to follow.
SKIP_FILES = {"CHANGELOG.md"}

PHASE_SKILLS = [
    "skills/seo-audit/SKILL.md",
    "skills/seo-entity-map/SKILL.md",
    "skills/seo-iteration/SKILL.md",
    "skills/seo-keywords/SKILL.md",
    "skills/seo-monitoring/SKILL.md",
    "skills/seo-publishing/SKILL.md",
    "skills/seo-writing/SKILL.md",
    "skills/_shared/setup-commands.md",
]

# A shell line that invokes something with a path in it.
INVOCATION = re.compile(r"(?:^|\s)(?:python3?|bash|sh)\s+\S*/\S+")


def iter_files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if SKIP_DIRS & set(path.parts):
            continue
        rel = path.relative_to(ROOT)
        if str(rel) in SKIP_FILES:
            continue
        yield rel, path


def read(path):
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


class TestNoLegacyPaths(unittest.TestCase):
    def test_legacy_path_absent_tree_wide(self):
        """No file may print the legacy global path (it does not exist on disk)."""
        hits = []
        for rel, path in iter_files():
            text = read(path)
            if text and LEGACY in text:
                for i, line in enumerate(text.splitlines(), 1):
                    if LEGACY in line:
                        hits.append(f"{rel}:{i}: {line.strip()}")
        self.assertEqual(hits, [], "legacy path still present:\n" + "\n".join(hits))

    def test_no_literal_skill_path_in_python_scripts(self):
        """Python scripts must derive the skill path, never hardcode it."""
        hits = []
        for path in sorted((ROOT / "scripts").rglob("*.py")):
            if SKIP_DIRS & set(path.parts):
                continue
            text = read(path)
            if not text:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                # a literal path inside a Python string literal
                if f"'{BARE_SURFACE}" in line or f'"{BARE_SURFACE}' in line:
                    hits.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
                elif BARE_SURFACE in line:
                    hits.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
        self.assertEqual(
            hits, [], "hardcoded skill path in scripts (use a variable):\n" + "\n".join(hits)
        )

    def test_phase_commands_use_cli_or_project_surface(self):
        """Every command with a path in the phase docs uses the agreed form."""
        bad = []
        for rel in PHASE_SKILLS:
            path = ROOT / rel
            self.assertTrue(path.exists(), f"missing phase doc: {rel}")
            in_block = False
            continuation = False
            for i, line in enumerate((path.read_text(encoding="utf-8")).splitlines(), 1):
                if line.startswith("```"):
                    in_block = line.strip() != "```"
                    continuation = False
                    continue
                if not in_block:
                    continue
                stripped = line.strip()
                was_continuation, continuation = continuation, stripped.endswith("\\")
                if was_continuation or not stripped or stripped.startswith("#"):
                    continue
                if not INVOCATION.search(stripped):
                    continue
                if stripped.startswith("seo-cycle ") or stripped.startswith(PROJECT_SURFACE + "/"):
                    continue
                bad.append(f"{rel}:{i}: {stripped}")
        self.assertEqual(
            bad,
            [],
            "commands must start with 'seo-cycle ' or "
            f"'{PROJECT_SURFACE}/':\n" + "\n".join(bad),
        )


if __name__ == "__main__":
    unittest.main()
