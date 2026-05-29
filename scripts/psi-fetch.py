#!/usr/bin/env python3
"""
psi-fetch.py — PageSpeed Insights API клиент (free, OAuth не нужен).

Берёт URL и вызывает PageSpeed Insights API → возвращает CWV (LCP, INP, CLS)
field data (из CrUX) + lab data (из Lighthouse). Output формат совместим с
snapshot-build.py --source psi.

Без API key работает (limit ~25 запросов/день по IP).
С API key (PSI_API_KEY в env) — 25000 запросов/день.

Использование:
    # Один URL
    python3 psi-fetch.py https://example.com
    python3 psi-fetch.py https://example.com --strategy mobile --output psi.json

    # Несколько URL → batch (по очереди, с rate limit)
    python3 psi-fetch.py --urls-file urls.txt --output-dir psi-results/

    # Сразу в pipeline:
    python3 psi-fetch.py https://example.com | \
      python3 snapshot-build.py --source psi --output snapshot.json --merge

Опции:
    url                  URL для анализа (или --urls-file для batch)
    --strategy           mobile (default) | desktop
    --api-key            PSI API key (или env PSI_API_KEY)
    --output PATH        JSON в файл (default: stdout)
    --output-dir DIR     Для batch — каждый URL в отдельный файл
    --urls-file PATH     Текстовый файл с URL по одному в строке
    --sleep N            Пауза между URL в batch режиме (default: 2 сек)
"""

from __future__ import annotations
import argparse, json, os, pathlib, sys, time, urllib.parse, urllib.request, re
from urllib.error import HTTPError, URLError


PSI_BASE = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def fetch(url: str, strategy: str, api_key: str | None) -> dict:
    params = {"url": url, "strategy": strategy, "category": "performance"}
    if api_key:
        params["key"] = api_key
    full = f"{PSI_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={
        "User-Agent": "seo-cycle/1.1 psi-fetch",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"⚠ HTTP {e.code} для {url}: {body[:200]}", file=sys.stderr)
        if e.code == 429:
            print("  Rate limit — попробуй позже или добавь PSI_API_KEY", file=sys.stderr)
        raise
    except URLError as e:
        print(f"⚠ Network error для {url}: {e}", file=sys.stderr)
        raise


def safe_slug(url: str) -> str:
    """Превращает URL в безопасное имя файла."""
    s = re.sub(r"https?://", "", url).rstrip("/")
    s = re.sub(r"[^\w.-]", "_", s)
    return s[:120] or "page"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?", help="URL для анализа")
    ap.add_argument("--strategy", default="mobile", choices=["mobile", "desktop"])
    ap.add_argument("--api-key", default=os.environ.get("PSI_API_KEY"))
    ap.add_argument("--output", type=pathlib.Path)
    ap.add_argument("--output-dir", type=pathlib.Path)
    ap.add_argument("--urls-file", type=pathlib.Path)
    ap.add_argument("--sleep", type=int, default=2)
    args = ap.parse_args()

    if not args.url and not args.urls_file:
        ap.error("Provide either URL or --urls-file")

    urls = []
    if args.url:
        urls.append(args.url)
    if args.urls_file:
        urls.extend([u.strip() for u in args.urls_file.read_text(encoding="utf-8").splitlines() if u.strip() and not u.startswith("#")])

    if len(urls) > 1 and not args.output_dir:
        print("Batch mode: используй --output-dir для результатов (или один URL через --output)", file=sys.stderr)

    for i, url in enumerate(urls):
        print(f"[{i+1}/{len(urls)}] PSI {args.strategy}: {url}", file=sys.stderr)
        try:
            data = fetch(url, args.strategy, args.api_key)
        except Exception as e:
            print(f"  skip: {e}", file=sys.stderr)
            continue

        # Сохраняем результат
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            target = args.output_dir / f"{safe_slug(url)}-{args.strategy}.json"
            target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  ✓ {target}", file=sys.stderr)
        elif args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  ✓ {args.output}", file=sys.stderr)
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))

        if i < len(urls) - 1:
            time.sleep(args.sleep)


if __name__ == "__main__":
    main()
