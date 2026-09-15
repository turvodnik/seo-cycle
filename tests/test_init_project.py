#!/usr/bin/env python3
"""Regression tests for the project init wizard."""

from __future__ import annotations

import pathlib
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = pathlib.Path(__file__).resolve().parents[1]
INIT_PROJECT = ROOT / "scripts" / "init-project.sh"
VALIDATE = ROOT / "scripts" / "validate-config.py"


def run_with_tty(cmd: list[str], cwd: pathlib.Path, answers: bytes, env: dict[str, str],
                  timeout: float = 90.0) -> tuple[int, bytes]:
    """Run `cmd` with a pseudo-terminal as /dev/tty but stdin = /dev/null.

    Same stand as tests/test_intake_wizard_tty.py (T-099): the wizard's own
    `read_answer` reads /dev/tty directly, so a pty is required even though
    stdin itself stays closed/not-a-terminal.
    """
    import pty

    pid, fd = pty.fork()
    if pid == 0:  # child
        try:
            os.chdir(cwd)
            devnull = os.open(os.devnull, os.O_RDONLY)
            os.dup2(devnull, 0)
            os.execvpe(cmd[0], cmd, env)
        finally:
            os._exit(127)

    os.write(fd, answers)
    output = bytearray()
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
            raise AssertionError(f"child timed out; output so far:\n{output.decode('utf-8', 'replace')}")
        ready, _, _ = select.select([fd], [], [], min(remaining, 1.0))
        if not ready:
            continue
        try:
            chunk = os.read(fd, 4096)
        except OSError:  # EIO: slave closed
            break
        if not chunk:
            break
        output.extend(chunk)
    _, status = os.waitpid(pid, 0)
    os.close(fd)
    return os.waitstatus_to_exitcode(status), bytes(output)


def base_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()}
    env["SEO_CYCLE_SKIP_REGISTRY"] = "1"
    env.update(extra)
    return env


@unittest.skipIf(yaml is None, "PyYAML is required")
class InitProjectTest(unittest.TestCase):
    def test_pipe_stdin_does_not_pollute_generated_config(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-init-project-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))

        fake_bootstrap_tail = '\n'.join(
            [
                'echo "Project: $PROJECT_DIR"',
                'echo "  ✓ Codex bootstrap finished"',
                'echo "Core: $CORE"',
                "",
            ]
        )
        proc = subprocess.run(
            ["bash", str(INIT_PROJECT)],
            cwd=tmp,
            input=fake_bootstrap_tail,
            text=True,
            capture_output=True,
            env={**os.environ, "SEO_CYCLE_SKIP_REGISTRY": "1"},
            check=True,
        )

        self.assertIn("safe defaults", proc.stdout)
        cfg = yaml.safe_load((tmp / "seo-cycle.yaml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["project"]["name"], "MyProject")
        self.assertEqual(cfg["project"]["domain"], "example.com")
        self.assertEqual(cfg["locale"]["language"], "ru")
        self.assertTrue((tmp / "seo" / "setup" / "setup-control-plane.md").exists())

    def test_local_codex_init_validates_without_global_skill_or_paid_keys(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-local-codex-"))
        home = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-home-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        self.addCleanup(lambda: shutil.rmtree(home, ignore_errors=True))

        skill_dir = tmp / ".codex" / "skills"
        skill_dir.mkdir(parents=True)
        (skill_dir / "seo-cycle").symlink_to(ROOT)

        # T-107: только 7 обязательных вопросов + переключатель "ещё" (default N).
        # Q1 name, Q2 domain, Q3 project_type, Q4 cms, Q5 locale, Q6 governance,
        # Q7 paid budget, Q8 "уточнить ещё?" — здесь "N" (Enter), остальное дефолты.
        proc = subprocess.run(
            ["bash", str(INIT_PROJECT)],
            cwd=tmp,
            input="\n".join(["gsse", "gsse.ru", "", "", "", "", "", ""]),
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "HOME": str(home),
                "SEO_RUNTIME": "codex",
                "SEO_SEARCH_RUNTIME": "direct",
                "SEO_CYCLE_SKIP_REGISTRY": "1",
            },
            check=True,
        )
        self.assertIn("Создан seo-cycle.yaml", proc.stdout)

        validation = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate-config.py"), str(tmp / "seo-cycle.yaml")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "HOME": str(home),
                "SEO_RUNTIME": "codex",
                "SEO_SEARCH_RUNTIME": "direct",
            },
            check=True,
        )

        self.assertIn("✓ Конфиг полностью валиден", validation.stdout)
        self.assertNotIn("WARNINGS", validation.stdout)
        self.assertNotIn("ЧЕК-ЛИСТ", validation.stdout)


