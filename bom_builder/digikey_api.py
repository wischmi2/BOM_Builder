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


def lookup_part(mpn: str) -> dict[str, Any]:
    """Keyword search; returns normalized cache payload or raises."""
    keyword = (mpn or "").strip()
    if not keyword:
        raise ValueError("MPN is required.")

    response = requests.post(
        f"{_api_base()}/products/v4/search/keyword",
        headers=_headers(),
        json={
            "Keywords": keyword,
            "RecordCount": 1,
            "RecordStartPosition": 0,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    products = data.get("Products") or []
    if not products:
        return {
            "found": False,
            "mpn": keyword,
            "url": digikey_search_url(keyword),
            "description": "",
            "stock": None,
            "price_1": None,
        }

    product = products[0]
    url = product.get("ProductUrl") or digikey_search_url(keyword)
    desc_obj = product.get("Description") or {}
    description = desc_obj.get("ProductDescription") or desc_obj.get("DetailedDescription") or ""
    stock = product.get("QuantityAvailable")
    price = _first_price(product.get("StandardPricing"))

    return {
        "found": True,
        "mpn": product.get("ManufacturerProductNumber") or keyword,
        "digikey_part": product.get("DigiKeyPartNumber", ""),
        "url": url,
        "description": description,
        "stock": int(stock) if stock is not None else None,
        "price_1": price,
    }
