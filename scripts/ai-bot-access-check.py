#!/usr/bin/env python3
"""Live access checker for search, AI, social, and SEO crawlers.

The check is report-only. It fetches robots.txt, evaluates relevant robots
rules, then requests one public URL with crawler User-Agent strings. It never
changes the site, bypasses WAF rules, submits URLs, or calls paid APIs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from vnext_audit_core import find_config, load_yaml, policy_path, project_root_for, rel_path, write_text


BOT_CATALOG: list[dict[str, str]] = [
    {"name": "YandexBot", "company": "Yandex", "category": "search", "token": "YandexBot", "user_agent": "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)"},
    {"name": "YandexImages", "company": "Yandex", "category": "search", "token": "YandexImages", "user_agent": "Mozilla/5.0 (compatible; YandexImages/3.0; +http://yandex.com/bots)"},
    {"name": "YandexVideo", "company": "Yandex", "category": "search", "token": "YandexVideo", "user_agent": "Mozilla/5.0 (compatible; YandexVideo/3.0; +http://yandex.com/bots)"},
    {"name": "YandexMedia", "company": "Yandex", "category": "search", "token": "YandexMedia", "user_agent": "Mozilla/5.0 (compatible; YandexMedia/3.0; +http://yandex.com/bots)"},
    {"name": "YandexBlogs", "company": "Yandex", "category": "search", "token": "YandexBlogs", "user_agent": "Mozilla/5.0 (compatible; YandexBlogs/0.99; robot; +http://yandex.com/bots)"},
    {"name": "YandexWebmaster", "company": "Yandex", "category": "search", "token": "YandexWebmaster", "user_agent": "Mozilla/5.0 (compatible; YandexWebmaster/2.0; +http://yandex.com/bots)"},
    {"name": "YandexPagechecker", "company": "Yandex", "category": "search", "token": "YandexPagechecker", "user_agent": "Mozilla/5.0 (compatible; YandexPagechecker/1.0; +http://yandex.com/bots)"},
    {"name": "Googlebot", "company": "Google", "category": "search", "token": "Googlebot", "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"},
    {"name": "Googlebot-Image", "company": "Google", "category": "search", "token": "Googlebot-Image", "user_agent": "Googlebot-Image/1.0"},
    {"name": "Google-Extended", "company": "Google", "category": "llm", "token": "Google-Extended", "user_agent": "Mozilla/5.0 (compatible; Google-Extended)"},
    {"name": "GoogleOther", "company": "Google", "category": "search", "token": "GoogleOther", "user_agent": "GoogleOther"},
    {"name": "AdsBot-Google", "company": "Google", "category": "search", "token": "AdsBot-Google", "user_agent": "AdsBot-Google (+http://www.google.com/adsbot.html)"},
    {"name": "GPTBot", "company": "OpenAI", "category": "llm", "token": "GPTBot", "user_agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.0; +https://openai.com/gptbot)"},
    {"name": "ChatGPT-User", "company": "OpenAI", "category": "llm", "token": "ChatGPT-User", "user_agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ChatGPT-User/1.0; +https://openai.com/bot)"},
    {"name": "OAI-SearchBot", "company": "OpenAI", "category": "llm", "token": "OAI-SearchBot", "user_agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)"},
    {"name": "ClaudeBot", "company": "Anthropic", "category": "llm", "token": "ClaudeBot", "user_agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +https://www.anthropic.com)"},
    {"name": "anthropic-ai", "company": "Anthropic", "category": "llm", "token": "anthropic-ai", "user_agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-Web/1.0; +https://www.anthropic.com)"},
    {"name": "Claude-Web", "company": "Anthropic", "category": "llm", "token": "claude-web", "user_agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-Web/1.0; +https://www.anthropic.com)"},
    {"name": "PerplexityBot", "company": "Perplexity", "category": "llm", "token": "PerplexityBot", "user_agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/bot)"},
    {"name": "CCBot", "company": "Common Crawl", "category": "llm", "token": "CCBot", "user_agent": "CCBot/2.0 (https://commoncrawl.org/faq/)"},
    {"name": "Bytespider", "company": "ByteDance", "category": "llm", "token": "Bytespider", "user_agent": "Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 (KHTML, like Gecko; compatible; Bytespider; spider@bytedance.com) Mobile Safari/537.36"},
    {"name": "Amazonbot", "company": "Amazon", "category": "llm", "token": "Amazonbot", "user_agent": "Amazonbot/0.1 (+https://developer.amazon.com/support/amazonbot)"},
    {"name": "Meta-ExternalAgent", "company": "Meta", "category": "social", "token": "Meta-ExternalAgent", "user_agent": "Mozilla/5.0 (compatible; Meta-ExternalAgent/1.1; +https://developers.facebook.com/docs/sharing/webmasters/crawler)"},
    {"name": "Meta-ExternalFetcher", "company": "Meta", "category": "social", "token": "Meta-ExternalFetcher", "user_agent": "Mozilla/5.0 (compatible; Meta-ExternalFetcher/1.0; +https://developers.facebook.com/docs/sharing/webmasters/crawler)"},
    {"name": "FacebookBot", "company": "Meta", "category": "social", "token": "FacebookBot", "user_agent": "Mozilla/5.0 (compatible; FacebookBot/1.0; +https://developers.facebook.com/docs/sharing/webmasters/crawler)"},
    {"name": "Applebot", "company": "Apple", "category": "llm", "token": "Applebot", "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko; compatible; Applebot/0.1; +http://www.apple.com/go/applebot)"},
    {"name": "Applebot-Extended", "company": "Apple", "category": "llm", "token": "Applebot-Extended", "user_agent": "Mozilla/5.0 (compatible; Applebot-Extended/1.0)"},
    {"name": "Grok", "company": "xAI", "category": "llm", "token": "Grok", "user_agent": "Mozilla/5.0 (compatible; Grok/1.0; +https://x.ai/bot)"},
    {"name": "Cohere-ai", "company": "Cohere", "category": "llm", "token": "cohere-ai", "user_agent": "cohere-ai/1.0 (+https://cohere.com; cohere-ai@cohere.com)"},
    {"name": "Diffbot", "company": "Diffbot", "category": "llm", "token": "Diffbot", "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/38.0.2125.122 Safari/537.36 DiffBot/2.0 (+https://www.diffbot.com)"},
    {"name": "PetalBot", "company": "Huawei", "category": "search", "token": "PetalBot", "user_agent": "Mozilla/5.0 (Linux; Android 7.0;) AppleWebKit/537.36 (KHTML, like Gecko) Mobile Safari/537.36 (compatible; PetalBot;+https://webmaster.petalsearch.com/site/petalbot)"},
    {"name": "YouBot", "company": "You.com", "category": "search", "token": "YouBot", "user_agent": "Mozilla/5.0 (compatible; YouBot/1.0; +https://about.you.com/youbot/)"},
    {"name": "Seekr", "company": "Seekr", "category": "search", "token": "Seekr", "user_agent": "Mozilla/5.0 (compatible; Seekr/1.0)"},
    {"name": "Timpibot", "company": "Timpi", "category": "search", "token": "Timpibot", "user_agent": "Mozilla/5.0 (compatible; Timpibot/0.9; +https://www.timpi.io)"},
    {"name": "VelenPublicWebCrawler", "company": "Velen", "category": "other", "token": "VelenPublicWebCrawler", "user_agent": "Mozilla/5.0 (compatible; VelenPublicWebCrawler/1.0; +https://velen.io)"},
    {"name": "Webzio-Extended", "company": "Webz.io", "category": "other", "token": "Webzio-Extended", "user_agent": "Mozilla/5.0 (compatible; Webzio-Extended/1.0; +https://webz.io/bot.html)"},
    {"name": "omgili", "company": "Webz.io", "category": "other", "token": "omgili", "user_agent": "Mozilla/5.0 (compatible; omgili/0.5; +http://omgili.com)"},
    {"name": "omgilibot", "company": "Webz.io", "category": "other", "token": "omgilibot", "user_agent": "Mozilla/5.0 (compatible; omgilibot/0.5; +http://omgili.com)"},
    {"name": "Kangaroo Bot", "company": "Kangaroo", "category": "other", "token": "Kangaroo Bot", "user_agent": "Mozilla/5.0 (compatible; Kangaroo Bot/1.0)"},
    {"name": "Ai2Bot", "company": "Allen Institute for AI", "category": "llm", "token": "Ai2Bot", "user_agent": "Mozilla/5.0 (compatible; AI2Bot/1.0; +https://www.allenai.org/)"},
    {"name": "Ai2Bot-Dolma", "company": "Allen Institute for AI", "category": "llm", "token": "Ai2Bot-Dolma", "user_agent": "Mozilla/5.0 (compatible; Ai2Bot-Dolma; +https://www.allenai.org/)"},
    {"name": "iaskspider", "company": "iAsk", "category": "search", "token": "iaskspider", "user_agent": "Mozilla/5.0 (compatible; iaskspider/2.0; +http://iask.com/spider)"},
    {"name": "Scrapy", "company": "Scrapy", "category": "other", "token": "Scrapy", "user_agent": "Scrapy/2.11.1 (+https://scrapy.org)"},
    {"name": "img2dataset", "company": "img2dataset", "category": "other", "token": "img2dataset", "user_agent": "img2dataset/1.0"},
    {"name": "ICC-Crawler", "company": "NICT", "category": "other", "token": "ICC-Crawler", "user_agent": "ICC-Crawler/2.0 (Mozilla-compatible; ; http://ucri.nict.go.jp/en/icccrawler.html)"},
    {"name": "Sidetrade indexer bot", "company": "Sidetrade", "category": "other", "token": "Sidetrade indexer bot", "user_agent": "Mozilla/5.0 (compatible; Sidetrade indexer bot; +http://bot.sidetrade.com)"},
    {"name": "DataForSeoBot", "company": "DataForSEO", "category": "seo_tool", "token": "DataForSeoBot", "user_agent": "Mozilla/5.0 (compatible; DataForSeoBot/1.0; +https://dataforseo.com/dataforseo-bot)"},
    {"name": "Brightbot", "company": "Bright Data", "category": "other", "token": "Brightbot", "user_agent": "Mozilla/5.0 (compatible; Brightbot/1.0)"},
    {"name": "FriendlyCrawler", "company": "FriendlyCrawler", "category": "other", "token": "FriendlyCrawler", "user_agent": "Mozilla/5.0 (compatible; FriendlyCrawler/1.0)"},
    {"name": "ISSCyberRiskCrawler", "company": "ISS", "category": "other", "token": "ISSCyberRiskCrawler", "user_agent": "Mozilla/5.0 (compatible; ISSCyberRiskCrawler/1.0)"},
    {"name": "ImagesiftBot", "company": "ImageSift", "category": "other", "token": "ImagesiftBot", "user_agent": "Mozilla/5.0 (compatible; ImagesiftBot; +imagesift.com)"},
    {"name": "sentibot", "company": "Senti", "category": "other", "token": "sentibot", "user_agent": "Mozilla/5.0 (compatible; sentibot/0.1; +http://www.sentibot.eu)"},
    {"name": "Nicecrawler", "company": "Nicecrawler", "category": "other", "token": "Nicecrawler", "user_agent": "Mozilla/5.0 (compatible; Nicecrawler/1.0)"},
    {"name": "Neevabot", "company": "Neeva", "category": "search", "token": "Neevabot", "user_agent": "Mozilla/5.0 (compatible; Neevabot/1.0; +https://neeva.com/bot)"},
    {"name": "BrightEdge Crawler", "company": "BrightEdge", "category": "seo_tool", "token": "BrightEdge Crawler", "user_agent": "Mozilla/5.0 (compatible; BrightEdge Crawler/1.0; +https://www.brightedge.com/privacy-policy)"},
    {"name": "Pinterestbot", "company": "Pinterest", "category": "social", "token": "Pinterestbot", "user_agent": "Mozilla/5.0 (compatible; Pinterestbot/1.0; +http://www.pinterest.com/bot.html)"},
    {"name": "Turnitin", "company": "Turnitin", "category": "other", "token": "TurnitinBot", "user_agent": "Mozilla/5.0 (compatible; TurnitinBot/3.0; +http://www.turnitin.com/robot/crawlerinfo.html)"},
    {"name": "Grapeshot", "company": "Oracle", "category": "other", "token": "GrapeshotCrawler", "user_agent": "Mozilla/5.0 (compatible; GrapeshotCrawler/2.0; +http://www.grapeshot.co.uk/crawler.php)"},
    {"name": "SemrushBot", "company": "Semrush", "category": "seo_tool", "token": "SemrushBot", "user_agent": "Mozilla/5.0 (compatible; SemrushBot/7~bl; +http://www.semrush.com/bot.html)"},
    {"name": "AhrefsBot", "company": "Ahrefs", "category": "seo_tool", "token": "AhrefsBot", "user_agent": "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)"},
    {"name": "MJ12bot", "company": "Majestic", "category": "seo_tool", "token": "MJ12bot", "user_agent": "Mozilla/5.0 (compatible; MJ12bot/v1.4.8; http://mj12bot.com/)"},
    {"name": "DotBot", "company": "Moz", "category": "seo_tool", "token": "DotBot", "user_agent": "Mozilla/5.0 (compatible; DotBot/1.2; +https://opensiteexplorer.org/dotbot)"},
    {"name": "BLEXBot", "company": "WebMeUp", "category": "seo_tool", "token": "BLEXBot", "user_agent": "Mozilla/5.0 (compatible; BLEXBot/1.0; +http://webmeup-crawler.com/)"},
    {"name": "Sogou web spider", "company": "Sogou", "category": "search", "token": "Sogou web spider", "user_agent": "Sogou web spider/4.0 (+http://www.sogou.com/docs/help/webmasters.htm#07)"},
    {"name": "Baiduspider", "company": "Baidu", "category": "search", "token": "Baiduspider", "user_agent": "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)"},
    {"name": "Yeti", "company": "Naver", "category": "search", "token": "Yeti", "user_agent": "Mozilla/5.0 (compatible; Yeti/1.1; +http://naver.me/spd)"},
    {"name": "Qwantify", "company": "Qwant", "category": "search", "token": "Qwantify", "user_agent": "Mozilla/5.0 (compatible; Qwantify/1.0; +https://www.qwant.com/)"},
    {"name": "archive.org_bot", "company": "Internet Archive", "category": "other", "token": "archive.org_bot", "user_agent": "Mozilla/5.0 (compatible; archive.org_bot +http://www.archive.org/details/archive.org_bot)"},
    {"name": "ia_archiver", "company": "Internet Archive", "category": "other", "token": "ia_archiver", "user_agent": "ia_archiver (+http://www.archive.org/details/archive.org_bot)"},
    {"name": "Exabot", "company": "Exalead", "category": "search", "token": "Exabot", "user_agent": "Mozilla/5.0 (compatible; Exabot/3.0; +http://www.exabot.com/go/robot)"},
    {"name": "Bingbot", "company": "Microsoft", "category": "search", "token": "bingbot", "user_agent": "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"},
    {"name": "DuckDuckBot", "company": "DuckDuckGo", "category": "search", "token": "DuckDuckBot", "user_agent": "DuckDuckBot/1.1; (+http://duckduckgo.com/duckduckbot.html)"},
    {"name": "Twitterbot", "company": "X/Twitter", "category": "social", "token": "Twitterbot", "user_agent": "Twitterbot/1.0"},
    {"name": "LinkedInBot", "company": "LinkedIn", "category": "social", "token": "LinkedInBot", "user_agent": "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)"},
    {"name": "Slackbot", "company": "Slack", "category": "social", "token": "Slackbot", "user_agent": "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)"},
    {"name": "TelegramBot", "company": "Telegram", "category": "social", "token": "TelegramBot", "user_agent": "TelegramBot (like TwitterBot)"},
    {"name": "WhatsApp", "company": "WhatsApp", "category": "social", "token": "WhatsApp", "user_agent": "WhatsApp/2.23.20.0 A"},
]


PRIORITY_CATEGORIES = {"llm", "search"}
WAF_CODES = {401, 403, 406, 429, 451, 503}


def normalize_target(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        raise ValueError("target URL/domain is empty")
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urllib.parse.urlparse(raw)
    if not parsed.netloc:
        raise ValueError(f"invalid target URL: {raw}")
    path = parsed.path or "/"
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", parsed.query, ""))


def robots_url_for(target_url: str, explicit: str | None) -> str:
    if explicit:
        return normalize_target(explicit)
    parsed = urllib.parse.urlparse(target_url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))


def selected_bots(names: str | None, categories: str | None, limit: int | None) -> list[dict[str, str]]:
    bots = BOT_CATALOG
    if categories:
        allowed = {item.strip().lower() for item in categories.split(",") if item.strip()}
        bots = [bot for bot in bots if bot["category"].lower() in allowed]
    if names:
        wanted = {item.strip().lower() for item in names.split(",") if item.strip()}
        bots = [bot for bot in bots if bot["name"].lower() in wanted or bot["token"].lower() in wanted]
    if limit:
        bots = bots[:limit]
    return bots


def fetch(url: str, user_agent: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "text/plain,text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read(512_000)
            final_url = response.geturl()
            return {
                "ok": True,
                "status_code": int(response.status),
                "final_url": final_url,
                "redirected": final_url != url,
                "content_type": response.headers.get("Content-Type", ""),
                "body": body.decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(64_000)
        return {
            "ok": False,
            "status_code": int(exc.code),
            "final_url": exc.geturl(),
            "redirected": exc.geturl() != url,
            "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
            "body": body.decode("utf-8", errors="replace"),
            "error": str(exc),
        }
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError) as exc:
        return {"ok": False, "status_code": None, "final_url": url, "redirected": False, "body": "", "error": str(exc)}


def strip_comment(line: str) -> str:
    return line.split("#", 1)[0].strip()


def parse_robots(text: str) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = strip_comment(raw)
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if current is None or current.get("rules"):
                current = {"agents": [], "rules": []}
                groups.append(current)
            current["agents"].append(value.lower())
            continue
        if current is None:
            continue
        if key in {"allow", "disallow"}:
            current["rules"].append({"directive": key, "path": value})
    return groups


def robots_pattern_matches(pattern: str, url_path: str) -> bool:
    if pattern == "":
        return False
    escaped = re.escape(pattern).replace(r"\*", ".*")
    if escaped.endswith(r"\$"):
        regex = "^" + escaped[:-2] + "$"
    else:
        regex = "^" + escaped
    return re.search(regex, url_path) is not None


def robots_decision(groups: list[dict[str, Any]], token: str, url_path: str) -> dict[str, Any]:
    token_l = token.lower()
    specific = [
        group
        for group in groups
        if any(agent != "*" and (agent in token_l or token_l in agent) for agent in group.get("agents", []))
    ]
    wildcard = [group for group in groups if any(agent == "*" for agent in group.get("agents", []))]
    matching = specific or wildcard
    best: dict[str, Any] | None = None
    for group in matching:
        for rule in group.get("rules", []):
            path = rule.get("path", "")
            if not robots_pattern_matches(path, url_path):
                continue
            length = len(path.replace("*", "").replace("$", ""))
            candidate = {"directive": rule["directive"], "path": path, "length": length}
            if best is None or length > best["length"] or (length == best["length"] and candidate["directive"] == "allow"):
                best = candidate
    if best is None:
        return {"status": "allow", "matched_rule": None}
    return {
        "status": "disallow" if best["directive"] == "disallow" else "allow",
        "matched_rule": f"{best['directive'].title()}: {best['path']}",
    }


def classify(robots_status: str, http: dict[str, Any]) -> str:
    code = http.get("status_code")
    if robots_status == "disallow":
        return "robots_block"
    if code in WAF_CODES:
        return "waf_block"
    if code is None:
        return "unreachable"
    if 300 <= int(code) < 400 or http.get("redirected"):
        return "redirect"
    if 200 <= int(code) < 300:
        return "available"
    if 500 <= int(code) < 600:
        return "server_error"
    if 400 <= int(code) < 500:
        return "client_error"
    return "unknown"


def outcome_label(outcome: str) -> str:
    return {
        "available": "available",
        "redirect": "redirect",
        "robots_block": "robots block",
        "waf_block": "CDN/WAF block",
        "unreachable": "timeout/unreachable",
        "server_error": "server error",
        "client_error": "client error",
    }.get(outcome, outcome)


def output_paths(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    return {
        "markdown": policy_path(cfg, project_root, "ai_bot_access_check_report", "seo/vnext/ai-bot-access-check.md"),
        "json": policy_path(cfg, project_root, "ai_bot_access_check_json", "seo/vnext/ai-bot-access-check.json"),
        "latest_markdown": policy_path(cfg, project_root, "latest_ai_bot_access_check", "seo/vnext/latest-ai-bot-access-check.md"),
        "latest_json": policy_path(cfg, project_root, "latest_ai_bot_access_check_json", "seo/vnext/latest-ai-bot-access-check.json"),
    }


def build_findings(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    blocked_priority = [row for row in results if row["category"] in PRIORITY_CATEGORIES and row["outcome"] in {"robots_block", "waf_block", "server_error", "unreachable"}]
    blocked_llm = [row for row in blocked_priority if row["category"] == "llm"]
    blocked_search = [row for row in blocked_priority if row["category"] == "search"]
    if blocked_llm:
        findings.append(
            {
                "id": "llm_crawlers_blocked",
                "severity": "high",
                "status": "issue",
                "message": f"{len(blocked_llm)} LLM crawlers are blocked or unavailable.",
                "bots": [row["name"] for row in blocked_llm[:15]],
            }
        )
    if blocked_search:
        findings.append(
            {
                "id": "search_crawlers_blocked",
                "severity": "high",
                "status": "issue",
                "message": f"{len(blocked_search)} search crawlers are blocked or unavailable.",
                "bots": [row["name"] for row in blocked_search[:15]],
            }
        )
    waf = [row for row in results if row["outcome"] == "waf_block"]
    if waf:
        findings.append(
            {
                "id": "possible_cdn_waf_or_hosting_block",
                "severity": "high",
                "status": "issue",
                "message": f"{len(waf)} crawlers returned WAF-like HTTP codes.",
                "bots": [row["name"] for row in waf[:15]],
            }
        )
    return findings


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    category_counts: dict[str, dict[str, int]] = {}
    for row in results:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
        bucket = category_counts.setdefault(row["category"], {})
        bucket[row["outcome"]] = bucket.get(row["outcome"], 0) + 1
    return {
        "total_checked": len(results),
        "available": counts.get("available", 0),
        "redirect": counts.get("redirect", 0),
        "robots_block": counts.get("robots_block", 0),
        "waf_block": counts.get("waf_block", 0),
        "unreachable": counts.get("unreachable", 0),
        "server_error": counts.get("server_error", 0),
        "client_error": counts.get("client_error", 0),
        "by_category": category_counts,
    }


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    project = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    target_seed = args.url or args.domain or project.get("domain")
    if not target_seed:
        raise SystemExit("ERROR: provide --url/--domain or project.domain in seo-cycle.yaml")
    target_url = normalize_target(target_seed)
    robots_url = robots_url_for(target_url, args.robots_url)
    path = urllib.parse.urlparse(target_url).path or "/"
    bots = selected_bots(args.bots, args.categories, args.limit)
    robots_fetch = fetch(robots_url, "Mozilla/5.0 (compatible; seo-cycle-ai-bot-access-check/1.0)", args.timeout)
    robots_groups = parse_robots(robots_fetch.get("body", "")) if robots_fetch.get("body") else []
    results: list[dict[str, Any]] = []
    for bot in bots:
        decision = robots_decision(robots_groups, bot["token"], path)
        http = fetch(target_url, bot["user_agent"], args.timeout)
        result = {
            "name": bot["name"],
            "company": bot["company"],
            "category": bot["category"],
            "robots_token": bot["token"],
            "robots": decision["status"],
            "robots_rule": decision["matched_rule"],
            "http_code": http.get("status_code"),
            "final_url": http.get("final_url"),
            "redirected": http.get("redirected"),
            "outcome": classify(decision["status"], http),
            "error": http.get("error"),
        }
        results.append(result)
    paths = output_paths(cfg, project_root)
    report = {
        "audit_id": "ai_bot_access_check",
        "slug": "ai-bot-access-check",
        "title": "AI Bot Access Check",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": {"name": project.get("name"), "domain": project.get("domain")},
        "target": {"url": target_url, "robots_url": robots_url, "path": path},
        "config": {
            "mode": "explicit_live_check",
            "paid_api_required": False,
            "writes_to_site": False,
            "timeout_seconds": args.timeout,
            "requested_bots": len(bots),
        },
        "robots": {
            "status_code": robots_fetch.get("status_code"),
            "ok": robots_fetch.get("ok"),
            "groups": len(robots_groups),
            "final_url": robots_fetch.get("final_url"),
            "error": robots_fetch.get("error"),
        },
        "summary": summarize(results),
        "findings": build_findings(results),
        "results": results,
        "actions": [
            "Fix robots.txt only when a priority crawler is explicitly disallowed and project policy allows that crawler.",
            "If robots.txt allows a crawler but HTTP returns 403/429/503, inspect CDN/WAF, hosting anti-bot rules, or Nginx user-agent rules.",
            "Keep deliberate SEO-tool blocks separate from AI/search crawler access decisions.",
            "For RF projects, this check does not install analytics tags or foreign counters; it is a read-only public fetch.",
        ],
        "source_policy": {
            "report_only": True,
            "raw_data_in_context": False,
            "paid_api_default": "disabled",
            "publish_default": "disabled",
        },
        "paths": {key: str(path_value.relative_to(project_root)) for key, path_value in paths.items()},
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['title']}",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Target: {report['target']['url']}",
        f"- Robots: {report['target']['robots_url']} (`{report['robots']['status_code']}`)",
        f"- Mode: `{report['config']['mode']}`",
        "- Guardrail: report-only; no site changes, index submission, tracking tags, ads, or paid APIs.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    summary = report["summary"]
    for key in ("total_checked", "available", "redirect", "robots_block", "waf_block", "unreachable", "server_error", "client_error"):
        lines.append(f"| {key} | {summary.get(key, 0)} |")
    lines.extend(["", "## Findings", ""])
    if report["findings"]:
        for finding in report["findings"]:
            bots = ", ".join(finding.get("bots", []))
            suffix = f" Bots: {bots}" if bots else ""
            lines.append(f"- `{finding['severity']}` `{finding['id']}`: {finding['message']}{suffix}")
    else:
        lines.append("- No priority crawler blocks detected in this run.")
    lines.extend(["", "## Results", ""])
    for category in ("llm", "search", "social", "seo_tool", "other"):
        rows = [row for row in report["results"] if row["category"] == category]
        if not rows:
            continue
        lines.extend([f"### {category}", "", "| Bot | Company | robots.txt | HTTP | Outcome |", "| --- | --- | --- | ---: | --- |"])
        for row in rows:
            robots = row["robots"]
            if row.get("robots_rule"):
                robots = f"{robots} ({row['robots_rule']})"
            code = row["http_code"] if row["http_code"] is not None else "-"
            lines.append(f"| {row['name']} | {row['company']} | {robots} | {code} | {outcome_label(row['outcome'])} |")
        lines.append("")
    lines.extend(["## Actions", ""])
    for action in report["actions"]:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], cfg_path: pathlib.Path) -> None:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    paths = {key: rel_path(project_root, path) for key, path in report["paths"].items()}
    markdown = render_markdown(report)
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    write_text(paths["markdown"], markdown)
    write_text(paths["json"], json_text)
    write_text(paths["latest_markdown"], markdown)
    write_text(paths["latest_json"], json_text)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check live HTTP access for AI/search/social/SEO crawler User-Agents.")
    parser.add_argument("config", nargs="?", type=pathlib.Path, help="Path to seo-cycle.yaml. If omitted, search cwd.")
    parser.add_argument("--url", help="Full public URL to test. Defaults to https://<project.domain>/")
    parser.add_argument("--domain", help="Domain shortcut for --url.")
    parser.add_argument("--robots-url", help="Explicit robots.txt URL.")
    parser.add_argument("--bots", help="Comma-separated bot names/tokens to check.")
    parser.add_argument("--categories", help="Comma-separated categories: llm,search,social,seo_tool,other.")
    parser.add_argument("--limit", type=int, help="Limit number of bots after filters; useful for tests.")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout per request in seconds.")
    parser.add_argument("--write", action="store_true", help="Write markdown/json reports under seo/vnext.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg_path = args.config or find_config(pathlib.Path.cwd())
    if not cfg_path:
        print("ERROR: seo-cycle.yaml not found", file=sys.stderr)
        return 2
    cfg_path = cfg_path.resolve()
    report = build_report(cfg_path, args)
    if args.write:
        write_report(report, cfg_path)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
