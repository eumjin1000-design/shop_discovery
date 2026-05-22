"""PDF report for a single Shop Discovery analysis (English, fpdf2).

Documents the verdict, 100-point scorecard, key metrics, and top keywords of
a :class:`~modules.models.PipelineResult`. Uses fpdf2 core fonts (Helvetica),
so no external font file is needed and it runs on Streamlit Cloud. Content is
English — the pipeline's verdict summary and scorecard names are already
English (US-market tool), and any stray non-Latin chars are sanitised.

Interface
---------
    report_bytes(result, shop_name=None) -> bytes
    report_filename(result) -> str
"""
from __future__ import annotations

import re

from fpdf import FPDF

from .models import PipelineResult

_DECISION_RGB = {"GO": (46, 125, 50), "WATCH": (249, 168, 37), "NO-GO": (198, 40, 40)}


def _ascii(text: str) -> str:
    """fpdf core fonts are latin-1 only — drop/replace anything outside it."""
    s = str(text or "")
    s = s.replace("→", "->").replace("—", "-").replace("·", "-")
    return s.encode("latin-1", "replace").decode("latin-1")


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", str(text or "")).strip("_") or "category"


class _Report(FPDF):
    def header(self) -> None:
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, "Shop Discovery - Analysis Report", align="R")
        self.ln(8)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(160, 160, 160)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")


def _verdict_block(pdf: _Report, result: PipelineResult) -> None:
    v = result.verdict
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 10, _ascii(v.category), new_x="LMARGIN", new_y="NEXT")

    rgb = _DECISION_RGB.get(v.decision, (90, 90, 90))
    pdf.set_font("Helvetica", "B", 32)
    pdf.set_text_color(*rgb)
    pdf.cell(40, 16, f"{v.total_score:.0f}", new_x="RIGHT", new_y="TOP")
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(20, 16, "/100", new_x="RIGHT", new_y="TOP")
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*rgb)
    pdf.cell(0, 16, f"  {v.decision}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(0, 6, f"GO >= {v.GO_THRESHOLD:.0f}  -  WATCH >= {v.WATCH_THRESHOLD:.0f}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 5, _ascii(v.summary))
    pdf.ln(3)


def _section(pdf: _Report, title: str) -> None:
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 30, 30)
    pdf.ln(2)
    pdf.cell(0, 7, _ascii(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(225, 112, 85)
    pdf.set_line_width(0.6)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.l_margin + 30, y)
    pdf.ln(2)


def _scorecard_table(pdf: _Report, result: PipelineResult) -> None:
    _section(pdf, "Scorecard (100 pts)")
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(45, 52, 54)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(85, 7, " Factor", border=0, fill=True)
    pdf.cell(25, 7, "Score", border=0, fill=True, align="C")
    pdf.cell(0, 7, " Detail", border=0, fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(40, 40, 40)
    fill = False
    for line in result.verdict.breakdown:
        pdf.set_fill_color(248, 248, 248)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(85, 7, " " + _ascii(line.name), border="B", fill=fill)
        pdf.cell(25, 7, f"{line.score:.1f}/{line.max_score:.0f}", border="B",
                 fill=fill, align="C")
        pdf.cell(0, 7, " " + _ascii(line.detail), border="B", fill=fill,
                 new_x="LMARGIN", new_y="NEXT")
        fill = not fill


def _metrics_block(pdf: _Report, result: PipelineResult) -> None:
    _section(pdf, "Key Metrics")
    t, b, r, i, m = (result.trend, result.bsr, result.review,
                     result.intent, result.margin)
    rows = [
        ("Search trend", f"{t.growth_ratio:.2f}x YoY, stability {t.stability:.2f}"
         + (", seasonal" if t.is_seasonal else "")),
        ("Amazon BSR", f"top ~{b.best_rank:,}, ~{b.competing_listings:,} competing"
         + (f", avg price ${b.avg_price:.2f}" if getattr(b, "avg_price", None) else "")),
        ("Reviews", f"incumbent {r.avg_rating}/5, {r.negative_ratio*100:.0f}% negative"),
        ("Purchase intent", f"commercial {i.commercial_intent*100:.0f}%, "
         f"problem-aware {i.problem_awareness*100:.0f}%"),
        ("Margin (gross)", f"{m.net_margin_pct*100:.0f}% (${m.net_margin}/unit, "
         f"retail ${m.avg_retail_price})"),
    ]
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(40, 40, 40)
    for label, val in rows:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(40, 6, " " + _ascii(label))
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 6, _ascii(val), new_x="LMARGIN", new_y="NEXT")


def _keywords_table(pdf: _Report, result: PipelineResult) -> None:
    kws = sorted(result.keywords, key=lambda k: k.est_monthly_volume or 0, reverse=True)
    if not kws:
        return
    _section(pdf, "Top Keywords")
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(45, 52, 54)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(120, 7, " Keyword", fill=True)
    pdf.cell(0, 7, "Monthly volume", fill=True, align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(40, 40, 40)
    fill = False
    for k in kws[:12]:
        pdf.set_fill_color(248, 248, 248)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(120, 6, " " + _ascii(k.term), border="B", fill=fill)
        vol = f"{k.est_monthly_volume:,}" if k.est_monthly_volume else "n/a"
        pdf.cell(0, 6, vol, border="B", fill=fill, align="C",
                 new_x="LMARGIN", new_y="NEXT")
        fill = not fill


def report_bytes(result: PipelineResult, shop_name: str | None = None) -> bytes:
    """Render the analysis to a PDF and return its bytes."""
    pdf = _Report(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    if shop_name:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(225, 112, 85)
        pdf.cell(0, 6, _ascii(f"Store: {shop_name}"), new_x="LMARGIN", new_y="NEXT")
    _verdict_block(pdf, result)
    _scorecard_table(pdf, result)
    _metrics_block(pdf, result)
    _keywords_table(pdf, result)
    out = pdf.output()
    return bytes(out)


def report_filename(result: PipelineResult) -> str:
    return f"report_{_slug(result.request.category)}.pdf"
