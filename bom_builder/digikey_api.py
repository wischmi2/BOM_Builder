from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import quote

import requests

from bom_builder.shopping import digikey_search_url

_TOKEN: str | None = None
_TOKEN_EXPIRES: float = 0.0


def is_configured() -> bool:
    return bool(os.environ.get("DIGIKEY_CLIENT_ID") and os.environ.get("DIGIKEY_CLIENT_SECRET"))


def _api_base() -> str:
    if os.environ.get("DIGIKEY_USE_SANDBOX", "").lower() in ("1", "true", "yes"):
        return "https://sandbox-api.digikey.com"
    return "https://api.digikey.com"


def _get_token() -> str:
    global _TOKEN, _TOKEN_EXPIRES
    if _TOKEN and time.time() < _TOKEN_EXPIRES - 60:
        return _TOKEN

    client_id = os.environ["DIGIKEY_CLIENT_ID"]
    client_secret = os.environ["DIGIKEY_CLIENT_SECRET"]
    response = requests.post(
        f"{_api_base()}/v1/oauth2/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    _TOKEN = data["access_token"]
    _TOKEN_EXPIRES = time.time() + int(data.get("expires_in", 3600))
    return _TOKEN


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "X-DIGIKEY-Client-Id": os.environ["DIGIKEY_CLIENT_ID"],
        "Content-Type": "application/json",
    }


def _first_price(pricing: list[dict[str, Any]] | None) -> float | None:
    if not pricing:
        return None
    for row in pricing:
        if row.get("BreakQuantity", 1) <= 1:
            price = row.get("UnitPrice")
            if price is not None:
                return float(price)
    first = pricing[0]
    price = first.get("UnitPrice")
    return float(price) if price is not None else None


def _manufacturer(product: dict[str, Any]) -> str:
    mfr = product.get("Manufacturer")
    if isinstance(mfr, dict):
        return str(mfr.get("Name") or "").strip()
    return str(mfr or "").strip()


def _description(product: dict[str, Any]) -> str:
    desc_obj = product.get("Description") or {}
    if isinstance(desc_obj, dict):
        return desc_obj.get("ProductDescription") or desc_obj.get("DetailedDescription") or ""
    return str(desc_obj or "")


def _normalize_product(product: dict[str, Any], keyword: str = "", *, kind: str = "similar") -> dict[str, Any]:
    """Normalize a DigiKey product record into the shared candidate shape."""
    stock = product.get("QuantityAvailable")
    return {
        "distributor": "digikey",
        "found": True,
        "mpn": product.get("ManufacturerProductNumber") or keyword,
        "digikey_part": product.get("DigiKeyPartNumber", ""),
        "manufacturer": _manufacturer(product),
        "description": _description(product),
        "datasheet_url": str(product.get("DatasheetUrl") or "").strip(),
        "url": product.get("ProductUrl") or digikey_search_url(product.get("ManufacturerProductNumber") or keyword),
        "stock": int(stock) if stock is not None else None,
        "price_1": _first_price(product.get("StandardPricing")),
        "kind": kind,
    }


def _search_products(keyword: str, record_count: int) -> list[dict[str, Any]]:
    response = requests.post(
        f"{_api_base()}/products/v4/search/keyword",
        headers=_headers(),
        json={
            "Keywords": keyword,
            "RecordCount": record_count,
            "RecordStartPosition": 0,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("Products") or []


def lookup_part(mpn: str) -> dict[str, Any]:
    """Keyword search; returns normalized cache payload for the best match or raises."""
    keyword = (mpn or "").strip()
    if not keyword:
        raise ValueError("MPN is required.")

    products = _search_products(keyword, 1)
    if not products:
        return {
            "found": False,
            "mpn": keyword,
            "url": digikey_search_url(keyword),
            "manufacturer": "",
            "description": "",
            "datasheet_url": "",
            "stock": None,
            "price_1": None,
        }
    return _normalize_product(products[0], keyword, kind="exact")


def search_candidates(mpn: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Return up to `limit` keyword-search matches as similar-part candidates."""
    keyword = (mpn or "").strip()
    if not keyword:
        return []
    products = _search_products(keyword, max(1, limit))
    return [_normalize_product(p, keyword, kind="similar") for p in products]


def get_substitutions(mpn: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Return DigiKey substitute parts for an MPN.

    Resolves the DigiKey part number via keyword search, then queries the
    product substitutions endpoint. Returns [] if nothing is found.
    """
    keyword = (mpn or "").strip()
    if not keyword:
        return []

    products = _search_products(keyword, 1)
    if not products:
        return []
    product_number = products[0].get("DigiKeyPartNumber") or keyword

    response = requests.get(
        f"{_api_base()}/products/v4/search/{quote(str(product_number), safe='')}/substitutions",
        headers=_headers(),
        timeout=30,
    )
    if response.status_code == 404:
        return []
    response.raise_for_status()
    data = response.json()
    subs = data.get("ProductSubstitutes") or data.get("Substitutions") or []
    out: list[dict[str, Any]] = []
    for entry in subs[:limit]:
        # Substitutions may wrap the product under a "Product" key or be flat.
        product = entry.get("Product") if isinstance(entry.get("Product"), dict) else entry
        out.append(_normalize_product(product, keyword, kind="substitute"))
    return out
