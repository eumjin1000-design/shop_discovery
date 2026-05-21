"""Unit tests for modules.shopify_exporter (Shopify Bulk-Import CSV).

Covers: handle slugify, multi-image row expansion (first row full, extras
handle+image only), price/compare-at margin math, and the credibility badge
in Body (HTML).
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import shopify_exporter as se

_MULTI = {
    "product_name": "Tempur-Pedic TEMPUR-Cloud Pillow, Standard",
    "asin": "B07CMKX3C7", "price_usd": 49.99, "rating": 4.5,
    "review_count": 12008,
    "images": ["https://img/a1.jpg", "https://img/a2.jpg", "https://img/a3.jpg"],
    "description": "<p>Adaptive foam.</p>",
}
_SINGLE = {
    "product_name": "Greaton Leg Wedge Pillow", "asin": "B0BX4J3TXT",
    "price_usd": 43.03, "rating": 3.8, "review_count": 50,
    "image_src": "https://img/b1.jpg",
}


class TestSlugify(unittest.TestCase):
    def test_lowercase_hyphen(self):
        assert se.slugify("Tempur-Pedic Cloud Pillow, Standard") == \
            "tempur-pedic-cloud-pillow-standard"

    def test_strips_non_ascii(self):
        # NFKD strips the accent (é→e); ™ decomposes to ascii "TM" → "tm".
        assert se.slugify("Café Memory Foam!!") == "cafe-memory-foam"
        assert se.slugify("Pillow & Co. (2-Pack)") == "pillow-co-2-pack"

    def test_empty_fallback(self):
        assert se.slugify("") == "product"


class TestReviewsFormat(unittest.TestCase):
    def test_thousands(self):
        assert se._format_reviews(12008) == "12,000+"

    def test_hundreds(self):
        assert se._format_reviews(450) == "400+"

    def test_small_no_plus(self):
        assert se._format_reviews(50) == "50"


class TestProductRows(unittest.TestCase):
    def test_multi_image_expansion(self):
        rows = se.product_rows(_MULTI)
        assert len(rows) == 3                       # 1 full + 2 image-only
        assert rows[0]["Title"]                     # first row full
        assert rows[0]["Image Position"] == 1
        for extra in rows[1:]:
            assert extra["Title"] == ""             # extras blank except 3 keys
            assert extra["Handle"] == rows[0]["Handle"]
            assert extra["Image Src"]
        assert [r["Image Position"] for r in rows] == [1, 2, 3]

    def test_single_image(self):
        rows = se.product_rows(_SINGLE)
        assert len(rows) == 1
        assert rows[0]["Image Position"] == 1

    def test_price_margin(self):
        rows = se.product_rows(_MULTI, margin_multiplier=2.0, compare_ratio=1.3)
        assert rows[0]["Variant Price"] == 99.98     # 49.99 × 2
        assert rows[0]["Variant Compare At Price"] == 129.97  # × 1.3

    def test_flat_add_margin(self):
        rows = se.product_rows(_MULTI, margin_multiplier=1.0, margin_add=20.0)
        assert rows[0]["Variant Price"] == 69.99     # 49.99 + 20

    def test_credibility_badge_on_top(self):
        body = se.product_rows(_MULTI)[0]["Body (HTML)"]
        assert "⭐ 4.5/5" in body
        assert "(12,000+ Reviews)" in body
        assert body.index("⭐") < body.index("Adaptive")  # badge precedes desc


class TestWriteCsv(unittest.TestCase):
    def test_csv_written_and_readable(self):
        with tempfile.TemporaryDirectory() as d:
            path = se.write_shopify_csv([_MULTI, _SINGLE], out_dir=d,
                                        filename="t.csv", vendor="Shop")
            assert os.path.exists(path)
            rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
            assert len(rows) == 4                    # 3 + 1
            assert list(rows[0].keys()) == se.HEADERS


if __name__ == "__main__":
    unittest.main(verbosity=2)
