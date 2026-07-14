"""LCSC lookups via the public EasyEDA/LCSC endpoints (no API key required).

LCSC has no official keyed API, so we use the same endpoints the KiCad/EasyEDA
tooling uses:
  * detail by C-number: https://easyeda.com/api/products/{code}/components
  * keyword search:      https://easyeda.com/api/eda/product/search?keyword=...

LCSC's exact key is the Cxxxx code (captured from KiCad imports). lookup_part
auto-detects: a Cxxxx code goes to the detail endpoint; anything else (an MPN)
falls back to keyword search.
"""
from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote

import requests

_DETAIL_URL = "https://easyeda.com/api/products/{code}/components"
_SEARCH_URL = "https://easyeda.com/api/eda/product/search"
_LCSC_BASE = "https://www.lcsc.com"

_C_NUMBER = re.compile(r"^C\d+$", re.IGNORECASE)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BOM-Builder/1.0",
    "Accept": "application/json",
}


def is_configured() -> bool:
    """LCSC needs no key, so it's available unless explicitly disabled."""
    return os.environ.get("LCSC_DISABLED", "").lower() not in ("1", "true", "yes")


def is_lcsc_code(value: str) -> bool:
    return bool(_C_NUMBER.match((value or "").strip()))


def lcsc_search_url(query: str) -> str:
    return f"{_LCSC_BASE}/search?q={quote((query or '').strip(), safe='')}"


def _clean_manufacturer(name: str) -> str:
    # LCSC returns names like "YAGEO(国巨)"; strip the trailing localized alias.
    return re.sub(r"\s*\([^)]*\)\s*$", "", str(name or "")).strip()


def _to_float(value: Any) -> float | None:
    try:
        f = float(str(value).replace("$", "").replace(",", "").strip())
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _abs_url(url: str) -> str:
    url = str(url or "").strip()
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return f"{_LCSC_BASE}{url}" if url.startswith("/") else f"{_LCSC_BASE}/{url}"


def _normalize_detail(result: dict[str, Any], code: str, *, kind: str = "exact") -> dict[str, Any]:
    lcsc = result.get("lcsc") if isinstance(result.get("lcsc"), dict) else {}
    szlcsc = result.get("szlcsc") if isinstance(result.get("szlcsc"), dict) else {}
    c_para = (((result.get("dataStr") or {}).get("head") or {}).get("c_para")) or {}

    mpn = result.get("title") or c_para.get("Manufacturer Part") or ""
    manufacturer = _clean_manufacturer(c_para.get("Manufacturer") or "")
    stock = _to_int(szlcsc.get("stock")) or _to_int(lcsc.get("stock"))
    price = _to_float(lcsc.get("price")) or _to_float(szlcsc.get("price"))
    url = _abs_url(lcsc.get("url") or szlcsc.get("url"))

    return {
        "distributor": "lcsc",
        "found": True,
        "mpn": mpn,
        "lcsc_part": lcsc.get("number") or szlcsc.get("number") or code,
        "manufacturer": manufacturer,
        "description": result.get("description") or "",
        "datasheet_url": "",  # not provided by this endpoint
        "url": url or lcsc_search_url(code),
        "stock": stock,
        "price_1": price,
        "kind": kind,
    }


def _normalize_search_item(item: dict[str, Any], *, kind: str = "similar") -> dict[str, Any]:
    price_breaks = item.get("price") or []
    price = None
    if price_breaks and isinstance(price_breaks[0], (list, tuple)) and len(price_breaks[0]) >= 2:
        price = _to_float(price_breaks[0][1])
    return {
        "distributor": "lcsc",
        "found": True,
        "mpn": item.get("mpn") or "",
        "lcsc_part": item.get("number") or "",
        "manufacturer": _clean_manufacturer(item.get("manufacturer") or ""),
        "description": item.get("package") or "",
        "datasheet_url": "",
        "url": _abs_url(item.get("url")),
        "stock": _to_int(item.get("stock")),
        "price_1": price,
        "kind": kind,
    }


def _not_found(query: str) -> dict[str, Any]:
    return {
        "distributor": "lcsc",
        "found": False,
        "mpn": query,
        "lcsc_part": query if is_lcsc_code(query) else "",
        "manufacturer": "",
        "description": "",
        "datasheet_url": "",
        "url": lcsc_search_url(query),
        "stock": None,
        "price_1": None,
    }


def lookup_code(code: str) -> dict[str, Any]:
    """Look up an LCSC part by its Cxxxx code via the detail endpoint."""
    code = (code or "").strip()
    if not code:
        raise ValueError("LCSC code is required.")
    response = requests.get(_DETAIL_URL.format(code=quote(code, safe="")), headers=_HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()
    result = data.get("result")
    if not data.get("success", data.get("code") in (0, 200)) or not isinstance(result, dict):
        return _not_found(code)
    return _normalize_detail(result, code)


def search_candidates(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Keyword search LCSC's catalog (used for MPN fallback and alternates)."""
    query = (query or "").strip()
    if not query:
        return []
    response = requests.get(
        _SEARCH_URL,
        params={"keyword": query, "needAggs": "false", "currPage": 1, "pageSize": max(1, limit)},
        headers=_HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    products = ((response.json().get("result") or {}).get("productList")) or []
    return [_normalize_search_item(p) for p in products[:limit]]


def lookup_part(query: str) -> dict[str, Any]:
    """Look up by C-number (exact detail) or, for an MPN, the top search match."""
    query = (query or "").strip()
    if not query:
        raise ValueError("Query is required.")
    if is_lcsc_code(query):
        return lookup_code(query)
    candidates = search_candidates(query, limit=1)
    if candidates:
        return {**candidates[0], "kind": "exact"}
    return _not_found(query)
