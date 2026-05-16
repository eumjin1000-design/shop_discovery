"""Regression tests: category annotation leak prevention.

Verifies that category names like "Car accessories (organizer, phone mount)"
never leak parentheses content into URLs, filenames, or display fields.

Note: summary strings may contain parentheses for Korean prose (e.g. "(URL당 ~900)").
The regression check only asserts that the annotation *content* words
("organizer", "phone mount", "automatic feeder", ...) do NOT appear — and
that the stripped category text IS present.  URL/subcategory/keyword/product
fields must contain NO parentheses at all.
"""
from __future__ import annotations

import re
import sys
import os
import unittest
from unittest.mock import patch

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_PAREN_RE = re.compile(r"[()]")
_ANNOTATED = "Car accessories (organizer, phone mount)"
_ANNOTATED_PET = "Pet supplies (automatic feeder, slow-feeder bowl)"

# Words that must NOT appear in summary when annotation is stripped
_ANNOTATED_LEAK_WORDS = ["organizer", "phone mount"]


class TestStripAnnotation(unittest.TestCase):
    """Unit tests for modules.sourcing._strip_annotation."""

    def setUp(self):
        from modules.sourcing import _strip_annotation
        self._strip = _strip_annotation

    def test_strips_parentheses_annotation(self):
        result = self._strip(_ANNOTATED)
        assert result == "Car accessories", repr(result)

    def test_strips_pet_supplies_annotation(self):
        result = self._strip(_ANNOTATED_PET)
        assert result == "Pet supplies", repr(result)

    def test_plain_category_unchanged(self):
        result = self._strip("Plain category")
        assert result == "Plain category", repr(result)

    def test_empty_string(self):
        result = self._strip("")
        assert result == "", repr(result)


def _assert_no_parens(value: str, context: str) -> None:
    if _PAREN_RE.search(value):
        raise AssertionError(
            f"Parenthesis found in {context!r}:\n  value = {value!r}"
        )


class TestGenerateSourcingListNoParens(unittest.TestCase):
    """End-to-end: generate_sourcing_list must not emit parentheses."""

    def test_no_parens_in_any_output_field(self):
        # Patch _from_llm to return None — forces deterministic fallback path
        with patch("modules.sourcing._from_llm", return_value=None):
            from modules.sourcing import generate_sourcing_list
            result = generate_sourcing_list(_ANNOTATED, n_subs=3, n_variants=2)

        _assert_no_parens(result.category, "result.category")
        _assert_no_parens(result.summary, "result.summary")

        for i, row in enumerate(result.rows):
            ctx = f"row[{i}]"
            _assert_no_parens(row.subcategory, f"{ctx}.subcategory")
            _assert_no_parens(row.base_product, f"{ctx}.base_product")
            _assert_no_parens(row.keyword,      f"{ctx}.keyword")
            _assert_no_parens(row.search_url,   f"{ctx}.search_url")
            _assert_no_parens(row.amazon_url,   f"{ctx}.amazon_url")


class TestSparkQueryListNoParens(unittest.TestCase):
    """End-to-end: spark_query_list must not emit parentheses in data fields.

    summary may contain Korean prose parentheses like "(URL당 ~900)" — those
    are intentional prose, not annotation leaks.  We check that annotation
    *content words* are absent from summary, and that structured data fields
    (rows) contain no parentheses at all.
    """

    def test_no_annotation_leak_in_summary(self):
        from modules.bulk_sourcing import spark_query_list
        result = spark_query_list(_ANNOTATED, n_variations=5)
        summary_lower = result.summary.lower()
        for word in _ANNOTATED_LEAK_WORDS:
            assert word not in summary_lower, (
                f"Annotation word {word!r} leaked into summary:\n  {result.summary!r}"
            )

    def test_no_parens_in_category_field(self):
        from modules.bulk_sourcing import spark_query_list
        result = spark_query_list(_ANNOTATED, n_variations=5)
        _assert_no_parens(result.category, "result.category")

    def test_no_parens_in_row_fields(self):
        from modules.bulk_sourcing import spark_query_list
        result = spark_query_list(_ANNOTATED, n_variations=5)
        for i, row in enumerate(result.rows):
            ctx = f"row[{i}]"
            _assert_no_parens(row.subcategory, f"{ctx}.subcategory")
            _assert_no_parens(row.base_product, f"{ctx}.base_product")
            _assert_no_parens(row.keyword,      f"{ctx}.keyword")
            _assert_no_parens(row.search_url,   f"{ctx}.search_url")
            _assert_no_parens(row.amazon_url,   f"{ctx}.amazon_url")


if __name__ == "__main__":
    unittest.main()
