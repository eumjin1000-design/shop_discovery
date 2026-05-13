"""Import Spark scraper output and merge it back into a sourcing result.

Workflow: sourcing list → Spark bulk tab (.txt) → Spark exports a CSV of the
products it found → :func:`parse_spark_csv` normalises it → :func:`calc_shopify_price`
derives Shopify sell/MSRP/margin → :func:`merge_with_sourcing` attaches the
priced rows to the :class:`~modules.sourcing.SourcingResult`.

Interface
---------
    parse_spark_csv(file_path) -> list[dict]
    calc_shopify_price(amazon_price, margin_rate=0.70, discount_rate=0.25) -> dict
    merge_with_sourcing(sourcing_result, spark_rows, margin_rate=0.70, discount_rate=0.25) -> SourcingResult
"""
from __future__ import annotations

import csv
import io
from dataclasses import replace

from .sourcing import SourcingResult

# Spark CSV header (Korean) -> normalised key.
_COLUMN_MAP = {
    "상품명": "product_name",
    "상품코드": "asin",
    "가격": "price_usd",
    "별점": "rating",
    "리뷰수": "review_count",
    "판매순위": "sales_rank",
    "상태": "status",
}


def _money_to_float(value: str) -> float:
    try:
        return round(float(str(value).replace("$", "").replace(",", "").strip()), 2)
    except (TypeError, ValueError):
        return 0.0


def _to_float(value: str) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: str) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def _read_text(file_path) -> str:
    """Read the file as UTF-8 (BOM-tolerant), falling back to CP949."""
    try:
        with open(file_path, encoding="utf-8-sig", newline="") as fh:
            return fh.read()
    except UnicodeDecodeError:
        with open(file_path, encoding="cp949", newline="") as fh:
            return fh.read()


def parse_spark_csv(file_path) -> list[dict]:
    """Parse a Spark CSV export into a list of normalised row dicts.

    Maps the Korean headers in :data:`_COLUMN_MAP`; numeric fields are cleaned
    ($ / commas stripped). Returns ``[]`` for an empty file.
    """
    text = _read_text(file_path)
    if not text or not text.strip():
        return []

    rows: list[dict] = []
    for raw in csv.DictReader(io.StringIO(text)):
        row: dict = {}
        for header, value in raw.items():
            if header is None:
                continue
            key = _COLUMN_MAP.get(str(header).strip())
            if key is None:
                continue
            value = (value or "").strip()
            if key == "price_usd":
                row[key] = _money_to_float(value)
            elif key == "rating":
                row[key] = _to_float(value)
            elif key == "review_count":
                row[key] = _to_int(value)
            else:
                row[key] = value
        if row:
            rows.append(row)
    return rows


def calc_shopify_price(amazon_price: float, margin_rate: float = 0.70,
                       discount_rate: float = 0.25) -> dict:
    """Derive Shopify pricing from an Amazon price.

    shopify_sell = amazon_price × (1 + margin_rate)
    shopify_msrp = shopify_sell / (1 − discount_rate)   (anchor "list" price)
    margin_usd   = shopify_sell − amazon_price
    """
    amazon_price = float(amazon_price or 0.0)
    shopify_sell = round(amazon_price * (1 + margin_rate), 2)
    shopify_msrp = round(shopify_sell / (1 - discount_rate), 2)
    margin_usd = round(shopify_sell - amazon_price, 2)
    return {"shopify_sell": shopify_sell, "shopify_msrp": shopify_msrp,
            "margin_usd": margin_usd, "margin_rate": margin_rate}


def merge_with_sourcing(sourcing_result: SourcingResult, spark_rows: list[dict],
                        margin_rate: float = 0.70, discount_rate: float = 0.25) -> SourcingResult:
    """Attach Shopify-priced Spark rows to ``sourcing_result.spark_rows``.

    Each Spark row gets its :func:`calc_shopify_price` output merged in (computed
    from the row's ``price_usd``); the priced rows are appended to the result's
    existing ``spark_rows``. Returns a new :class:`SourcingResult` (frozen).
    """
    priced: list[dict] = []
    for row in spark_rows:
        merged = dict(row)
        merged.update(calc_shopify_price(merged.get("price_usd", 0.0),
                                         margin_rate, discount_rate))
        priced.append(merged)
    return replace(sourcing_result,
                   spark_rows=tuple(sourcing_result.spark_rows) + tuple(priced))
