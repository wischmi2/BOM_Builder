(function () {
    const table = document.getElementById("compare-table");
    if (!table) return;

    const searchInput = document.getElementById("compare-search");
    const filterMissing = document.getElementById("filter-missing");
    const filterPartial = document.getElementById("filter-partial");
    const filterHideOk = document.getElementById("filter-hide-ok");
    const filterHideDni = document.getElementById("filter-hide-dni");
    const emptyMsg = document.getElementById("compare-empty");
    const expandAllBtn = document.getElementById("compare-expand-all");
    const collapseAllBtn = document.getElementById("compare-collapse-all");
    const overrideUrl = "/compare/category-override";
    const collapseKey = "bom-builder-compare-collapsed";

    let dataRows = Array.from(table.querySelectorAll("tbody tr.compare-row"));
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

    function updateAllCategoryCounts() {
        categoryHeaders.forEach((header) => updateCategoryCount(header.dataset.category));
    }

    function isCategoryCollapsed(categoryId) {
        const stored = sessionStorage.getItem(collapseKey);
        if (!stored) return false;
        try {
            const collapsed = JSON.parse(stored);
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
            const categoryId = header.dataset.category;
            applyCategoryCollapse(categoryId, isCategoryCollapsed(categoryId));
        });
    }

    function setAllCategoriesCollapsed(collapsed) {
        categoryHeaders.forEach((header) => {
            const categoryId = header.dataset.category;
            setCategoryCollapsed(categoryId, collapsed);
            applyCategoryCollapse(categoryId, collapsed);
        });
    }

    function applyFilters() {
        const query = (searchInput?.value || "").trim().toLowerCase();
        const missingOnly = filterMissing?.checked ?? false;
        const partialOnly = filterPartial?.checked ?? false;
        const hideOk = filterHideOk?.checked ?? false;
        const hideDni = filterHideDni?.checked ?? false;
        let visible = 0;

        dataRows.forEach((row) => {
            const status = row.dataset.status;
            const searchHay = row.dataset.search || "";
            let show = true;

            if (missingOnly && status !== "missing") show = false;
            if (partialOnly && status !== "partial") show = false;
            if (hideOk && status === "ok") show = false;
            if (hideDni && status === "dni") show = false;
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
            if (next !== row && next.classList.contains("compare-row") && next.dataset.categoryGroup === targetCategoryId) {
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
        const partKey = row.dataset.partKey;
        const autoCategory = row.dataset.autoCategory;
        const response = await fetch(overrideUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                part_key: partKey,
                category_id: targetCategoryId,
                auto_category: autoCategory,
            }),
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
            throw new Error(payload.error || "Could not save category.");
        }
        return payload;
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

    [searchInput, filterMissing, filterPartial, filterHideOk, filterHideDni].forEach((el) => {
        el?.addEventListener("input", applyFilters);
        el?.addEventListener("change", applyFilters);
    });

    initCollapseState();
    setupCollapseToggles();
    setupDragAndDrop();
    applyFilters();
})();
