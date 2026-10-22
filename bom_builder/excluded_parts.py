"""Parts that are on the BOM but are never purchased (PCB features).

Examples: test-point pads, mounting holes, mouse bites, fiducials, logos.
They are keyed by the same part key used for category overrides
(``lib:<normalized first LibRef>`` or ``name:<normalized name>``), so hiding one
line hides every line that shares that LibRef across all BOMs.

Excluded parts are left out of Compare (rows, summary counts, gap CSV) and Shop
(buy list, stats, CSV). The Need page and the stored BOM are not changed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bom_builder import storage

FILENAME = "excluded_parts.json"


def excluded_path() -> Path:
    # Resolve at call time so BOM_DATA_DIR / test overrides of storage.DATA_DIR apply.
    return storage.DATA_DIR / FILENAME


def load_excluded() -> dict[str, dict[str, Any]]:
    path = excluded_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw = data.get("excluded", {}) if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for key, meta in raw.items():
        result[str(key)] = meta if isinstance(meta, dict) else {}
    return result


def save_excluded(excluded: dict[str, dict[str, Any]]) -> None:
    ordered = dict(sorted(excluded.items()))
    storage.atomic_write_text(excluded_path(), json.dumps({"excluded": ordered}, indent=2))


def excluded_keys() -> set[str]:
    return set(load_excluded().keys())


def set_excluded(
    part_key: str,
    excluded: bool,
    *,
    name: str = "",
    lib_ref: str = "",
) -> dict[str, dict[str, Any]]:
    part_key = part_key.strip()
    if not part_key:
        raise ValueError("Missing part key.")
    current = load_excluded()
    if excluded:
        current[part_key] = {"name": name.strip(), "lib_ref": lib_ref.strip()}
    else:
        current.pop(part_key, None)
    save_excluded(current)
    return current


def hidden_summary(
    entries: list[tuple[str, str, str]],
    excluded: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse (part_key, name, lib_ref) tuples for hidden rows into one entry per key.

    Used to render the "Not purchased" list (with Restore buttons) on Compare/Shop.
    """
    by_key: dict[str, dict[str, Any]] = {}
    for part_key, name, lib_ref in entries:
        if part_key not in excluded:
            continue
        item = by_key.get(part_key)
        if item is None:
            item = {"part_key": part_key, "names": [], "lib_ref": lib_ref, "count": 0}
            by_key[part_key] = item
        item["count"] += 1
        if name and name not in item["names"]:
            item["names"].append(name)
    result = list(by_key.values())
    for item in result:
        item["names_display"] = ", ".join(item["names"])
    result.sort(key=lambda i: (i["lib_ref"].upper(), i["names_display"].upper()))
    return result
