"""Regression tests: passes / pages expansion in sourcing + bulk_sourcing.

Verifies the new ``passes`` (multi-pass LLM dedup) and ``pages`` (per-URL
page expansion) parameters preserve legacy behaviour at defaults and emit
the expected row multiplication when set higher.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSparkUrlsPage(unittest.TestCase):
    """spark_urls.build_search_url page param emits &page=N for N>=2 only."""

    def test_page_1_no_suffix(self):
        from modules.spark_urls import build_search_url
        url = build_search_url("wine glasses", node_id="289914", page=1)
        assert "&page=" not in url

    def test_page_3_has_suffix(self):
        from modules.spark_urls import build_search_url
        url = build_search_url("wine glasses", node_id="289914", page=3)
        assert url.endswith("&page=3")

    def test_default_page_no_suffix(self):
        from modules.spark_urls import build_search_url
        url = build_search_url("wine glasses", node_id="289914")
        assert "&page=" not in url


class TestSourcingPages(unittest.TestCase):
    """sourcing.generate_sourcing_list pages=N multiplies row count by N."""

    def test_pages_1_default_behaviour(self):
        # Force fallback path so output is deterministic.
        with patch("modules.sourcing.from_llm_multipass", return_value=None):
            from modules.sourcing import generate_sourcing_list
            res = generate_sourcing_list("test cat", n_subs=2, n_variants=3, pages=1)
        # 2 subs × 5 products × 3 variants × 1 page = 30
        assert res.total == 30, f"expected 30 got {res.total}"

    def test_pages_3_triples_rows(self):
        with patch("modules.sourcing.from_llm_multipass", return_value=None):
            from modules.sourcing import generate_sourcing_list
            res = generate_sourcing_list("test cat", n_subs=2, n_variants=3, pages=3)
        # 2 × 5 × 3 × 3 = 90
        assert res.total == 90, f"expected 90 got {res.total}"

    def test_page_field_distributed(self):
        """Each base row expands to N copies with page=1..N."""
        with patch("modules.sourcing.from_llm_multipass", return_value=None):
            from modules.sourcing import generate_sourcing_list
            res = generate_sourcing_list("test cat", n_subs=1, n_variants=1, pages=4)
        # 1 × 5 × 1 × 4 = 20; each product appears with page 1,2,3,4
        pages_seen = sorted({r.page for r in res.rows})
        assert pages_seen == [1, 2, 3, 4], f"expected [1,2,3,4] got {pages_seen}"

    def test_search_url_includes_page(self):
        with patch("modules.sourcing.from_llm_multipass", return_value=None):
            from modules.sourcing import generate_sourcing_list
            res = generate_sourcing_list("test cat", n_subs=1, n_variants=1, pages=2)
        page2_rows = [r for r in res.rows if r.page == 2]
        assert page2_rows, "expected at least one page=2 row"
        assert "&page=2" in page2_rows[0].search_url


class TestBulkSourcingPages(unittest.TestCase):
    """bulk_sourcing.spark_query_list pages=N multiplies row count by N."""

    def test_pages_1_default(self):
        from modules.bulk_sourcing import spark_query_list
        res = spark_query_list("reading nook", n_variations=4, pages=1)
        # 4 keyword variations × 1 page = 4 rows
        assert res.total == 4, f"expected 4 got {res.total}"

    def test_pages_3_triples_rows(self):
        from modules.bulk_sourcing import spark_query_list
        res = spark_query_list("reading nook", n_variations=4, pages=3)
        # 4 × 3 = 12
        assert res.total == 12, f"expected 12 got {res.total}"

    def test_page_field_distributed(self):
        from modules.bulk_sourcing import spark_query_list
        res = spark_query_list("reading nook", n_variations=2, pages=3)
        pages_seen = sorted({r.page for r in res.rows})
        assert pages_seen == [1, 2, 3], f"expected [1,2,3] got {pages_seen}"


class TestMultiPassMerge(unittest.TestCase):
    """from_llm_multipass dedups subcategory names case-insensitively."""

    def test_single_pass_returns_first_pass_only(self):
        spec_pass1 = [{"subcategory": "A", "amazon_node_id": "",
                       "products": [{"name": "x"}]}]
        from modules.sourcing_llm import from_llm_multipass
        with patch("modules.sourcing_llm._from_llm", return_value=spec_pass1):
            out = from_llm_multipass("cat", 1, lambda c: "", passes=1)
        assert len(out) == 1

    def test_multi_pass_dedup_by_name(self):
        # Pass 1 + Pass 2 share "A"; result should have 2 unique not 4
        responses = [
            [{"subcategory": "A", "amazon_node_id": "", "products": [{"name": "x"}]},
             {"subcategory": "B", "amazon_node_id": "", "products": [{"name": "y"}]}],
            [{"subcategory": "a", "amazon_node_id": "", "products": [{"name": "z"}]},  # dup (case)
             {"subcategory": "C", "amazon_node_id": "", "products": [{"name": "w"}]}],
        ]
        from modules.sourcing_llm import from_llm_multipass
        with patch("modules.sourcing_llm._from_llm", side_effect=responses):
            out = from_llm_multipass("cat", 2, lambda c: "", passes=2)
        names = [s["subcategory"] for s in out]
        # Expect A and B from pass 1, then only C from pass 2 (a deduped)
        assert names == ["A", "B", "C"], names


if __name__ == "__main__":
    unittest.main()
