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

- **Buy list state:** `data/shopping_list.json` (notes, ordered, buy qty overrides).
- **API cache:** `data/distributor_cache.json` (stock/price snapshots from lookups).

Both can be committed to git with other `data/` files for multi-PC sync.

## Phase 2 — API lookup (optional)

Search links work without keys. For live stock and pricing:

### 1. Register for APIs

| Distributor | Sign up | Credentials |
|-------------|---------|-------------|
| **DigiKey** | [developer.digikey.com](https://developer.digikey.com/) | OAuth2 client ID + secret |
| **Mouser** | [mouser.com/api-search](https://www.mouser.com/api-search/) | API key |

### 2. Configure environment

```powershell
cd C:\Users\Brian\PycharmProjects\BOM_Builder
copy .env.example .env
# Edit .env with your keys
pip install -r requirements.txt
python main.py
```

Variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DIGIKEY_CLIENT_ID` | For DigiKey lookup | API client ID |
| `DIGIKEY_CLIENT_SECRET` | For DigiKey lookup | API client secret |
| `DIGIKEY_USE_SANDBOX` | No | Set `1` to use DigiKey sandbox |
| `MOUSER_API_KEY` | For Mouser lookup | Mouser Search API key |

You can configure one or both distributors.

### 3. Use lookup on Shop

- **Lookup** on a row — fetch/cache that MPN (uses cache if fresh).
- **Lookup visible** — batch up to 25 visible lines (rate-limited).
- **Force refresh visible** — bypass cache and call APIs again.

Cached results show stock and unit price under the distributor buttons. Links update to product URLs when the API returns them.

### Rate limits

- Mouser: ~30 calls/min — the app waits ~2s between Mouser calls in a batch.
- DigiKey: account limits apply — use batch lookup sparingly on large lists.

### Without API keys

The Shop page still shows **DigiKey** / **Mouser** search links (Phase 1). No configuration required.
