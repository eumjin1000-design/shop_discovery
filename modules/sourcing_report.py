"""Excel writer for the sourcing list (see modules.sourcing).

Interface
---------
    write_sourcing_report(result: SourcingResult, shop_name=None, out_dir="output") -> str
"""
from __future__ import annotations

import os
import re
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from .report_gen import _HEADER_FILL, _HEADER_FONT
from .sourcing import SourcingResult

_HEADERS = ["#", "서브카테고리", "브랜드(추정)", "상품명", "변형", "Amazon URL(노드·Prime·리뷰순)",
            "예상가격(USD)", "키워드", "ASIN", "리뷰수", "노드ID"]
_WIDTHS = {"A": 5, "B": 24, "C": 18, "D": 38, "E": 14, "F": 56, "G": 14, "H": 32,
           "I": 14, "J": 10, "K": 14}


def write_sourcing_report(result: SourcingResult, shop_name: str | None = None,
                          out_dir: str = "output") -> str:
    os.makedirs(out_dir, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Sourcing"

    row0 = 1
    if shop_name:
        ws.cell(row=1, column=1, value=f"Store: {shop_name}").font = Font(bold=True, size=13)
        ws.cell(row=2, column=1, value=result.summary)
        row0 = 4
    else:
        ws.cell(row=1, column=1, value=result.summary)
        row0 = 3

    for col, label in enumerate(_HEADERS, start=1):
        c = ws.cell(row=row0, column=col, value=label)
        c.fill = _HEADER_FILL
        c.font = _HEADER_FONT

    for i, r in enumerate(result.rows, start=1):
        row = row0 + i
        ws.cell(row=row, column=1, value=i)
        ws.cell(row=row, column=2, value=r.subcategory)
        ws.cell(row=row, column=3, value=r.brand or "")
        ws.cell(row=row, column=4, value=r.product_name)
        ws.cell(row=row, column=5, value=r.variant)
        url_cell = ws.cell(row=row, column=6, value=r.amazon_url)
        url_cell.hyperlink = r.amazon_url
        url_cell.style = "Hyperlink"
        ws.cell(row=row, column=7, value=r.est_price)
        ws.cell(row=row, column=8, value=r.keyword)
        ws.cell(row=row, column=9, value=r.asin or "")
        ws.cell(row=row, column=10, value=r.review_count or "")
        ws.cell(row=row, column=11, value=r.amazon_node_id or "")

    for col, width in _WIDTHS.items():
        ws.column_dimensions[col].width = width
    ws.freeze_panes = f"A{row0 + 1}"
    ws.cell(row=row0, column=1).alignment = Alignment(horizontal="center")

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", result.category).strip("_") or "category"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"sourcing_{slug}_{stamp}.xlsx")
    wb.save(path)
    return path
