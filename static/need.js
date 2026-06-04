(function () {
    const config = window.BOM_BUILDER;
    if (!config) return;

    const table = document.getElementById("need-table");
    const searchInput = document.getElementById("search-input");
    const hideDni = document.getElementById("hide-dni");
    const onlyMissing = document.getElementById("only-missing");
    const emptyFilter = document.getElementById("empty-filter");
    const progressText = document.getElementById("progress-text");
    const progressFill = document.getElementById("progress-fill");
    const boardCountInput = document.getElementById("board-count");
    const qtySummary = document.getElementById("qty-summary");
    const expandAllBtn = document.getElementById("need-expand-all");
    const collapseAllBtn = document.getElementById("need-collapse-all");
    const collapseKey = "bom-builder-need-collapsed";

    if (!table) return;

    const rows = Array.from(table.querySelectorAll("tbody tr.need-row"));
    const categoryHeaders = Array.from(table.querySelectorAll("tbody tr.category-header"));

    function rowsForCategory(categoryId) {
        return rows.filter((row) => row.dataset.categoryGroup === categoryId);
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
        if (collapsed) state[categoryId] = true;
        else delete state[categoryId];
        sessionStorage.setItem(collapseKey, JSON.stringify(state));
    }

    function applyCategoryCollapse(categoryId, collapsed) {
        const header = headerForCategory(categoryId);
        const toggle = header?.querySelector(".category-toggle");
        if (header) header.classList.toggle("is-collapsed", collapsed);
        if (toggle) toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
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

    categoryHeaders.forEach((header) => {
        header.querySelector(".category-toggle")?.addEventListener("click", () => {
            const categoryId = header.dataset.category;
            const next = !header.classList.contains("is-collapsed");
            setCategoryCollapsed(categoryId, next);
            applyCategoryCollapse(categoryId, next);
        });
    });

    expandAllBtn?.addEventListener("click", () => setAllCategoriesCollapsed(false));
    collapseAllBtn?.addEventListener("click", () => setAllCategoriesCollapsed(true));

    function lineUrl(lineId) {
        return config.updateUrlTemplate.replace("__LINE_ID__", encodeURIComponent(lineId));
    }

    function updateProgress(stats) {
        if (!stats || !progressText || !progressFill) return;
        const pct = stats.total ? Math.round((100 * stats.acquired) / stats.total) : 0;
        let suffix = "";
        if (stats.dni) suffix = ` (${stats.dni} DNI)`;
        progressText.innerHTML =
            `${stats.acquired} / ${stats.total} acquired` +
            (suffix ? `<span class="muted">${suffix}</span>` : "");
        progressFill.style.width = `${pct}%`;
        if (qtySummary && stats.qty_per_board !== undefined) {
            qtySummary.innerHTML =
                `${stats.qty_per_board} parts per board × ${stats.board_count} boards = <strong>${stats.qty_total}</strong> total`;
        }
    }

    function updateLineTotals(boardCount) {
        const boards = Math.max(1, boardCount);
        rows.forEach((row) => {
            const totalCell = row.querySelector(".qty-total");
            const perBoard = parseInt(totalCell?.dataset.perBoard || "0", 10) || 0;
            if (totalCell) {
                totalCell.textContent = String(perBoard * boards);
            }
        });
    }

    async function patchLine(lineId, body) {
        const response = await fetch(lineUrl(lineId), {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify(body),
        });
        if (!response.ok) throw new Error("Update failed");
        return response.json();
    }

    function applyFilters() {
        const query = (searchInput?.value || "").trim().toLowerCase();
        const skipDni = hideDni?.checked ?? false;
        const missingOnly = onlyMissing?.checked ?? false;
        let visible = 0;

        rows.forEach((row) => {
            const isDni = row.dataset.isDni === "1";
            const acquired = row.dataset.acquired === "1";
            const searchHay = row.dataset.search || "";

            let show = true;
            if (skipDni && isDni) show = false;
            if (missingOnly && acquired) show = false;
            if (query && !searchHay.includes(query)) show = false;

            row.hidden = !show;
            if (show) visible += 1;
        });

        categoryHeaders.forEach((header) => {
            const categoryId = header.dataset.category;
            const hasVisible = rowsForCategory(categoryId).some((row) => !row.hidden);
            header.hidden = !hasVisible;
            updateCategoryCount(categoryId);
        });

        if (emptyFilter) emptyFilter.hidden = visible > 0;
    }

    rows.forEach((row) => {
        const lineId = row.dataset.lineId;
        const checkbox = row.querySelector(".acquired-check");
        const librefInput = row.querySelector(".libref-input");
        const notesInput = row.querySelector(".notes-input");
        const applyMpnBtn = row.querySelector(".apply-mpn-xref");

        checkbox?.addEventListener("change", async () => {
            const acquired = checkbox.checked;
            try {
                const result = await patchLine(lineId, { acquired });
                row.dataset.acquired = acquired ? "1" : "0";
                row.classList.toggle("row-acquired", acquired);
                updateProgress(result.stats);
                applyFilters();
            } catch {
                checkbox.checked = !acquired;
                alert("Could not save. Is the server still running?");
            }
        });

        async function saveLibRef(value) {
            const libRef = value.trim();
            if (!libRef) {
                alert("MPN (LibRef) cannot be empty.");
                return;
            }
            try {
                const result = await patchLine(lineId, { lib_ref: libRef });
                if (librefInput) {
                    librefInput.value = result.lib_ref || libRef;
                    librefInput.defaultValue = librefInput.value;
                }
                applyMpnBtn?.closest(".mpn-xref")?.remove();
                const searchParts = [
                    row.querySelector(".cell-primary")?.textContent,
                    librefInput?.value,
                    row.querySelector(".col-designators")?.textContent,
                    row.querySelector(".col-footprint")?.textContent,
                ];
                row.dataset.search = searchParts.filter(Boolean).join(" ").toLowerCase();
                applyFilters();
            } catch {
                alert("Could not save MPN. Is the server still running?");
            }
        }

        applyMpnBtn?.addEventListener("click", () => {
            const suggested = applyMpnBtn.dataset.suggested || "";
            if (!suggested || !librefInput) return;
            librefInput.value = suggested;
            saveLibRef(suggested);
        });

        librefInput?.addEventListener("blur", () => {
            const current = librefInput.value.trim();
            const original = librefInput.defaultValue.trim();
            if (current && current !== original) {
                saveLibRef(current);
                librefInput.defaultValue = current;
            }
        });

        let notesTimer;
        notesInput?.addEventListener("input", () => {
            clearTimeout(notesTimer);
            notesTimer = setTimeout(async () => {
                try {
                    await patchLine(lineId, { notes: notesInput.value });
                } catch {
                    /* silent debounce failure */
                }
            }, 400);
        });
    });

    let boardTimer;
    boardCountInput?.addEventListener("input", () => {
        clearTimeout(boardTimer);
        boardTimer = setTimeout(async () => {
            const raw = parseInt(boardCountInput.value, 10);
            const boardCount = Number.isFinite(raw) && raw >= 1 ? raw : 1;
            try {
                const response = await fetch(config.boardsUrl, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", Accept: "application/json" },
                    body: JSON.stringify({ board_count: boardCount }),
                });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || "Update failed");
                }
                boardCountInput.value = String(result.board_count);
                config.boardCount = result.board_count;
                updateLineTotals(result.board_count);
                updateProgress(result.stats);
            } catch (err) {
                boardCountInput.value = String(config.boardCount || 1);
                alert(err.message || "Could not save board count.");
            }
        }, 400);
    });

    searchInput?.addEventListener("input", applyFilters);
    hideDni?.addEventListener("change", applyFilters);
    onlyMissing?.addEventListener("change", applyFilters);

    document.querySelectorAll("form[data-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            const message = form.getAttribute("data-confirm");
            if (message && !window.confirm(message)) event.preventDefault();
        });
    });

    initCollapseState();
    applyFilters();
})();
