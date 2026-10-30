"""One-off Mouser API diagnostic. Run from the project root:

    .venv\\Scripts\\python diag_mouser.py

Prints the RAW Mouser responses so we can see whether the API is erroring,
returning zero parts, or returning parts the app then discards.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from bom_builder import mouser_api

KEY = mouser_api._api_key()
TEST_MPNS = ["CC0603KRX7R9BB104", "LM358", "1206W4F1003T5E"]


def show(label: str, url: str, body: dict) -> None:
    print("=" * 70)
    print(label)
    print("request:", json.dumps(body))
    try:
        r = requests.post(f"{url}?apiKey={KEY}", json=body, timeout=30)
    except Exception as exc:  # noqa: BLE001
        print("TRANSPORT ERROR:", repr(exc))
        return
    print("http status:", r.status_code)
    try:
        data = r.json()
    except ValueError:
        print("non-JSON body:", r.text[:500])
        return
    results = data.get("SearchResults")
    print("Errors:", json.dumps(data.get("Errors")))
    print("SearchResults is None:", results is None)
    if isinstance(results, dict):
        parts = results.get("Parts") or []
        print("NumberOfResult:", results.get("NumberOfResult"), "| Parts returned:", len(parts))
        for p in parts[:3]:
            print(
                "   -",
                p.get("MouserPartNumber"),
                "|",
                p.get("ManufacturerPartNumber"),
                "|",
                p.get("Manufacturer"),
            )
    else:
        print("raw body:", json.dumps(data)[:800])


print("key length:", len(KEY), "| looks like a GUID:", KEY.count("-") == 4)
print("key prefix:", KEY[:8] + "...")
print("MOUSER_API_KEY present in env:", bool(os.environ.get("MOUSER_API_KEY")))

for mpn in TEST_MPNS:
    show(
        f"[partnumber / Exact] {mpn}",
        "https://api.mouser.com/api/v1/search/partnumber",
        {"SearchByPartRequest": {"mouserPartNumber": mpn, "partSearchOptions": "Exact"}},
    )
    show(
        f"[partnumber / no options] {mpn}",
        "https://api.mouser.com/api/v1/search/partnumber",
        {"SearchByPartRequest": {"mouserPartNumber": mpn}},
    )
    show(
        f"[keyword] {mpn}",
        "https://api.mouser.com/api/v1/search/keyword",
        {"SearchByKeywordRequest": {"keyword": mpn, "records": 5, "startingRecord": 0}},
    )
