"""Aggregate DigiKey/Mouser lookups into a single proposed part record, and
build a list of alternate parts (DigiKey substitutes + similar search results).

The pure functions here (build_enrichment_proposal, build_alternates) take
already-fetched data so they can be unit tested without network access. The
fetch_* wrappers call the distributor APIs.
"""
from __future__ import annotations

from typing import Any

from bom_builder import digikey_api, lcsc_api, mouser_api
from bom_builder.distributor_cache import utc_now_iso
from bom_builder.distributor_lookup import (
    DIGIKEY_MIN_INTERVAL_SEC,
    LCSC_MIN_INTERVAL_SEC,
    MOUSER_MIN_INTERVAL_SEC,
    lookup_mpn,
)

# Prefer DigiKey, then Mouser, then LCSC when more than one has a value for a field.
_SOURCE_PRIORITY = ("digikey", "mouser", "lcsc")


def _first_nonempty(results: dict[str, dict[str, Any]], field: str) -> tuple[str, str]:
    """Return (value, distributor) for the first non-empty field by priority."""
    for dist in _SOURCE_PRIORITY:
        payload = results.get(dist)
        if not isinstance(payload, dict) or not payload.get("found"):
            continue
        value = str(payload.get(field) or "").strip()
        if value:
            return value, dist
    return "", ""


def _best_price(results: dict[str, dict[str, Any]]) -> tuple[float | None, str]:
    """Lowest unit price across distributors, with the distributor it came from."""
    best: float | None = None
    best_dist = ""
    for dist in _SOURCE_PRIORITY:
        payload = results.get(dist)
        if not isinstance(payload, dict) or not payload.get("found"):
            continue
        price = payload.get("price_1")
        if price is None:
            continue
        price = float(price)
        if best is None or price < best:
            best = price
            best_dist = dist
    return best, best_dist


