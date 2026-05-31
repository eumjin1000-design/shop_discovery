"""Live-ish domain availability via Whois.

Wraps ``python-whois`` with a thread-pool + per-process cache so the UI can
check 8 candidate domains in parallel within a few seconds. Whois is
notoriously inconsistent (per-TLD servers, rate limits, parser quirks), so
every failure degrades to ``"unknown"`` — the feature never blocks the rest
of the flow.

Interface
---------
    check_many(domains, timeout=5, max_workers=8) -> dict[domain, status]

    where status ∈ {"available", "taken", "unknown"}.
"""
from __future__ import annotations

import concurrent.futures
from typing import Literal

Status = Literal["available", "taken", "unknown"]

_CACHE: dict[str, Status] = {}
_AVAIL_HINTS = (
    "no match", "not found", "no entries", "no data found",
    "domain not found", "status: free", "status: available",
)


def _check_one(domain: str, timeout: float = 5.0) -> Status:
    """One Whois lookup. Returns 'taken'/'available'/'unknown'."""
    if domain in _CACHE:
        return _CACHE[domain]
    status: Status = "unknown"
    try:
        import whois  # python-whois

        w = whois.whois(domain)
        # python-whois returns a dict-like; ``domain_name`` is set when the
        # registry confirms the domain exists. Empty/None → likely available.
        if w and getattr(w, "domain_name", None):
            status = "taken"
        else:
            status = "available"
    except Exception as e:
        msg = str(e).lower()
        if any(h in msg for h in _AVAIL_HINTS):
            status = "available"
        # else: keep "unknown" — Whois server unreachable, rate-limited, etc.
    _CACHE[domain] = status
    return status


def check_many(domains: list[str], timeout: float = 5.0,
               max_workers: int = 8) -> dict[str, Status]:
    """Parallel Whois lookup for several domains.

    Uses a thread pool with a wall-clock timeout per call. Cached results are
    served immediately. Anything that doesn't finish or errors out returns
    ``"unknown"``.
    """
    out: dict[str, Status] = {}
    pending: list[str] = []
    for d in domains:
        if d in _CACHE:
            out[d] = _CACHE[d]
        else:
            pending.append(d)
    if not pending:
        return out

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_check_one, d, timeout): d for d in pending}
        try:
            done, _ = concurrent.futures.wait(
                futures, timeout=timeout * 2,
                return_when=concurrent.futures.ALL_COMPLETED)
        except Exception:
            done = set()
        for fut in futures:
            d = futures[fut]
            if fut in done:
                try:
                    out[d] = fut.result(timeout=0.1)
                except Exception:
                    out[d] = "unknown"
            else:
                out[d] = "unknown"
                fut.cancel()
    return out


def clear_cache() -> None:
    _CACHE.clear()
