from __future__ import annotations

import os
import re
from typing import Any

import requests

from bom_builder.shopping import mouser_search_url

_API_URL = "https://api.mouser.com/api/v1/search/partnumber"


def is_configured() -> bool:
    return bool(os.environ.get("MOUSER_API_KEY", "").strip())


def _api_key() -> str:
    return os.environ["MOUSER_API_KEY"].strip()


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


def lookup_part(mpn: str) -> dict[str, Any]:
    keyword = (mpn or "").strip()
    if not keyword:
        raise ValueError("MPN is required.")

    response = requests.post(
        f"{_API_URL}?apiKey={_api_key()}",
        json={
            "SearchByPartNumberRequest": {
                "mouserPartNumber": keyword,
                "partSearchOptions": "Exact",
            }
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    parts = (data.get("SearchResults") or {}).get("Parts") or []
    if not parts:
        return {
            "found": False,
            "mpn": keyword,
            "url": mouser_search_url(keyword),
            "description": "",
            "stock": None,
            "stock_text": "",
            "price_1": None,
            "price_breaks": [],
        }

    part = parts[0]
    availability = part.get("Availability", "")
    breaks = part.get("PriceBreaks") or []

    return {
        "found": True,
        "mpn": part.get("ManufacturerPartNumber") or keyword,
        "mouser_part": part.get("MouserPartNumber", ""),
        "url": part.get("ProductDetailUrl") or mouser_search_url(keyword),
        "description": part.get("Description", ""),
        "stock": _parse_stock(availability),
        "stock_text": availability,
        "price_1": _first_price(breaks),
        "price_breaks": breaks[:5],
    }
