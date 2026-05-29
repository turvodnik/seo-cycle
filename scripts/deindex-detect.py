#!/usr/bin/env python3
"""
deindex-detect.py — детектор деиндексированных страниц (Full Step 10).

Workflow:
1. Загружает sitemap.xml (или несколько) — список URL которые ты хочешь
   индексировать
2. Получает список indexed URLs из GSC (через gsc-fetch.py output или
   готовый JSON от делегата)
3. Diff: sitemap - indexed = «потерянные»
4. Для каждой потерянной — classification:
   - http_4xx (404/410) → техническая проблема, не deindex
   - http_5xx → серверная проблема
   - http_200 + noindex meta → намеренный noindex
   - http_200 без noindex → **deindex** (Google сам исключил)
   - redirect → проверить target в indexed
5. Output JSON для page-rewrite-rescue workflow

Использование:
    # Базовый — sitemap + GSC export
    python3 deindex-detect.py \\
        --sitemap https://example.com/sitemap.xml \\
        --gsc-pages-json gsc-pages.json \\
        --output deindex-report.json

    # Локальный sitemap.xml
    python3 deindex-detect.py --sitemap-file sitemap.xml --gsc-pages-json gsc.json

    # С classification (curl на каждый «потерянный» URL — медленно, но точно)
    python3 deindex-detect.py --sitemap <URL> --gsc-pages-json <file> --classify --output ...

    # В pipeline после gsc-fetch:
    python3 gsc-fetch.py --days 90 --dimensions page --row-limit 5000 > gsc-pages.json
    python3 deindex-detect.py --sitemap https://example.com/sitemap.xml \\
        --gsc-pages-json gsc-pages.json --classify --output deindex.json

Опции:
    --sitemap URL              Sitemap XML URL (recursive если sitemap index)
    --sitemap-file PATH        Локальный sitemap.xml
    --gsc-pages-json PATH      JSON от gsc-fetch.py с dimensions=page
    --classify                 HTTP probe каждого потерянного URL (slow, accurate)
    --classify-limit N         Лимит на classification (default: 100)
    --classify-sleep N         Пауза между requests (default: 1 сек)
    --user-agent UA            UA для requests (default: Googlebot-like)
    --output PATH              JSON report (default: stdout)

Schema output:
    {
      "sitemap_total": N,
      "gsc_indexed_total": M,
      "lost": [{"url": "...", "classification": "deindex|http_4xx|noindex|redirect", "details": "..."}],
      "summary": {"deindex": N, "http_4xx": M, ...}
    }
"""

from __future__ import annotations
import argparse, gzip, json, pathlib, re, sys, time, urllib.parse, urllib.request
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET


SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
NOINDEX_RE = re.compile(
    r'<meta\s+[^>]*name=["\']robots["\'][^>]*content=["\'][^"\']*noindex',
    re.IGNORECASE,
)
DEFAULT_UA = (
    "Mozilla/5.0 (compatible; SeoCycleBot/1.1; +https://github.com/seo-cycle)"
)


# ----- Sitemap loading ---------------------------------------------------

