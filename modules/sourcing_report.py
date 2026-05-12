"""Excel writer for the 150-item sourcing list (see modules.sourcing).

Interface
---------
    write_sourcing_report(category, items, shop_name=None, out_dir="output") -> str
"""
from __future__ import annotations

import os
import re
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font

from .report_gen import _HEADER_FILL, _HEADER_FONT
from .sourcing import SourcingItem

_HEADERS = ["#", "서브카테고리", "상품명", "변형", "Amazon 검색 URL", "예상가격(USD)", "키워드"]
_WIDTHS = {"A": 5, "B": 26, "C": 42, "D": 14, "E": 62, "F": 14, "G": 36}


def write_sourcing_report(
    category: str,
    items: list[SourcingItem],
    shop_name: str | None = None,
    out_dir: str = "output",
) -> str:
    os.makedirs(out_dir, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Sourcing"

    row0 = 1
    if shop_name:
        ws.cell(row=1, column=1, value=f"Store: {shop_name}").font = Font(bold=True, size=13)
        ws.cell(row=2, column=1, value=f"Category: {category}  ·  {len(items)} products")
        row0 = 4

    for col, label in enumerate(_HEADERS, start=1):
        c = ws.cell(row=row0, column=col, value=label)
        c.fill = _HEADER_FILL
        c.font = _HEADER_FONT

    for i, it in enumerate(items, start=1):
        r = row0 + i
        ws.cell(row=r, column=1, value=i)
        ws.cell(row=r, column=2, value=it.subcategory)
        ws.cell(row=r, column=3, value=it.product_name)
        ws.cell(row=r, column=4, value=it.variant)
        url_cell = ws.cell(row=r, column=5, value=it.amazon_url)
        url_cell.hyperlink = it.amazon_url
        url_cell.style = "Hyperlink"
        ws.cell(row=r, column=6, value=it.est_price)
        ws.cell(row=r, column=7, value=it.keyword)

    for col, width in _WIDTHS.items():
        ws.column_dimensions[col].width = width
    ws.freeze_panes = f"A{row0 + 1}"

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", category).strip("_") or "category"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"sourcing_{slug}_{stamp}.xlsx")
    wb.save(path)
    return path
