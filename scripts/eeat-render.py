#!/usr/bin/env python3
"""
eeat-render.py — превращает fact_check_log из frontmatter публикации в видимый
на странице trust-блок «Источники». Это прямой E-E-A-T сигнал (Trust): читатель
и поисковик видят, что технические утверждения опираются на нормативы/ТУ.

Канонический формат fact_check_log (в frontmatter publish.md / entity-map):
    fact_check_log:
      - claim: "ОСП-3 — несущий и влагостойкий класс плиты"
        source: "ГОСТ Р 56309-2014"
        url: "https://..."          # опционально
        verdict: достоверно          # достоверно | частично | спорно | недостоверно
        checked: 2026-05-28

Рендерит HTML-блок (для вставки в конец статьи). В блок попадают только
уникальные источники с verdict достоверно/частично. Утверждения с verdict
спорно/недостоверно НЕ показываются (их формулировку нужно править в тексте,
а не «подтверждать» источником).

Использование:
    python3 eeat-render.py path/to/publish.md            # печать HTML в stdout
    python3 eeat-render.py path/to/publish.md --heading "Источники и нормативы"
"""

from __future__ import annotations
import argparse, html, pathlib, sys

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. `pip3 install pyyaml`", file=sys.stderr)
    sys.exit(2)

SHOW_VERDICTS = {"достоверно", "частично", "verified", "partial"}


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    return yaml.safe_load(text[3:end]) or {}


def render(log: list, heading: str, intro: str) -> str:
    # Дедуп по source, сохраняя порядок; берём первый url
    seen: dict[str, dict] = {}
    latest_check = ""
    for item in log:
        if not isinstance(item, dict):
            continue
        verdict = str(item.get("verdict", "")).strip().lower()
        if verdict and verdict not in SHOW_VERDICTS:
            continue
        src = (item.get("source") or "").strip()
        if not src:
            continue
        if src not in seen:
            seen[src] = {"url": item.get("url")}
        if item.get("checked"):
            latest_check = max(latest_check, str(item["checked"]))

    if not seen:
        return ""

    lines = ['<section class="fact-sources" aria-label="Источники">']
    lines.append(f"  <h2>{html.escape(heading)}</h2>")
    lines.append(f"  <p>{html.escape(intro)}</p>")
    lines.append("  <ul>")
    for src, meta in seen.items():
        if meta.get("url"):
            lines.append(f'    <li><a href="{html.escape(meta["url"])}" rel="nofollow">{html.escape(src)}</a></li>')
        else:
            lines.append(f"    <li>{html.escape(src)}</li>")
    lines.append("  </ul>")
    if latest_check:
        lines.append(f'  <p class="fact-check-date">Проверка фактов: {html.escape(latest_check)}.</p>')
    lines.append("</section>")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="publish.md / entity-map с fact_check_log в frontmatter")
    ap.add_argument("--heading", default="Источники")
    ap.add_argument("--intro", default="Материал подготовлен с опорой на действующие нормативные документы и технические условия производителей:")
    args = ap.parse_args()

    p = pathlib.Path(args.file)
    if not p.exists():
        print(f"ERROR: файл не найден: {args.file}", file=sys.stderr)
        return 2
    fm = parse_frontmatter(p.read_text(encoding="utf-8"))
    log = fm.get("fact_check_log")
    if not log:
        print(f"# нет fact_check_log в {p.name} — блок не сгенерирован", file=sys.stderr)
        return 1
    out = render(log, args.heading, args.intro)
    if not out:
        print("# нет источников с verdict достоверно/частично", file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
