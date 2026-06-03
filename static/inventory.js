(function () {
    const config = window.BOM_INVENTORY;
    if (!config) return;

    const scanBtn = document.getElementById("scan-label-btn");
    const scanInput = document.getElementById("label-image");
    const scanStatus = document.getElementById("scan-status");
    const scanRawDetails = document.getElementById("scan-raw-details");
    const scanRawText = document.getElementById("scan-raw-text");

    function showScanStatus(message, isError) {
        if (!scanStatus) return;
        scanStatus.hidden = false;
        scanStatus.textContent = message;
        scanStatus.classList.toggle("flash-error", !!isError);
        scanStatus.classList.toggle("flash-success", !isError);
    }

    scanBtn?.addEventListener("click", async () => {
        const file = scanInput?.files?.[0];
        if (!file) {
            showScanStatus("Choose or take a photo first.", true);
            return;
        }
        scanBtn.disabled = true;
        showScanStatus("Reading label…", false);
        try {
            const body = new FormData();
            body.append("label_image", file);
            const response = await fetch(config.scanLabelUrl, {
                method: "POST",
                body,
            });
            const data = await response.json();
            if (!response.ok || !data.ok) {
                throw new Error(data.error || "Scan failed");
            }

            const libRef = document.getElementById("add-lib-ref");
            const name = document.getElementById("add-name");
            const qty = document.getElementById("add-qty");
            const location = document.getElementById("add-location");
            const notes = document.getElementById("add-notes");

            if (libRef && data.lib_ref) libRef.value = data.lib_ref;
            if (name && data.name) name.value = data.name;
            if (qty && data.qty_on_hand) qty.value = data.qty_on_hand;
            if (notes && data.notes) {
                notes.value = data.notes;
            }

            let msg = "Fields filled — review and click Add to inventory.";
            if (data.warnings?.length) {
                msg += " " + data.warnings.join(" ");
            }
            showScanStatus(msg, false);

            if (scanRawText && scanRawDetails && data.raw_text) {
                scanRawText.textContent = data.raw_text;
                scanRawDetails.hidden = false;
            }

            document.getElementById("inventory-add-form")?.scrollIntoView({ behavior: "smooth" });
        } catch (err) {
            showScanStatus(err.message || "Could not read label.", true);
        } finally {
            scanBtn.disabled = false;
        }
    });

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

    const table = document.querySelector("#inventory-table");
    if (!table) return;

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
