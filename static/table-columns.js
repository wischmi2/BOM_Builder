(function () {
    const MIN_WIDTH = 48;
    const STORAGE_PREFIX = "bom-table-cols-pct-v3-";

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

    function headerColumns(table) {
        return Array.from(table.querySelectorAll("thead th")).filter((th) => th.colSpan <= 1);
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

    function colId(th, index) {
        return th.dataset.col || `col-${index}`;
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

    function initTable(table) {
        const tableId = table.id;
        if (!tableId || table.dataset.resizable === "false") return;

        table.classList.add("resizable-table");
        table.style.width = "100%";

        const headers = headerColumns(table);
        if (!headers.length) return;

        const colgroup = ensureColgroup(table, headers.length);
        let rows = rowsFromStorage(loadPercents(tableId), headers);
        if (!rows) rows = defaultRows(headers);
        normalizeMinWidths(headers, rows);
        applyRows(colgroup, rows);

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

        return { table, colgroup, headers, rows, tableId };
    }

    const tableState = [];

    function initAll() {
        tableState.length = 0;
        document.querySelectorAll("table.data-table[id]").forEach((table) => {
            const state = initTable(table);
            if (state) tableState.push(state);
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
