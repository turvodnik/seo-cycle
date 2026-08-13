#!/usr/bin/env python3
"""secret-scan.py — поиск утёкших значений секретов в дереве проекта.

Политика seo-cycle: значения ключей живут в macOS Keychain (ai-secret),
в файлах — только ИМЕНА переменных. Этот скрипт — enforcement: гоняется
перед коммитом/публикацией (`seo-cycle secret-scan`) и падает (exit 1),
если в tracked-подобных файлах найдено похожее на реальное значение.

Значения НИКОГДА не печатаются: в отчёте file:line, правило и маска
(первые 3 символа + «…»). Строку можно осознанно разрешить inline-прагмой
`secret-scan: allow` в той же строке (например, документационный пример).

Использование:
    python3 secret-scan.py [PATH ...] [--format text|json] [--max-bytes N]

Exit: 0 чисто, 1 findings, 2 ошибка вызова.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import pathlib
import re
import sys

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".ruff_cache", ".pytest_cache", "artifacts", "cache", "tmp", "backups",
}
SKIP_SUFFIXES = {
    ".db", ".sqlite", ".sqlite3", ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".ico", ".pdf", ".zip", ".gz", ".woff", ".woff2", ".mp4", ".mov", ".key",
}
ALLOW_PRAGMA = "secret-scan: allow"

RULES: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("google_oauth", re.compile(r"\bya29\.[0-9A-Za-z_\-]{20,}")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b")),
    ("stripe_key", re.compile(r"\b[rs]k_(?:live|test)_[0-9a-zA-Z]{16,}\b")),
    ("telegram_bot", re.compile(r"\b\d{8,10}:AA[0-9A-Za-z_\-]{33}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}\b")),
    ("generic_assignment", re.compile(
        r"(?i)\b(?:password|passwd|secret|token|api[_-]?key|app[_-]?password|client[_-]?secret)\b"
        r"\s*[=:]\s*['\"]?(?!\$\{|\$[A-Z_]|ENV\b|env\b|<)[A-Za-z0-9+/_\-]{20,}")),
]
# .env-подобные файлы: любое непустое значение = нарушение политики
ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")
ENV_PLACEHOLDERS = re.compile(r"^(['\"]?)(?:|\.\.\.|xxx+|<[^>]*>|\$\{[^}]*\}|change_?me|todo|none|auto|claude|codex|direct|codex_external)\1$", re.IGNORECASE)


def mask(value: str) -> str:
    return value[:3] + "…" if len(value) > 3 else "…"


def fingerprint(value: str) -> str:
    """sha256 совпадения — необратимый отпечаток для реестра ложных срабатываний.

    ЗАПРЕТ: в реестр (false-positives.yaml) заносится только этот хеш и
    координаты, никогда — значение секрета. Хеш совпадения секретом не
    является (не позволяет восстановить исходную строку), но реестр всё
    равно предназначен ИСКЛЮЧИТЕЛЬНО для доказанно ложных совпадений —
    заносить туда запись, скрывающую настоящий секрет («потом уберём»),
    запрещено.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_binary(path: pathlib.Path, sniff: int = 1024) -> bool:
    try:
        return b"\0" in path.open("rb").read(sniff)
    except OSError:
        return True


