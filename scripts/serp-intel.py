#!/usr/bin/env python3
"""SERP intelligence from already-imported validation data (fully offline).

Reads `dataforseo_serp_validation` from semantic-architecture-final.json
(filled by serp-validation-import.py from XMLRiver/DataForSEO/Serpstat
exports) and answers three questions without any network call:

  --clusters   SERP-overlap clustering: keywords whose top-10 URLs share a
               Jaccard overlap above the threshold belong on one page.
               Compared against the current core (semantic-core.csv) it
               yields merge candidates (same SERP, different clusters) and
               split candidates (same cluster, disjoint SERPs).
  --features   SERP feature shares (AI overview, featured snippet, PAA, maps…)
               overall and per dominant page type — where AEO answer units
               and schema matter most.
  --entities   Entity-map candidates: frequent tokens/bigrams from competitor
               titles that the current entity map does not mention yet.

Default runs all three. Output: seo/research-package/serp-intel.{json,md}
with --write, stdout otherwise.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib
import re
import sys
from typing import Any

from seo_cycle_core.config import find_config, project_root_for, write_text
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("serp-intel")

STOP_TOKENS = {
    "и", "в", "на", "с", "со", "для", "по", "из", "не", "что", "как", "или", "от",
    "до", "при", "к", "у", "о", "об", "же", "за", "это", "все", "год", "года",
    "купить", "цена", "цены", "недорого", "заказать", "отзывы", "топ", "лучшие",
    "the", "and", "for", "with", "your", "best",
}
FEATURE_ALIASES = {
    "ai overview": "ai_overview", "aioverview": "ai_overview", "sge": "ai_overview",
    "featured snippet": "featured_snippet", "featured_snippet": "featured_snippet",
    "people also ask": "paa", "paa": "paa", "related questions": "paa",
    "local pack": "local_pack", "map": "local_pack", "maps": "local_pack",
    "image": "images", "images": "images", "video": "video", "videos": "video",
    "shopping": "shopping", "reviews": "reviews", "top stories": "news", "news": "news",
}


def load_validation(package: pathlib.Path) -> dict[str, dict[str, Any]]:
    path = package / "semantic-architecture-final.json"
    try:
        architecture = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    validation = architecture.get("dataforseo_serp_validation")
    if not isinstance(validation, dict):
        return {}
    return {
        keyword: record for keyword, record in validation.items()
        if isinstance(record, dict) and record.get("top_urls")
    }


def load_core_clusters(package: pathlib.Path) -> dict[str, str]:
    path = package / "semantic-core.csv"
    clusters: dict[str, str] = {}
    try:
        for row in csv.DictReader(path.open(encoding="utf-8")):
            keyword = (row.get("keyword") or "").strip().lower()
            if keyword:
                clusters[keyword] = (row.get("cluster_id") or row.get("cluster") or "").strip()
    except OSError:
        pass
    return clusters


def normalize_url(url: str) -> str:
    url = re.sub(r"^https?://", "", str(url).strip().lower())
    return url.rstrip("/")


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def serp_overlap_clusters(validation: dict[str, dict[str, Any]], core: dict[str, str],
                          threshold: float) -> dict[str, Any]:
    keywords = sorted(validation.keys())
    urls = {kw: {normalize_url(u) for u in validation[kw]["top_urls"][:10]} for kw in keywords}
    parent = {kw: kw for kw in keywords}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pairs: list[dict[str, Any]] = []
    for i, kw_a in enumerate(keywords):
        for kw_b in keywords[i + 1:]:
            overlap = jaccard(urls[kw_a], urls[kw_b])
            if overlap >= threshold:
                pairs.append({"a": kw_a, "b": kw_b, "overlap": round(overlap, 2)})
                parent[find(kw_a)] = find(kw_b)

    groups: dict[str, list[str]] = collections.defaultdict(list)
    for kw in keywords:
        groups[find(kw)].append(kw)
    serp_clusters = [sorted(members) for members in groups.values() if len(members) > 1]
    serp_clusters.sort(key=len, reverse=True)

    merge_candidates = []
    for pair in pairs:
        cluster_a = core.get(pair["a"].lower())
        cluster_b = core.get(pair["b"].lower())
        if cluster_a and cluster_b and cluster_a != cluster_b:
            merge_candidates.append({**pair, "cluster_a": cluster_a, "cluster_b": cluster_b})

    split_candidates = []
    by_core: dict[str, list[str]] = collections.defaultdict(list)
    for kw in keywords:
        cluster = core.get(kw.lower())
        if cluster:
            by_core[cluster].append(kw)
    for cluster, members in by_core.items():
        for i, kw_a in enumerate(members):
            for kw_b in members[i + 1:]:
                overlap = jaccard(urls[kw_a], urls[kw_b])
                if overlap < 0.08:
                    split_candidates.append({"cluster": cluster, "a": kw_a, "b": kw_b,
                                             "overlap": round(overlap, 2)})

    return {
        "threshold": threshold,
        "keywords_with_serp": len(keywords),
        "serp_clusters": serp_clusters,
        "pairs_above_threshold": sorted(pairs, key=lambda p: -p["overlap"])[:50],
        "merge_candidates": merge_candidates[:30],
        "split_candidates": split_candidates[:30],
    }


def normalize_feature(raw: str) -> str:
    key = re.sub(r"[^a-zа-яё ]", " ", str(raw).strip().lower()).strip()
    return FEATURE_ALIASES.get(key, key.replace(" ", "_") or "other")


def feature_share(validation: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total = len(validation)
    counter: collections.Counter[str] = collections.Counter()
    by_type: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    aeo_keywords: list[str] = []
    for keyword, record in validation.items():
        features = {normalize_feature(f) for f in (record.get("features") or [])}
        counter.update(features)
        page_type = (record.get("dominant_page_type") or "unknown").strip().lower()
        by_type[page_type].update(features)
        if features & {"ai_overview", "featured_snippet", "paa"}:
            aeo_keywords.append(keyword)
    return {
        "keywords": total,
        "shares": {name: {"count": count, "share": round(count / total, 2)}
                   for name, count in counter.most_common()},
        "by_page_type": {ptype: dict(cnt.most_common(5)) for ptype, cnt in by_type.items()},
        "aeo_priority_keywords": sorted(aeo_keywords)[:40],
    }


def load_known_entities(package: pathlib.Path) -> set[str]:
    known: set[str] = set()
    for path in package.glob("*entity*map*.json"):
        try:
            text = path.read_text(encoding="utf-8").lower()
        except OSError:
            continue
        known.update(re.findall(r"[а-яёa-z][а-яёa-z-]{3,}", text))
    return known


def entity_candidates(validation: dict[str, dict[str, Any]], known: set[str],
                      min_count: int = 3) -> list[dict[str, Any]]:
    # префикс-вычет гасит морфологию: «вагонка» в карте закрывает «вагонку/вагонки»
    known_prefixes = {word[:5] for word in known if len(word) >= 5}

    def is_known(word: str) -> bool:
        return word in known or (len(word) >= 5 and word[:5] in known_prefixes)

    words: collections.Counter[str] = collections.Counter()
    bigrams: collections.Counter[str] = collections.Counter()
    for record in validation.values():
        for title in record.get("top_titles") or []:
            tokens = [t for t in re.findall(r"[а-яёa-z][а-яёa-z-]{3,}", str(title).lower())
                      if t not in STOP_TOKENS]
            words.update(tokens)
            bigrams.update(" ".join(pair) for pair in zip(tokens, tokens[1:]))
    out = []
    for token, count in (words + bigrams).most_common(200):
        if count < min_count:
            break
        if all(is_known(part) for part in token.split()):
            continue
        out.append({"candidate": token, "mentions": count})
    return out[:30]


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# SERP intelligence", ""]
    clusters = report.get("clusters")
    if clusters:
        lines.append(f"## Кластеры по пересечению выдачи (порог {clusters['threshold']})")
        lines.append("")
        lines.append(f"- Запросов с SERP-данными: {clusters['keywords_with_serp']}; "
                     f"SERP-групп ≥2 запросов: {len(clusters['serp_clusters'])}")
        for group in clusters["serp_clusters"][:10]:
            lines.append(f"- одна страница: {', '.join(group)}")
        if clusters["merge_candidates"]:
            lines.extend(["", "### Кандидаты на объединение (один SERP — разные кластеры)"])
            lines.extend(f"- «{c['a']}» ({c['cluster_a']}) + «{c['b']}» ({c['cluster_b']}) — overlap {c['overlap']}"
                         for c in clusters["merge_candidates"][:10])
        if clusters["split_candidates"]:
            lines.extend(["", "### Кандидаты на разделение (один кластер — разные SERP)"])
            lines.extend(f"- {c['cluster']}: «{c['a']}» vs «{c['b']}» — overlap {c['overlap']}"
                         for c in clusters["split_candidates"][:10])
        lines.append("")
    features = report.get("features")
    if features:
        lines.extend([f"## SERP-фичи ({features['keywords']} запросов)", ""])
        lines.extend(f"- {name}: {data['count']} ({int(data['share'] * 100)}%)"
                     for name, data in list(features["shares"].items())[:10])
        if features["aeo_priority_keywords"]:
            lines.extend(["", f"AEO-приоритет (AI overview / featured / PAA): "
                          f"{', '.join(features['aeo_priority_keywords'][:15])}"])
        lines.append("")
    entities = report.get("entities")
    if entities is not None:
        lines.extend(["## Кандидаты в entity map (из заголовков конкурентов)", ""])
        if entities:
            lines.extend(f"- {item['candidate']} — {item['mentions']} упоминаний" for item in entities[:20])
        else:
            lines.append("_Новых кандидатов нет — карта покрывает заголовки конкурентов._")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("package", nargs="?", default="seo/research-package")
    parser.add_argument("--clusters", action="store_true")
    parser.add_argument("--features", action="store_true")
    parser.add_argument("--entities", action="store_true")
    parser.add_argument("--min-overlap", type=float, default=0.3)
    parser.add_argument("--min-mentions", type=int, default=3,
                        help="Minimum title mentions for an entity candidate")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    cfg_path = find_config(pathlib.Path.cwd())
    project_root = project_root_for(cfg_path) if cfg_path else pathlib.Path.cwd()
    package = (project_root / args.package).resolve() if not pathlib.Path(args.package).is_absolute() \
        else pathlib.Path(args.package)
    validation = load_validation(package)
    if not validation:
        print(f"Нет SERP-данных: заполните {package}/semantic-architecture-final.json "
              "через serp-validation-import.py (XMLRiver/DataForSEO/Serpstat экспорт).", file=sys.stderr)
        return 0

    run_all = not (args.clusters or args.features or args.entities)
    report: dict[str, Any] = {"audit_id": "serp_intel", "package": str(package)}
    if args.clusters or run_all:
        report["clusters"] = serp_overlap_clusters(validation, load_core_clusters(package), args.min_overlap)
    if args.features or run_all:
        report["features"] = feature_share(validation)
    if args.entities or run_all:
        report["entities"] = entity_candidates(validation, load_known_entities(package),
                                               args.min_mentions)

    markdown = render_markdown(report)
    if args.write:
        write_text(package / "serp-intel.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        write_text(package / "serp-intel.md", markdown)
        print(f"✓ {package}/serp-intel.md", file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else markdown,
          end="" if args.format == "md" else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
