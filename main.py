from __future__ import annotations

import argparse
import webbrowser
from threading import Timer

from flask import (
    Flask,
    abort,
    flash,
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
from bom_builder.need_io import bom_stats, bom_to_csv, find_line, merge_bom_state
from bom_builder.parser import bom_id_from_filename, parse_bom_csv

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.secret_key = "bom-builder-local-dev"


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
        from flask import jsonify

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
    items = sorted(items, key=lambda i: (i.lib_ref.upper(), i.location.upper()))
    return render_template(
        "inventory.html",
        items=items,
        stats=stats,
        search=search,
    )


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
            from flask import jsonify

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
            updates["qty_on_hand"] = int(payload.get("qty_on_hand", 0) or 0)
        if "location" in payload:
            updates["location"] = str(payload.get("location", ""))
        if "notes" in payload:
            updates["notes"] = str(payload.get("notes", ""))
        update_item(item, **updates)
    except ValueError as exc:
        if request.accept_mimetypes.best == "application/json" or request.is_json:
            from flask import jsonify

            return jsonify({"ok": False, "error": str(exc)}), 400
        flash(str(exc), "error")
        return redirect(url_for("inventory_page"))

    storage.save_inventory(doc)
    stats = inventory_stats(doc)

    if request.accept_mimetypes.best == "application/json" or request.is_json:
        from flask import jsonify

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


@app.route("/compare")
def compare_page():
    return render_template("compare.html")


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
