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

    const searchInput = document.getElementById("inventory-search");
    const emptyMsg = document.getElementById("inventory-empty");
    const expandAllBtn = document.getElementById("inventory-expand-all");
    const collapseAllBtn = document.getElementById("inventory-collapse-all");
    const overrideUrl = config.categoryOverrideUrl || "/compare/category-override";
    const collapseKey = "bom-builder-inventory-collapsed";

    let dataRows = Array.from(table.querySelectorAll("tbody tr.inventory-row"));
    let categoryHeaders = Array.from(table.querySelectorAll("tbody tr.category-header"));

    function rowsForCategory(categoryId) {
        return dataRows.filter((row) => row.dataset.categoryGroup === categoryId);
    }

    function headerForCategory(categoryId) {
        return categoryHeaders.find((h) => h.dataset.category === categoryId);
    }

    function updateCategoryCount(categoryId) {
        const header = headerForCategory(categoryId);
        if (!header) return;
        const countEl = header.querySelector(".category-count");
        if (!countEl) return;
        const visible = rowsForCategory(categoryId).filter((r) => !r.hidden).length;
        const total = rowsForCategory(categoryId).length;
        countEl.textContent = `(${visible === total ? total : visible + "/" + total})`;
    }

    function isCategoryCollapsed(categoryId) {
        try {
            const collapsed = JSON.parse(sessionStorage.getItem(collapseKey) || "{}");
            return Boolean(collapsed[categoryId]);
        } catch {
            return false;
        }
    }

    function setCategoryCollapsed(categoryId, collapsed) {
        let state = {};
        try {
            state = JSON.parse(sessionStorage.getItem(collapseKey) || "{}");
        } catch {
            state = {};
        }
        if (collapsed) {
            state[categoryId] = true;
        } else {
            delete state[categoryId];
        }
        sessionStorage.setItem(collapseKey, JSON.stringify(state));
    }

    function applyCategoryCollapse(categoryId, collapsed) {
        const header = headerForCategory(categoryId);
        const toggle = header?.querySelector(".category-toggle");
        if (header) {
            header.classList.toggle("is-collapsed", collapsed);
        }
        if (toggle) {
            toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
        }
        rowsForCategory(categoryId).forEach((row) => {
            row.classList.toggle("category-collapsed", collapsed);
        });
    }

    function initCollapseState() {
        categoryHeaders.forEach((header) => {
            applyCategoryCollapse(header.dataset.category, isCategoryCollapsed(header.dataset.category));
        });
    }

    function setAllCategoriesCollapsed(collapsed) {
        categoryHeaders.forEach((header) => {
            const categoryId = header.dataset.category;
            setCategoryCollapsed(categoryId, collapsed);
            applyCategoryCollapse(categoryId, collapsed);
        });
    }

    function applySearchFilter() {
        const query = (searchInput?.value || "").trim().toLowerCase();
        let visible = 0;

        dataRows.forEach((row) => {
            const searchHay = row.dataset.search || "";
            const show = !query || searchHay.includes(query);
            row.hidden = !show;
            if (show) visible += 1;
        });

        categoryHeaders.forEach((header) => {
            const categoryId = header.dataset.category;
            const hasVisible = rowsForCategory(categoryId).some((row) => !row.hidden);
            header.hidden = !hasVisible;
            updateCategoryCount(categoryId);
        });

        if (emptyMsg) emptyMsg.hidden = visible > 0;
    }

    function insertRowIntoCategory(row, targetCategoryId) {
        const header = headerForCategory(targetCategoryId);
        if (!header) return;

        const oldCategory = row.dataset.categoryGroup;
        row.dataset.categoryGroup = targetCategoryId;

        let insertAfter = header;
        let next = header.nextElementSibling;
        while (next && !next.classList.contains("category-header")) {
            if (next !== row && next.classList.contains("inventory-row") && next.dataset.categoryGroup === targetCategoryId) {
                insertAfter = next;
            }
            next = next.nextElementSibling;
        }
        insertAfter.parentNode.insertBefore(row, insertAfter.nextElementSibling);

        if (oldCategory && oldCategory !== targetCategoryId) {
            updateCategoryCount(oldCategory);
        }
        updateCategoryCount(targetCategoryId);
    }

    async function saveCategoryOverride(row, targetCategoryId) {
        const response = await fetch(overrideUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                part_key: row.dataset.partKey,
                category_id: targetCategoryId,
                auto_category: row.dataset.autoCategory,
            }),
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
            throw new Error(payload.error || "Could not save category.");
        }
    }

    function setupDragAndDrop() {
        let draggedRow = null;

        dataRows.forEach((row) => {
            row.addEventListener("dragstart", (event) => {
                draggedRow = row;
                row.classList.add("is-dragging");
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", row.dataset.partKey || "");
            });

            row.addEventListener("dragend", () => {
                row.classList.remove("is-dragging");
                categoryHeaders.forEach((header) => header.classList.remove("drop-target-active"));
                draggedRow = null;
            });
        });

        categoryHeaders.forEach((header) => {
            header.addEventListener("dragover", (event) => {
                if (!draggedRow) return;
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
                header.classList.add("drop-target-active");
            });

            header.addEventListener("dragleave", () => {
                header.classList.remove("drop-target-active");
            });

            header.addEventListener("drop", async (event) => {
                event.preventDefault();
                header.classList.remove("drop-target-active");
                if (!draggedRow) return;

                const targetCategory = header.dataset.category;
                if (!targetCategory || draggedRow.dataset.categoryGroup === targetCategory) {
                    return;
                }

                const previousCategory = draggedRow.dataset.categoryGroup;
                insertRowIntoCategory(draggedRow, targetCategory);

                try {
                    await saveCategoryOverride(draggedRow, targetCategory);
                } catch (err) {
                    insertRowIntoCategory(draggedRow, previousCategory);
                    window.alert(err.message || "Could not save category.");
                }
            });
        });
    }

    function setupCollapseToggles() {
        categoryHeaders.forEach((header) => {
            const toggle = header.querySelector(".category-toggle");
            const categoryId = header.dataset.category;
            toggle?.addEventListener("click", (event) => {
                event.stopPropagation();
                const collapsed = !header.classList.contains("is-collapsed");
                setCategoryCollapsed(categoryId, collapsed);
                applyCategoryCollapse(categoryId, collapsed);
            });
        });

        expandAllBtn?.addEventListener("click", () => setAllCategoriesCollapsed(false));
        collapseAllBtn?.addEventListener("click", () => setAllCategoriesCollapsed(true));
    }

    searchInput?.addEventListener("input", applySearchFilter);
    initCollapseState();
    setupCollapseToggles();
    setupDragAndDrop();
    applySearchFilter();

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
                const categoryId = row.dataset.categoryGroup;
                row.remove();
                dataRows = Array.from(table.querySelectorAll("tbody tr.inventory-row"));
                updateCategoryCount(categoryId);
                applySearchFilter();
                updateStats(result.stats);
                if (!document.querySelector("#inventory-table tbody tr.inventory-row")) {
                    window.location.reload();
                }
            } catch {
                alert("Could not delete. Is the server still running?");
            }
        });
    });
})();
