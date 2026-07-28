"""Тесты консистентности skills/manifest.yaml (v2 модульная архитектура)."""
import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "skill-manifest-validate.py"

spec = importlib.util.spec_from_file_location("skill_manifest_validate", SCRIPT)
smv = importlib.util.module_from_spec(spec)
sys.modules["skill_manifest_validate"] = smv
spec.loader.exec_module(smv)


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def minimal_tree(root: pathlib.Path, *, break_entry=False, dup_phase=False, break_shim=False) -> None:
    phases_mod = "[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]" if not dup_phase else "[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]"
    write(root / "skills" / "manifest.yaml", f"""
version: 2
orchestrator:
  entry: SKILL.md
  phases: [0]
modules:
  mega:
    entry: skills/mega/SKILL.md
    phases: {phases_mod}
shared: []
compat_shims:{" [prompts/x.md]" if break_shim else " []"}
""")
    if not break_entry:
        write(root / "skills" / "mega" / "SKILL.md", "---\nname: mega\n---\n# mega\n")
    if break_shim:
        write(root / "prompts" / "x.md", "обычный файл, не symlink")


class SkillManifestTest(unittest.TestCase):
    def test_repo_manifest_is_consistent(self):
        findings = smv.validate(ROOT)
        self.assertEqual(findings, [], f"manifest рассогласован: {findings}")

    def test_all_eleven_phases_covered_exactly_once_in_repo(self):
        import yaml
        data = yaml.safe_load((ROOT / "skills" / "manifest.yaml").read_text(encoding="utf-8"))
        phases = list(data["orchestrator"]["phases"])
        for spec_ in data["modules"].values():
            phases.extend(spec_["phases"])
        self.assertEqual(sorted(phases), list(range(0, 11)))

    def test_missing_entry_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            minimal_tree(root, break_entry=True)
            findings = smv.validate(root)
            self.assertTrue(any("entry не найден" in f for f in findings), findings)

    def test_duplicate_phase_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            minimal_tree(root, dup_phase=True)
            findings = smv.validate(root)
            self.assertTrue(any("дважды" in f for f in findings), findings)

    def test_non_symlink_shim_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            minimal_tree(root, break_shim=True)
            findings = smv.validate(root)
            self.assertTrue(any("не является symlink" in f for f in findings), findings)


if __name__ == "__main__":
    unittest.main()
