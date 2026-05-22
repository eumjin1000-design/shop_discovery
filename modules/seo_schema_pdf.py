"""K-Beauty-Lab-style 5-section SEO-schema PDF (English, fpdf2).

Renders a ShopCloner universal-seo-schema dict (as produced by
:func:`modules.shopcloner_export.to_universal_schema`) into the same 5-section
layout as the K Beauty Lab report, so *any* analysed shop gets a comparable
PDF:

    1. Shop Concept    2. SEO Meta (homepage)   3. Smart Collections
    4. Gem Keywords matching (table)            5. Blog Topics

Section 4 maps gem keywords to collections. ShopCloner gems carry an explicit
``category`` (multi-niche shops); shop_discovery gems do not, so a fallback
matches on distinctive words — the category's own common words are stopped
dynamically so a single-niche shop ("memory foam pillow" everywhere) still
differentiates by the meaningful token (cervical / cooling / travel ...).

Uses fpdf2 core fonts (latin-1), so no font file is needed and it runs on
Streamlit Cloud. The schema is English, so labels are English too.

Interface
---------
    report_bytes(schema, category=None) -> bytes
    report_filename(schema) -> str
"""
from __future__ import annotations

import re

from fpdf import FPDF

_HEAD_RGB = (45, 52, 54)
_ACCENT = (225, 112, 85)
_GENERIC_STOP = {
    "the", "for", "and", "with", "best", "your", "top", "rated", "premium",
    "home", "skin", "care", "products", "product", "set", "size", "amazon",
    "seller", "of",
}


def _ascii(text: str) -> str:
    s = str(text or "").replace("→", "->").replace("—", "-").replace("·", "-")
    return s.encode("latin-1", "replace").decode("latin-1")


def _fit(text: str, max_chars: int) -> str:
    """Truncate to fit a fixed-width table cell (fpdf cell() doesn't clip)."""
    s = _ascii(text)
    return s if len(s) <= max_chars else s[: max_chars - 1] + "."


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-") or "shop"


def _dynamic_stop(category: str) -> set[str]:
    """Category's own words (+ singular/plural) — too common to differentiate."""
    stop: set[str] = set()
    for w in _words(category):
        stop.add(w)
        stop.add(w.rstrip("s"))
        stop.add(w + "s")
    return stop


def _match_gems(cat: dict, gems: list[dict], extra_stop: set[str]) -> list[dict]:
    """Gems belonging to a collection. Mirrors ShopCloner.matchGemsToCategory:
    explicit gem.category (stem-matched to the name) wins; otherwise a
    meaningful, non-stopword whole-word overlap."""
    name_words = set(_words(cat.get("name", "")))
    kw_words: set[str] = set()
    for k in cat.get("keywords", []):
        kw_words.update(_words(k))

    def stem_hit(token: str) -> bool:
        return any(len(w) >= 3 and (w == token or w.startswith(token)
                   or token.startswith(w)) for w in name_words)

    out: list[dict] = []
    for g in gems:
        gem_cat = str(g.get("category") or "").strip().lower()
        if gem_cat:
            if any(len(t) >= 3 and stem_hit(t) for t in _words(gem_cat)):
                out.append(g)
        else:
            gw = _words(g.get("keyword", ""))
            if any(len(w) >= 4 and w not in _GENERIC_STOP and w not in extra_stop
                   and (w in kw_words or w in name_words) for w in gw):
                out.append(g)
    return out[:8]


class _Report(FPDF):
    def header(self) -> None:
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, "Shop Discovery - SEO Schema (ShopCloner format)", align="R")
        self.ln(7)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(160, 160, 160)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")


def _section(pdf: _Report, title: str) -> None:
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 7, _ascii(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*_ACCENT)
    pdf.set_line_width(0.6)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.l_margin + 26, y)
    pdf.ln(2)


def _kv(pdf: _Report, rows: list[tuple[str, str]]) -> None:
    fill = False
    for k, v in rows:
        pdf.set_fill_color(248, 248, 248)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(38, 7, " " + _ascii(k), fill=fill)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(0, 7, " " + _ascii(v), fill=fill, new_x="LMARGIN", new_y="NEXT")
        fill = not fill


def _thead(pdf: _Report, cols: list[tuple[str, float]]) -> None:
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(*_HEAD_RGB)
    pdf.set_text_color(255, 255, 255)
    for label, w in cols:
        pdf.cell(w, 7, " " + label, fill=True)
    pdf.ln()
    pdf.set_text_color(40, 40, 40)


