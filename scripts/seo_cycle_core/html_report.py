"""Shared self-contained HTML rendering for human-facing reports.

client-report.py and position-progress.py both print markdown first and wrap
it into a styled standalone page here — one place for the table/list parser
and the print-friendly stylesheet, no external assets so the file opens
offline and converts to PDF via headless Chrome.
"""

from __future__ import annotations

import html

DEFAULT_ACCENT = "#0f6b54"


def inline_html(text: str) -> str:
    """Escape + minimal markdown inline: **bold**."""
    escaped = html.escape(text)
    while "**" in escaped:
        escaped = escaped.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
    return escaped


def markdown_to_html_body(markdown_body: str) -> str:
    out: list[str] = []
    lines = markdown_body.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("|"):
            table_lines = []
            while index < len(lines) and lines[index].startswith("|"):
                table_lines.append(lines[index])
                index += 1
            out.append("<table>")
            header_done = False
            for raw in table_lines:
                cells = [cell.strip() for cell in raw.strip("|").split("|")]
                if set("".join(cells)) <= {"-", ":", " "}:
                    continue
                tag = "td" if header_done else "th"
                header_done = True
                out.append("<tr>" + "".join(f"<{tag}>{inline_html(cell)}</{tag}>" for cell in cells) + "</tr>")
            out.append("</table>")
            continue
        if line.startswith("- "):
            out.append("<ul>")
            while index < len(lines) and lines[index].lstrip().startswith("- "):
                out.append(f"<li>{inline_html(lines[index].lstrip()[2:])}</li>")
                index += 1
            out.append("</ul>")
            continue
        if line.startswith("# "):
            out.append(f"<h1>{inline_html(line[2:])}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{inline_html(line[3:])}</h2>")
        elif line.startswith("### "):
            out.append(f"<h3>{inline_html(line[4:])}</h3>")
        elif line.strip() == "---":
            out.append("<hr>")
        elif line.strip():
            out.append(f"<p>{inline_html(line)}</p>")
        index += 1
    return "\n".join(out)


def bar(value: float, max_value: float, color: str = DEFAULT_ACCENT, label: str = "") -> str:
    """Inline horizontal bar (pure CSS) for visual trend rows."""
    share = 0.0 if max_value <= 0 else min(1.0, max(0.0, value / max_value))
    text = html.escape(label or f"{value:g}")
    return (f'<div class="bar-row"><div class="bar" style="width:{share * 100:.0f}%;'
            f'background:{color}"></div><span class="bar-label">{text}</span></div>')


def html_page(title: str, body: str, accent: str = DEFAULT_ACCENT, extra_css: str = "") -> str:
    accent = html.escape(accent or DEFAULT_ACCENT)
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;max-width:860px;margin:2rem auto;padding:0 1.5rem;color:#1a1a1a;line-height:1.55}}
h1{{color:{accent};border-bottom:3px solid {accent};padding-bottom:.4rem}}
h2{{color:{accent};margin-top:2rem}} h3{{margin-top:1.4rem}}
table{{border-collapse:collapse;width:100%;margin:.7rem 0}}
td,th{{border:1px solid #ddd;padding:.45rem .7rem;text-align:left;font-size:.95rem}}
li{{margin:.25rem 0}} strong{{color:{accent}}}
hr{{border:none;border-top:1px solid #ddd;margin:2rem 0}}
.bar-row{{display:flex;align-items:center;gap:.5rem;margin:.15rem 0}}
.bar{{height:14px;border-radius:3px;min-width:2px}}
.bar-label{{font-size:.85rem;color:#444;white-space:nowrap}}
@media print{{body{{margin:0;max-width:none}}}}
{extra_css}
</style></head><body>
{body}
</body></html>
"""
