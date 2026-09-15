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


def utf8_locale() -> str | None:
    """A UTF-8 locale present on this machine (macOS: en_US.UTF-8, Linux CI: C.UTF-8)."""
    try:
        available = subprocess.run(["locale", "-a"], capture_output=True, text=True, check=False).stdout.split()
    except OSError:
        return None
    lower = {name.lower().replace("-", ""): name for name in available}
    for candidate in ("en_us.utf8", "c.utf8"):
        if candidate in lower:
            return lower[candidate]
    return None


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
        self.assertEqual(proc.returncode, 2, proc.stderr)  # environment error, like «config not found»
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

    def test_invalid_utf8_answer_is_asked_again_not_written(self) -> None:
        tmp = self._project()
        # Dangling lead byte (backspace over a Cyrillic char), then a valid answer.
        answers = b"\xd0saas\n" + b"saas\n" + b"\n" * 120
        rc, out = run_with_tty(
            [sys.executable, str(INTAKE_WIZARD), "seo-cycle.yaml", "--interactive", "--write"],
            tmp, answers, base_env(),
        )
        text = out.decode("utf-8", "replace")
        self.assertEqual(rc, 0, text)
        self.assertIn("невалидный UTF-8", text)
        raw = (tmp / "seo" / "project-intake.yaml").read_bytes()
        self.assertNotIn("\ufffd".encode("utf-8"), raw)
        intake = yaml.safe_load(raw.decode("utf-8"))
        self.assertEqual(intake["business"]["project_type"], "saas")

    def test_dangling_byte_does_not_poison_later_answers(self) -> None:
        """Review R8: a lone lead byte flushed by Ctrl-D must cost one re-ask, not every answer after it."""
        tmp = self._project()
        answers = b"\xd0\x04saas\n" + b"\n" * 120
        rc, out = run_with_tty(
            [sys.executable, str(INTAKE_WIZARD), "seo-cycle.yaml", "--interactive", "--write"],
            tmp, answers, base_env(),
        )
        text = out.decode("utf-8", "replace")
        self.assertEqual(rc, 0, text)
        self.assertEqual(text.count("невалидный UTF-8"), 1, text)
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
        # T-107 renumbered the wizard to 7 mandatory questions + a switch.
        # Q1-2 defaults, Q3 project_type typed as «blog» after a backspace over
        # a Cyrillic char (one dangling lead byte, exactly the #28 report),
        # Q4-7 defaults, Q8 "y" (switch) → Q9-22 defaults (brand/budget/images),
        # Q23 "y" → detailed intake reads /dev/tty (#29), then defaults for
        # every intake question, Q24 (apply profile) and the validate prompt.
        answers = b"\n" * 2 + b"\xd0blog\n" + b"\n" * 4 + b"y\n" + b"\n" * 14 + b"y\n" + b"\n" * 120
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

    def test_utf8_locale_the_one_from_the_bug_report(self) -> None:
        """The reporter's locale: on 89a0218 this is rc=1 + `illegal byte sequence` + a temp file."""
        locale = utf8_locale()
        if locale is None:
            self.skipTest("no UTF-8 locale installed")
        self._run_init(locale)

    def test_intake_failure_is_reported_not_masked(self) -> None:
        """Ctrl-D on the first intake question: init must say «не заполнен», never «✓»."""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-t099-init-eof-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        # T-107: Q1-7 defaults, Q8 "y" (switch) → Q9-22 defaults, Q23 "y" (detailed
        # intake toggle), then Ctrl-D on the first intake question itself.
        answers = b"\n" * 7 + b"y\n" + b"\n" * 14 + b"y\n" + b"\x04" + b"\n" * 5
        rc, out = run_with_tty(["bash", str(INIT_PROJECT)], tmp, answers, base_env(LC_ALL="C"))
        text = out.decode("utf-8", "replace")
        self.assertEqual(rc, 0, text)
        self.assertNotIn("Traceback", text)
        self.assertIn("ℹ project intake не заполнен", text)
        self.assertNotIn("✓ project intake заполнен", text)

    def test_sed_in_place_survives_invalid_utf8_in_utf8_locale(self) -> None:
        """Issue #28 at sed level: garbage byte written by call 1 must not abort call 2 (LC_ALL=C inside)."""
        locale = utf8_locale()
        if locale is None:
            self.skipTest("no UTF-8 locale installed")
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-t099-sed-utf8-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        target = tmp / "t.yaml"
        script = (
            "f=$(mktemp); sed -n '/^sed_in_place() {/,/^}/p' \"$1\" > \"$f\"; source \"$f\"; rm -f \"$f\"; "
            "cp \"$2\" \"$3\"; "
            "sed_in_place \"s|^project_type: ecommerce|project_type: $(printf 'b\\xd0log')|\" \"$3\" && "
            "sed_in_place 's|^cms: wordpress|cms: static|' \"$3\""
        )
        proc = subprocess.run(
            ["bash", "-c", script, "_", str(INIT_PROJECT), str(TEMPLATE), str(target)],
            capture_output=True, text=True, env=base_env(LC_ALL=locale), check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("illegal byte sequence", proc.stderr)
        self.assertEqual([p.name for p in tmp.iterdir() if p.name.startswith(".!")], [])
        self.assertIn(b"cms: static", target.read_bytes())

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
