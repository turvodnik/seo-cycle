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
import datetime as dt
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

# Реестр ложных срабатываний (T-021, _tools/AGENTS.md §5): запись обязана
# нести все эти поля, scope обязан быть привязан к месту в дереве (см. _scope_is_anchored).
LEDGER_REQUIRED_FIELDS = ("fingerprint", "scope", "rule", "reason", "recognized_by", "recognized_at", "review_after")
SHA256_EMPTY = hashlib.sha256(b"").hexdigest()
# ЯКОРНЫЙ критерий узости scope (T-021, четвёртый гейт 2026-08-14). История
# трёх отвергнутых версий, каждая — урок:
#   1) чёрный список литералов ("*", "**") — перечень плохих форм бесконечен,
#      пробивался "*/*", "?*", "[a-z]*";
#   2) «в сегменте остался буквенно-цифровой ОСТАТОК после вычёркивания
#      глоб-символов» — пробивался маской "*e*" (остаток "e" есть, но fnmatch
#      не считает "/" особым символом, и маска совпадает с любым путём, где
#      встречается буква "e" — 364 из 400 файлов реального дерева);
#   3) «хотя бы ОДИН сегмент полностью литерален, где угодно в маске» —
#      пробивался маской "**/.env": сегмент ".env" литерален, но привязывает
#      подавление к ИМЕНИ файла, а не к МЕСТУ в дереве, и гасит .env на любой
#      глубине в любом каталоге (тот же класс: "*/prod/*", "**/x/**").
# Действующий инвариант: ПЕРВЫЙ сегмент (до первого "/") обязан быть
# ПОЛНОСТЬЮ свободен от глоб-символов (*, ?, [, ]) И содержать буквенно-
# цифровой символ или "_". Первое условие даёт якорь — маска не может
# «плавать» по дереву; второе обязательно, иначе якорем считается ".." или
# "." и пролезают "../../*e*", "./prod/**".
_GLOB_META_CHARS = "*?[]"
# Строгий формат review_after: date.fromisoformat() тише документа —
# принимает и "20270101" (без дефисов) начиная с Python 3.11.
_REVIEW_AFTER_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _scope_is_anchored(scope: object) -> bool:
    """True, только если scope — непустая строка, ПЕРВЫЙ сегмент которой (до
    первого "/") ПОЛНОСТЬЮ свободен от глоб-символов (*, ?, [, ]) и при этом
    содержит букву/цифру/"_".

    Цена якоря названа явно: невалидны и одиночная маска "*.env" (нужен
    "prod/*.env"), и «эта проблема во всех папках тестов» — "**/tests/**" и
    "./prod/**" тоже отвергаются, такие исключения придётся записывать по
    местам ("src/tests/**", "prod/**"). Это осознанный fail-closed: маска,
    не привязанная к месту, гасит совпадение по всему дереву."""
    if not isinstance(scope, str) or not scope:
        return False
    head = scope.split("/", 1)[0]
    if any(ch in _GLOB_META_CHARS for ch in head):
        return False
    return any(ch.isalnum() or ch == "_" for ch in head)

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

    Здесь только СТРУКТУРНАЯ целостность файла: путь не существует (битая
    симлинка, опечатка), файл нечитаем (права/`chmod 000`), битый YAML,
    не-объект верхнего уровня, `entries` не список или элемент списка не
    объект (скаляр вместо записи) — фатальны для гейта перед коммитом,
    поэтому явная ошибка и exit 2, а не голый traceback и не тихий пустой
    реестр. Решение про несуществующий путь (гейт T-021, повторный заход):
    `--ledger` всегда передаётся явно оператором/скриптом — значит опечатка
    в пути обязана быть услышана, а не тихо привести к «реестр применён,
    но пуст» (оператор иначе думает, что защита работает). Смысловая
    валидация отдельной записи (обязательные поля, узость scope, запрет
    fingerprint пустой строки, срок пересмотра) — в reconcile(), она же
    используется тестами напрямую на списках без файла.
    """
    try:
        import yaml
    except ImportError:
        print("ERROR: для --ledger нужен PyYAML. `pip3 install pyyaml`", file=sys.stderr)
        raise SystemExit(2)
    if not path.exists():
        print(f"ERROR: реестр не найден: {path}", file=sys.stderr)
        raise SystemExit(2)
    try:
        # UnicodeDecodeError — подкласс ValueError, а не OSError: без него
        # реестр в чужой кодировке давал голый traceback вместо ERROR/exit 2.
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: реестр нечитаем: {path}: {exc}", file=sys.stderr)
        raise SystemExit(2)
    # Пустой/битый реестр НЕ считается пустым молча: «не смог прочитать» не
    # равно «прочитал, и там чисто». Легальная пустота записывается явно —
    # `entries: []`.
    if raw is None:
        print(f"ERROR: реестр нечитаем: {path}: файл не содержит YAML-данных "
              f"(пустой или только комментарии); пустой реестр записывается явно: 'entries: []'",
              file=sys.stderr)
        raise SystemExit(2)
    if not isinstance(raw, dict):
        print(f"ERROR: реестр нечитаем: {path}: верхний уровень должен быть объектом (dict), "
              f"получено {type(raw).__name__}", file=sys.stderr)
        raise SystemExit(2)
    if "entries" not in raw:
        print(f"ERROR: реестр нечитаем: {path}: нет ключа 'entries' (опечатка в имени ключа?); "
              f"пустой реестр записывается явно: 'entries: []'", file=sys.stderr)
        raise SystemExit(2)
    entries = raw["entries"]
    if entries is None:
        print(f"ERROR: реестр нечитаем: {path}: 'entries' пуст (null); "
              f"пустой реестр записывается явно: 'entries: []'", file=sys.stderr)
        raise SystemExit(2)
    if not isinstance(entries, list):
        print(f"ERROR: реестр нечитаем: {path}: 'entries' должен быть списком, "
              f"получено {type(entries).__name__}", file=sys.stderr)
        raise SystemExit(2)
    for item in entries:
        if not isinstance(item, dict):
            print(f"ERROR: реестр нечитаем: {path}: запись реестра должна быть объектом (dict), "
                  f"получено {type(item).__name__}: {item!r}", file=sys.stderr)
            raise SystemExit(2)
    return entries


def validate_ledger_entry(entry: dict, today: dt.date) -> str | None:
    """Смысловая проверка одной записи реестра (_tools/AGENTS.md §5).

    None — запись валидна и действует. Иначе — причина отказа (строка):
    запись с такой причиной НЕ участвует в подавлении находок (отвергается,
    а не применяется частично). Причины: не хватает обязательного поля;
    scope не привязан к месту в дереве (якорный критерий — см.
    _scope_is_anchored: требуем, чтобы ПЕРВЫЙ сегмент пути был полностью
    литеральным, а не «хоть один литеральный сегмент где угодно» — последнее
    пробивалось маской "**/.env", привязывающей подавление к имени файла, а
    не к месту; ДОКАЗАТЕЛЬСТВО узости вместо перечня плохих строк; заодно
    отвергает нестроковый scope — иначе fnmatch() в reconcile() падает
    TypeError на int/bool/списке); fingerprint == sha256("") (подавил бы
    находку без реального совпадения — воспроизведённый гейтом обход
    защиты); review_after не похож на дату или уже в прошлом (протухший
    срок — запись не подавляет, только явно предупреждает, см. reconcile()).
    """
    if not isinstance(entry, dict):
        return f"запись не объект (dict), получено {type(entry).__name__}"
    missing = [field for field in LEDGER_REQUIRED_FIELDS if not entry.get(field)]
    if missing:
        return "не хватает обязательных полей: " + ", ".join(missing)
    if not _scope_is_anchored(entry["scope"]):
        return (f"scope не привязан к месту в дереве: ПЕРВЫЙ сегмент пути (до первого '/') "
                f"обязан быть ПОЛНОСТЬЮ без глоб-символов *?[] и содержать букву/цифру/_ — "
                f"например 'prod/*.env' вместо '*.env' и 'src/tests/**' вместо '**/tests/**' "
                f"(получено: {entry['scope']!r})")
    if entry["fingerprint"] == SHA256_EMPTY:
        return "fingerprint == sha256('') — отвергнуто (не может ссылаться на настоящее совпадение)"
    # date.fromisoformat() принимает и компактный формат без дефисов
    # ("20270101") начиная с Python 3.11 — тише документированного
    # "YYYY-MM-DD" (README/шаблон/это же сообщение об ошибке); явная
    # проверка формата не даёт записи с "тихим" отклонением от контракта.
    if not _REVIEW_AFTER_RE.match(str(entry["review_after"])):
        return f"review_after не похож на дату YYYY-MM-DD: {entry['review_after']!r}"
    try:
        review_after = dt.date.fromisoformat(str(entry["review_after"]))
    except ValueError:
        return f"review_after не похож на дату YYYY-MM-DD: {entry['review_after']!r}"
    if review_after < today:
        return f"review_after истёк ({review_after.isoformat()} < {today.isoformat()}) — запись просрочена"
    return None


def reconcile(findings: list[dict[str, str]], ledger: list[dict],
              today: dt.date | None = None) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Двусторонняя сверка находок с реестром.

    Возвращает (активные_находки, подавленные_находки, протухшие_записи,
    отвергнутые_записи). Запись подавляет находку, если совпал fingerprint
    (sha256 совпадения) И находка попадает в scope (glob по относительному
    пути) И правило совпадает (или rule записи — "*"). Только записи,
    прошедшие validate_ledger_entry() (полные, узкие, не просроченные),
    вообще допускаются к сверке — отвергнутые никогда никого не подавляют,
    только сообщают о себе через `rejected`. Запись, прошедшая проверку, но
    не подавившая ни одной находки за этот прогон, — протухшая: она либо
    перестала что-либо совпадать (код почистили), либо никогда не была
    точной — в обоих случаях реестр должен явно спросить о пересмотре, а не
    молчать вечно.
    """
    today = today or dt.date.today()
    eligible: list[dict] = []
    rejected: list[dict] = []
    for entry in ledger:
        reason = validate_ledger_entry(entry, today)
        if reason is not None:
            rejected.append({"entry": entry, "reason": reason})
        else:
            eligible.append(entry)

    active: list[dict] = []
    suppressed: list[dict] = []
    # Ключ — ПОРЯДКОВЫЙ НОМЕР записи, не её "id": два дубля одного id (или две
    # записи без id с общим fingerprint и разными scope — штатный сценарий
    # «тот же ложный текст в двух местах») схлопывались в один ключ, и
    # совпадение одной навсегда прятало мёртвую вторую от двусторонней сверки.
    matched_idx: set[int] = set()

    for f in findings:
        hit_idx = None
        fp = f.get("fingerprint")
        if fp is not None:
            for idx, entry in enumerate(eligible):
                if entry["fingerprint"] != fp:
                    continue
                if not fnmatch.fnmatch(f["file"], entry["scope"]):
                    continue
                rule = entry["rule"]
                if rule != "*" and rule != f["rule"]:
                    continue
                hit_idx = idx
                break
        if hit_idx is not None:
            matched_idx.add(hit_idx)
            suppressed.append({**f, "ledger_id": eligible[hit_idx].get("id")})
        else:
            active.append(f)

    stale = [e for idx, e in enumerate(eligible) if idx not in matched_idx]
    return active, suppressed, stale, rejected


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
    rejected: list[dict] = []
    if args.ledger is not None:
        ledger = load_ledger(args.ledger)
        findings, suppressed, stale, rejected = reconcile(findings, ledger)

    for r in rejected:
        entry = r["entry"]
        eid = entry.get("id", "?") if isinstance(entry, dict) else "?"
        print(f"⚠ запись реестра '{eid}' отклонена: {r['reason']}", file=sys.stderr)

    # fingerprint — хеш РЕАЛЬНОГО совпадения (для generic_assignment/env_value
    # словарно проверяем офлайн — пограничье §5). Печатаем только когда явно
    # запрошен --ledger (нужен, чтобы завести запись реестра); без --ledger —
    # никогда, и без --ledger вывод обязан остаться побайтно прежним (T-021
    # фикс-заход по гейту).
    show_fp = args.ledger is not None
    findings_out = findings if show_fp else [{k: v for k, v in f.items() if k != "fingerprint"} for f in findings]
    suppressed_out = suppressed if show_fp else [{k: v for k, v in s.items() if k != "fingerprint"} for s in suppressed]

    if args.format == "json":
        payload: dict = {"findings": findings_out, "count": len(findings)}
        if args.ledger is not None:
            payload["suppressed"] = suppressed_out
            payload["stale_ledger_entries"] = stale
            payload["rejected_ledger_entries"] = [
                {"id": (r["entry"].get("id", "?") if isinstance(r["entry"], dict) else "?"), "reason": r["reason"]}
                for r in rejected]
        # default=str: PyYAML парсит незакавыченные ISO-даты в реестре
        # (`recognized_at: 2026-08-13` — ровно формат из README/шаблона) в
        # datetime.date, что json.dumps не умеет сериализовать нативно
        # (TypeError, найдено повторным гейтом T-021). str(date(...)) даёт
        # тот же ISO-формат, что и исходная запись в YAML.
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
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
