#!/usr/bin/env python3
"""seo-cycle publish — гейт → WordPress (REST + Application Password) → проверка (3.2.0).

Публикует черновик `*.publish.md`, который прошёл гейт черновика:

1. гейт: `draft-quality-gate` с правилами проекта и профилем голоса —
   любая error-находка = отказ (почини через `seo-cycle loop draft`);
2. сборка: frontmatter (title, slug, excerpt, meta_title/meta_description,
   categories/tags — id, featured_image + featured_image_alt) + тело в HTML
   (`seo_cycle_core/markdown_html.py`) + блок «Источники» из `fact_check_log`;
3. без `--live` — только план (`<черновик>.publish-plan.json`), ничего не
   отправляется;
4. с `--live` — картинки грузятся в медиатеку (один раз, кэш по sha256),
   пост создаётся или обновляется (тот же id: `wp_id` во frontmatter →
   publish-log → поиск по slug), SEO-мета по `publishing.seo_plugin`;
5. проверка живой страницы (если статус publish): у каждой недекоративной
   картинки есть alt, у inline — подпись, заголовок на месте;
6. журнал: строка в `artifacts.publish_log`, `wp_id`/`wp_url` во frontmatter
   черновика, отчёт `<черновик>.publish-report.json|md`, `07-published.md`
   цикла при `--cycle-dir`.

Статус по умолчанию — `publishing.default_status` (publish). С
`publishing.require_approval: true` для `--live` нужен одобренный тикет
`content_publish` (`--ticket`).

Ключи: WP_BASE_URL, WP_USER, WP_APP_PASSWORD (`seo-cycle auth login wordpress`).

Коды выхода: 0 — опубликовано / план; 1 — отказ гейта или тикета, ошибка
WordPress; 2 — ошибка вызова или конфига; 3 — опубликовано, но проверка
живой страницы не прошла.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import importlib.util
import io
import json
import os
import pathlib
import re
import subprocess
import sys
from html.parser import HTMLParser
from typing import Any

from seo_cycle_core.config import (
    boolish,
    config_section,
    find_project_config,
    load_yaml,
    project_root_for,
    rel_path,
    write_text,
)
from seo_cycle_core.frontmatter import split_frontmatter
from seo_cycle_core.markdown_html import FEATURED_TYPES, render
from seo_cycle_core.wordpress import WPClient, WPError, missing_credentials, seo_meta

SCRIPTS = pathlib.Path(__file__).resolve().parent
EXIT_OK, EXIT_REFUSED, EXIT_CONFIG, EXIT_VERIFY = 0, 1, 2, 3
STATUSES = ("publish", "draft", "pending", "private", "future")
PUBLISH_LOG_HEADER = ["date", "type", "url", "title", "status", "notes"]
DEFAULT_SOURCES_INTRO = "Ключевые факты в материале сверены с источниками:"


class CallError(Exception):
    """Call/config error with a ready one-line message (exit 2)."""


def _load_script(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# gate, build
# --------------------------------------------------------------------------

def run_gate(draft: pathlib.Path, outline: pathlib.Path, cfg_path: pathlib.Path) -> dict[str, Any]:
    gate = _load_script("draft_quality_gate_for_publish", "draft-quality-gate.py")
    try:
        return gate.build_report(draft, outline, cfg_path)
    except gate.CallError as exc:
        raise CallError(str(exc)) from None


def rest_base_for(cfg: dict[str, Any], kind: str) -> str:
    post_types = config_section(cfg, "publishing").get("post_types")
    value = post_types.get(kind) if isinstance(post_types, dict) else None
    value = str(value or kind or "posts").strip()
    return {"post": "posts", "page": "pages", "blog_post": "posts"}.get(value, value)


def slug_of(draft: pathlib.Path, front: dict[str, Any]) -> str:
    if front.get("slug"):
        return str(front["slug"]).strip().strip("/").split("/")[-1]
    stem = draft.name
    for suffix in (".md", ".publish", ".wp-draft", ".public"):
        stem = stem.removesuffix(suffix)
    return stem


def _ids(value: Any) -> list[int]:
    if isinstance(value, list):
        return [int(item) for item in value if isinstance(item, int) or (isinstance(item, str) and item.isdigit())]
    return []


def local_image(src: str, draft_dir: pathlib.Path, project_root: pathlib.Path) -> pathlib.Path | None:
    if re.match(r"^(?:https?:)?//", src) or src.startswith("data:"):
        return None
    for base in (draft_dir, project_root):
        candidate = (base / src.lstrip("/")).resolve() if src.startswith("/") else (base / src).resolve()
        if candidate.is_file():
            return candidate
    return (draft_dir / src).resolve()


def sources_block(front: dict[str, Any]) -> str:
    log = front.get("fact_check_log")
    if not isinstance(log, list) or not log:
        return ""
    eeat = _load_script("eeat_render_for_publish", "eeat-render.py")
    return str(eeat.render(log, "Источники", DEFAULT_SOURCES_INTRO))


def build_plan(
    draft: pathlib.Path,
    text: str,
    cfg: dict[str, Any],
    project_root: pathlib.Path,
    *,
    kind: str,
    status: str,
) -> dict[str, Any]:
    front = split_frontmatter(text)
    data = front.data
    rendered = render(front.body)
    images = []
    for image in rendered.images:
        if image.kind in ("og", "icon"):
            continue
        local = local_image(image.src, draft.parent, project_root)
        images.append({"src": image.src, "kind": image.kind, "alt": image.alt, "caption": image.caption,
                       "local": str(local) if local else None, "exists": bool(local and local.is_file()) if local else True})
    featured_src = str(data.get("featured_image") or (rendered.featured.src if rendered.featured else "") or "")
    featured_alt = str(data.get("featured_image_alt") or data.get("featured_alt")
                       or (rendered.featured.alt if rendered.featured else "") or "")
    if featured_src and not any(item["src"] == featured_src for item in images):
        local = local_image(featured_src, draft.parent, project_root)
        images.append({"src": featured_src, "kind": "hero", "alt": featured_alt, "caption": "",
                       "local": str(local) if local else None, "exists": bool(local and local.is_file()) if local else True})
    publishing = config_section(cfg, "publishing")
    title = str(data.get("title") or rendered.title or slug_of(draft, data)).strip()
    meta_title = str(data.get("meta_title") or data.get("seo_title") or "").strip()
    meta_description = str(data.get("meta_description") or data.get("description") or "").strip()
    return {
        "draft": str(draft),
        "rest_base": str(data.get("wp_type") or rest_base_for(cfg, kind)),
        "slug": slug_of(draft, data),
        "title": title,
        "status": status,
        "excerpt": str(data.get("excerpt") or "").strip(),
        "categories": _ids(data.get("categories")),
        "tags": _ids(data.get("tags")),
        "meta": seo_meta(str(publishing.get("seo_plugin") or ""), meta_title, meta_description),
        "featured": {"src": featured_src, "alt": featured_alt} if featured_src else None,
        "images": images,
        "sources_block": bool(sources_block(data)),
        "wp_id": int(data["wp_id"]) if str(data.get("wp_id") or "").isdigit() else None,
    }


def build_content(text: str, url_map: dict[str, str]) -> str:
    front = split_frontmatter(text)
    # first inline image eager (above the fold), the rest lazy — images.lazy_loading defaults
    rendered = render(front.body, url_for=lambda src: url_map.get(src, src))
    block = sources_block(front.data)
    return rendered.html + (("\n" + block) if block else "")


# --------------------------------------------------------------------------
# approvals, idempotency, media cache, logs
# --------------------------------------------------------------------------

def approved_ticket(project_root: pathlib.Path, ticket: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "approval-gate.py"), "list", "--status", "approved",
         "--type", "content_publish", "--json"],
        cwd=project_root, text=True, capture_output=True, check=False,
    )
    try:
        tickets = json.loads(proc.stdout) if proc.stdout.strip().startswith("[") else []
    except json.JSONDecodeError:
        tickets = []
    for row in tickets:
        if isinstance(row, dict) and str(row.get("id")) == ticket:
            return True, "approved"
    status = subprocess.run([sys.executable, str(SCRIPTS / "approval-gate.py"), "status", ticket],
                            cwd=project_root, text=True, capture_output=True, check=False)
    state = status.stdout.strip().splitlines()[-1].strip() if status.stdout.strip() else "not_found"
    return False, state if state != "approved" else "approved, но не типа content_publish"


def publish_log_path(cfg: dict[str, Any], project_root: pathlib.Path) -> pathlib.Path:
    raw = config_section(cfg, "artifacts").get("publish_log") or "seo/publish-log.csv"
    return rel_path(project_root, str(raw))


def logged_wp_id(log_path: pathlib.Path, draft_display: str) -> int | None:
    if not log_path.exists():
        return None
    found = None
    with log_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            notes = str(row.get("notes") or "")
            if f"draft={draft_display}" in notes:
                match = re.search(r"wp_id=(\d+)", notes)
                if match:
                    found = int(match.group(1))
    return found


def append_publish_log(log_path: pathlib.Path, row: dict[str, str]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new = not log_path.exists() or not log_path.read_text(encoding="utf-8").strip()
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PUBLISH_LOG_HEADER, lineterminator="\n")
    if new:
        writer.writeheader()
    writer.writerow(row)
    with log_path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(buffer.getvalue())


def media_cache_path(project_root: pathlib.Path) -> pathlib.Path:
    return project_root / "seo" / "publish" / "media-cache.json"


def load_media_cache(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_back_frontmatter(draft: pathlib.Path, text: str, values: dict[str, Any]) -> str:
    """Set top-level frontmatter keys textually; everything else stays byte-for-byte."""
    lines = text.splitlines(keepends=True)
    rendered = {key: f"{key}: {json.dumps(value, ensure_ascii=False)}\n" for key, value in values.items()}
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() in ("---", "...")), None)
        if end is not None:
            block = lines[1:end]
            for key, line in rendered.items():
                for index, existing in enumerate(block):
                    if re.match(rf"^{re.escape(key)}\s*:", existing):
                        block[index] = line
                        break
                else:
                    block.append(line)
            new_text = "".join([lines[0], *block, *lines[end:]])
            draft.write_text(new_text, encoding="utf-8")
            return new_text
    new_text = "---\n" + "".join(rendered.values()) + "---\n" + text
    draft.write_text(new_text, encoding="utf-8")
    return new_text


# --------------------------------------------------------------------------
# verification of the live page
# --------------------------------------------------------------------------

class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, Any]] = []
        self.figure_depth = 0
        self.figcaptions = 0
        self.figures: list[dict[str, Any]] = []
        self.h1: list[str] = []
        self._in_h1 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "figure":
            self.figures.append({"img": False, "caption": False, "alt": None})
        elif tag == "figcaption" and self.figures:
            self.figures[-1]["caption"] = True
        elif tag == "img":
            decorative = "decorative" in values.get("class", "") or values.get("role") == "presentation"
            image = {"alt": values.get("alt"), "decorative": decorative, "src": values.get("src", "")}
            self.images.append(image)
            if self.figures:
                self.figures[-1]["img"] = True
                self.figures[-1]["alt"] = image["alt"]
        elif tag == "h1":
            self._in_h1 = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self._in_h1 = False

    def handle_data(self, data: str) -> None:
        if self._in_h1:
            self.h1.append(data)


def verify_page(page_html: str, plan: dict[str, Any]) -> list[str]:
    parser = _PageParser()
    parser.feed(page_html)
    problems = []
    no_alt = [img["src"] for img in parser.images if img["alt"] is None or (not img["alt"].strip() and not img["decorative"])]
    # decorative images in our HTML are rendered with alt="" on purpose
    decorative_srcs = {item["src"] for item in plan["images"] if item["kind"] == "decorative"}
    no_alt = [src for src in no_alt if not any(src.endswith(d.split("/")[-1]) for d in decorative_srcs)]
    if no_alt:
        problems.append(f"картинки без alt на живой странице: {', '.join(no_alt[:5])}")
    captions_needed = sum(1 for item in plan["images"] if item["caption"] and item["kind"] not in FEATURED_TYPES)
    captions_seen = sum(1 for figure in parser.figures if figure["img"] and figure["caption"])
    if captions_seen < captions_needed:
        problems.append(f"подписей у картинок {captions_seen}, в черновике {captions_needed} — тема/оптимизатор их срезает")
    title = html.unescape("".join(parser.h1)).strip()
    if plan["title"] and plan["title"].lower() not in html.unescape(page_html).lower():
        problems.append("заголовка поста нет на странице")
    elif not title:
        problems.append("на странице нет H1")
    return problems


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def render_markdown(report: dict[str, Any]) -> str:
    plan = report.get("plan") or {}
    lines = [f"# Публикация: {report['status']}", ""]
    for key in ("action", "url", "wp_id", "rest_base", "slug", "post_status"):
        if report.get(key) not in (None, ""):
            lines.append(f"- {key}: {report[key]}")
    if plan:
        lines.append(f"- Заголовок: {plan.get('title')}")
        lines.append(f"- Картинок: {len(plan.get('images') or [])}; SEO-мета: {', '.join(plan.get('meta') or {}) or '-'}")
    for item in report.get("errors", []):
        lines.append(f"- ✗ {item}")
    for item in report.get("warnings", []):
        lines.append(f"- ⚠ {item}")
    for item in report.get("next", []):
        lines.append(f"- Дальше: `{item}`")
    return "\n".join(lines) + "\n"


def emit(report: dict[str, Any], fmt: str, draft: pathlib.Path, *, write: bool) -> None:
    if write:
        write_text(draft.with_suffix(".publish-report.json"), json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
        write_text(draft.with_suffix(".publish-report.md"), render_markdown(report))
    if fmt == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_markdown(report), end="")


def resolve_project(draft: pathlib.Path, explicit: str | None) -> tuple[pathlib.Path, pathlib.Path, dict[str, Any]]:
    if explicit:
        cfg_path = pathlib.Path(explicit).expanduser().resolve()
        if not cfg_path.exists():
            raise CallError(f"конфиг не найден: {cfg_path}")
    else:
        found = find_project_config(draft.parent)
        if found is None:
            raise CallError("seo-cycle.yaml не найден вверх от черновика — публикация берёт правила проекта из конфига (--config)")
        cfg_path = found
    cfg = load_yaml(cfg_path)
    if not cfg:
        raise CallError(f"конфиг пуст: {cfg_path}")
    return cfg_path, project_root_for(cfg_path), cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("draft", help="Черновик *.publish.md")
    parser.add_argument("--outline", required=True, help="page-outline JSON (для гейта черновика)")
    parser.add_argument("--config", help="seo-cycle.yaml (по умолчанию — ближайший вверх от черновика)")
    parser.add_argument("--live", action="store_true", help="Отправить в WordPress (без флага — только план)")
    parser.add_argument("--status", choices=STATUSES, help="Статус поста (по умолчанию publishing.default_status)")
    parser.add_argument("--type", dest="kind", default="blog", help="Ключ publishing.post_types (blog, static_pages, …) или rest_base")
    parser.add_argument("--ticket", help="Одобренный тикет content_publish (нужен при publishing.require_approval)")
    parser.add_argument("--cycle-dir", help="Каталог цикла seo/cycles/<тема> — дописать 07-published.md")
    parser.add_argument("--no-verify", action="store_true", help="Не проверять живую страницу")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    draft = pathlib.Path(args.draft).expanduser().resolve()
    outline = pathlib.Path(args.outline).expanduser().resolve()
    report: dict[str, Any] = {"script": "wp-publish", "draft": str(draft), "status": "", "errors": [], "warnings": [], "next": []}
    try:
        try:
            text = draft.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CallError(f"черновик не прочитан: {draft}: {exc}") from None
        cfg_path, project_root, cfg = resolve_project(draft, args.config)
        publishing = config_section(cfg, "publishing")
        status = args.status or str(publishing.get("default_status") or "publish")
        if status not in STATUSES:
            raise CallError(f"publishing.default_status={status!r} — допустимо {', '.join(STATUSES)}")
        gate = run_gate(draft, outline, cfg_path)
    except CallError as exc:
        print(f"ERROR: {str(exc).replace(chr(10), ' ')}", file=sys.stderr)
        return EXIT_CONFIG

    errors = [f for f in gate.get("findings", []) if f.get("severity") in ("error", "critical")]
    if errors:
        report.update(status="refused_by_gate", errors=[f"{f['id']}: {f.get('message', '')}" for f in errors[:20]],
                      next=[f"seo-cycle loop draft {args.draft} --outline {args.outline}"])
        emit(report, args.format, draft, write=False)
        return EXIT_REFUSED

    plan = build_plan(draft, text, cfg, project_root, kind=args.kind, status=status)
    report["plan"] = plan
    missing_files = [item["src"] for item in plan["images"] if not item["exists"]]
    if missing_files:
        report.update(status="refused", errors=[f"файл картинки не найден: {src}" for src in missing_files])
        emit(report, args.format, draft, write=False)
        return EXIT_REFUSED

    if not args.live:
        write_text(draft.with_suffix(".publish-plan.json"), json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
        report.update(status="plan", next=[f"seo-cycle publish {args.draft} --outline {args.outline} --live"])
        if plan["wp_id"]:
            report["action"] = "update"
        emit(report, args.format, draft, write=False)
        return EXIT_OK

    # ---- live --------------------------------------------------------------
    if not boolish(publishing.get("enabled"), False):
        print("ERROR: publishing.enabled: false в seo-cycle.yaml — включи публикацию в конфиге", file=sys.stderr)
        return EXIT_CONFIG
    missing = missing_credentials(dict(os.environ))
    if missing:
        print(f"ERROR: нет {', '.join(missing)} — seo-cycle auth login wordpress", file=sys.stderr)
        return EXIT_CONFIG
    if boolish(publishing.get("require_approval"), False):
        if not args.ticket:
            print("ERROR: publishing.require_approval: true — нужен --ticket <одобренный content_publish>", file=sys.stderr)
            return EXIT_REFUSED
        ok, state = approved_ticket(project_root, args.ticket)
        if not ok:
            print(f"ERROR: тикет {args.ticket}: {state} — публикация отклонена", file=sys.stderr)
            return EXIT_REFUSED

    client = WPClient.from_env(dict(os.environ))
    log_path = publish_log_path(cfg, project_root)
    draft_display = os.path.relpath(draft, project_root)
    cache_path = media_cache_path(project_root)
    cache = load_media_cache(cache_path)
    try:
        url_map: dict[str, str] = {}
        featured_id = None
        for item in plan["images"]:
            if not item["local"]:
                continue
            local = pathlib.Path(item["local"])
            digest = hashlib.sha256(local.read_bytes()).hexdigest()
            cached = cache.get(digest)
            if not cached:
                media = client.upload_media(local, alt=item["alt"] if item["kind"] != "decorative" else "",
                                            caption=item["caption"], title=item["alt"])
                cached = {"id": media["id"], "url": media.get("source_url") or "", "file": local.name}
                cache[digest] = cached
                write_text(cache_path, json.dumps(cache, ensure_ascii=False, indent=2) + "\n")
            url_map[item["src"]] = str(cached["url"])
            if plan["featured"] and item["src"] == plan["featured"]["src"]:
                featured_id = cached["id"]

        existing_id = plan["wp_id"] or logged_wp_id(log_path, draft_display)
        if existing_id and client.get_item(plan["rest_base"], existing_id) is None:
            report["warnings"].append(f"пост wp_id={existing_id} не найден — ищу по slug")
            existing_id = None
        if not existing_id:
            found = client.find_by_slug(plan["rest_base"], plan["slug"])
            existing_id = int(found["id"]) if found else None
        payload: dict[str, Any] = {
            "title": plan["title"], "slug": plan["slug"], "status": plan["status"],
            "content": build_content(text, url_map),
        }
        if plan["excerpt"]:
            payload["excerpt"] = plan["excerpt"]
        if plan["categories"]:
            payload["categories"] = plan["categories"]
        if plan["tags"]:
            payload["tags"] = plan["tags"]
        if featured_id:
            payload["featured_media"] = featured_id
        if plan["meta"]:
            payload["meta"] = plan["meta"]
        result = client.upsert(plan["rest_base"], payload, existing_id)
    except WPError as exc:
        report.update(status="failed", errors=[str(exc)])
        emit(report, args.format, draft, write=True)
        return EXIT_REFUSED

    action = "update" if existing_id else "create"
    wp_id = int(result["id"])
    url = str(result.get("link") or "")
    if plan["meta"]:
        stored = result.get("meta") if isinstance(result.get("meta"), dict) else {}
        dropped = [key for key in plan["meta"] if key not in stored]
        if dropped:
            report["warnings"].append(
                f"SEO-мета не записалась ({', '.join(dropped)}): поле не открыто в REST — включи show_in_rest для плагина или заполни вручную")
    report.update(status="published" if plan["status"] == "publish" else "saved", action=action, wp_id=wp_id,
                  url=url, rest_base=plan["rest_base"], slug=plan["slug"], post_status=result.get("status") or plan["status"])

    exit_code = EXIT_OK
    verify = boolish(publishing.get("verify_after_publish"), True) and not args.no_verify
    if verify and plan["status"] == "publish" and url:
        try:
            problems = verify_page(client.fetch_page(url), plan)
        except WPError as exc:
            problems = [str(exc)]
        report["verify"] = "failed" if problems else "ok"
        if problems:
            report["warnings"].extend(problems)
            exit_code = EXIT_VERIFY

    today = dt.date.today().isoformat()
    append_publish_log(log_path, {
        "date": today, "type": plan["rest_base"], "url": url, "title": plan["title"],
        "status": str(report["post_status"]),
        "notes": f"wp_id={wp_id}; draft={draft_display}; action={action}" + (f"; ticket={args.ticket}" if args.ticket else ""),
    })
    write_back_frontmatter(draft, text, {"wp_id": wp_id, "wp_url": url})
    if args.cycle_dir:
        cycle = pathlib.Path(args.cycle_dir).expanduser()
        cycle = cycle if cycle.is_absolute() else project_root / cycle
        target = cycle / "07-published.md"
        prior = target.read_text(encoding="utf-8") if target.exists() else "# 07 — Опубликовано\n\n| Дата | URL | Заголовок | Статус |\n|---|---|---|---|\n"
        write_text(target, prior + f"| {today} | {url} | {plan['title']} | {report['post_status']} |\n")
    if plan["status"] == "publish" and url:
        report["next"] = [f"seo-cycle run script indexnow-submit --url {url} --live",
                          f"seo-cycle run script yandex-recrawl-submit --mode submit --url {url} --live"]
    emit(report, args.format, draft, write=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