def fetch_url(url: str, ua: str = DEFAULT_UA, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip" or url.endswith(".gz"):
            try:
                data = gzip.decompress(data)
            except OSError:
                pass
        return data


def parse_sitemap(content: bytes, source: str, ua: str) -> list[str]:
    """Парсит sitemap.xml или sitemap_index.xml (рекурсивно). Возвращает list URLs."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"⚠ {source}: parse error: {e}", file=sys.stderr)
        return []

    urls: list[str] = []
    tag = root.tag.split("}")[-1]  # уберём namespace

    if tag == "sitemapindex":
        # Это sitemap index — рекурсивно загружаем child sitemaps
        for sitemap_el in root.findall("sm:sitemap", SITEMAP_NS):
            loc = sitemap_el.find("sm:loc", SITEMAP_NS)
            if loc is not None and loc.text:
                child_url = loc.text.strip()
                try:
                    child = fetch_url(child_url, ua)
                    urls.extend(parse_sitemap(child, child_url, ua))
                except (HTTPError, URLError) as e:
                    print(f"⚠ child sitemap {child_url}: {e}", file=sys.stderr)
    elif tag == "urlset":
        for url_el in root.findall("sm:url", SITEMAP_NS):
            loc = url_el.find("sm:loc", SITEMAP_NS)
            if loc is not None and loc.text:
                urls.append(loc.text.strip())
    else:
        print(f"⚠ {source}: unknown root tag {tag!r}", file=sys.stderr)
    return urls


def load_sitemap(url: str | None, file: pathlib.Path | None, ua: str) -> list[str]:
    if url:
        try:
            content = fetch_url(url, ua)
            return parse_sitemap(content, url, ua)
        except (HTTPError, URLError) as e:
            print(f"⚠ failed to fetch sitemap {url}: {e}", file=sys.stderr)
            return []
    if file:
        return parse_sitemap(file.read_bytes(), str(file), ua)
    return []


# ----- GSC indexed pages loading ----------------------------------------

def load_indexed_urls(gsc_json: pathlib.Path) -> set[str]:
    """Из gsc-fetch.py output извлекает уникальные URL (по dimension=page)."""
    data = json.loads(gsc_json.read_text(encoding="utf-8"))
    urls: set[str] = set()
    for row in data.get("rows", []):
        keys = row.get("keys", [])
        # Если dimensions=query,page — page в keys[1], иначе keys[0]
        for k in keys:
            if isinstance(k, str) and k.startswith(("http://", "https://")):
                urls.add(k)
    return urls


def normalize_url(url: str) -> str:
    """Нормализация: убрать trailing slash, lowercase scheme/host, без fragment."""
    p = urllib.parse.urlsplit(url)
    scheme = p.scheme.lower()
    netloc = p.netloc.lower()
    path = p.path or "/"
    # Не убираем trailing slash для корня
    if len(path) > 1 and path.endswith("/"):
        # Trailing slash может быть значимым — но для diff обычно нет.
        # Оставляем как есть, чтобы не ломать.
        pass
    return urllib.parse.urlunsplit((scheme, netloc, path, p.query, ""))


# ----- Classification ----------------------------------------------------

def classify_url(url: str, ua: str, timeout: int = 15) -> dict:
    """HTTP probe + meta parse для определения причины отсутствия в индексе."""
    info = {"url": url, "classification": "unknown", "details": ""}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.status
            if r.url != url:
                info["classification"] = "redirect"
                info["details"] = f"{code} → {r.url}"
                return info
            if 200 <= code < 300:
                body = r.read(50000).decode("utf-8", errors="replace")
                if NOINDEX_RE.search(body):
                    info["classification"] = "noindex"
                    info["details"] = f"{code} + meta robots noindex"
                else:
                    info["classification"] = "deindex"
                    info["details"] = f"{code} no noindex — Google excluded"
            else:
                info["classification"] = f"http_{code}"
                info["details"] = f"non-2xx: {code}"
    except HTTPError as e:
        if 400 <= e.code < 500:
            info["classification"] = "http_4xx"
        elif 500 <= e.code < 600:
            info["classification"] = "http_5xx"
        else:
            info["classification"] = f"http_{e.code}"
        info["details"] = f"HTTP {e.code}: {e.reason}"
    except URLError as e:
        info["classification"] = "network_error"
        info["details"] = str(e)
    except Exception as e:
        info["classification"] = "error"
        info["details"] = str(e)
    return info


# ----- Main --------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sitemap", help="Sitemap URL (recursive если sitemap index)")
    ap.add_argument("--sitemap-file", type=pathlib.Path)
    ap.add_argument("--gsc-pages-json", type=pathlib.Path, required=True,
                    help="JSON от gsc-fetch.py с dimensions=page")
    ap.add_argument("--classify", action="store_true",
                    help="HTTP probe каждого потерянного URL (медленно)")
    ap.add_argument("--classify-limit", type=int, default=100)
    ap.add_argument("--classify-sleep", type=int, default=1)
    ap.add_argument("--user-agent", default=DEFAULT_UA)
    ap.add_argument("--output", type=pathlib.Path)
    args = ap.parse_args()

    if not (args.sitemap or args.sitemap_file):
        ap.error("Provide --sitemap URL or --sitemap-file PATH")
    if not args.gsc_pages_json.exists():
        ap.error(f"GSC JSON не существует: {args.gsc_pages_json}")

    print(f"Loading sitemap...", file=sys.stderr)
    sitemap_urls = load_sitemap(args.sitemap, args.sitemap_file, args.user_agent)
    print(f"  {len(sitemap_urls)} URLs", file=sys.stderr)

    print(f"Loading GSC indexed pages from {args.gsc_pages_json}...", file=sys.stderr)
    indexed = load_indexed_urls(args.gsc_pages_json)
    print(f"  {len(indexed)} indexed URLs", file=sys.stderr)

    # Нормализация для diff
    sitemap_norm = {normalize_url(u): u for u in sitemap_urls}
    indexed_norm = {normalize_url(u) for u in indexed}

    lost_norm = set(sitemap_norm.keys()) - indexed_norm
    lost_urls = [sitemap_norm[n] for n in lost_norm]
    print(f"\n📊 Diff: {len(lost_urls)} URLs в sitemap, не в GSC indexed", file=sys.stderr)

    classified: list[dict] = []
    if args.classify and lost_urls:
        print(f"\nClassifying (limit={args.classify_limit}, sleep={args.classify_sleep}s)...", file=sys.stderr)
        for i, url in enumerate(lost_urls[:args.classify_limit]):
            print(f"  [{i+1}/{min(len(lost_urls), args.classify_limit)}] {url}", file=sys.stderr)
            classified.append(classify_url(url, args.user_agent))
            if i < args.classify_limit - 1:
                time.sleep(args.classify_sleep)
    else:
        for url in lost_urls:
            classified.append({"url": url, "classification": "not_classified", "details": "use --classify"})

    summary: dict[str, int] = {}
    for item in classified:
        c = item.get("classification", "unknown")
        summary[c] = summary.get(c, 0) + 1

    report = {
        "sitemap_total": len(sitemap_urls),
        "gsc_indexed_total": len(indexed),
        "lost_total": len(lost_urls),
        "classified_total": len(classified),
        "lost": classified,
        "summary": summary,
    }

    print(f"\n📋 Summary:", file=sys.stderr)
    for cat, n in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"  {cat:<20}: {n}", file=sys.stderr)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✓ Report → {args.output}", file=sys.stderr)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
