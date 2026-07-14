from __future__ import annotations

import os
import re
from typing import Any

import requests

from bom_builder.shopping import mouser_search_url

_API_URL = "https://api.mouser.com/api/v1/search/partnumber"
_KEYWORD_URL = "https://api.mouser.com/api/v1/search/keyword"


def _clean_key(raw: str) -> str:
    # Tolerate common .env mistakes: surrounding quotes, whitespace, a trailing
    # inline comment. A stray quote makes Mouser reject the key as an invalid GUID.
    key = (raw or "").strip()
    if key and key[0] in "\"'" and key[-1:] == key[0]:
        key = key[1:-1].strip()
    if "#" in key:
        key = key.split("#", 1)[0].strip()
    return key


def is_configured() -> bool:
    return bool(_clean_key(os.environ.get("MOUSER_API_KEY", "")))


def _api_key() -> str:
    return _clean_key(os.environ.get("MOUSER_API_KEY", ""))


def _parse_stock(availability: str) -> int | None:
    if not availability:
        return None
    match = re.search(r"(\d[\d,]*)", availability.replace(",", ""))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    lower = availability.lower()
    if "in stock" in lower:
        return None
    return None


def _first_price(breaks: list[dict[str, Any]] | None) -> float | None:
    if not breaks:
        return None
    for row in breaks:
        qty = row.get("Quantity", 1)
        try:
            if int(qty) <= 1:
                price = row.get("Price")
                if price:
                    return float(str(price).replace("$", "").replace(",", "").strip())
        except (TypeError, ValueError):
            continue
    row = breaks[0]
    price = row.get("Price")
    if not price:
        return None
    try:
        return float(str(price).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def _raise_on_errors(data: dict[str, Any]) -> None:
    """Mouser returns API-level problems (rate limits, key/permission issues,
    validation failures) as a 200 response with an Errors array. Surface them —
    including which field (PropertyName) triggered it — instead of masking as
    'no match'."""
    errors = data.get("Errors") or []
    messages = []
    for e in errors:
        if not isinstance(e, dict):
            continue
        message = str(e.get("Message") or "").strip()
        code = str(e.get("Code") or "").strip()
        prop = str(e.get("PropertyName") or "").strip()
        # De-duplicate when Message == Code (e.g. both "Required").
        label = " ".join(dict.fromkeys([b for b in (message, code) if b]))
        if prop:
            label = f"{label} [{prop}]" if label else f"Required [{prop}]"
        if label:
            messages.append(label)
    if messages:
        raise RuntimeError("Mouser API: " + "; ".join(messages))


def _normalize_part(part: dict[str, Any], keyword: str = "", *, kind: str = "similar") -> dict[str, Any]:
    """Normalize a Mouser part record into the shared candidate shape."""
    availability = part.get("Availability", "")
    breaks = part.get("PriceBreaks") or []
    return {
        "distributor": "mouser",
        "found": True,
        "mpn": part.get("ManufacturerPartNumber") or keyword,
        "mouser_part": part.get("MouserPartNumber", ""),
        "manufacturer": str(part.get("Manufacturer") or "").strip(),
        "url": part.get("ProductDetailUrl") or mouser_search_url(keyword),
        "description": part.get("Description", ""),
        "datasheet_url": str(part.get("DataSheetUrl") or "").strip(),
        "stock": _parse_stock(availability),
        "stock_text": availability,
        "price_1": _first_price(breaks),
        "price_breaks": breaks[:5],
        "kind": kind,
    }


def lookup_part(mpn: str) -> dict[str, Any]:
    keyword = (mpn or "").strip()
    if not keyword:
        raise ValueError("MPN is required.")

    response = requests.post(
        f"{_API_URL}?apiKey={_api_key()}",
        json={
            "SearchByPartRequest": {
                "mouserPartNumber": keyword,
                "partSearchOptions": "Exact",
            }
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    _raise_on_errors(data)
    parts = (data.get("SearchResults") or {}).get("Parts") or []
    if parts:
        return _normalize_part(parts[0], keyword, kind="exact")

    # The exact part-number endpoint misses many manufacturer part numbers that
    # Mouser's site keyword search finds (e.g. Royalohm 1206W4F1003T5E, which
    # Mouser carries as 303-1206W4F1003T5E). Fall back to keyword search.
    candidates = search_candidates(keyword, limit=1)
    if candidates:
        return {**candidates[0], "kind": "exact"}

    return {
        "found": False,
        "mpn": keyword,
        "url": mouser_search_url(keyword),
        "manufacturer": "",
        "description": "",
        "datasheet_url": "",
        "stock": None,
        "stock_text": "",
        "price_1": None,
        "price_breaks": [],
    }


def search_candidates(mpn: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Return up to `limit` keyword-search matches as similar-part candidates."""
    keyword = (mpn or "").strip()
    if not keyword:
        return []

    response = requests.post(
        f"{_KEYWORD_URL}?apiKey={_api_key()}",
        json={
            "SearchByKeywordRequest": {
                "keyword": keyword,
                "records": max(1, limit),
                "startingRecord": 0,
            }
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    _raise_on_errors(data)
    parts = (data.get("SearchResults") or {}).get("Parts") or []
    return [_normalize_part(p, keyword, kind="similar") for p in parts[:limit]]
