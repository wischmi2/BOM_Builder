(function () {
    const MIN_WIDTH = 48;
    const STORAGE_PREFIX = "bom-table-cols-pct-v3-";
    const VISIBILITY_PREFIX = "bom-table-cols-vis-v1-";

    /** Relative column weights — normalized to 100% of table width. */
    const WEIGHTS = {
        check: 0.55,
        qty: 0.65,
        buy: 0.65,
        libref: 1.1,
        name: 1.5,
        status: 0.75,
        bom: 1.0,
        designators: 1.35,
        footprint: 1.05,
        distributors: 2.0,
        notes: 1.35,
        actions: 0.7,
        drag: 0.35,
        alternate: 0.5,
        received: 1.1,
        match: 1,
        board: 0.95,
        location: 0.85,
        delta: 0.65,
        leftover: 0.65,
        onhand: 0.65,
        need: 0.6,
        total: 0.65,
    };

    /** Floor % so columns never collapse (fixes vertical letter stacking). */
    const MIN_PCT = {
        check: 3.5,
        qty: 4,
        buy: 4,
        libref: 7,
        name: 10,
        status: 5.5,
        bom: 8,
        designators: 8,
        footprint: 7,
        distributors: 14,
        notes: 10,
        actions: 6,
        drag: 3,
        alternate: 3.5,
        received: 8,
        match: 7,
        board: 7,
        location: 6,
        delta: 4,
        leftover: 4,
        onhand: 4,
        need: 4,
        total: 4,
    };

    function loadPercents(tableId) {
        try {
            return JSON.parse(localStorage.getItem(STORAGE_PREFIX + tableId) || "null");
        } catch {
            return null;
        }
    }

    function savePercents(tableId, rows) {
        const map = {};
        rows.forEach((row) => {
            map[row.id] = Math.round(row.pct * 100) / 100;
        });
        localStorage.setItem(STORAGE_PREFIX + tableId, JSON.stringify(map));
    }

    function loadVisibility(tableId) {
        try {
            return JSON.parse(localStorage.getItem(VISIBILITY_PREFIX + tableId) || "null");
        } catch {
            return null;
        }
    }

    function saveVisibility(tableId, map) {
        localStorage.setItem(VISIBILITY_PREFIX + tableId, JSON.stringify(map));
    }

    function headerColumns(table) {
        return Array.from(table.querySelectorAll("thead th")).filter((th) => th.colSpan <= 1);
    }

    function visibleHeaderColumns(table) {
        return headerColumns(table).filter((th) => !th.classList.contains("col-hidden"));
    }

    function colId(th, index) {
        return th.dataset.col || `col-${index}`;
    }

    function columnLabel(th) {
        const text = th.textContent.replace(/\s+/g, " ").trim();
        if (text) return text;
        return th.getAttribute("aria-label") || th.dataset.col || "Column";
    }

    function ensureColgroup(table, count) {
        let colgroup = table.querySelector("colgroup");
        if (!colgroup) {
            colgroup = document.createElement("colgroup");
            for (let i = 0; i < count; i += 1) {
                colgroup.appendChild(document.createElement("col"));
            }
            table.insertBefore(colgroup, table.firstChild);
        }
        while (colgroup.children.length < count) {
            colgroup.appendChild(document.createElement("col"));
        }
        while (colgroup.children.length > count) {
            colgroup.removeChild(colgroup.lastChild);
        }
        return colgroup;
    }

    function defaultRows(headers) {
        const weights = headers.map((th, index) => WEIGHTS[colId(th, index)] || 1);
        const sum = weights.reduce((acc, w) => acc + w, 0);
        return headers.map((th, index) => ({
            id: colId(th, index),
            pct: (weights[index] / sum) * 100,
        }));
    }

    function rowsFromStorage(saved, headers) {
        if (!saved || typeof saved !== "object") return null;
        const rows = headers.map((th, index) => {
            const id = colId(th, index);
            const pct = saved[id];
            if (typeof pct !== "number" || pct <= 0) return null;
            return { id, pct };
        });
        if (rows.some((row) => row === null)) return null;
        const sum = rows.reduce((acc, row) => acc + row.pct, 0);
        if (sum <= 0) return null;
        return rows.map((row) => ({ id: row.id, pct: (row.pct / sum) * 100 }));
    }

    function normalizeMinWidths(headers, rows) {
        const floors = headers.map((th, index) => MIN_PCT[colId(th, index)] ?? 4);
        let deficit = 0;

        rows.forEach((row, index) => {
            if (row.pct < floors[index]) {
                deficit += floors[index] - row.pct;
                row.pct = floors[index];
            }
        });

        if (deficit > 0) {
            const flexible = rows
                .map((row, index) => ({ index, slack: row.pct - floors[index] }))
                .filter((entry) => entry.slack > 0.15);
            const totalSlack = flexible.reduce((sum, entry) => sum + entry.slack, 0);
            if (totalSlack > 0) {
                flexible.forEach((entry) => {
                    rows[entry.index].pct -= (entry.slack / totalSlack) * deficit;
                });
            }
        }

        const sum = rows.reduce((acc, row) => acc + row.pct, 0);
        if (sum > 0) {
            rows.forEach((row) => {
                row.pct = (row.pct / sum) * 100;
            });
        }
    }

    function applyRows(colgroup, rows) {
        const cols = colgroup.querySelectorAll("col");
        rows.forEach((row, index) => {
            if (cols[index]) cols[index].style.width = `${row.pct}%`;
        });
    }

    function minPercent(table) {
        const w = table.getBoundingClientRect().width || table.offsetWidth || 800;
        return (MIN_WIDTH / w) * 100;
    }

    function startResize(event, table, colgroup, index, headers, rows, tableId) {
        event.preventDefault();
        event.stopPropagation();

        const tableWidth = table.getBoundingClientRect().width;
        if (tableWidth <= 0) return;

        const startX = event.clientX;
        const startPct = rows.map((row) => row.pct);
        const minPct = minPercent(table);
        const partner = index < headers.length - 1 ? index + 1 : index - 1;
        if (partner < 0) return;

        document.body.classList.add("col-resize-active");

        function onMove(moveEvent) {
            const deltaPct = ((moveEvent.clientX - startX) / tableWidth) * 100;
            const next = startPct.slice();

            let a = next[index] + deltaPct;
            let b = next[partner] - deltaPct;

            if (a < minPct) {
                b -= minPct - a;
                a = minPct;
            }
            if (b < minPct) {
                a -= minPct - b;
                b = minPct;
            }

            next[index] = Math.max(minPct, a);
            next[partner] = Math.max(minPct, b);

            const pairStart = startPct[index] + startPct[partner];
            const pairNext = next[index] + next[partner];
            const fix = pairStart - pairNext;
            if (Math.abs(fix) > 0.01) {
                next[index] += fix / 2;
                next[partner] += fix / 2;
            }

            rows.forEach((row, i) => {
                row.pct = next[i];
            });
            normalizeMinWidths(headers, rows);
            applyRows(colgroup, rows);
        }

        function onUp() {
            document.body.classList.remove("col-resize-active");
            savePercents(tableId, rows);
            document.removeEventListener("mousemove", onMove);
            document.removeEventListener("mouseup", onUp);
        }

        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
    }

    function setColumnVisible(table, index, visible) {
        table.querySelectorAll("thead tr, tbody tr").forEach((row) => {
            const cell = row.children[index];
            if (cell) cell.classList.toggle("col-hidden", !visible);
        });
    }

    function updateCategoryColspans(table) {
        const count = visibleHeaderColumns(table).length;
        if (!count) return;
        table.querySelectorAll("tbody tr.category-header td[colspan]").forEach((td) => {
            td.colSpan = count;
        });
    }

    function defaultVisibilityMap(headers) {
        const map = {};
        headers.forEach((th, index) => {
            map[colId(th, index)] = true;
        });
        return map;
    }

    function mergeVisibilityMap(saved, headers) {
        const map = defaultVisibilityMap(headers);
        if (!saved || typeof saved !== "object") return map;
        headers.forEach((th, index) => {
            const id = colId(th, index);
            if (typeof saved[id] === "boolean") map[id] = saved[id];
        });
        return map;
    }

    function visibleCountFromMap(headers, visibilityMap) {
        return headers.reduce((count, th, index) => {
            const id = colId(th, index);
            return count + (visibilityMap[id] !== false ? 1 : 0);
        }, 0);
    }

    function applyVisibility(table, visibilityMap) {
        const headers = headerColumns(table);
        headers.forEach((th, index) => {
            const id = colId(th, index);
            setColumnVisible(table, index, visibilityMap[id] !== false);
        });
        updateCategoryColspans(table);
    }

    function bindResizeHandles(table, colgroup, headers, rows, tableId) {
        headers.forEach((th, index) => {
            th.classList.add("th-resizable");

            let handle = th.querySelector(".col-resize-handle");
            if (!handle) {
                handle = document.createElement("span");
                handle.className = "col-resize-handle";
                handle.title = "Drag to resize · double-click to reset all columns";
                handle.setAttribute("aria-hidden", "true");
                th.appendChild(handle);
            }

            handle.onmousedown = (event) => {
                startResize(event, table, colgroup, index, headers, rows, tableId);
            };
            handle.ondblclick = (event) => {
                event.preventDefault();
                event.stopPropagation();
                rows = defaultRows(headers);
                normalizeMinWidths(headers, rows);
                applyRows(colgroup, rows);
                savePercents(tableId, rows);
            };
        });
    }

    function initTable(table) {
        const tableId = table.id;
        if (!tableId || table.dataset.resizable === "false") return null;

        table.classList.add("resizable-table");
        table.style.width = "100%";

        const allHeaders = headerColumns(table);
        if (!allHeaders.length) return null;

        const visibilityMap = mergeVisibilityMap(loadVisibility(tableId), allHeaders);
        applyVisibility(table, visibilityMap);

        const headers = visibleHeaderColumns(table);
        if (!headers.length) {
            visibilityMap[colId(allHeaders[0], 0)] = true;
            saveVisibility(tableId, visibilityMap);
            applyVisibility(table, visibilityMap);
            headers.push(allHeaders[0]);
        }

        const colgroup = ensureColgroup(table, headers.length);
        let rows = rowsFromStorage(loadPercents(tableId), headers);
        if (!rows) rows = defaultRows(headers);
        normalizeMinWidths(headers, rows);
        applyRows(colgroup, rows);
        bindResizeHandles(table, colgroup, headers, rows, tableId);

        return { table, colgroup, headers, rows, tableId, visibilityMap };
    }

    const tableState = [];
    const pickerState = [];

    function closeAllPickers(except) {
        pickerState.forEach((entry) => {
            if (entry.root === except) return;
            entry.root.classList.remove("is-open");
            entry.button.setAttribute("aria-expanded", "false");
        });
    }

    function refreshTableLayout(tableId) {
        const index = tableState.findIndex((state) => state.tableId === tableId);
        if (index >= 0) {
            const { table } = tableState[index];
            table.querySelectorAll(".col-resize-handle").forEach((handle) => {
                handle.onmousedown = null;
                handle.ondblclick = null;
            });
            tableState.splice(index, 1);
        }
        const table = document.getElementById(tableId);
        if (!table) return;
        const state = initTable(table);
        if (state) tableState.push(state);
    }

    function buildColumnPicker(table) {
        const tableId = table.id;
        const slot =
            document.querySelector(`.table-col-picker-slot[data-table-id="${tableId}"]`) ||
            table.closest(".table-wrap")?.querySelector(".table-col-picker-slot");
        if (!slot) return;

        const headers = headerColumns(table);
        if (!headers.length) return;

        slot.innerHTML = "";
        slot.classList.add("table-col-picker-slot");

        const root = document.createElement("div");
        root.className = "table-col-picker";

        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-secondary btn-sm table-col-picker-btn";
        button.textContent = "Columns";
        button.setAttribute("aria-haspopup", "true");
        button.setAttribute("aria-expanded", "false");

        const menu = document.createElement("div");
        menu.className = "table-col-picker-menu";
        menu.hidden = true;

        const title = document.createElement("p");
        title.className = "table-col-picker-title";
        title.textContent = "Show or hide columns";
        menu.appendChild(title);

        const list = document.createElement("div");
        list.className = "table-col-picker-list";

        function renderChecks() {
            list.innerHTML = "";
            const visibilityMap = mergeVisibilityMap(loadVisibility(tableId), headers);
            const visibleCount = visibleCountFromMap(headers, visibilityMap);

            headers.forEach((th, index) => {
                const id = colId(th, index);
                const locked = th.dataset.colLocked === "true";
                const label = document.createElement("label");
                label.className = "table-col-picker-item";

                const input = document.createElement("input");
                input.type = "checkbox";
                input.checked = visibilityMap[id] !== false;
                input.disabled = locked || (input.checked && visibleCount <= 1);
                input.dataset.colId = id;

                input.addEventListener("change", () => {
                    const current = mergeVisibilityMap(loadVisibility(tableId), headers);
                    const nextVisible = visibleCountFromMap(headers, current);
                    if (!input.checked && nextVisible <= 1) {
                        input.checked = true;
                        return;
                    }
                    current[id] = input.checked;
                    saveVisibility(tableId, current);
                    applyVisibility(table, current);
                    refreshTableLayout(tableId);
                    renderChecks();
                });

                const text = document.createElement("span");
                text.textContent = columnLabel(th);

                label.appendChild(input);
                label.appendChild(text);
                list.appendChild(label);
            });
        }

        menu.appendChild(list);

        const actions = document.createElement("div");
        actions.className = "table-col-picker-actions";

        const showAllBtn = document.createElement("button");
        showAllBtn.type = "button";
        showAllBtn.className = "btn btn-secondary btn-sm";
        showAllBtn.textContent = "Show all";
        showAllBtn.addEventListener("click", () => {
            const map = defaultVisibilityMap(headers);
            saveVisibility(tableId, map);
            applyVisibility(table, map);
            refreshTableLayout(tableId);
            renderChecks();
        });

        actions.appendChild(showAllBtn);
        menu.appendChild(actions);

        button.addEventListener("click", (event) => {
            event.stopPropagation();
            const open = root.classList.toggle("is-open");
            menu.hidden = !open;
            button.setAttribute("aria-expanded", open ? "true" : "false");
            if (open) {
                closeAllPickers(root);
                renderChecks();
            }
        });

        root.appendChild(button);
        root.appendChild(menu);
        slot.appendChild(root);

        pickerState.push({ root, button, tableId });

        document.addEventListener("click", (event) => {
            if (!root.contains(event.target)) {
                root.classList.remove("is-open");
                menu.hidden = true;
                button.setAttribute("aria-expanded", "false");
            }
        });
    }

    function initAll() {
        tableState.length = 0;
        pickerState.length = 0;
        document.querySelectorAll("table.data-table[id]").forEach((table) => {
            const state = initTable(table);
            if (state) tableState.push(state);
            buildColumnPicker(table);
        });
    }

    let resizeTimer;
    window.addEventListener("resize", () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            tableState.forEach(({ table, colgroup, headers, rows }) => {
                normalizeMinWidths(headers, rows);
                applyRows(colgroup, rows);
            });
        }, 150);
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }
})();
