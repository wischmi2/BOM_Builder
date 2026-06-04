from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from bom_builder.models import BomDocument, InventoryDocument

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
NEEDS_DIR = DATA_DIR / "needs"
INVENTORY_PATH = DATA_DIR / "inventory.json"
SHOPPING_LIST_PATH = DATA_DIR / "shopping_list.json"


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NEEDS_DIR.mkdir(parents=True, exist_ok=True)


def _need_path(bom_id: str) -> Path:
    safe_id = bom_id.replace("/", "_").replace("\\", "_")
    return NEEDS_DIR / f"{safe_id}.json"


def list_bom_ids() -> list[str]:
    ensure_data_dirs()
    ids = [path.stem for path in NEEDS_DIR.glob("*.json")]
    return sorted(ids)


def save_bom(bom: BomDocument) -> None:
    ensure_data_dirs()
    path = _need_path(bom.bom_id)
    path.write_text(json.dumps(bom.to_dict(), indent=2), encoding="utf-8")


def load_bom(bom_id: str) -> BomDocument | None:
    path = _need_path(bom_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return BomDocument.from_dict(data)


def delete_bom(bom_id: str) -> bool:
    path = _need_path(bom_id)
    if path.exists():
        path.unlink()
        return True
    return False


def load_inventory() -> InventoryDocument:
    ensure_data_dirs()
    if not INVENTORY_PATH.exists():
        return InventoryDocument()
    data = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    return InventoryDocument.from_dict(data)


def save_inventory(inventory: InventoryDocument) -> None:
    """Persist inventory; auto-backup if a save would wipe most rows (safety net)."""
    ensure_data_dirs()
    new_count = len(inventory.items)
    if INVENTORY_PATH.exists() and new_count < 5:
        try:
            previous = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
            old_items = previous.get("items", [])
            if isinstance(old_items, list) and len(old_items) >= 10:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                backup = INVENTORY_PATH.with_name(f"inventory.json.bak-{stamp}")
                shutil.copy2(INVENTORY_PATH, backup)
                latest = INVENTORY_PATH.with_suffix(".json.bak")
                shutil.copy2(INVENTORY_PATH, latest)
        except (OSError, json.JSONDecodeError):
            pass
    INVENTORY_PATH.write_text(
        json.dumps(inventory.to_dict(), indent=2),
        encoding="utf-8",
    )


def load_shopping_list() -> dict[str, dict]:
    ensure_data_dirs()
    if not SHOPPING_LIST_PATH.exists():
        return {}
    data = json.loads(SHOPPING_LIST_PATH.read_text(encoding="utf-8"))
    raw = data.get("lines", {})
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def save_shopping_list(lines: dict[str, dict]) -> None:
    ensure_data_dirs()
    SHOPPING_LIST_PATH.write_text(
        json.dumps({"lines": lines}, indent=2),
        encoding="utf-8",
    )
