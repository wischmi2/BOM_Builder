(function () {
    const config = window.BOM_INVENTORY;
    if (!config) return;

    const statsEl = document.querySelector(".inventory-stats");

    function itemUrl(itemId) {
        return config.updateUrlTemplate.replace("__ITEM_ID__", encodeURIComponent(itemId));
    }

    function updateStats(stats) {
        if (!stats || !statsEl) return;
        const count = stats.part_count ?? stats.items ?? 0;
        statsEl.innerHTML =
            `<span><strong>${count}</strong> parts</span>` +
            `<span class="muted">·</span>` +
            `<span><strong>${stats.total_qty}</strong> total qty on hand</span>`;
    }

    async function patchItem(itemId, body) {
        const response = await fetch(itemUrl(itemId), {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify(body),
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || "Update failed");
        }
        return response.json();
    }

    document.querySelectorAll("#inventory-table tbody tr.inventory-row").forEach((row) => {
        const itemId = row.dataset.itemId;
        const libRef = row.querySelector(".lib-ref-input");
        const name = row.querySelector(".name-input");
        const qty = row.querySelector(".qty-input");
        const location = row.querySelector(".location-input");
        const notes = row.querySelector(".notes-input");
        const deleteBtn = row.querySelector(".delete-btn");

        let timer;
        function scheduleSave() {
            clearTimeout(timer);
            timer = setTimeout(async () => {
                try {
                    const body = {
                        lib_ref: libRef.value,
                        name: name.value,
                        location: location.value,
                        notes: notes.value,
                    };
                    const qtyRaw = qty.value.trim();
                    if (qtyRaw !== "") {
                        body.qty_on_hand = parseInt(qtyRaw, 10) || 0;
                    }
                    const result = await patchItem(itemId, body);
                    updateStats(result.stats);
                    if (result.item) {
                        qty.value = result.item.qty_on_hand;
                        qty.dataset.initialQty = String(result.item.qty_on_hand);
                    }
                } catch (err) {
                    alert(err.message || "Could not save. Is the server still running?");
                }
            }, 400);
        }

        [libRef, name, qty, location, notes].forEach((el) => {
            el?.addEventListener("input", scheduleSave);
            el?.addEventListener("change", scheduleSave);
        });

        deleteBtn?.addEventListener("click", async () => {
            if (!window.confirm("Remove this part from inventory?")) return;
            try {
                const result = await patchItem(itemId, { action: "delete" });
                row.remove();
                updateStats(result.stats);
                if (!document.querySelector("#inventory-table tbody tr")) {
                    window.location.reload();
                }
            } catch {
                alert("Could not delete. Is the server still running?");
            }
        });
    });
})();
