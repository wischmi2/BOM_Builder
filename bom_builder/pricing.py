"""Pick the cheapest distributor offer for a Shop line and cost it out.

Prices come from the distributor cache (filled by Lookup). DigiKey and Mouser
are compared at the actual buy quantity using their price breaks; a distributor
that does not have enough stock only wins when nobody does.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bom_builder.distributor_cache import cache_key_for_mpn

COST_DISTRIBUTORS = (("digikey", "DigiKey"), ("mouser", "Mouser"))


@dataclass
class CostOffer:
    unit: float | None = None
    total: float = 0.0
    distributor: str = ""  # "DigiKey" / "Mouser" / ""
    note: str = ""  # e.g. "low stock", "no price — run Lookup"
    # chosen distributor's price breaks [[min_qty, unit], ...] so the page can
    # re-cost a line when its buy quantity is edited
    breaks: list = field(default_factory=list)

    @property
    def known(self) -> bool:
        return self.unit is not None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def _breaks(payload: dict[str, Any]) -> list[tuple[int, float]]:
    """Normalize DigiKey ({BreakQuantity, UnitPrice}) and Mouser ({Quantity, Price})
    price breaks to sorted (min_qty, unit_price)."""
    out: list[tuple[int, float]] = []
    for row in payload.get("price_breaks") or []:
        if not isinstance(row, dict):
            continue
        qty = row.get("BreakQuantity", row.get("Quantity"))
        price = _to_float(row.get("UnitPrice", row.get("Price")))
        try:
            qty_int = int(qty)
        except (TypeError, ValueError):
            continue
        if price is not None and price > 0:
            out.append((qty_int, price))
    return sorted(out)


def unit_price_at(payload: dict[str, Any], qty: int) -> float | None:
    """Unit price for buying ``qty`` (largest break not above qty)."""
    qty = max(1, qty)
    breaks = _breaks(payload)
    if breaks:
        eligible = [price for min_qty, price in breaks if min_qty <= qty]
        if eligible:
            return eligible[-1]
        return breaks[0][1]  # below the first break: you pay the first break price
    return _to_float(payload.get("price_1"))


def best_offer(cache_entry: dict[str, Any] | None, qty: int) -> CostOffer:
    if qty <= 0:
        return CostOffer(unit=None, total=0.0)
    offers: list[tuple[bool, float, str, list]] = []  # (enough_stock, unit, label, breaks)
    for key, label in COST_DISTRIBUTORS:
        payload = (cache_entry or {}).get(key)
        if not isinstance(payload, dict) or not payload.get("found"):
            continue
        unit = unit_price_at(payload, qty)
        if unit is None:
            continue
        stock = payload.get("stock")
        enough = stock is None or int(stock) >= qty  # unknown stock is not held against it
        breaks = [[q, p] for q, p in _breaks(payload)] or [[1, unit]]
        offers.append((enough, unit, label, breaks))
    if not offers:
        return CostOffer(note="no price — run Lookup")
    in_stock = [o for o in offers if o[0]]
    pool = in_stock or offers
    _, unit, label, breaks = min(pool, key=lambda o: o[1])
    return CostOffer(
        unit=unit,
        total=round(unit * qty, 4),
        distributor=label,
        note="" if in_stock else "low stock",
        breaks=breaks,
    )


def apply_costs(lines: list, cache: dict[str, dict[str, Any]]) -> None:
    """Attach ``line.cost`` (and ``line.alternate_cost``) offers to Shop lines."""
    for line in lines:
        line.cost = best_offer(cache.get(cache_key_for_mpn(line.primary_mpn)), line.buy_qty)
        alt = line.alternate
        if alt.enabled and alt.mpn:
            line.alternate_cost = best_offer(cache.get(cache_key_for_mpn(alt.mpn)), alt.buy_qty)
        else:
            line.alternate_cost = CostOffer()


def line_cost_total(line) -> float:
    return getattr(line, "cost", CostOffer()).total + getattr(line, "alternate_cost", CostOffer()).total


def group_cost_total(rows: list) -> float:
    return round(sum(line_cost_total(line) for line in rows), 2)


def unpriced_count(rows: list) -> int:
    count = 0
    for line in rows:
        if line.buy_qty > 0 and not getattr(line, "cost", CostOffer()).known:
            count += 1
        alt = line.alternate
        if alt.enabled and alt.mpn and alt.buy_qty > 0 and not getattr(line, "alternate_cost", CostOffer()).known:
            count += 1
    return count
