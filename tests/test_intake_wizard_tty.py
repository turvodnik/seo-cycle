#!/usr/bin/env python3
"""Regression tests for GitHub issues #28 / #29 (init wizard on macOS).

#28 — a garbage byte in an answer (backspace over a multibyte char in a tty)
      made `sed -i` die with "RE error: illegal byte sequence" half-way
      through seo-cycle.yaml and leave a `.!PID!seo-cycle.yaml` temp file.
#29 — project-intake-wizard.py read answers from stdin while init-project.sh
      read them from /dev/tty; with stdin != tty the first question died with
      an EOFError traceback and init went on printing "✓".
"""

from __future__ import annotations

import os
import pathlib
import pty
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
INTAKE_WIZARD = ROOT / "scripts" / "project-intake-wizard.py"
VALIDATE = ROOT / "scripts" / "validate-config.py"
TEMPLATE = ROOT / "config" / "project.template.yaml"


def run_with_tty(cmd: list[str], cwd: pathlib.Path, answers: bytes, env: dict[str, str],
                 timeout: float = 180.0) -> tuple[int, bytes]:
    """Run `cmd` with a pseudo-terminal as /dev/tty but stdin = /dev/null.

    That is the shape of the bug reports: the wizard is launched from an agent
    or a pipe (stdin is not a terminal) while a terminal is still attached.
    Returns (exit status, everything the child printed to the pty).
    """
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
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LC_", "LANG"))}
    env["SEO_CYCLE_SKIP_REGISTRY"] = "1"
    env.update(extra)
    return env


@unittest.skipIf(yaml is None, "PyYAML is required")
class IntakeWizardTtyTest(unittest.TestCase):
    def _project(self) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-t099-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        shutil.copy(TEMPLATE, tmp / "seo-cycle.yaml")
        return tmp

    def test_interactive_without_any_terminal_fails_cleanly(self) -> None:
        tmp = self._project()
        proc = subprocess.run(
            [sys.executable, str(INTAKE_WIZARD), "seo-cycle.yaml", "--interactive", "--write"],
            cwd=tmp,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            start_new_session=True,  # no controlling terminal → /dev/tty is unavailable
            env=base_env(),
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("нет интерактивного ввода", proc.stderr)
        self.assertFalse((tmp / "seo" / "project-intake.yaml").exists(), "nothing must be written")

    def test_interactive_reads_answers_from_dev_tty_when_stdin_is_not_a_tty(self) -> None:
        tmp = self._project()
        answers = b"saas\n" + b"\n" * 120
        rc, out = run_with_tty(
            [sys.executable, str(INTAKE_WIZARD), "seo-cycle.yaml", "--interactive", "--write"],
            tmp, answers, base_env(),
        )
        text = out.decode("utf-8", "replace")
        self.assertEqual(rc, 0, text)
        self.assertNotIn("Traceback", text)
        intake = yaml.safe_load((tmp / "seo" / "project-intake.yaml").read_text(encoding="utf-8"))
        self.assertEqual(intake["business"]["project_type"], "saas")

    def test_interactive_eof_on_tty_is_not_a_traceback(self) -> None:
        tmp = self._project()
        # The terminal hangs up after the first answer (Ctrl-D on an empty line).
        rc, out = run_with_tty(
            [sys.executable, str(INTAKE_WIZARD), "seo-cycle.yaml", "--interactive", "--write"],
            tmp, b"saas\n\x04", base_env(),
        )
        text = out.decode("utf-8", "replace")
        self.assertNotEqual(rc, 0)
        self.assertNotIn("Traceback", text)
        self.assertIn("EOF", text)
        self.assertFalse((tmp / "seo" / "project-intake.yaml").exists())


class InitProjectLocaleTest(unittest.TestCase):
    """Issue #28: init with a garbage byte in an answer under LC_ALL=C/POSIX."""

    def _run_init(self, locale: str) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-t099-init-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        # Q1-4 defaults, Q5 project_type typed as «blog» after a backspace over
        # a Cyrillic char (one dangling lead byte, exactly the #28 report),
        # Q6-21 defaults, Q22 "y" → detailed intake reads /dev/tty (#29),
        # then defaults for every intake question, Q23 and the validate prompt.
        answers = b"\n" * 4 + b"\xd0blog\n" + b"\n" * 16 + b"y\n" + b"\n" * 120
        rc, out = run_with_tty(["bash", str(INIT_PROJECT)], tmp, answers, base_env(LC_ALL=locale))
        text = out.decode("utf-8", "replace")
        self.assertEqual(rc, 0, text)
        self.assertNotIn("illegal byte sequence", text)
        self.assertNotIn("Traceback", text)
        self.assertIn("✓ project intake заполнен", text)
        self.assertEqual([p.name for p in tmp.iterdir() if p.name.startswith(".!")], [])
        (tmp / "seo-cycle.yaml").read_text(encoding="utf-8")  # valid UTF-8 or UnicodeDecodeError
        self.assertTrue((tmp / "seo" / "project-intake.yaml").exists())
        validate = subprocess.run(
            [sys.executable, str(VALIDATE), "seo-cycle.yaml"], cwd=tmp, capture_output=True, text=True,
            env=base_env(LC_ALL=locale), check=False,
        )
        self.assertEqual(validate.returncode, 0, validate.stdout + validate.stderr)
        return tmp

    def test_lc_all_c(self) -> None:
        self._run_init("C")

    def test_lc_all_posix(self) -> None:
        self._run_init("POSIX")

    def test_sed_in_place_keeps_cyrillic_bytes_intact(self) -> None:
        """Byte-for-byte: lines the wizard does not touch stay identical in C vs UTF-8 locale."""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-t099-sed-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        # bash 3.2 (macOS) cannot `source <(...)`, hence the temp file.
        script = (
            "f=$(mktemp); sed -n '/^sed_in_place() {/,/^}/p' \"$1\" > \"$f\"; source \"$f\"; rm -f \"$f\"; "
            "cp \"$2\" \"$3\"; sed_in_place 's|^project_type: ecommerce|project_type: blog|' \"$3\""
        )
        results = []
        for locale in ("C", "en_US.UTF-8"):
            target = tmp / f"{locale}.yaml"
            subprocess.run(
                ["bash", "-c", script, "_", str(INIT_PROJECT), str(TEMPLATE), str(target)],
                check=True, env=base_env(LC_ALL=locale),
            )
            results.append(target.read_bytes())
        self.assertEqual(results[0], results[1])
        original = TEMPLATE.read_bytes().splitlines()
        edited = results[0].splitlines()
        self.assertEqual(len(original), len(edited))
        changed = [i for i, (a, b) in enumerate(zip(original, edited, strict=True)) if a != b]
        self.assertEqual(len(changed), 1)
        self.assertTrue(any(b > 0x7F for b in results[0]), "template must contain non-ASCII bytes for this test to mean anything")


if __name__ == "__main__":
    unittest.main()
