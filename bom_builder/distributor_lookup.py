from __future__ import annotations

import time
from typing import Any

from bom_builder import digikey_api, lcsc_api, mouser_api
from bom_builder.distributor_cache import (
    cache_key_for_mpn,
    get_cached,
    load_distributor_cache,
    save_distributor_cache,
    set_cached,
    utc_now_iso,
)

# Mouser ~30/min — stay conservative for batch lookups.
MOUSER_MIN_INTERVAL_SEC = 2.1
DIGIKEY_MIN_INTERVAL_SEC = 0.35
LCSC_MIN_INTERVAL_SEC = 0.5
BATCH_MAX_MPNS = 25

# Distributors queried by default, in preference order.
DISTRIBUTORS = ("digikey", "mouser", "lcsc")

_last_mouser_call = 0.0
_last_digikey_call = 0.0
_last_lcsc_call = 0.0


def api_status() -> dict[str, bool]:
    return {
        "digikey": digikey_api.is_configured(),
        "mouser": mouser_api.is_configured(),
        "lcsc": lcsc_api.is_configured(),
    }


def any_api_configured() -> bool:
    return any(api_status().values())


def _throttle(distributor: str) -> None:
    global _last_mouser_call, _last_digikey_call, _last_lcsc_call
    if distributor == "mouser":
        elapsed = time.time() - _last_mouser_call
        if elapsed < MOUSER_MIN_INTERVAL_SEC:
            time.sleep(MOUSER_MIN_INTERVAL_SEC - elapsed)
        _last_mouser_call = time.time()
    elif distributor == "digikey":
        elapsed = time.time() - _last_digikey_call
        if elapsed < DIGIKEY_MIN_INTERVAL_SEC:
            time.sleep(DIGIKEY_MIN_INTERVAL_SEC - elapsed)
        _last_digikey_call = time.time()
    elif distributor == "lcsc":
        elapsed = time.time() - _last_lcsc_call
        if elapsed < LCSC_MIN_INTERVAL_SEC:
            time.sleep(LCSC_MIN_INTERVAL_SEC - elapsed)
        _last_lcsc_call = time.time()


def lookup_mpn(
    mpn: str,
    *,
    distributors: list[str] | None = None,
    force: bool = False,
    entries: dict[str, dict[str, Any]] | None = None,
    lcsc_code: str = "",
) -> tuple[dict[str, Any], dict[str, str]]:
    """
    Lookup one MPN. Returns (results per distributor, errors per distributor).
    Updates entries in place when provided.

    LCSC is queried by its Cxxxx code when `lcsc_code` is given (its exact key),
    otherwise by the MPN via keyword search.
    """
    if entries is None:
        entries = load_distributor_cache()

    status = api_status()
    targets = distributors or [d for d in DISTRIBUTORS if status.get(d)]
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}

    for dist in targets:
        if not status.get(dist):
            errors[dist] = "API not configured."
            continue

        if not force:
            cached = get_cached(entries, mpn, dist)
            if cached:
                results[dist] = cached
                continue

        try:
            _throttle(dist)
            if dist == "digikey":
                payload = digikey_api.lookup_part(mpn)
            elif dist == "mouser":
                payload = mouser_api.lookup_part(mpn)
            else:  # lcsc
                payload = lcsc_api.lookup_part((lcsc_code or "").strip() or mpn)
            payload["fetched_at"] = utc_now_iso()
            set_cached(entries, mpn, dist, payload)
            results[dist] = payload
        except Exception as exc:  # noqa: BLE001 — surface message to UI
            errors[dist] = str(exc)

    return results, errors


def lookup_batch(
    mpns: list[str],
    *,
    distributors: list[str] | None = None,
    force: bool = False,
    lcsc_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    lcsc_map = lcsc_map or {}
    unique = []
    seen: set[str] = set()
    for raw in mpns:
        mpn = (raw or "").strip()
        if not mpn:
            continue
        key = mpn.upper()
        if key in seen:
            continue
        seen.add(key)
        unique.append(mpn)
        if len(unique) >= BATCH_MAX_MPNS:
            break

    entries = load_distributor_cache()
    out: dict[str, dict[str, Any]] = {}
    errors: dict[str, dict[str, str]] = {}

    for mpn in unique:
        results, row_errors = lookup_mpn(
            mpn,
            distributors=distributors,
            force=force,
            entries=entries,
            lcsc_code=lcsc_map.get(mpn, ""),
        )
        cache_key = cache_key_for_mpn(mpn)
        out[cache_key] = results
        if row_errors:
            errors[cache_key] = row_errors

    save_distributor_cache(entries)

    return {
        "ok": True,
        "results": out,
        "errors": errors,
        "api_status": api_status(),
        "limited_to": BATCH_MAX_MPNS,
    }