def scan_file(path: pathlib.Path, rel: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    is_env_file = path.name.startswith(".env") and not path.name.startswith(".env.example")
    for lineno, line in enumerate(text.splitlines(), 1):
        if ALLOW_PRAGMA in line:
            continue
        for rule, pattern in RULES:
            m = pattern.search(line)
            if m:
                findings.append({"file": rel, "line": str(lineno), "rule": rule, "match": mask(m.group(0)),
                                 "fingerprint": fingerprint(m.group(0))})
                break
        else:
            if is_env_file:
                m = ENV_LINE.match(line)
                if m and not ENV_PLACEHOLDERS.match(m.group(2)):
                    findings.append({"file": rel, "line": str(lineno), "rule": "env_value",
                                     "match": f"{m.group(1)}={mask(m.group(2))}",
                                     "fingerprint": fingerprint(m.group(2))})
    return findings


def scan_tree(root: pathlib.Path, max_bytes: int) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if root.is_file():
        return scan_file(root, str(root))
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            if path.stat().st_size > max_bytes or is_binary(path):
                continue
        except OSError:
            continue
        findings.extend(scan_file(path, str(path.relative_to(root))))
    return findings


def load_ledger(path: pathlib.Path) -> list[dict]:
    """Реестр известных ложных срабатываний (см. .agents/security/false-positives.yaml).

    Формат и запрет вносить настоящие секреты — README/AGENTS.md проекта,
    а не этот скрипт; здесь только механика сверки.
    """
    try:
        import yaml
    except ImportError:
        print("ERROR: для --ledger нужен PyYAML. `pip3 install pyyaml`", file=sys.stderr)
        raise SystemExit(2)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("entries") or []


def reconcile(findings: list[dict[str, str]], ledger: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Двусторонняя сверка находок с реестром.

    Возвращает (активные_находки, подавленные_находки, протухшие_записи).
    Запись подавляет находку, если совпал fingerprint (sha256 совпадения) И
    находка попадает в scope (glob по относительному пути) И правило
    совпадает (или scope/rule записи — "*"). Запись, которая не подавила ни
    одной находки за этот прогон, — протухшая: она либо перестала что-либо
    совпадать (код почистили), либо никогда не была точной — в обоих
    случаях реестр должен явно спросить о пересмотре, а не молчать вечно.
    """
    active: list[dict] = []
    suppressed: list[dict] = []
    matched_ids: set[str] = set()

    for f in findings:
        hit = None
        for entry in ledger:
            if entry.get("fingerprint") != f.get("fingerprint"):
                continue
            scope = entry.get("scope", "*")
            if scope != "*" and not fnmatch.fnmatch(f["file"], scope):
                continue
            rule = entry.get("rule", "*")
            if rule != "*" and rule != f["rule"]:
                continue
            hit = entry
            break
        if hit is not None:
            matched_ids.add(hit.get("id", hit.get("fingerprint")))
            suppressed.append({**f, "ledger_id": hit.get("id")})
        else:
            active.append(f)

    stale = [e for e in ledger if e.get("id", e.get("fingerprint")) not in matched_ids]
    return active, suppressed, stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", default=["."], help="файлы/каталоги (default: .)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--max-bytes", type=int, default=2_000_000)
    parser.add_argument("--ledger", type=pathlib.Path, default=None,
                         help="реестр известных ложных срабатываний (.agents/security/false-positives.yaml)")
    args = parser.parse_args(argv)

    findings: list[dict[str, str]] = []
    for raw in args.paths:
        root = pathlib.Path(raw)
        if not root.exists():
            print(f"ERROR: путь не найден: {raw}", file=sys.stderr)
            return 2
        findings.extend(scan_tree(root, args.max_bytes))

    suppressed: list[dict] = []
    stale: list[dict] = []
    if args.ledger is not None:
        ledger = load_ledger(args.ledger)
        findings, suppressed, stale = reconcile(findings, ledger)

    if args.format == "json":
        print(json.dumps({"findings": findings, "count": len(findings),
                          "suppressed": suppressed, "stale_ledger_entries": stale},
                         ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print(f"✗ {f['file']}:{f['line']} [{f['rule']}] {f['match']}")
        if suppressed:
            print(f"· подавлено записями реестра: {len(suppressed)}")
        for e in stale:
            print(f"⚠ протухшая запись реестра {e.get('id', '?')} (rule={e.get('rule')}, "
                  f"scope={e.get('scope')}, признал: {e.get('recognized_by')} {e.get('recognized_at')}) — "
                  "больше ни на что не совпадает, рассмотри удаление")
        print(("✗ findings: %d — значения перенеси в Keychain (ai-secret import/set) и удали из файлов"
               % len(findings)) if findings else "✓ секретных значений не найдено")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
