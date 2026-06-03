(function () {
    const config = window.BOM_SHOP;
    const table = document.getElementById("shop-table");
    if (!config || !table) return;

    const searchInput = document.getElementById("shop-search");
    const hideOrdered = document.getElementById("shop-hide-ordered");
    const emptyMsg = document.getElementById("shop-empty");
    const rows = Array.from(table.querySelectorAll("tbody tr.shop-row"));

    function lineUrl(lineId) {
        return config.updateUrlTemplate.replace("__LINE_ID__", encodeURIComponent(lineId));
    }

    async function patchLine(lineId, body) {
        const response = await fetch(lineUrl(lineId), {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify(body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) {
            throw new Error(data.error || "Could not save.");
        }
        return data;
    }

    function applyFilters() {
        const query = (searchInput?.value || "").trim().toLowerCase();
        const skipOrdered = hideOrdered?.checked ?? false;
        let visible = 0;

        rows.forEach((row) => {
            const ordered = row.dataset.ordered === "1";
            const searchHay = row.dataset.search || "";
            let show = true;
            if (skipOrdered && ordered) show = false;
            if (query && !searchHay.includes(query)) show = false;
            row.hidden = !show;
            if (show) visible += 1;
        });

        if (emptyMsg) emptyMsg.hidden = visible > 0;
    }

    rows.forEach((row) => {
        const lineId = row.dataset.lineId;
        const orderedCheck = row.querySelector(".ordered-check");
        const buyQtyInput = row.querySelector(".buy-qty-input");
        const notesInput = row.querySelector(".notes-input");

        let timer;
        function scheduleSave(body) {
            clearTimeout(timer);
            timer = setTimeout(async () => {
                try {
                    const result = await patchLine(lineId, body);
                    if ("ordered" in body) {
                        row.dataset.ordered = result.ordered ? "1" : "0";
                        row.classList.toggle("row-ordered", result.ordered);
                    }
                    applyFilters();
                } catch (err) {
                    alert(err.message || "Could not save. Is the server still running?");
                }
            }, 400);
        }

        orderedCheck?.addEventListener("change", () => {
            scheduleSave({ ordered: orderedCheck.checked });
        });

        buyQtyInput?.addEventListener("input", () => {
            const raw = parseInt(buyQtyInput.value, 10);
            const qty = Number.isFinite(raw) && raw >= 0 ? raw : 0;
            scheduleSave({ buy_qty: qty });
        });

        notesInput?.addEventListener("input", () => {
            scheduleSave({ notes: notesInput.value });
        });
    });

    searchInput?.addEventListener("input", applyFilters);
    hideOrdered?.addEventListener("change", applyFilters);
    applyFilters();
})();
