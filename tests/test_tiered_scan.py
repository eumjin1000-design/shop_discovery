"""Regression tests: tiered (differential) Keepa scan strategy.

A category's intrinsic score (perceived_value + problem_solving +
niche_specificity) selects Deep Scan (15 samples) vs Fast Scan (5), and the
tiered cost estimate is lower than the flat estimate.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import amazon_bsr, keepa_status as ks


class TestScanClassification(unittest.TestCase):
    def test_threshold_boundary(self):
        assert ks.scan_mode(7) == "deep"
        assert ks.scan_mode(6) == "fast"

    def test_samples(self):
        assert ks.samples_for(9) == ks.DEEP_SCAN_SAMPLES == 15
        assert ks.samples_for(3) == ks.FAST_SCAN_SAMPLES == 5


class TestTieredCost(unittest.TestCase):
    def test_savings_vs_flat(self):
        flat = ks.estimate_analysis_cost(20)        # 200
        tiered = ks.estimate_tiered_cost(5, 15)     # 5×10 + 15×4 = 110
        assert flat == 200
        assert tiered == 110
        assert tiered < flat

    def test_all_deep_equals_flat(self):
        assert ks.estimate_tiered_cost(20, 0) == ks.estimate_analysis_cost(20)


class TestBsrBranch(unittest.TestCase):
    def test_high_score_deep_low_score_fast(self):
        class Cat:
            def __init__(self, pv, ps, ns):
                self.perceived_value, self.problem_solving, self.niche_specificity = pv, ps, ns

        with patch("modules.categories.by_name", return_value=Cat(3, 3, 3)):
            assert amazon_bsr._scan_sample_size("X") == 15   # score 9 → deep
        with patch("modules.categories.by_name", return_value=Cat(1, 1, 1)):
            assert amazon_bsr._scan_sample_size("Y") == 5    # score 3 → fast

    def test_unknown_category_defaults_deep(self):
        with patch("modules.categories.by_name", return_value=None):
            assert amazon_bsr._scan_sample_size("ad-hoc") == 15

    def test_snapshot_called_with_sample_size(self):
        """check_bsr threads the chosen sample_size into keepa_snapshot."""
        class Cat:
            perceived_value = problem_solving = niche_specificity = 1  # score 3 → fast
        with patch("modules.categories.by_name", return_value=Cat()), \
             patch("modules.amazon_bsr.sources.keepa_snapshot",
                   return_value=None) as snap:
            amazon_bsr.check_bsr("Y", ())
            snap.assert_called_once_with("Y", sample_size=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
