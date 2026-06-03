from __future__ import annotations

import argparse
import webbrowser
from threading import Timer

from flask import Flask, redirect, render_template, url_for

from bom_builder import storage

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


@app.context_processor
def inject_nav():
    return {"bom_ids": storage.list_bom_ids()}


@app.route("/")
def index():
    return redirect(url_for("need_page"))


@app.route("/need")
def need_page():
    return render_template("need.html")


@app.route("/inventory")
def inventory_page():
    return render_template("inventory.html")


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
