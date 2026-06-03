from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bom_builder.storage import DATA_DIR, ensure_data_dirs

DISTRIBUTOR_CACHE_PATH = DATA_DIR / "distributor_cache.json"


def cache_key_for_mpn(mpn: str) -> str:
    normalized = (mpn or "").strip().upper()
    return f"mpn:{normalized}" if normalized else "mpn:"


def load_distributor_cache() -> dict[str, dict[str, Any]]:
    ensure_data_dirs()
    if not DISTRIBUTOR_CACHE_PATH.exists():
        return {}
    data = json.loads(DISTRIBUTOR_CACHE_PATH.read_text(encoding="utf-8"))
    entries = data.get("entries", {})
    if not isinstance(entries, dict):
        return {}
    return {str(k): v for k, v in entries.items() if isinstance(v, dict)}


def save_distributor_cache(entries: dict[str, dict[str, Any]]) -> None:
    ensure_data_dirs()
    DISTRIBUTOR_CACHE_PATH.write_text(
        json.dumps({"entries": entries}, indent=2),
        encoding="utf-8",
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_cached(entries: dict[str, dict[str, Any]], mpn: str, distributor: str) -> dict[str, Any] | None:
    entry = entries.get(cache_key_for_mpn(mpn), {})
    raw = entry.get(distributor)
    return raw if isinstance(raw, dict) else None


def set_cached(
    entries: dict[str, dict[str, Any]],
    mpn: str,
    distributor: str,
    payload: dict[str, Any],
) -> None:
    key = cache_key_for_mpn(mpn)
    entry = dict(entries.get(key, {}))
    entry[distributor] = {**payload, "fetched_at": payload.get("fetched_at") or utc_now_iso()}
    entries[key] = entry
