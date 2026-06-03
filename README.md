# BOM Builder

Local web app for bill-of-materials workflows: import BOM CSVs, track parts you need, maintain inventory, and compare need vs stock.

## Setup

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Run

```bash
.venv\Scripts\python main.py
```

Opens http://127.0.0.1:5000/ (use `--no-browser` to skip auto-open).

## Pages

- **Need** — Upload BOM CSV, check off acquired parts, search/filter, export CSV
- **Inventory** — Add/edit/delete stock, CSV import/export (merge by LibRef+Location)
- **Compare** — Need vs inventory gap report (Phase 4+)

## Tests

```bash
.venv\Scripts\python -m unittest tests.test_parser -v
```

## Data

Runtime JSON is stored under `data/` (gitignored). Re-import BOMs after clone.
