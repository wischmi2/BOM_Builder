# Shopping list (DigiKey + Mouser)

The **Shop** page builds a buy list from Compare **missing** and **partial** lines.

## Workflow

1. **Compare** — Select BOM(s), use combined view if building multiple boards.
2. Click **Open shopping list** (or use the **Shop** nav tab).
3. Adjust **Buy qty** if needed (default is shortfall: need minus on hand).
4. Open **DigiKey** or **Mouser** links to find and order parts.
5. Check **Ordered** and add **Notes** (PO number, cart name, etc.) — saves automatically.
6. When parts arrive, update **Inventory** (manual entry or label scan).

## Export

**Export buy list CSV** includes MPN, quantities, notes, ordered flag, and distributor search URLs.

## Persistence

Saved in `data/shopping_list.json` (committed to git with other data). Keys match Compare line identity so notes and ordered flags survive a refresh when the same BOMs are selected.

## Phase 2 (not implemented yet)

Optional DigiKey and Mouser APIs can add live stock and pricing. Phase 1 uses search links only — no API keys required.

- [DigiKey API](https://developer.digikey.com/)
- [Mouser Search API](https://www.mouser.com/api-search/)
