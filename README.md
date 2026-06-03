# BOM Builder

Local web app for bill-of-materials workflows: import BOM CSVs, track parts you still need, maintain inventory, and compare need vs stock.

**Repository:** https://github.com/wischmi2/BOM_Builder

## Requirements

- Python 3.11+
- Windows, macOS, or Linux

## Quick start

```bash
git clone https://github.com/wischmi2/BOM_Builder.git
cd BOM_Builder
python -m venv .venv

# Windows
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py

# macOS / Linux
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

Opens http://127.0.0.1:5000/ in your browser.

**Options:**

```bash
.venv\Scripts\python main.py --port 8080 --no-browser
```

## Workflow

```text
1. Need      → Upload Altium-style BOM CSV
2. Inventory → Add or import parts you have on hand
3. Compare   → Select BOM(s), see OK / partial / missing, export gap CSV
```

### 1. Need (BOM checklist)

Use this page when building or purchasing for a board.

1. Open **Need** and upload your BOM CSV (e.g. from Altium).
2. Review the table — check off lines as you **acquire** parts (ordered, on the bench, etc.).
3. Use search and filters (hide DNI, only not acquired).
4. **Export CSV** to share progress or open in Excel.

Re-uploading the same file keeps your checkmarks and notes.

**Expected BOM columns:**

| Column | Required | Notes |
|--------|----------|-------|
| Name | Yes | Part value / label |
| Description | No | Long description |
| Designator | Yes | Comma-separated refs (`C2, C4, C5`) |
| Footprint | Yes | Package |
| LibRef | Yes | MPN / library reference |
| Quantity | Yes | Integer |

### 2. Inventory (stock on hand)

Use this page for parts you already have, independent of any single BOM.

1. Open **Inventory** and add parts (LibRef required), or **Import CSV**.
2. **Scan part label** — upload a photo of a DigiKey-style reel bag; OCR fills MFR PN, description, and qty into the add form.
3. Edit quantities and locations inline — changes save automatically.
4. **Export CSV** for backup or editing in Excel.

**Label scan (OCR)** requires [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) on Windows. Run the installer (default location `C:\Program Files\Tesseract-OCR\` is fine — you do not need to change PATH). Then `pip install -r requirements.txt` and restart the app. Uses **MFR PN** for LibRef (best for BOM matching); DigiKey PN goes in Notes.

**Import columns:** `LibRef`, `Name`, `QtyOnHand`, `Location`, `Notes`

Rows with the same **LibRef + Location** are updated; new combinations are added.

### 3. Compare (need vs stock)

Use this page to see what you still need to pull from inventory or buy.

1. Open **Compare** and select one or more BOMs.
2. With multiple boards, use **Combined totals** (default) to sum the same MPN across all BOMs and compare once against inventory.
3. Use **Per board** for the original line-by-line view (each BOM row checked separately).
4. Filter to missing/partial lines; export **gap CSV** for purchasing.

**Matching rules:**

- Primary key: normalized **LibRef** / MPN
- Multi-MPN BOM lines (comma-separated LibRef): match if any MPN hits inventory
- Fallback: match by **Name** when LibRef does not match
- Quantities sum across inventory rows (multiple bins)
- **DNI** lines are labeled separately and excluded from “missing” counts by default

**Gap export columns:** LibRef, Name, NeedQty, OnHand, Delta, Status, BOM, Designators, MatchType, MatchedInventory

## Project layout

```text
BOM_Builder/
  main.py                 # Flask app entry point
  bom_builder/
    parser.py             # BOM CSV import
    need_io.py            # Need list merge + export
    inventory_io.py       # Inventory CRUD + CSV
    matcher.py            # Compare logic
    storage.py            # JSON persistence
    models.py             # Data classes
  templates/              # HTML pages
  static/                 # CSS + JS
  tests/
  data/                   # BOM + inventory JSON (tracked in git)
    needs/                # One JSON file per BOM
    inventory.json        # Stock list
```

## Data in Git

Imported BOMs and inventory are stored as JSON under `data/` and **committed to the repo** so they sync via GitHub:

- `data/needs/{bom_id}.json` — parsed BOM + acquired checkmarks and notes
- `data/inventory.json` — parts on hand

After importing or editing in the app, commit and push to update GitHub:

```bash
git add data/
git commit -m "Update BOM and inventory data"
git push
```

You can still use **Export CSV** on each page for Excel. Original uploaded CSV files are not kept—only the JSON.

## Tests

```bash
.venv\Scripts\python -m unittest discover -s tests -v
```

## Development notes

- Single-user local app; no authentication.
- Flask debug mode is enabled in `main.py` for local use only.
- CSV encoding: UTF-8 preferred; Windows-1252/latin-1 BOM files are supported on import.

## License

Private / internal use — add a license file if you plan to distribute.
