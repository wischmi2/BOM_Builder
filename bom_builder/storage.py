from __future__ import annotations

import json
from pathlib import Path

from bom_builder.models import BomDocument, InventoryDocument

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
NEEDS_DIR = DATA_DIR / "needs"
INVENTORY_PATH = DATA_DIR / "inventory.json"


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
    ensure_data_dirs()
    INVENTORY_PATH.write_text(
        json.dumps(inventory.to_dict(), indent=2),
        encoding="utf-8",
    )
