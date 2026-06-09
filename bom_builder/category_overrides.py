from __future__ import annotations

import json
from typing import Callable

from bom_builder import storage
from bom_builder.part_categories import (
    CATEGORY_ORDER,
    CompareGroup,
    category_for_aggregated_row,
    category_for_compare_row,
    category_for_inventory_item,
    category_for_need_line,
    category_for_shop_line,
    sort_aggregated_rows,
    sort_compare_rows,
    sort_inventory_items,
    sort_need_lines,
    sort_shop_lines,
)

OVERRIDES_PATH = storage.DATA_DIR / "compare_category_overrides.json"


def load_overrides() -> dict[str, str]:
    if not OVERRIDES_PATH.exists():
        return {}
    data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    raw = data.get("overrides", {})
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def save_overrides(overrides: dict[str, str]) -> None:
    storage.atomic_write_text(
        OVERRIDES_PATH, json.dumps({"overrides": overrides}, indent=2)
    )


def set_override(part_key: str, category_id: str | None, *, auto_category: str | None = None) -> dict[str, str]:
    overrides = load_overrides()
    if not category_id or (auto_category and category_id == auto_category):
        overrides.pop(part_key, None)
    else:
        valid_ids = {cat_id for cat_id, _ in CATEGORY_ORDER}
        if category_id not in valid_ids:
            raise ValueError(f"Unknown category: {category_id}")
        overrides[part_key] = category_id
    save_overrides(overrides)
    return overrides


def effective_category(
    part_key: str,
    auto_category: str,
    overrides: dict[str, str],
) -> str:
    return overrides.get(part_key, auto_category)


def _group_by_category(
    rows: list,
    *,
    category_fn: Callable,
    part_key_fn: Callable,
    overrides: dict[str, str],
    sort_fn: Callable[[list], list],
    include_empty: bool = True,
) -> list[CompareGroup]:
    labels = dict(CATEGORY_ORDER)
    by_cat: dict[str, list] = {cat_id: [] for cat_id, _ in CATEGORY_ORDER}

    for row in rows:
        part_key = part_key_fn(row)
        auto = category_fn(row)
        cat_id = effective_category(part_key, auto, overrides)
        if cat_id not in by_cat:
            cat_id = "other"
        by_cat[cat_id].append(row)

    groups: list[CompareGroup] = []
    for cat_id, label in CATEGORY_ORDER:
        cat_rows = by_cat.get(cat_id, [])
        if not cat_rows and not include_empty:
            continue
        sorted_rows = sort_fn(cat_rows) if cat_rows else []
        groups.append(CompareGroup(category_id=cat_id, label=label, rows=sorted_rows))
    return groups


def group_compare_rows(rows: list, overrides: dict[str, str] | None = None) -> list[CompareGroup]:
    overrides = overrides or {}
    from bom_builder.matcher import part_key_for_compare_row

    return _group_by_category(
        rows,
        category_fn=category_for_compare_row,
        part_key_fn=part_key_for_compare_row,
        overrides=overrides,
        sort_fn=sort_compare_rows,
    )


def group_aggregated_rows(rows: list, overrides: dict[str, str] | None = None) -> list[CompareGroup]:
    overrides = overrides or {}

    return _group_by_category(
        rows,
        category_fn=category_for_aggregated_row,
        part_key_fn=lambda row: row.aggregate_key,
        overrides=overrides,
        sort_fn=sort_aggregated_rows,
    )


def part_key_for_inventory_item(item) -> str:
    from bom_builder.matcher import normalize_key, split_lib_refs

    segments = split_lib_refs(item.lib_ref or "")
    if segments:
        return "lib:" + normalize_key(segments[0])
    if item.name:
        return "name:" + normalize_key(item.name)
    return f"id:{item.id}"


def group_inventory_items(items: list, overrides: dict[str, str] | None = None) -> list[CompareGroup]:
    overrides = overrides or {}
    return _group_by_category(
        items,
        category_fn=category_for_inventory_item,
        part_key_fn=part_key_for_inventory_item,
        overrides=overrides,
        sort_fn=sort_inventory_items,
    )


def part_key_for_shop_line(line) -> str:
    from bom_builder.matcher import normalize_key, split_lib_refs

    segments = split_lib_refs(line.lib_ref or "")
    if segments:
        return "lib:" + normalize_key(segments[0])
    if line.name:
        return "name:" + normalize_key(line.name)
    return f"id:{line.line_id}"


def group_shop_lines(lines: list, overrides: dict[str, str] | None = None) -> list[CompareGroup]:
    overrides = overrides or {}
    return _group_by_category(
        lines,
        category_fn=category_for_shop_line,
        part_key_fn=part_key_for_shop_line,
        overrides=overrides,
        sort_fn=sort_shop_lines,
        include_empty=False,
    )


def group_need_lines(lines: list, overrides: dict[str, str] | None = None) -> list[CompareGroup]:
    from bom_builder.matcher import part_key_for_need_line

    overrides = overrides or {}
    return _group_by_category(
        lines,
        category_fn=category_for_need_line,
        part_key_fn=part_key_for_need_line,
        overrides=overrides,
        sort_fn=sort_need_lines,
        include_empty=False,
    )
