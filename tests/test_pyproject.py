"""tests/test_pyproject.py — pyproject.toml как источник правды по зависимостям.

Два инварианта (T-047):

1. `[project].version` в pyproject.toml совпадает с VERSION. Версия не
   объявлена dynamic-из-файла (это капризнее на разных setuptools) — вместо
   этого дублируется строкой, а совпадение держит этот тест.
2. Каждый сторонний top-level импорт, реально встречающийся где-либо в
   scripts/** (в т.ч. внутри функций/try-блоков — интерпретатор всё равно
   попытается его выполнить в рантайме), объявлен хотя бы в одной группе
   зависимостей pyproject (base `dependencies` или любая запись
   `[project.optional-dependencies]`). Иначе `pip install -e ".[group]"`
   молча не даёт того, что скрипт реально импортирует — прецедент I-037
   (восстановление site-packages по памяти).
"""
from __future__ import annotations

import ast
import pathlib
import sys
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# Имя импорта (после `import`/`from`) -> имена PyPI-дистрибутивов, когда они
# расходятся с именем импорта. "google" резолвится сразу в несколько
# дистрибутивов (google-auth/google-api-python-client/google-analytics-data
# все ставят пакеты в namespace `google.*`) — достаточно, чтобы был объявлен
# хотя бы один.
IMPORT_TO_DISTRIBUTIONS: dict[str, tuple[str, ...]] = {
    "yaml": ("pyyaml",),
    "google": ("google-auth", "google-api-python-client", "google-analytics-data"),
    "googleapiclient": ("google-api-python-client",),
    "graphify": ("graphifyy",),
    "bs4": ("beautifulsoup4",),
    "PIL": ("Pillow",),
}


def _local_module_names() -> set[str]:
    """Всё, что в scripts/** — не сторонний пакет, а локальный модуль/пакет."""
    names: set[str] = set()
    for f in SCRIPTS.rglob("*.py"):
        names.add(f.stem)
    for d in SCRIPTS.rglob("*"):
        if d.is_dir():
            names.add(d.name)
    return names


def _normalize(name: str) -> str:
    """PEP 503-подобная нормализация: регистр и '_'/'.' против '-' — один и тот же пакет."""
    return name.strip().lower().replace("_", "-").replace(".", "-")


def _requirement_name(spec: str) -> str:
    """'pyyaml' / 'google-auth>=2' / 'a[extra]==1; python_version<\"4\"' -> имя пакета.
    Группы в этом pyproject сегодня без версий/экстра-квалификаторов, но тест
    не обязан на это полагаться."""
    name = spec
    for sep in ("[", ">", "<", "=", "!", "~", ";", " "):
        name = name.split(sep, 1)[0]
    return _normalize(name)


def _foreign_imports(scripts_dir: pathlib.Path) -> dict[str, list[str]]:
    """top-level имя импорта -> файлы scripts/**, где он встречается."""
    local = _local_module_names()
    stdlib = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
    found: dict[str, list[str]] = {}
    for f in scripts_dir.rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                tops = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if (node.level and node.level > 0) or node.module is None:
                    continue
                tops = [node.module.split(".")[0]]
            else:
                continue
            for top in tops:
                if top in stdlib or top in local:
                    continue
                found.setdefault(top, []).append(str(f.relative_to(scripts_dir.parent)))
    return found


class PyprojectVersionTest(unittest.TestCase):
    def test_version_matches_VERSION_file(self) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        version_file = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(data["project"]["version"], version_file)


class DependencyGroupsCoverTheirImportsTest(unittest.TestCase):
    """Каждый сторонний top-level импорт из scripts/** объявлен где-то в pyproject."""

    @classmethod
    def setUpClass(cls) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = data["project"]
        all_requirements: list[str] = list(project.get("dependencies", []))
        for group_reqs in project.get("optional-dependencies", {}).values():
            all_requirements.extend(group_reqs)
        cls.declared = {_requirement_name(r) for r in all_requirements}
        cls.found_imports = _foreign_imports(SCRIPTS)

    def test_every_foreign_import_is_declared_somewhere(self) -> None:
        missing = []
        for top, files in sorted(self.found_imports.items()):
            candidates = IMPORT_TO_DISTRIBUTIONS.get(top, (top,))
            wanted = {_normalize(c) for c in candidates}
            if not (wanted & self.declared):
                missing.append(f"{top} (см. {files[0]}) — ни один из {sorted(wanted)} не в pyproject")
        self.assertEqual(
            missing,
            [],
            "сторонний импорт без объявленной зависимости в pyproject.toml — "
            "добавь пакет в dependencies/optional-dependencies (и, если имя "
            "дистрибутива отличается от имени импорта, впиши это в "
            "IMPORT_TO_DISTRIBUTIONS в этом файле):\n" + "\n".join(missing),
        )

    def test_scan_actually_finds_known_imports(self) -> None:
        # Отрицательный контроль на сам сборщик: если ast-скан сломается и
        # начнёт возвращать пусто, test_every_foreign_import_is_declared_somewhere
        # пройдёт "зелёным" ложно — эта проверка гарантирует, что скан
        # реально что-то нашёл (yaml используют десятки скриптов).
        self.assertIn("yaml", self.found_imports)
        self.assertGreaterEqual(len(self.found_imports), 8)


if __name__ == "__main__":
    unittest.main()
