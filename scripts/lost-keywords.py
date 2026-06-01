#!/usr/bin/env python3
"""
lost-keywords.py — находит потерянные и просевшие ключи между двумя снапшотами
мониторинга (GSC / Яндекс.Вебмастер). Детерминированно, на наших данных — без
трат API-кредитов.

Категории:
  LOST    — был в выдаче (position>0) в старом снапшоте, в новом исчез/ушёл за --out-of-top.
  DROPPED — позиция ухудшилась минимум на --drop-min (и стала хуже порога топа).
  (опц.) для каждого считается потеря кликов (old.clicks).

Вход — два snapshot JSON формата snapshot-build.py: {"queries":[{query,position,clicks,impressions,url}]}.

Использование:
  python3 lost-keywords.py --old OLD.json --new NEW.json [--top 10] [--drop-min 3] [--md]

Результат — список потерянных/просевших, отсортированный по потерянным кликам (desc).
Связка: запускать в Phase 9-10; найденное → задачи на возврат (refresh/перелинковка).
"""

from __future__ import annotations
import argparse, json, pathlib, re, sys


def norm(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lower().replace("ё", "е"))


def load(path: str) -> dict[str, dict]:
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    queries = data.get("queries") or data.get("merged", {}).get("queries") or []
    out: dict[str, dict] = {}
    for q in queries:
        k = norm(q.get("query", ""))
        if not k:
            continue
        pos = float(q.get("position", 0) or 0)
        rec = out.get(k)
        # лучшая (минимальная) позиция при дублях
        if rec is None or (pos and (rec["position"] == 0 or pos < rec["position"])):
            out[k] = {"position": pos, "clicks": int(q.get("clicks", 0) or 0),
                      "impressions": int(q.get("impressions", 0) or 0), "url": q.get("url", "")}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, help="старый snapshot JSON")
    ap.add_argument("--new", required=True, help="новый snapshot JSON")
    ap.add_argument("--top", type=float, default=10, help="порог топа (default 10)")
    ap.add_argument("--drop-min", type=float, default=3, help="мин. ухудшение позиции для DROPPED")
    ap.add_argument("--out-of-top", type=float, default=100, help="позиция считается выпавшей если > этого")
    ap.add_argument("--md", action="store_true")
    args = ap.parse_args()

    old, new = load(args.old), load(args.new)
    findings = []
    for kw, o in old.items():
        if o["position"] <= 0:
            continue
        n = new.get(kw)
        new_pos = n["position"] if (n and n["position"] > 0) else None
        if new_pos is None or new_pos > args.out_of_top:
            findings.append(("LOST", kw, o["position"], new_pos or 0, o["clicks"], o["url"]))
        elif new_pos - o["position"] >= args.drop_min and new_pos > args.top:
            findings.append(("DROPPED", kw, o["position"], new_pos, o["clicks"], o["url"]))

    findings.sort(key=lambda x: x[4], reverse=True)  # по потерянным кликам

    if not findings:
        print("✓ Потерянных/просевших ключей не найдено между снапшотами.")
        return 0

    lost = sum(1 for f in findings if f[0] == "LOST")
    drop = len(findings) - lost
    print(f"== Потерянные ключи: LOST {lost}, DROPPED {drop} ==")
    if args.md:
        print("| Тип | Ключ | было | стало | клики(старые) | URL |")
        print("|---|---|---|---|---|---|")
        for t, kw, op, np_, cl, url in findings:
            new_s = "—" if np_ == 0 else f"{np_:.0f}"
            print(f"| {t} | {kw} | {op:.0f} | {new_s} | {cl} | {url} |")
    else:
        for t, kw, op, np_, cl, url in findings:
            new_s = "—" if np_ == 0 else f"{np_:.0f}"
            print(f"  [{t:<7}] {kw}  (поз {op:.0f}→{new_s}, клики {cl})")
    print("\n  → Действие: вернуть через refresh контента + перелинковку (Phase 10).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
