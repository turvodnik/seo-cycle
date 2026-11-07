"""Markdown draft → WordPress post HTML, stdlib only (3.2.0).

`html_report.markdown_to_html_body` renders reports (headings, lists, tables,
bold) and escapes everything else — no links, images, italics or captions.
A post body needs those, with the same image conventions the draft gate
checks (`seo_cycle_core/draft_checks.py`):

- the image type is the markdown title: `![alt](file.webp "hero")`;
- the caption is the next non-empty line in italics (`*…*` / `_…_`) and
  becomes `<figcaption>`;
- `hero`/`featured`/`cover` images are not put into the body — they are the
  post's featured image; `decorative` images get `alt=""`;
- the first inline image is loaded eagerly (above the fold), the rest lazily.

The H1 of the draft is the post title, not part of the body. Raw HTML lines
(`<figure>`, `<table>`, …) pass through unchanged.
"""

from __future__ import annotations

import dataclasses
import html
import re
from typing import Callable

FEATURED_TYPES = {"hero", "featured", "cover"}
SKIP_TYPES = {"og", "icon"}  # metadata images, never in the body

IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+[\"']([^\"']*)[\"'])?\s*\)\s*(.*)$")
CAPTION_RE = re.compile(r"^(?:\*(?!\*)(.+?)\*|_(?!_)(.+?)_)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
OL_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
UL_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
RAW_HTML_RE = re.compile(r"^\s*</?(?:figure|figcaption|table|thead|tbody|tr|td|th|div|section|iframe|video|aside|details|summary|img|p|ul|ol|li|blockquote|h[1-6]|hr|br|!--)\b", re.I)


@dataclasses.dataclass
class ImageRef:
    src: str
    alt: str
    kind: str
    caption: str


@dataclasses.dataclass
class RenderResult:
    title: str
    html: str
    featured: ImageRef | None
    images: list[ImageRef]


def inline(text: str) -> str:
    """Escape, then apply inline markdown: code, links, bold, italics."""
    codes: list[str] = []

    def keep_code(match: re.Match[str]) -> str:
        codes.append(f"<code>{html.escape(match.group(1), quote=False)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", keep_code, text)
    links: list[str] = []

    def keep_link(match: re.Match[str]) -> str:
        label, href = match.group(1), match.group(2)
        title = match.group(3)
        attr = f' title="{html.escape(title, quote=True)}"' if title else ""
        links.append(f'<a href="{html.escape(href, quote=True)}"{attr}>{_emphasis(html.escape(label))}</a>')
        return f"\x01{len(links) - 1}\x01"

    text = re.sub(r"(?<!!)\[([^\]]+)\]\(\s*<?([^)\s>]+)>?(?:\s+[\"']([^\"']*)[\"'])?\s*\)", keep_link, text)
    text = _emphasis(html.escape(text, quote=False))
    text = re.sub(r"\x01(\d+)\x01", lambda m: links[int(m.group(1))], text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def _emphasis(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    return re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", text)


def _caption_at(lines: list[str], index: int) -> tuple[str, int]:
    """(caption text, index after it) when lines[index:] start with an italic caption line."""
    probe = index
    while probe < len(lines) and not lines[probe].strip():
        probe += 1
    if probe < len(lines):
        match = CAPTION_RE.match(lines[probe].strip())
        if match:
            return (match.group(1) or match.group(2) or "").strip(), probe + 1
    return "", index


def render(markdown: str, *, url_for: Callable[[str], str] | None = None, lazy: bool = True) -> RenderResult:
    """Render a draft body (frontmatter already removed)."""
    url_for = url_for or (lambda src: src)
    lines = markdown.splitlines()
    out: list[str] = []
    images: list[ImageRef] = []
    featured: ImageRef | None = None
    title = ""
    inline_seen = 0
    index = 0
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            out.append(f"<p>{inline(' '.join(part.strip() for part in paragraph))}</p>")
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            lang = stripped[3:].strip()
            body: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                body.append(lines[index])
                index += 1
            index += 1
            cls = f' class="language-{html.escape(lang, quote=True)}"' if lang else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(body), quote=False)}</code></pre>")
            continue
        if not stripped:
            flush()
            index += 1
            continue
        heading = HEADING_RE.match(stripped)
        if heading:
            flush()
            level = len(heading.group(1))
            text = heading.group(2)
            if level == 1 and not title:
                title = re.sub(r"[*_`]", "", text).strip()
            else:
                level = max(2, level)
                out.append(f"<h{level}>{inline(text)}</h{level}>")
            index += 1
            continue
        image = IMAGE_RE.match(stripped)
        if image:
            flush()
            alt, src, kind, tail = image.group(1), image.group(2), (image.group(3) or "").strip().lower(), image.group(4).strip()
            caption = ""
            tail_caption = CAPTION_RE.match(tail) if tail else None
            index += 1
            if tail_caption:
                caption = (tail_caption.group(1) or tail_caption.group(2) or "").strip()
            else:
                caption, index = _caption_at(lines, index)
            ref = ImageRef(src=src, alt=alt, kind=kind, caption=caption)
            images.append(ref)
            if kind in FEATURED_TYPES and featured is None:
                featured = ref
                continue
            if kind in SKIP_TYPES:
                continue
            alt_text = "" if kind == "decorative" else alt
            loading = ' loading="lazy"' if lazy and inline_seen > 0 else ""
            inline_seen += 1
            img = f'<img src="{html.escape(url_for(src), quote=True)}" alt="{html.escape(alt_text, quote=True)}"{loading}>'
            figcaption = f"<figcaption>{inline(caption)}</figcaption>" if caption else ""
            out.append(f"<figure>{img}{figcaption}</figure>")
            continue
        if stripped.startswith("|"):
            flush()
            rows: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(lines[index].strip())
                index += 1
            out.append(_table(rows))
            continue
        if stripped.startswith(">"):
            flush()
            quote: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip()[1:].strip())
                index += 1
            out.append(f"<blockquote><p>{inline(' '.join(quote))}</p></blockquote>")
            continue
        if UL_RE.match(line) or OL_RE.match(line):
            flush()
            ordered = bool(OL_RE.match(line)) and not UL_RE.match(line)
            tag = "ol" if ordered else "ul"
            pattern = OL_RE if ordered else UL_RE
            items: list[str] = []
            while index < len(lines) and pattern.match(lines[index]):
                items.append(f"<li>{inline(pattern.match(lines[index]).group(1))}</li>")  # type: ignore[union-attr]
                index += 1
            out.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue
        if stripped in ("---", "***", "___"):
            flush()
            out.append("<hr>")
            index += 1
            continue
        if RAW_HTML_RE.match(stripped):
            flush()
            out.append(stripped)
            index += 1
            continue
        paragraph.append(line)
        index += 1
    flush()
    return RenderResult(title=title, html="\n".join(out), featured=featured, images=images)


def _table(rows: list[str]) -> str:
    out = ["<table>"]
    header_done = False
    for raw in rows:
        cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell):
            continue
        tag = "td" if header_done else "th"
        if not header_done:
            out.append("<thead>")
        out.append("<tr>" + "".join(f"<{tag}>{inline(cell)}</{tag}>" for cell in cells) + "</tr>")
        if not header_done:
            out.append("</thead><tbody>")
            header_done = True
    out.append("</tbody></table>" if header_done else "</table>")
    return "".join(out)
