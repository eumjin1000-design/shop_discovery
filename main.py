"""Shop Discovery - dropshipping new-shop discovery automation.

Pipeline (see CLAUDE.md):

    category --> keyword_gen --> trend_check --> amazon_bsr --> review_miner
             --> intent_check --> margin_calc --> synthesizer (Go/No-Go, 100pt)
             --> report_gen (Excel in ./output)

Usage
-----
    python main.py "wireless earbuds"
    python main.py            # prompts for a category

The Anthropic API key is read from .env / the ANTHROPIC_API_KEY environment
variable. Without it the data modules fall back to deterministic mock data so
the full pipeline still runs end to end.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Load .env if python-dotenv is available; otherwise rely on the real env.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"))
except ImportError:
    pass

from modules import (
    amazon_bsr,
    intent_check,
    keyword_gen,
    margin_calc,
    report_gen,
    review_miner,
    synthesizer,
    trend_check,
)
from modules.models import DiscoveryRequest, PipelineResult


def run_pipeline(category: str, *, target_market: str = "US", currency: str = "USD") -> PipelineResult:
    """Run the full discovery pipeline for ``category`` and return the result.

    Strips ``(annotation)`` from category at the entry point so all downstream
    consumers (DiscoveryRequest → Verdict → GUI subheader → report filename
    → LLM verdict prompt) see the clean form. Single-point normalization.
    """
    from modules.sourcing import _strip_annotation
    category = _strip_annotation(category)
    request = DiscoveryRequest(category=category, target_market=target_market, currency=currency)

    keywords = keyword_gen.generate_keywords(request)
    trend = trend_check.check_trend(category, keywords)
    keywords = trend.keywords  # trend_check enriches volume estimates
    bsr = amazon_bsr.check_bsr(category, keywords)
    review = review_miner.mine_reviews(category, keywords)
    intent = intent_check.check_intent(category, keywords)
    # Feed the real Amazon 1st-page avg price (from Keepa via BSR step) into
    # the margin reverse-calc. None → calc_margin falls back to seed estimate.
    margin = margin_calc.calc_margin(
        category, currency, amazon_avg_price=getattr(bsr, "avg_price", None))
    verdict = synthesizer.synthesize(category, trend, bsr, review, intent, margin)

    return PipelineResult(
        request=request,
        keywords=keywords,
        trend=trend,
        bsr=bsr,
        review=review,
        intent=intent,
        margin=margin,
        verdict=verdict,
    )


def run_categories(category_names, progress=None) -> list[tuple[str, PipelineResult]]:
    """Run the pipeline for the given category names, returned best-score-first.

    ``progress`` (optional) is called as ``progress(done, total, name, eta_secs)``
    after each category so a GUI can render a progress bar with an ETA. Each
    completed batch's verdicts are recorded to the analysis history.
    """
    import time

    from modules import categories

    names = [n for n in category_names if n]
    results: list[tuple[str, PipelineResult]] = []
    t0 = time.time()
    for i, name in enumerate(names, start=1):
        results.append((name, run_pipeline(name)))
        if progress is not None:
            elapsed = time.time() - t0
            eta = (len(names) - i) * (elapsed / i)
            progress(i, len(names), name, eta)
    categories.record_decisions({name: res.verdict.decision for name, res in results})
    results.sort(key=lambda pair: pair[1].verdict.total_score, reverse=True)
    return results


def run_all_curated(progress=None, only_unanalyzed: bool = False) -> list[tuple[str, PipelineResult]]:
    """Run every known category. Thin wrapper over :func:`run_categories`."""
    from modules import categories

    cats = list(categories.all_categories())
    if only_unanalyzed:
        done = categories.load_history()
        cats = [c for c in cats if c.name not in done] or cats
    wrapped = (lambda d, t, n, e: progress(d, t, n)) if progress else None
    return run_categories([c.name for c in cats], wrapped)


def _print_console(result: PipelineResult) -> None:
    v = result.verdict
    print()
    print("=" * 64)
    print(f"  Shop Discovery  -  {v.category}")
    print("=" * 64)
    for line in v.breakdown:
        bar_len = int(round(line.score / line.max_score * 20)) if line.max_score else 0
        bar = "#" * bar_len + "-" * (20 - bar_len)
        print(f"  {line.name:<28} [{bar}] {line.score:5.1f}/{line.max_score:<4.0f}  {line.detail}")
    print("-" * 64)
    print(f"  TOTAL: {v.total_score:.1f}/100   ->   {v.decision}")
    print("-" * 64)
    print(f"  {v.summary}")
    print("=" * 64)


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        category = " ".join(argv[1:]).strip()
    else:
        category = input("Category to evaluate: ").strip()
    if not category:
        print("No category provided.", file=sys.stderr)
        return 2

    result = run_pipeline(category)
    _print_console(result)
    path = report_gen.write_report(result)
    print(f"\nExcel report written to: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
