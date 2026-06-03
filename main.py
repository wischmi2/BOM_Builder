from __future__ import annotations

import argparse
import os
import webbrowser
from threading import Timer
from urllib.parse import urlencode

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from bom_builder import storage
from bom_builder.inventory_io import (
    add_item,
    delete_item,
    find_item,
    inventory_stats,
    inventory_to_csv,
    merge_import,
    parse_inventory_csv,
    update_item,
)
from bom_builder.matcher import (
    compare_aggregated_to_csv,
    compare_boms,
    compare_boms_aggregated,
    compare_summary,
    compare_summary_aggregated,
    compare_to_csv,
)
from bom_builder.label_scan import LabelScanError, scan_label_image
from bom_builder.category_overrides import (
    group_aggregated_rows,
    group_compare_rows,
    group_inventory_items,
    load_overrides,
    set_override,
)
from bom_builder.part_categories import CATEGORY_ORDER
from bom_builder.need_io import bom_stats, bom_to_csv, find_line, line_total_quantity, merge_bom_state
from bom_builder.parser import bom_id_from_filename, parse_bom_csv

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.secret_key = os.environ.get("BOM_BUILDER_SECRET", "bom-builder-local-dev")


@app.template_filter("inventory_auto_category")
def inventory_auto_category_filter(item) -> str:
    from bom_builder.part_categories import category_for_inventory_item

    return category_for_inventory_item(item)


@app.template_filter("inventory_part_key")
def inventory_part_key_filter(item) -> str:
    from bom_builder.category_overrides import part_key_for_inventory_item

    return part_key_for_inventory_item(item)


@app.template_filter("compare_auto_category")
def compare_auto_category_filter(row) -> str:
    from bom_builder.part_categories import (
        category_for_aggregated_row,
        category_for_compare_row,
    )

    if hasattr(row, "aggregate_key"):
        return category_for_aggregated_row(row)
    return category_for_compare_row(row)


@app.context_processor
def inject_nav():
    return {"bom_ids": storage.list_bom_ids()}


@app.route("/")
def index():
    return redirect(url_for("need_page"))


@app.route("/need")
def need_page():
    bom_ids = storage.list_bom_ids()
    active_bom_id = request.args.get("bom_id") or (bom_ids[0] if bom_ids else None)
    bom = storage.load_bom(active_bom_id) if active_bom_id else None
    stats = bom_stats(bom) if bom else None
    return render_template(
        "need.html",
        bom_ids=bom_ids,
        active_bom_id=active_bom_id,
        bom=bom,
        stats=stats,
    )


@app.route("/need/upload", methods=["POST"])
def need_upload():
    uploaded = request.files.get("bom_file")
    if not uploaded or not uploaded.filename:
        flash("Choose a CSV file to upload.", "error")
        return redirect(url_for("need_page"))

    filename = uploaded.filename
    bom_id = bom_id_from_filename(filename)
    try:
        content = uploaded.read()
        incoming = parse_bom_csv(content, bom_id=bom_id, source_filename=filename)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("need_page"))

    existing = storage.load_bom(bom_id)
    bom = merge_bom_state(existing, incoming)
    storage.save_bom(bom)
    flash(f"Imported {len(bom.lines)} lines from {filename}.", "success")
    return redirect(url_for("need_page", bom_id=bom_id))


@app.route("/need/<bom_id>/boards", methods=["POST"])
def need_update_boards(bom_id: str):
    bom = storage.load_bom(bom_id)
    if bom is None:
        abort(404)

    payload = request.get_json(silent=True) or request.form
    try:
        board_count = max(1, int(payload.get("board_count", 1) or 1))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Board count must be a positive number."}), 400

    bom.board_count = board_count
    storage.save_bom(bom)
    stats = bom_stats(bom)

    if request.accept_mimetypes.best == "application/json" or request.is_json:
        return jsonify(
            {
                "ok": True,
                "board_count": board_count,
                "stats": stats,
                "line_totals": {
                    line.id: line_total_quantity(line, board_count) for line in bom.lines
                },
            }
        )

    return redirect(url_for("need_page", bom_id=bom_id))


@app.route("/need/<bom_id>/line/<line_id>", methods=["POST"])
def need_update_line(bom_id: str, line_id: str):
    bom = storage.load_bom(bom_id)
    if bom is None:
        abort(404)

    line = find_line(bom, line_id)
    if line is None:
        abort(404)

    payload = request.get_json(silent=True) or request.form
    if "acquired" in payload:
        raw = payload.get("acquired")
        line.acquired = raw in (True, "true", "on", "1", 1)
    if "notes" in payload:
        line.notes = str(payload.get("notes", ""))

    storage.save_bom(bom)
    stats = bom_stats(bom)

    if request.accept_mimetypes.best == "application/json" or request.is_json:
        return jsonify(
            {
                "ok": True,
                "line_id": line_id,
                "acquired": line.acquired,
                "notes": line.notes,
                "stats": stats,
            }
        )

    return redirect(url_for("need_page", bom_id=bom_id))


