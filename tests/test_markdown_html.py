#!/usr/bin/env python3
"""seo_cycle_core.markdown_html — draft markdown → WordPress post HTML (3.2.0)."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seo_cycle_core.markdown_html import inline, render  # noqa: E402


class InlineTest(unittest.TestCase):
    def test_escape_bold_italic_code_links(self) -> None:
        self.assertEqual(inline("a < b & **жирный** и *курсив*"),
                         "a &lt; b &amp; <strong>жирный</strong> и <em>курсив</em>")
        self.assertEqual(inline("`<x> **не жирный**`"), "<code>&lt;x&gt; **не жирный**</code>")
        self.assertEqual(inline('[раздел **A**](/catalog/?a=1&b=2 "T")'),
                         '<a href="/catalog/?a=1&amp;b=2" title="T">раздел <strong>A</strong></a>')
        self.assertEqual(inline("snake_case_name и 2*3*4"), "snake_case_name и 2*3*4")


class RenderTest(unittest.TestCase):
    def test_title_headings_paragraphs(self) -> None:
        result = render("# Как выбрать *минвату*\n\nПервый\nабзац.\n\n## Плотность\n\n#### Мелко\n\nТекст.\n")
        self.assertEqual(result.title, "Как выбрать минвату")
        self.assertEqual(result.html, "<p>Первый абзац.</p>\n<h2>Плотность</h2>\n<h4>Мелко</h4>\n<p>Текст.</p>")
        self.assertIn("<h2>Второй</h2>", render("# A\n\n# Второй\n").html)  # extra H1 demoted

    def test_images_captions_featured_decorative_lazy(self) -> None:
        md = ('![Плита в разрезе](/cut.webp "hero")\n\n'
              '![Монтаж плиты](/frame.webp)\n*Плиту ставят враспор.*\n\n'
              '![Слои](/layers.webp) _Пирог стены._\n\n'
              '![узор](/pattern.webp "decorative")\n\n![og](/og.png "og")\n')
        result = render(md, url_for=lambda src: "https://cdn.example.com" + src)
        self.assertEqual(result.featured.src, "/cut.webp")
        self.assertNotIn("cut.webp", result.html)
        self.assertNotIn("og.png", result.html)
        self.assertIn('<figure><img src="https://cdn.example.com/frame.webp" alt="Монтаж плиты">'
                      "<figcaption>Плиту ставят враспор.</figcaption></figure>", result.html)
        self.assertIn('alt="Слои" loading="lazy"><figcaption>Пирог стены.</figcaption>', result.html)
        self.assertIn('alt="" loading="lazy"></figure>', result.html)
        self.assertEqual([img.kind for img in result.images], ["hero", "", "", "decorative", "og"])
        self.assertNotIn('loading="lazy"', render("![a](/a.webp)\n", lazy=False).html)

    def test_lists_tables_quotes_code_rule_raw_html(self) -> None:
        md = ("- раз\n- **два**\n\n1. первый\n2. второй\n\n| A | B |\n|---|---|\n| 1 | <2> |\n\n"
              "> цитата\n> дальше\n\n```python\nx = '<b>'\n```\n\n---\n\n<figure class=\"x\"><img src=\"/r.webp\" alt=\"r\"></figure>\n")
        out = render(md).html
        self.assertIn("<ul><li>раз</li><li><strong>два</strong></li></ul>", out)
        self.assertIn("<ol><li>первый</li><li>второй</li></ol>", out)
        self.assertIn("<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>1</td><td>&lt;2&gt;</td></tr></tbody></table>", out)
        self.assertIn("<blockquote><p>цитата дальше</p></blockquote>", out)
        self.assertIn('<pre><code class="language-python">x = \'&lt;b&gt;\'</code></pre>', out)
        self.assertIn("<hr>", out)
        self.assertIn('<figure class="x"><img src="/r.webp" alt="r"></figure>', out)

    def test_paragraph_html_is_escaped(self) -> None:
        self.assertEqual(render("Цена <script>x</script> 5 руб.\n").html,
                         "<p>Цена &lt;script&gt;x&lt;/script&gt; 5 руб.</p>")


if __name__ == "__main__":
    unittest.main()
