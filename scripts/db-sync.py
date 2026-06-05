#!/usr/bin/env python3
"""
db-sync.py — собирает разрозненные артефакты проекта (CSV/JSON) в единую
SQLite-БД. Это фундамент Этапа 1: единая точка правды для будущих дашбордов
(Obsidian/Metabase/Next.js) и алертов, без переписывания источников.

Источники (любой может отсутствовать — пропускается):
  CSV → таблица по имени файла, колонки = заголовок CSV (full refresh):
    seo/keyword-queue.csv        → keyword_queue
    seo/source-attribution.csv   → source_attribution
    seo/publish-log.csv          → publish_log
  JSON:
    seo/monitoring/**/*-snapshot.json и seo/cycles/**/09-monitoring/*.json
      → positions (snapshot_date, engine, query, position, clicks, impressions, url)
    seo/research/*/_usage.json + seo/usage/usage-ledger.jsonl
      → api_usage (service, month, category, spend, tokens, requests, credits)

Путь к БД: data_store.path из seo-cycle.yaml (default ./seo/seo.db).
Idempotent: каждый запуск пересоздаёт таблицы из текущих файлов.

Использование:
    python3 ~/.codex/skills/seo-cycle/scripts/db-sync.py [--db PATH] [--root DIR]
"""

from __future__ import annotations
import argparse, csv, glob, json, pathlib, re, sqlite3, sys

try:
    import yaml
except ImportError:
    yaml = None

CONFIG_PATHS = ["seo-cycle.yaml", ".seo-cycle.yaml", "seo/seo-cycle.yaml", ".claude/seo-cycle.yaml"]
CSV_SOURCES = {
    "keyword_queue": "seo/keyword-queue.csv",
    "source_attribution": "seo/source-attribution.csv",
    "publish_log": "seo/publish-log.csv",
}


def load_cfg(root: pathlib.Path) -> dict:
    if yaml:
        for rel in CONFIG_PATHS:
            p = root / rel
            if p.exists():
                return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}


def find_db_path(root: pathlib.Path, cfg: dict, override: str | None) -> pathlib.Path:
    if override:
        return pathlib.Path(override)
    ds = (cfg.get("data_store") or {}).get("path")
    return (root / ds) if ds else (root / "seo" / "seo.db")


def dashboard_path(cfg: dict) -> pathlib.Path | None:
    """Путь к md-дашборду в Obsidian vault, если obsidian включён с dashboards."""
    ob = cfg.get("obsidian") or {}
    if not (ob.get("enabled") and ob.get("dashboards")):
        return None
    vault = ob.get("central_vault")
    if not vault:
        return None
    sub = ob.get("project_subfolder", "")
    return pathlib.Path(vault) / sub / "_Dashboards" / "SEO-Automation.md"


def write_md_dashboard(conn, out: pathlib.Path, project: str):
    import datetime
    def q(sql):
        try:
            return conn.execute(sql).fetchall()
        except Exception:
            return []
    lines = [f"# SEO Automation — {project}", "",
             f"> Автогенерация `db-sync.py` · {datetime.datetime.now():%Y-%m-%d %H:%M}", ""]

    # Очередь ключей по статусам
    rows = q("SELECT status, COUNT(*) FROM keyword_queue GROUP BY status")
    if rows:
        lines += ["## Очередь ключей", "", "| Статус | Кол-во |", "|---|---|"]
        lines += [f"| {s or '—'} | {n} |" for s, n in rows]
        lines.append("")

    # API usage
    rows = q("SELECT service, month, spent_usd, rows FROM api_usage")
    if rows:
        lines += ["## Расход API", "", "| Сервис | Месяц | $ | Строк |", "|---|---|---|---|"]
        lines += [f"| {s} | {m} | {sp} | {r} |" for s, m, sp, r in rows]
        lines.append("")

    # Топ просадок / позиций (если есть)
    rows = q("SELECT query, position, clicks FROM positions WHERE position>0 ORDER BY position LIMIT 15")
    if rows:
        lines += ["## Топ-15 позиций", "", "| Запрос | Позиция | Клики |", "|---|---|---|"]
        lines += [f"| {qy} | {p} | {c} |" for qy, p, c in rows]
        lines.append("")

    if len(lines) <= 4:
        lines.append("_Данных пока нет — наполни очередь/мониторинг и запусти db-sync._")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def safe_col(name: str) -> str:
    c = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    return c or "col"