def build_enrichment_proposal(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Combine per-distributor lookup payloads into one proposed enrichment record."""
    # Resolved manufacturer part number (e.g. LCSC turns a Cxxxx code into the real
    # MPN, which is what makes DigiKey/Mouser alternate searches work afterward).
    mpn, _ = _first_nonempty(results, "mpn")
    manufacturer, mfr_src = _first_nonempty(results, "manufacturer")
    description, _ = _first_nonempty(results, "description")
    datasheet_url, _ = _first_nonempty(results, "datasheet_url")
    unit_price, price_src = _best_price(results)

    # Stock comes from the distributor we treat as the source (price source, then
    # manufacturer source, then any found distributor).
    source = price_src or mfr_src
    if not source:
        for dist in _SOURCE_PRIORITY:
            payload = results.get(dist)
            if isinstance(payload, dict) and payload.get("found"):
                source = dist
                break

    stock = None
    if source and isinstance(results.get(source), dict):
        raw_stock = results[source].get("stock")
        stock = int(raw_stock) if raw_stock is not None else None

    found = any(isinstance(p, dict) and p.get("found") for p in results.values())

    return {
        "found": found,
        "mpn": mpn,
        "manufacturer": manufacturer,
        "description": description,
        "datasheet_url": datasheet_url,
        "unit_price": unit_price,
        "stock": stock,
        "source": source,
        "enriched_at": utc_now_iso(),
        "distributors": results,
    }


def build_alternates(
    substitutes: list[dict[str, Any]],
    similar: list[dict[str, Any]],
    *,
    original_mpn: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Merge substitute + similar candidates: dedupe by MPN, drop the original,
    substitutes first, then by ascending price (unknown price last)."""
    original = (original_mpn or "").strip().upper()
    by_mpn: dict[str, dict[str, Any]] = {}

    # Substitutes take precedence over similar results for the same MPN.
    for cand in [*substitutes, *similar]:
        mpn = str(cand.get("mpn") or "").strip()
        key = mpn.upper()
        if not mpn or key == original:
            continue
        existing = by_mpn.get(key)
        if existing is None:
            by_mpn[key] = dict(cand)
            continue
        # Keep substitute kind if either says substitute; fill missing fields.
        if cand.get("kind") == "substitute":
            existing["kind"] = "substitute"
        for field in ("manufacturer", "description", "datasheet_url", "url"):
            if not existing.get(field) and cand.get(field):
                existing[field] = cand[field]
        if existing.get("price_1") is None and cand.get("price_1") is not None:
            existing["price_1"] = cand["price_1"]
        if existing.get("stock") is None and cand.get("stock") is not None:
            existing["stock"] = cand["stock"]

    def sort_key(item: dict[str, Any]) -> tuple[int, float]:
        is_sub = 0 if item.get("kind") == "substitute" else 1
        price = item.get("price_1")
        price_key = float(price) if price is not None else float("inf")
        return (is_sub, price_key)

    return sorted(by_mpn.values(), key=sort_key)[:limit]


# --------------------------------------------------------------------------- #
# Network wrappers (call the distributor APIs).
# --------------------------------------------------------------------------- #

def fetch_enrichment(mpn: str, *, force: bool = False, lcsc_code: str = "") -> dict[str, Any]:
    """Look up an MPN across configured distributors and build a proposal.

    Reuses the distributor cache (via lookup_mpn) so repeated enrich calls are cheap.
    LCSC is queried by its Cxxxx code when available.
    """
    results, errors = lookup_mpn(mpn, force=force, lcsc_code=lcsc_code)
    proposal = build_enrichment_proposal(results)
    proposal["errors"] = errors
    return proposal


def fetch_alternates(mpn: str, *, limit: int = 10, lcsc_code: str = "") -> dict[str, Any]:
    """Fetch DigiKey substitutes + DigiKey/Mouser/LCSC similar results for an MPN."""
    import time

    keyword = (mpn or "").strip()
    substitutes: list[dict[str, Any]] = []
    similar: list[dict[str, Any]] = []
    errors: dict[str, str] = {}

    if digikey_api.is_configured():
        try:
            substitutes.extend(digikey_api.get_substitutions(keyword, limit=limit))
            time.sleep(DIGIKEY_MIN_INTERVAL_SEC)
            similar.extend(digikey_api.search_candidates(keyword, limit=limit))
        except Exception as exc:  # noqa: BLE001 — surface to UI
            errors["digikey"] = str(exc)

    if mouser_api.is_configured():
        try:
            time.sleep(MOUSER_MIN_INTERVAL_SEC)
            similar.extend(mouser_api.search_candidates(keyword, limit=limit))
        except Exception as exc:  # noqa: BLE001
            errors["mouser"] = str(exc)

    if lcsc_api.is_configured():
        try:
            time.sleep(LCSC_MIN_INTERVAL_SEC)
            similar.extend(lcsc_api.search_candidates(keyword, limit=limit))
        except Exception as exc:  # noqa: BLE001
            errors["lcsc"] = str(exc)

    alternates = build_alternates(substitutes, similar, original_mpn=keyword, limit=limit)

    # DigiKey's substitutions endpoint often omits stock/pricing, so those rows
    # show "—". Backfill quantity-available (and price/datasheet) for any alternate
    # that's missing them via a cached lookup so every row shows a stock figure.
    for alt in alternates:
        if alt.get("stock") is not None and alt.get("price_1") is not None:
            continue
        alt_mpn = str(alt.get("mpn") or "").strip()
        if not alt_mpn:
            continue
        try:
            results, _ = lookup_mpn(alt_mpn, lcsc_code=str(alt.get("lcsc_part") or ""))
        except Exception:  # noqa: BLE001 — backfill is best-effort
            continue
        proposal = build_enrichment_proposal(results)
        if alt.get("stock") is None and proposal.get("stock") is not None:
            alt["stock"] = proposal["stock"]
        if alt.get("price_1") is None and proposal.get("unit_price") is not None:
            alt["price_1"] = proposal["unit_price"]
        if not alt.get("datasheet_url") and proposal.get("datasheet_url"):
            alt["datasheet_url"] = proposal["datasheet_url"]
        if not alt.get("manufacturer") and proposal.get("manufacturer"):
            alt["manufacturer"] = proposal["manufacturer"]

    return {
        "ok": True,
        "mpn": keyword,
        "alternates": alternates,
        "errors": errors,
    }
