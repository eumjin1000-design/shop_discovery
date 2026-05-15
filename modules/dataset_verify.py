"""Live-URL verification for ASINs sourced from the (older) HF dataset.

Amazon rejects HEAD requests with 405, so we issue a Range-limited GET
(``bytes=0-2047``), inspect the first 2 KB of the response, and classify the
URL as ``live`` / ``dead`` / ``robot_check`` / ``unknown``. Electronics
ASINs trigger bot-check at a higher rate; for that category we slow the
request cadence and retry once on bot-check.

Interface
---------
    verify_asins(rows: list[dict], *, max_check: int = 30,
                 drop_dead: bool = True) -> list[dict]

``rows`` is the list produced by :func:`modules.dataset_lookup.top_asins`.
The returned list has each row annotated with ``verify_status``
(``"live"``, ``"dead"``, ``"robot_check"``, ``"unchecked"``); when
``drop_dead=True`` rows known to be dead are removed.
"""
from __future__ import annotations

import time
from typing import Optional

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 8
# Per-category cadence (seconds between requests). Electronics is the only
# category we've seen actively bot-check; everyone else gets the fast lane.
SLEEP_DEFAULT = 0.5
SLEEP_SLOW = 1.5
SLOW_CATEGORIES = {"Electronics", "Cell_Phones_and_Accessories"}
RETRY_AFTER_SEC = 5.0


def _classify(status: int, final_url: str, body_low: str) -> str:
    if status == 404:
        return "dead"
    if "robot check" in body_low or "captcha" in body_low \
            or "/errors/" in final_url.lower():
        return "robot_check"
    if "/ap/signin" in final_url:
        return "robot_check"
    if status in (200, 206):
        if "page you requested cannot be found" in body_low:
            return "dead"
        if "/dp/" in final_url:
            return "live"
    return "unknown"


def _probe(asin: str, session: requests.Session) -> str:
    url = f"https://www.amazon.com/dp/{asin}"
    try:
        with session.get(url, allow_redirects=True, timeout=TIMEOUT,
                         stream=True,
                         headers={"User-Agent": UA,
                                  "Accept-Language": "en-US",
                                  "Range": "bytes=0-2047"}) as r:
            chunk = next(r.iter_content(2048), b"") or b""
            return _classify(r.status_code, r.url or url,
                             chunk.decode("utf-8", "ignore").lower())
    except requests.RequestException:
        return "unknown"


def verify_asins(rows: list[dict], *, max_check: int = 30,
                 drop_dead: bool = True,
                 progress: Optional[callable] = None) -> list[dict]:
    if not rows:
        return rows
    session = requests.Session()
    checked = 0
    out: list[dict] = []
    for row in rows:
        if checked >= max_check:
            row = {**row, "verify_status": "unchecked"}
            out.append(row)
            continue
        asin = (row.get("asin") or "").strip().upper()
        if len(asin) != 10:
            row = {**row, "verify_status": "unchecked"}
            out.append(row)
            continue

        ds_cat = row.get("_dataset_category", "")
        slow = ds_cat in SLOW_CATEGORIES
        status = _probe(asin, session)
        if status == "robot_check":
            time.sleep(RETRY_AFTER_SEC)
            status = _probe(asin, session)

        annotated = {**row, "verify_status": status}
        if not (drop_dead and status == "dead"):
            out.append(annotated)
        checked += 1
        if progress:
            try:
                progress(checked, max_check, asin, status)
            except Exception:
                pass
        time.sleep(SLEEP_SLOW if slow else SLEEP_DEFAULT)
    return out