@app.route("/need/<bom_id>/export.csv")
def need_export(bom_id: str):
    bom = storage.load_bom(bom_id)
    if bom is None:
        abort(404)

    response = make_response(bom_to_csv(bom))
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{bom_id}_need.csv"'
    return response


@app.route("/need/<bom_id>/delete", methods=["POST"])
def need_delete(bom_id: str):
    storage.delete_bom(bom_id)
    flash(f"Removed BOM {bom_id}.", "success")
    return redirect(url_for("need_page"))


@app.route("/inventory")
def inventory_page():
    doc = storage.load_inventory()
    stats = inventory_stats(doc)
    search = (request.args.get("q") or "").strip().lower()
    items = doc.items
    if search:
        items = [
            item
            for item in items
            if search in " ".join(
                [item.lib_ref, item.name, item.location, item.notes]
            ).lower()
        ]
    category_overrides = load_overrides()
    grouped_items = group_inventory_items(items, category_overrides)
    return render_template(
        "inventory.html",
        items=items,
        grouped_items=grouped_items,
        stats=stats,
        search=search,
        category_overrides=category_overrides,
    )


@app.route("/inventory/scan-label", methods=["POST"])
def inventory_scan_label():
    uploaded = request.files.get("label_image")
    if not uploaded or not uploaded.filename:
        return jsonify({"ok": False, "error": "Choose a photo of the part label."}), 400

    allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in allowed:
        return jsonify({"ok": False, "error": "Unsupported image type. Use JPG or PNG."}), 400

    try:
        result = scan_label_image(uploaded.read())
    except LabelScanError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    payload = result.to_dict()
    payload["ok"] = True
    return jsonify(payload)


@app.route("/inventory/add", methods=["POST"])
def inventory_add():
    doc = storage.load_inventory()
    try:
        qty = int(request.form.get("qty_on_hand", 0) or 0)
    except ValueError:
        qty = 0
    try:
        add_item(
            doc,
            lib_ref=request.form.get("lib_ref", ""),
            name=request.form.get("name", ""),
            qty_on_hand=qty,
            location=request.form.get("location", ""),
            notes=request.form.get("notes", ""),
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("inventory_page"))

    storage.save_inventory(doc)
    flash("Part added to inventory.", "success")
    return redirect(url_for("inventory_page"))


@app.route("/inventory/<item_id>", methods=["POST"])
def inventory_update(item_id: str):
    doc = storage.load_inventory()
    item = find_item(doc, item_id)
    if item is None:
        abort(404)

    payload = request.get_json(silent=True) or request.form
    if payload.get("action") == "delete":
        delete_item(doc, item_id)
        storage.save_inventory(doc)
        if request.accept_mimetypes.best == "application/json" or request.is_json:
            return jsonify({"ok": True, "deleted": True, "stats": inventory_stats(doc)})
        flash("Part removed from inventory.", "success")
        return redirect(url_for("inventory_page"))

    try:
        updates: dict = {}
        if "lib_ref" in payload:
            updates["lib_ref"] = str(payload.get("lib_ref", ""))
        if "name" in payload:
            updates["name"] = str(payload.get("name", ""))
        if "qty_on_hand" in payload:
            raw_qty = payload.get("qty_on_hand")
            if str(raw_qty).strip() != "":
                updates["qty_on_hand"] = int(raw_qty)
        if "location" in payload:
            updates["location"] = str(payload.get("location", ""))
        if "notes" in payload:
            updates["notes"] = str(payload.get("notes", ""))
        update_item(item, **updates)
    except ValueError as exc:
        if request.accept_mimetypes.best == "application/json" or request.is_json:
            return jsonify({"ok": False, "error": str(exc)}), 400
        flash(str(exc), "error")
        return redirect(url_for("inventory_page"))

    storage.save_inventory(doc)
    stats = inventory_stats(doc)

    if request.accept_mimetypes.best == "application/json" or request.is_json:
        return jsonify(
            {
                "ok": True,
                "item": item.to_dict(),
                "stats": stats,
            }
        )

    flash("Inventory updated.", "success")
    return redirect(url_for("inventory_page"))


