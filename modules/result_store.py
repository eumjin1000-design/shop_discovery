"""Persist the last single-analysis PipelineResult across app restarts.

The batch ranking already survives a restart via
:func:`modules.categories.load_batch_results`; this does the same for the
single-analysis result so the result panel (verdict, scorecard, downloads)
is restored after a reboot / Streamlit Cloud redeploy.

Stored as JSON (``dataclasses.asdict`` → file → typed reconstruction) — not
pickle, to avoid arbitrary-code-execution risk on load. Load is best-effort:
a malformed / schema-changed file is ignored (returns ``None``) rather than
crashing the app.

Interface
---------
    save_last_result(result) -> None
    load_last_result() -> PipelineResult | None
    clear_last_result() -> None
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import (BSRResult, DiscoveryRequest, IntentResult, Keyword,
                     MarginResult, PipelineResult, ReviewResult, ScoreLine,
                     TrendResult, Verdict)

_FILE = Path(__file__).resolve().parent.parent / "last_result.json"


def save_last_result(result) -> None:
    try:
        _FILE.write_text(
            json.dumps(asdict(result), ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except Exception:
        pass  # best-effort, never block the analysis flow


def _keywords(items) -> tuple[Keyword, ...]:
    return tuple(Keyword(**k) for k in (items or ()))


def load_last_result():
    """Reconstruct the saved PipelineResult, or None if missing/incompatible.

    Nested dicts are rebuilt into their dataclass types (so attribute access
    like ``verdict.breakdown[i].name`` works). datetime fields, persisted as
    ISO strings, are left as strings — nothing in the result panel reads them.
    """
    try:
        if not _FILE.exists():
            return None
        d = json.loads(_FILE.read_text(encoding="utf-8"))
        trend_d = dict(d["trend"]); trend_d["keywords"] = _keywords(trend_d.get("keywords"))
        verdict_d = dict(d["verdict"])
        verdict_d["breakdown"] = tuple(ScoreLine(**s) for s in verdict_d.get("breakdown", ()))
        return PipelineResult(
            request=DiscoveryRequest(**d["request"]),
            keywords=_keywords(d["keywords"]),
            trend=TrendResult(**trend_d),
            bsr=BSRResult(**d["bsr"]),
            review=ReviewResult(**d["review"]),
            intent=IntentResult(**d["intent"]),
            margin=MarginResult(**d["margin"]),
            verdict=Verdict(**verdict_d),
        )
    except Exception:
        return None  # corrupt / schema-changed → treat as no saved result


def clear_last_result() -> None:
    try:
        _FILE.unlink(missing_ok=True)
    except Exception:
        pass
