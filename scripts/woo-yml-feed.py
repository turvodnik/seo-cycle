#!/usr/bin/env python3
"""Generate a Яндекс YML feed from WooCommerce products (или любого экспорта).

Closes the «фид для Яндекс.Товаров/Маркета» gap for WordPress+WooCommerce
shops: pulls products over the Woo REST API (read-only) and writes a valid
`yml_catalog` file, ready for Яндекс.Вебмастер «Товары и предложения» /
Маркет. Validate afterwards with yml-feed-audit.py.

Sources:
  --live          GET /wp-json/wc/v3/products (env WP_BASE_URL + WOO_REST_API_KEY/SECRET)
  --input-file    JSON array of Woo-shaped products (an export; offline)

Usage:
  python3 scripts/woo-yml-feed.py --live --write [--max-products 500]
  python3 scripts/woo-yml-feed.py --input-file products.json --write
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for, write_text
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("woo-yml-feed")


def fetch_products(base_url: str, key: str, secret: str, *, max_products: int,
                   timeout: int) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    auth = base64.b64encode(f"{key}:{secret}".encode()).decode()
    page = 1
    while len(products) < max_products:
        per_page = min(100, max_products - len(products))
        url = (f"{base_url.rstrip('/')}/wp-json/wc/v3/products?"
               + urllib.parse.urlencode({"per_page": per_page, "page": page, "status": "publish"}))
        request = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            batch = json.loads(response.read().decode("utf-8"))
        if not isinstance(batch, list) or not batch:
            break
        products.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return products[:max_products]


def strip_html(text: str, limit: int = 500) -> str:
    clean = re.sub(r"<[^>]+>", " ", str(text or ""))
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:limit]


def build_yml(products: list[dict[str, Any]], *, shop_name: str, company: str,
              shop_url: str, currency: str) -> tuple[str, dict[str, Any]]:
    categories: dict[int, str] = {}
    offers: list[str] = []
    skipped = 0
    for product in products:
        if not isinstance(product, dict):
            continue
        price = str(product.get("price") or product.get("regular_price") or "").strip()
        url = str(product.get("permalink") or "").strip()
        name = str(product.get("name") or "").strip()
        if not price or not url or not name:
            skipped += 1
            continue
        product_categories = [c for c in (product.get("categories") or []) if isinstance(c, dict)]
        for category in product_categories:
            if category.get("id"):
                categories[int(category["id"])] = str(category.get("name") or f"cat-{category['id']}")
        category_id = int(product_categories[0]["id"]) if product_categories and product_categories[0].get("id") else 1
        images = [img.get("src") for img in (product.get("images") or []) if isinstance(img, dict) and img.get("src")]
        available = "true" if str(product.get("stock_status") or "instock") == "instock" else "false"
        parts = [
            f'    <offer id="{html.escape(str(product.get("id") or product.get("sku") or len(offers) + 1))}" '
            f'available="{available}">',
            f"      <name>{html.escape(name)}</name>",
            f"      <url>{html.escape(url)}</url>",
            f"      <price>{html.escape(price)}</price>",
            f"      <currencyId>{html.escape(currency)}</currencyId>",
            f"      <categoryId>{category_id}</categoryId>",
        ]
        parts.extend(f"      <picture>{html.escape(str(img))}</picture>" for img in images[:3])
        if product.get("sku"):
            parts.append(f"      <vendorCode>{html.escape(str(product['sku']))}</vendorCode>")
        description = strip_html(product.get("short_description") or product.get("description") or "")
        if description:
            parts.append(f"      <description>{html.escape(description)}</description>")
        parts.append("    </offer>")
        offers.append("\n".join(parts))

    if not categories:
        categories[1] = "Каталог"
    categories_xml = "\n".join(
        f'      <category id="{cid}">{html.escape(cname)}</category>'
        for cid, cname in sorted(categories.items())
    )
    from datetime import datetime

    yml = f"""<?xml version="1.0" encoding="UTF-8"?>
<yml_catalog date="{datetime.now().strftime('%Y-%m-%d %H:%M')}">
  <shop>
    <name>{html.escape(shop_name)}</name>
    <company>{html.escape(company or shop_name)}</company>
    <url>{html.escape(shop_url)}</url>
    <currencies>
      <currency id="{html.escape(currency)}" rate="1"/>
    </currencies>
    <categories>
{categories_xml}
    </categories>
    <offers>
{chr(10).join(offers)}
    </offers>
  </shop>
</yml_catalog>
"""
    return yml, {"offers": len(offers), "categories": len(categories), "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="Fetch products over the Woo REST API")
    parser.add_argument("--input-file", help="JSON array of Woo-shaped products (offline)")
    parser.add_argument("--max-products", type=int, default=500)
    parser.add_argument("--currency", default="RUR", help="YML currencyId (RUR|RUB|USD|EUR|KZT|BYN|UAH)")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--write", action="store_true", help="Write seo/feeds/yml-feed.xml")
    args = parser.parse_args(argv)

    cfg_path = find_config(pathlib.Path.cwd())
    if not cfg_path:
        print("ERROR: seo-cycle.yaml not found", file=sys.stderr)
        return 2
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    global log
    log = setup_logging("woo-yml-feed", project_root, cfg)

    if args.input_file:
        try:
            products = json.loads(pathlib.Path(args.input_file).expanduser().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot read {args.input_file}: {exc}", file=sys.stderr)
            return 2
    elif args.live:
        import os

        base_url = os.environ.get("WP_BASE_URL") or str(nested_get(cfg, "project.url", "") or "")
        key = os.environ.get("WOO_REST_API_KEY", "")
        secret = os.environ.get("WOO_REST_API_SECRET", "")
        if not base_url or not key or not secret:
            print("ERROR: --live требует WP_BASE_URL + WOO_REST_API_KEY/WOO_REST_API_SECRET в .env "
                  "(WooCommerce → Settings → Advanced → REST API, права Read).", file=sys.stderr)
            return 2
        try:
            products = fetch_products(base_url, key, secret,
                                      max_products=args.max_products, timeout=args.timeout)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: Woo API: {exc}", file=sys.stderr)
            return 1
    else:
        print("Сеть выключена по умолчанию: --live для Woo REST или --input-file <products.json>.",
              file=sys.stderr)
        return 0

    project = cfg.get("project") or {}
    yml, summary = build_yml(
        products if isinstance(products, list) else [],
        shop_name=str(project.get("name") or project_root.name),
        company=str(project.get("company") or ""),
        shop_url=str(project.get("url") or project.get("domain") or ""),
        currency=args.currency,
    )
    log.info("yml feed built: %s", summary)
    if args.write:
        out = project_root / "seo" / "feeds" / "yml-feed.xml"
        write_text(out, yml)
        print(f"✓ {out} · offers: {summary['offers']} · categories: {summary['categories']}"
              f" · пропущено без цены/URL: {summary['skipped']}", file=sys.stderr)
        print("Проверка: python3 scripts/yml-feed-audit.py seo/feeds/yml-feed.xml", file=sys.stderr)
    else:
        print(yml, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