def _shop_concept(pdf: _Report, sc: dict) -> None:
    _section(pdf, "1. Shop Concept")
    _kv(pdf, [(k, sc.get(k, "")) for k in ("name", "niche", "tag", "target", "tone")])


def _seo_meta(pdf: _Report, schema: dict) -> None:
    _section(pdf, "2. SEO Meta (Homepage)")
    mk = schema.get("mega_keyword", {}) or {}
    primary = mk.get("primary", "")
    shop = (schema.get("shop_concept", {}) or {}).get("name", "")
    cap = primary[:1].upper() + primary[1:] if primary else ""
    title_tag = f"{cap} & {shop.split(' ')[0]} Products | {shop}" if (primary and shop) else cap
    desc = (f"Discover {primary} - hand-picked, fast US shipping, "
            "hassle-free returns. Shop now.") if primary else ""
    _kv(pdf, [
        ("mega keyword", f"{primary}  (vol {mk.get('volume', 0):,} / KD {mk.get('kd', 0)})"),
        ("title_tag (suggested)", title_tag),
        ("description (suggested)", desc),
    ])


def _collections(pdf: _Report, cats: list[dict]) -> None:
    _section(pdf, "3. Smart Collections")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(0, 5, _ascii(f"{len(cats)} collections"), new_x="LMARGIN", new_y="NEXT")
    _thead(pdf, [("Collection", 60), ("Handle", 50), ("TITLE CONTAINS", 80)])
    fill = False
    for c in cats:
        pdf.set_fill_color(248, 248, 248)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(60, 6, " " + _fit(c.get("name", ""), 38), border="B", fill=fill)
        pdf.cell(50, 6, " " + _fit(_slug(c.get("name", "")), 32), border="B", fill=fill)
        pdf.cell(80, 6, " " + _fit(", ".join(c.get("keywords", [])[:4]), 52),
                 border="B", fill=fill, new_x="LMARGIN", new_y="NEXT")
        fill = not fill


def _gem_matching(pdf: _Report, schema: dict, category: str) -> None:
    _section(pdf, "4. Gem Keywords Matching")
    cats = schema.get("categories", []) or []
    gems = schema.get("gem_keywords", []) or []
    extra_stop = _dynamic_stop(category or
                               (schema.get("shop_concept", {}) or {}).get("niche", ""))
    _thead(pdf, [("Collection", 55), ("Gem Keyword", 95), ("Vol / KD", 40)])
    fill = False
    rows = 0
    for c in cats:
        for g in _match_gems(c, gems, extra_stop):
            pdf.set_fill_color(248, 248, 248)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(55, 6, " " + _fit(c.get("name", ""), 35), border="B", fill=fill)
            pdf.cell(95, 6, " " + _fit(g.get("keyword", ""), 62), border="B", fill=fill)
            pdf.cell(40, 6, f" {g.get('volume', 0):,} / KD {g.get('kd', 0)}",
                     border="B", fill=fill, new_x="LMARGIN", new_y="NEXT")
            fill = not fill
            rows += 1
    if rows == 0:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 6, " (no gem-to-collection matches)", new_x="LMARGIN", new_y="NEXT")


def _blog(pdf: _Report, schema: dict) -> None:
    _section(pdf, "5. Blog Topics")
    topics = schema.get("blog_topics", []) or []
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(130, 130, 130)
    if not topics:
        pdf.multi_cell(0, 5, _ascii("No topics in schema - ShopCloner generates "
                       "30 via Gemini (mega 5 + gem 15 + longtail 10) at apply time."))
        return
    pdf.set_text_color(40, 40, 40)
    for i, t in enumerate(topics[:30], 1):
        title = t.get("title") if isinstance(t, dict) else t
        pdf.multi_cell(0, 5, _ascii(f"{i}. {title}"), new_x="LMARGIN", new_y="NEXT")


def report_bytes(schema: dict, category: str | None = None) -> bytes:
    """Render a universal-seo-schema dict to the 5-section PDF; return bytes."""
    sc = schema.get("shop_concept", {}) or {}
    pdf = _Report(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 10, _ascii(f"{sc.get('name', 'Shop')} - SEO Schema"),
             new_x="LMARGIN", new_y="NEXT")
    _shop_concept(pdf, sc)
    _seo_meta(pdf, schema)
    _collections(pdf, schema.get("categories", []) or [])
    _gem_matching(pdf, schema, category or sc.get("tag", ""))
    _blog(pdf, schema)
    return bytes(pdf.output())


def report_filename(schema: dict) -> str:
    tag = (schema.get("shop_concept", {}) or {}).get("tag", "shop")
    return f"seo_schema_{_slug(tag)}.pdf"
