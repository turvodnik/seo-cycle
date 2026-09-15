"""A fake `ai-secret` broker for tests (T-108).

Every test of the secrets canon runs against this stub, never against the
real macOS Keychain: the stub is a small Python script written into a temp
directory as an executable named `ai-secret`, and the test builds a PATH
that contains that directory plus the bare system dirs — so whatever the
developer machine has in ~/.local/bin is invisible to the suite.

Behaviour (mirrors the real CLI's contract as far as the tests need it):
  list <scope>          -> "scope: X", "keys: N", one name per line
  set <scope> <name>    -> reads ONE line from stdin, stores it in its own
                           store file, logs "set <scope> <name>" (names only)
  run <scope> -- cmd..  -> logs "run <scope>", exports the stored names of
                           `global` + scope into the child, execs the command

The store file is the stub's "keychain" (values may sit there — that is
the point of a keychain); the LOG file never receives a value, and the
tests assert on the log, on stdout/stderr, and on the project's .env.
"""

from __future__ import annotations

import os
import pathlib
import stat
import sys

STUB_SOURCE = r'''
import os, sys, pathlib
HERE = pathlib.Path(__file__).resolve().parent
LOG = HERE / "ai-secret.log"
STORE = HERE / "store.txt"

def log(line):
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")

def load():
    data = {}
    if STORE.exists():
        for raw in STORE.read_text(encoding="utf-8").splitlines():
            key, _, value = raw.partition("=")
            data[key] = value
    return data

args = sys.argv[1:]
if len(args) == 2 and args[0] == "list":
    scope = args[1]
    names = sorted(k.split("/", 1)[1] for k in load() if k.startswith(scope + "/"))
    log(f"list {scope}")
    print(f"scope: {scope}")
    print(f"keys: {len(names)}")
    for n in names:
        print(n)
    sys.exit(0)
if len(args) == 3 and args[0] == "set":
    scope, name = args[1], args[2]
    value = sys.stdin.readline().strip()
    if not value:
        log(f"set {scope} {name} EMPTY")
        print("empty value — nothing stored", file=sys.stderr)
        sys.exit(13)
    data = load()
    outcome = "updated" if f"{scope}/{name}" in data else "added"
    data[f"{scope}/{name}"] = value
    STORE.write_text("".join(f"{k}={v}\n" for k, v in data.items()), encoding="utf-8")
    log(f"set {scope} {name}")
    print(f"stored: {scope}/{name} ({outcome})")
    sys.exit(0)
if len(args) >= 4 and args[0] == "run" and args[2] == "--":
    scope = args[1]
    log(f"run {scope}")
    env = dict(os.environ)
    data = load()
    for sc in ("global", scope):
        for key, value in data.items():
            if key.startswith(sc + "/"):
                env[key.split("/", 1)[1]] = value
    env["AI_SECRET_STUB_RAN"] = scope
    os.execvpe(args[3], args[3:], env)
print("usage", file=sys.stderr)
sys.exit(64)
'''


def install_stub(directory: pathlib.Path) -> pathlib.Path:
    """Write the executable stub into `directory` and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    stub = directory / "ai-secret"
    # Shebang = the interpreter running the tests: the isolated PATH below has
    # no guarantee of a `python3`.
    stub.write_text(f"#!{sys.executable}" + STUB_SOURCE, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def stub_log(directory: pathlib.Path) -> str:
    log = directory / "ai-secret.log"
    return log.read_text(encoding="utf-8") if log.exists() else ""


def seed_store(directory: pathlib.Path, entries: dict[str, str]) -> None:
    """Pre-register names in the stub keychain: {"scope/NAME": "value"}."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "store.txt").write_text(
        "".join(f"{k}={v}\n" for k, v in entries.items()), encoding="utf-8",
    )


def isolated_path(*stub_dirs: pathlib.Path) -> str:
    """PATH with only the stub dir(s) and bare system dirs — no real ai-secret."""
    return os.pathsep.join([*(str(d) for d in stub_dirs), "/usr/bin", "/bin"])


def clean_env(*, path: str, extra: dict[str, str] | None = None, drop_prefixes: tuple[str, ...] = ()) -> dict[str, str]:
    """Copy of os.environ with PATH replaced and secret-looking names dropped."""
    drop = ("YANDEX_", "GOOGLE_", "GBP_", "PERPLEXITY", "TELEGRAM_", "WP_", "AI_SECRET_", "SEO_CYCLE_SECRETS",
            *drop_prefixes)
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    env["PATH"] = path
    if extra:
        env.update(extra)
    return env
