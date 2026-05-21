"""Build a Shopify Bulk-Import CSV from cleaned Spark product rows.

Input rows are the dicts produced by :mod:`modules.spark_import`
(``product_name`` / ``asin`` / ``price_usd`` / ``rating`` / ``review_count``
plus an optional ``images`` list or single ``image_src``). This module turns
each product into one or more Shopify CSV rows following Shopify's
multi-image convention: the first row carries all product fields, every extra
image is a follow-up row with only ``Handle`` + ``Image Src`` + ``Image
Position`` set.

Interface
---------
    slugify(title) -> str
    build_body_html(row) -> str
    product_rows(product, *, margin_multiplier=2.0, margin_add=0.0,
                 compare_ratio=1.3, vendor="", product_type="") -> list[dict]
    write_shopify_csv(products, out_dir="output", filename=None, **price_kw) -> str
"""
from __future__ import annotations

import csv
import os
import re
import unicodedata
from pathlib import Path

from .timez import stamp as kst_stamp

# Shopify Bulk-Import column order (matches a standard product export).
HEADERS = [
    "Handle", "Title", "Body (HTML)", "Vendor", "Type", "Tags", "Published",
    "Option1 Name", "Option1 Value", "Variant SKU", "Variant Inventory Qty",
    "Variant Inventory Policy", "Variant Fulfillment Service", "Variant Price",
    "Variant Compare At Price", "Variant Requires Shipping", "Variant Taxable",
    "Image Src", "Image Position", "Status",
]

# Defaults for unit economics.
DEFAULT_MARGIN_MULTIPLIER = 2.0   # Variant Price = base × multiplier (+ add)
DEFAULT_MARGIN_ADD = 0.0
DEFAULT_COMPARE_RATIO = 1.3       # Compare At = Price × ratio (anchor "list")


def slugify(title: str) -> str:
    """Title → URL-safe Shopify handle (ascii lowercase, hyphen-joined)."""
    # Strip accents → ascii, drop anything that isn't a word char or space.
    norm = unicodedata.normalize("NFKD", str(title or ""))
    ascii_only = norm.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", "", ascii_only).lower()
    slug = re.sub(r"[\s-]+", "-", cleaned).strip("-")
    return slug or "product"


def _format_reviews(reviews: int) -> str:
    """12008 → '12,000+'  ·  450 → '400+'  ·  50 → '50' (no '+' under 100)."""
    n = max(0, int(reviews or 0))
    if n >= 1000:
        floored = (n // 1000) * 1000
        return f"{floored:,}+"
    if n >= 100:
        floored = (n // 100) * 100
        return f"{floored:,}+"
    return str(n)


def _credibility_badge(rating: float, reviews: int) -> str:
    """'⭐ 4.5/5 (12,000+ Reviews)' wrapped in a styled div, or '' if no data."""
    r = float(rating or 0.0)
    if r <= 0 and not reviews:
        return ""
    rating_txt = f"⭐ {r:.1f}/5" if r > 0 else "⭐"
    review_txt = f" ({_format_reviews(reviews)} Reviews)" if reviews else ""
    return (
        '<div style="display:inline-block;background:#fff8e1;border:1px solid '
        '#ffe082;border-radius:8px;padding:6px 12px;font-size:15px;'
        'font-weight:700;color:#8d6e00;margin-bottom:12px">'
        f"{rating_txt}{review_txt}</div>"
    )


def build_body_html(row: dict) -> str:
    """Body (HTML): credibility badge on top, then any existing description."""
    badge = _credibility_badge(row.get("rating"), row.get("review_count"))
    body = str(row.get("body_html") or row.get("description") or "").strip()
    parts = [p for p in (badge, body) if p]
    return "\n".join(parts)


def _price_pair(base: float, multiplier: float, add: float,
                compare_ratio: float) -> tuple[float, float]:
    base = float(base or 0.0)
    price = round(base * float(multiplier) + float(add), 2)
    compare_at = round(price * float(compare_ratio), 2)
    return price, compare_at


def _images_of(product: dict) -> list[str]:
    """Normalise an ``images`` list or a single ``image_src`` to a clean list."""
    imgs = product.get("images")
    if isinstance(imgs, (list, tuple)):
        out = [str(u).strip() for u in imgs if str(u or "").strip()]
    else:
        single = str(product.get("image_src") or "").strip()
        out = [single] if single else []
    return out


def product_rows(product: dict, *, margin_multiplier: float = DEFAULT_MARGIN_MULTIPLIER,
                 margin_add: float = DEFAULT_MARGIN_ADD,
                 compare_ratio: float = DEFAULT_COMPARE_RATIO,
                 vendor: str = "", product_type: str = "") -> list[dict]:
    """Expand one product into Shopify rows (1 + N-1 extra image rows)."""
    title = str(product.get("product_name") or product.get("title") or "").strip()
    handle = slugify(title)
    price, compare_at = _price_pair(
        product.get("price_usd"), margin_multiplier, margin_add, compare_ratio)
    images = _images_of(product)

    # First row carries every product field.
    first = {h: "" for h in HEADERS}
    first.update({
        "Handle": handle,
        "Title": title,
        "Body (HTML)": build_body_html(product),
        "Vendor": vendor or str(product.get("vendor") or "").strip(),
        "Type": product_type or str(product.get("type") or "").strip(),
        "Tags": str(product.get("tags") or "").strip(),
        "Published": "TRUE",
        "Option1 Name": "Title",
        "Option1 Value": "Default Title",
        "Variant SKU": str(product.get("asin") or "").strip(),
        "Variant Inventory Qty": product.get("inventory_qty", 100),
        "Variant Inventory Policy": "deny",
        "Variant Fulfillment Service": "manual",
        "Variant Price": price,
        "Variant Compare At Price": compare_at,
        "Variant Requires Shipping": "TRUE",
        "Variant Taxable": "TRUE",
        "Image Src": images[0] if images else "",
        "Image Position": 1 if images else "",
        "Status": str(product.get("status_shopify") or "active"),
    })
    rows = [first]

    # Extra images: Handle + Image Src + Image Position only.
    for pos, url in enumerate(images[1:], start=2):
        extra = {h: "" for h in HEADERS}
        extra.update({"Handle": handle, "Image Src": url, "Image Position": pos})
        rows.append(extra)
    return rows


def to_shopify_rows(products, **kw) -> list[dict]:
    """Flatten a list of products into Shopify CSV rows."""
    out: list[dict] = []
    for p in products:
        out.extend(product_rows(p, **kw))
    return out


def write_shopify_csv(products, out_dir: str = "output",
                      filename: str | None = None, **kw) -> str:
    """Write the Shopify Bulk-Import CSV and return its path.

    ``kw`` forwards pricing/vendor options to :func:`product_rows`
    (``margin_multiplier`` / ``margin_add`` / ``compare_ratio`` / ``vendor`` /
    ``product_type``).
    """
    os.makedirs(out_dir, exist_ok=True)
    rows = to_shopify_rows(products, **kw)
    if filename is None:
        filename = f"shopify_import_{kst_stamp()}.csv"
    path = os.path.join(out_dir, filename)
    # utf-8-sig so Excel/Shopify read non-ASCII titles correctly.
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    return path