@unittest.skipIf(yaml is None, "PyYAML is required")
class WizardSevenQuestionsTest(unittest.TestCase):
    """T-107: 7 обязательных вопроса + один переключатель «ещё» вместо 23 вопросов
    (issue-107 / отчёт 2026-09-15-seo-cycle-people-and-quality.md §4.5 H3).
    """

    def test_default_run_asks_exactly_eight_prompts_and_validates(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-t107-default-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))

        # 7 обязательных вопроса + переключатель — все на Enter (дефолты),
        # плюс финальный «Запустить validate-config.py сейчас? [Y/n]».
        answers = b"\n" * 30
        rc, out = run_with_tty(["bash", str(INIT_PROJECT)], tmp, answers, base_env())
        text = out.decode("utf-8", "replace")
        self.assertEqual(rc, 0, text)

        pre_generation = text.split("Создаю seo-cycle.yaml")[0]
        prompt_numbers = re.findall(r"\d+\.\s", pre_generation)
        self.assertEqual(len(prompt_numbers), 8, text)  # было 23 на HEAD (T-107, п.1)

        self.assertIn("Дальше:", text)
        self.assertIn("seo-cycle validate", text)
        self.assertIn("seo-cycle doctor", text)
        self.assertIn("seo-cycle status", text)
        self.assertNotIn("WebP", pre_generation)  # картинки за переключателем по умолчанию не спрашиваются

        cfg = yaml.safe_load((tmp / "seo-cycle.yaml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["project"]["name"], "MyProject")
        self.assertEqual(cfg["project"]["domain"], "example.com")
        self.assertEqual(cfg["images"]["output"]["width"], 1200)  # дефолт из шаблона не изменился

        validate = subprocess.run(
            [sys.executable, str(VALIDATE), "seo-cycle.yaml"], cwd=tmp,
            capture_output=True, text=True, env=base_env(), check=False,
        )
        self.assertEqual(validate.returncode, 0, validate.stdout + validate.stderr)

    def test_broken_required_default_makes_validate_red(self) -> None:
        """Инсценировка invariant-критерия: ломаем обязательное поле (project.domain,
        отвечает за него Q2) в сгенерированной копии — validate обязан покраснеть."""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-t107-negative-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        rc, _ = run_with_tty(["bash", str(INIT_PROJECT)], tmp, b"\n" * 30, base_env())
        self.assertEqual(rc, 0)

        broken = tmp / "seo-cycle.yaml"
        text = broken.read_text(encoding="utf-8").replace(
            'domain: "example.com"', 'domain: ""', 1
        )
        broken.write_text(text, encoding="utf-8")

        validate = subprocess.run(
            [sys.executable, str(VALIDATE), "seo-cycle.yaml"], cwd=tmp,
            capture_output=True, text=True, env=base_env(), check=False,
        )
        self.assertNotEqual(validate.returncode, 0, validate.stdout + validate.stderr)
        self.assertIn("project.domain is required", validate.stdout)

    def test_more_switch_yes_asks_image_and_intake_questions(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-t107-more-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))

        # Q1-7 дефолты, Q8 «y» — дальше как раньше: бренд/бюджеты, картинки,
        # переключатель detailed intake («y»), сам intake-мастер (дефолты),
        # apply-profile и финальный validate-prompt.
        answers = b"\n" * 7 + b"y\n" + b"\n" * 14 + b"y\n" + b"\n" * 120
        rc, out = run_with_tty(["bash", str(INIT_PROJECT)], tmp, answers, base_env(), timeout=120.0)
        text = out.decode("utf-8", "replace")
        self.assertEqual(rc, 0, text)
        self.assertIn("WebP", text)
        self.assertIn("Ширина WebP в px", text)
        self.assertIn("Запустить подробный wizard", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