@app.route("/inventory/import", methods=["POST"])
def inventory_import():
    uploaded = request.files.get("inventory_file")
    if not uploaded or not uploaded.filename:
        flash("Choose a CSV file to import.", "error")
        return redirect(url_for("inventory_page"))

    try:
        rows = parse_inventory_csv(uploaded.read())
        if not rows:
            flash("No valid rows found in CSV.", "error")
            return redirect(url_for("inventory_page"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("inventory_page"))

    doc = storage.load_inventory()
    added, updated = merge_import(doc, rows)
    storage.save_inventory(doc)
    flash(f"Imported inventory: {added} added, {updated} updated.", "success")
    return redirect(url_for("inventory_page"))


@app.route("/inventory/export.csv")
def inventory_export():
    doc = storage.load_inventory()
    response = make_response(inventory_to_csv(doc))
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="inventory.csv"'
    return response


def _selected_bom_ids() -> list[str]:
    ids = request.args.getlist("bom_id")
    if not ids and request.args.get("bom_ids"):
        ids = [part.strip() for part in request.args.get("bom_ids", "").split(",") if part.strip()]
    available = set(storage.list_bom_ids())
    return [bom_id for bom_id in ids if bom_id in available]


def _load_selected_boms(bom_ids: list[str]) -> list:
    boms = []
    for bom_id in bom_ids:
        bom = storage.load_bom(bom_id)
        if bom is not None:
            boms.append(bom)
    return boms


def _compare_view_mode(selected_ids: list[str]) -> str:
    view = request.args.get("view", "").strip()
    if view in ("combined", "per_board"):
        return view
    return "combined" if len(selected_ids) > 1 else "per_board"


@app.route("/compare")
def compare_page():
    bom_ids = storage.list_bom_ids()
    selected_ids = _selected_bom_ids()
    if not selected_ids and bom_ids:
        selected_ids = [bom_ids[0]]

    view_mode = _compare_view_mode(selected_ids)
    rows = []
    agg_rows = []
    grouped_rows = []
    extra = []
    summary = None
    pool_stats = None

    category_overrides = load_overrides()

    if selected_ids:
        boms = _load_selected_boms(selected_ids)
        inventory = storage.load_inventory()

        if view_mode == "combined":
            agg_rows, extra = compare_boms_aggregated(boms, inventory)
            grouped_rows = group_aggregated_rows(agg_rows, category_overrides)
            summary = compare_summary_aggregated(agg_rows)
            if agg_rows:
                pool_stats = {
                    "total_need_qty": sum(r.qty_needed_total for r in agg_rows if not r.is_dni),
                    "total_on_hand": sum(r.qty_on_hand for r in agg_rows),
                    "total_leftover": sum(r.leftover for r in agg_rows if not r.is_dni),
                    "boards": len(selected_ids),
                }
        else:
            rows, extra = compare_boms(boms, inventory)
            grouped_rows = group_compare_rows(rows, category_overrides)
            summary = compare_summary(rows)

    export_url = None
    if selected_ids and (rows or agg_rows):
        params = [("bom_id", bom_id) for bom_id in selected_ids]
        params.append(("view", view_mode))
        export_url = f"{url_for('compare_export')}?{urlencode(params)}"

    return render_template(
        "compare.html",
        bom_ids=bom_ids,
        selected_ids=selected_ids,
        view_mode=view_mode,
        rows=rows,
        agg_rows=agg_rows,
        grouped_rows=grouped_rows,
        extra=extra,
        summary=summary,
        pool_stats=pool_stats,
        export_url=export_url,
        category_overrides=category_overrides,
        category_options=CATEGORY_ORDER,
    )


@app.route("/inventory/category-override", methods=["POST"])
@app.route("/compare/category-override", methods=["POST"])
def compare_category_override():
    payload = request.get_json(silent=True) or {}
    part_key = str(payload.get("part_key", "")).strip()
    category_id = payload.get("category_id")
    auto_category = payload.get("auto_category")

    if not part_key:
        return jsonify({"ok": False, "error": "Missing part key."}), 400

    try:
        if category_id is not None:
            category_id = str(category_id).strip()
        if auto_category is not None:
            auto_category = str(auto_category).strip()
        overrides = set_override(part_key, category_id, auto_category=auto_category)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify({"ok": True, "part_key": part_key, "overrides": overrides})


@app.route("/compare/export.csv")
def compare_export():
    selected_ids = _selected_bom_ids()
    if not selected_ids:
        flash("Select at least one BOM to export.", "error")
        return redirect(url_for("compare_page"))

    view_mode = _compare_view_mode(selected_ids)
    boms = _load_selected_boms(selected_ids)
    inventory = storage.load_inventory()

    if view_mode == "combined":
        agg_rows, _ = compare_boms_aggregated(boms, inventory)
        response = make_response(compare_aggregated_to_csv(agg_rows))
        filename = "compare_combined_gap_report.csv"
    else:
        rows, _ = compare_boms(boms, inventory)
        response = make_response(compare_to_csv(rows))
        filename = "compare_gap_report.csv"
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def main() -> None:
    parser = argparse.ArgumentParser(description="BOM Builder local web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser on start")
    args = parser.parse_args()

    storage.ensure_data_dirs()

    if not args.no_browser:
        Timer(1.0, lambda: webbrowser.open(f"http://{args.host}:{args.port}/")).start()

    print(f"BOM Builder running at http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=True, use_reloader=False)


if __name__ == "__main__":
    main()
