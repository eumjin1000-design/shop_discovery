"""Batch Excel report: one ranking sheet for many analysed categories.

Used by the GUI's "20개 전체 자동 분석" feature.

Interface
---------
    write_batch_report(results, out_dir="output") -> str
        results: list[tuple[str, PipelineResult]] already sorted best-first.
        returns the path to the written .xlsx file
"""
from __future__ import annotations

import os
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from .models import PipelineResult
from .report_gen import _DECISION_FILL, _HEADER_FILL, _HEADER_FONT  # reuse styles


def _header(ws, *labels: str) -> None:
    for col, label in enumerate(labels, start=1):
        c = ws.cell(row=1, column=col, value=label)
        c.fill = _HEADER_FILL
        c.font = _HEADER_FONT


def write_batch_report(
    results: list[tuple[str, PipelineResult]], out_dir: str = "output"
) -> str:
    os.makedirs(out_dir, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Ranking"

    factor_names = [l.name for l in results[0][1].verdict.breakdown] if results else []
    _header(ws, "순위", "카테고리", "총점 /100", "판정", *factor_names, "Verdict")

    for rank, (name, res) in enumerate(results, start=1):
        v = res.verdict
        row = rank + 1
        ws.cell(row=row, column=1, value=rank)
        ws.cell(row=row, column=2, value=name)
        ws.cell(row=row, column=3, value=round(v.total_score, 1))
        cell = ws.cell(row=row, column=4, value=v.decision)
        cell.font = Font(bold=True)
        if v.decision in _DECISION_FILL:
            cell.fill = _DECISION_FILL[v.decision]
        for j, line in enumerate(v.breakdown):
            ws.cell(row=row, column=5 + j, value=round(line.score, 1))
        sc = ws.cell(row=row, column=5 + len(factor_names), value=v.summary)
        sc.alignment = Alignment(wrap_text=True)

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 44
    ws.column_dimensions["C"].width = 11
    ws.column_dimensions["D"].width = 9
    for i in range(len(factor_names)):
        ws.column_dimensions[chr(ord("E") + i)].width = 12
    ws.column_dimensions[chr(ord("E") + len(factor_names))].width = 80
    ws.freeze_panes = "A2"

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"shop_discovery_batch_{stamp}.xlsx")
    wb.save(path)
    return path
