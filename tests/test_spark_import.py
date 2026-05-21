"""Regression tests: Spark CSV parser numeric cleanup.

Covers two defects fixed in :mod:`modules.spark_import`:
  1. ``_money_to_float`` must strip ANY currency symbol/word (KRW, $, €),
     and roughly convert a >1000 value (non-USD leak) to USD via /1400.
  2. ``sales_rank`` must be parsed to an int from strings like
     "#1,234 in Bed Pillows".
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.spark_import import (_money_to_float, _rank_to_int,
                                   _split_images, parse_spark_csv)

_FIXTURE = """상품명,상품코드,가격,별점,리뷰수,판매순위,상태
"Tempur-Pedic Cloud Pillow",B07CMKX3C7,"$49.99",4.3,"7,412","#3 in Bed Pillows",수집완료
"Greaton Leg Wedge Pillow",B0BX4J3TXT,"KRW 60,249",3.8,50,"#1,234 in Bed Pillows",수집완료
"Euro Priced Item",B0091J5XCS,"€ 1,029.00",4.1,"12,008","42 in Home & Kitchen",수집완료
"""


class TestMoneyToFloat(unittest.TestCase):
    def test_plain_usd(self):
        assert _money_to_float("$49.99") == 49.99

    def test_comma_thousands(self):
        assert _money_to_float("$72.00") == 72.0

    def test_krw_converted(self):
        # 60249 / 1400 ≈ 43.03
        assert _money_to_float("KRW 60,249") == 43.03

    def test_euro_symbol_and_spaces(self):
        # 1029 > 1000 → treated as non-USD → /1400 ≈ 0.73
        assert _money_to_float("€ 1,029.00") == 0.73

    def test_empty_and_garbage(self):
        assert _money_to_float("") == 0.0
        assert _money_to_float("N/A") == 0.0


_IMAGE_FIXTURE = """상품명,상품코드,가격,이미지
"Multi Image Pillow",B07CMKX3C7,"$49.99","http://img1.jpg, http://img2.jpg"
"Pipe Delimited",B0BX4J3TXT,"$30.00","http://a.jpg|http://b.jpg|http://c.jpg"
"No Image",B0091J5XCS,"$10.00",""
"""


class TestSplitImages(unittest.TestCase):
    def test_comma_two_urls(self):
        assert _split_images("http://img1.jpg, http://img2.jpg") == \
            ["http://img1.jpg", "http://img2.jpg"]

    def test_pipe_delimited(self):
        assert _split_images("a.jpg|b.jpg|c.jpg") == ["a.jpg", "b.jpg", "c.jpg"]

    def test_empty_returns_empty_list(self):
        assert _split_images("") == []
        assert _split_images(None) == []


class TestParseSparkImages(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write(_IMAGE_FIXTURE)

    def tearDown(self):
        os.remove(self.path)

    def test_images_parsed_as_list_len2(self):
        rows = parse_spark_csv(self.path)
        assert rows[0]["images"] == ["http://img1.jpg", "http://img2.jpg"]
        assert len(rows[0]["images"]) == 2

    def test_pipe_delimited_len3(self):
        rows = parse_spark_csv(self.path)
        assert len(rows[1]["images"]) == 3

    def test_missing_image_empty_list(self):
        rows = parse_spark_csv(self.path)
        assert rows[2]["images"] == []


class TestRankToInt(unittest.TestCase):
    def test_hash_with_comma(self):
        assert _rank_to_int("#1,234 in Bed Pillows") == 1234

    def test_leading_number(self):
        assert _rank_to_int("3 in Home & Kitchen") == 3

    def test_no_number(self):
        assert _rank_to_int("Best Seller") == 0

    def test_empty(self):
        assert _rank_to_int("") == 0


class TestParseSparkCsvEdgeCases(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write(_FIXTURE)

    def tearDown(self):
        os.remove(self.path)

    def test_rows_parsed(self):
        rows = parse_spark_csv(self.path)
        assert len(rows) == 3

    def test_krw_price_cleaned_and_typed(self):
        rows = parse_spark_csv(self.path)
        krw = rows[1]
        assert krw["price_usd"] == 43.03
        assert isinstance(krw["price_usd"], float)

    def test_bsr_extracted_as_int(self):
        rows = parse_spark_csv(self.path)
        assert rows[0]["sales_rank"] == 3
        assert rows[1]["sales_rank"] == 1234
        assert rows[2]["sales_rank"] == 42
        assert all(isinstance(r["sales_rank"], int) for r in rows)

    def test_core_fields_present(self):
        row = parse_spark_csv(self.path)[0]
        for key in ("asin", "product_name", "price_usd", "rating",
                    "review_count", "sales_rank"):
            assert key in row, f"missing {key}"


if __name__ == "__main__":
    unittest.main(verbosity=2)