def sync_csv(conn, table: str, path: pathlib.Path) -> int:
    if not path.exists():
        return -1
    with path.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return 0
    header = [safe_col(h) for h in rows[0]]
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    cols = ", ".join(f'"{h}" TEXT' for h in header)
    conn.execute(f"CREATE TABLE {table} ({cols})")
    ph = ", ".join("?" for _ in header)
    for r in rows[1:]:
        r = (r + [""] * len(header))[:len(header)]
        conn.execute(f"INSERT INTO {table} VALUES ({ph})", r)
    return len(rows) - 1


def sync_positions(conn, root: pathlib.Path) -> int:
    patterns = ["seo/monitoring/**/*snapshot*.json", "seo/cycles/**/09-monitoring/*.json",
                "seo/monitoring/*.json"]
    files = set()
    for pat in patterns:
        files.update(glob.glob(str(root / pat), recursive=True))
    conn.execute("DROP TABLE IF EXISTS positions")
    conn.execute("""CREATE TABLE positions (snapshot_date TEXT, engine TEXT, query TEXT,
                    position REAL, clicks INTEGER, impressions INTEGER, url TEXT)""")
    n = 0
    for fp in sorted(files):
        try:
            data = json.loads(pathlib.Path(fp).read_text(encoding="utf-8"))
        except Exception:
            continue
        date = data.get("date") or re.search(r"(\d{4}-\d{2}-\d{2})", fp)
        date = date.group(1) if hasattr(date, "group") else (date or "")
        engine = data.get("engine", "")
        queries = data.get("queries") or data.get("merged", {}).get("queries") or []
        for q in queries:
            conn.execute("INSERT INTO positions VALUES (?,?,?,?,?,?,?)",
                         (date, q.get("engine", engine), q.get("query", ""),
                          q.get("position"), q.get("clicks"), q.get("impressions"),
                          q.get("url", "")))
            n += 1
    return n


def sync_usage(conn, root: pathlib.Path) -> int:
    conn.execute("DROP TABLE IF EXISTS api_usage")
    conn.execute("""CREATE TABLE api_usage (
                    service TEXT, month TEXT, category TEXT, spent_usd REAL,
                    input_tokens REAL, output_tokens REAL, requests REAL,
                    credits REAL, units REAL, rows REAL)""")
    n = 0
    for fp in glob.glob(str(root / "seo/research/*/_usage.json")):
        try:
            u = json.loads(pathlib.Path(fp).read_text(encoding="utf-8"))
        except Exception:
            continue
        service = pathlib.Path(fp).parent.name
        conn.execute("INSERT INTO api_usage VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (service, u.get("month", ""), "", u.get("spent_usd", 0), 0, 0,
                      u.get("requests", 0), 0, 0, u.get("rows", 0)))
        n += 1
    ledger = root / "seo/usage/usage-ledger.jsonl"
    if ledger.exists():
        for raw in ledger.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            metrics = row.get("metrics", {}) if isinstance(row.get("metrics"), dict) else {}
            conn.execute("INSERT INTO api_usage VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (row.get("service", ""), row.get("month", ""), row.get("category", ""),
                          metrics.get("usd", 0), metrics.get("input_tokens", 0),
                          metrics.get("output_tokens", 0), metrics.get("requests", 0),
                          metrics.get("credits", 0), metrics.get("units", 0),
                          metrics.get("rows", 0)))
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help="путь к SQLite (override config)")
    ap.add_argument("--root", default=".", help="корень проекта")
    args = ap.parse_args()

    root = pathlib.Path(args.root).resolve()
    cfg = load_cfg(root)
    db_path = find_db_path(root, cfg, args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    print(f"== db-sync → {db_path} ==")
    for table, rel in CSV_SOURCES.items():
        n = sync_csv(conn, table, root / rel)
        if n < 0:
            print(f"  · {table}: (нет {rel})")
        else:
            print(f"  ✓ {table}: {n} строк")
    print(f"  ✓ positions: {sync_positions(conn, root)} строк")
    print(f"  ✓ api_usage: {sync_usage(conn, root)} сервис(ов)")
    conn.commit()

    dash = dashboard_path(cfg)
    if dash:
        project = (cfg.get("project") or {}).get("name", root.name)
        try:
            write_md_dashboard(conn, dash, project)
            print(f"  ✓ Obsidian-дашборд → {dash}")
        except Exception as e:
            print(f"  · дашборд пропущен: {e}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
