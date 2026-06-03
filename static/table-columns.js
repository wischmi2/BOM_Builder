(function () {
    const MIN_WIDTH = 48;
    const STORAGE_PREFIX = "bom-table-cols-pct-v2-";

    /** Relative weights — normalized to 100% of table width. */
    const WEIGHTS = {
        check: 0.55,
        qty: 0.65,
        buy: 0.65,
        libref: 1.1,
        name: 1.5,
        status: 0.75,
        bom: 1.05,
        designators: 1,
        distributors: 1.35,
        notes: 1.25,
        actions: 0.7,
        drag: 0.35,
        match: 1,
        board: 0.95,
        footprint: 0.85,
        location: 0.85,
        delta: 0.65,
        leftover: 0.65,
        onhand: 0.65,
        need: 0.6,
        total: 0.65,
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
                applyRows(colgroup, rows);
                savePercents(tableId, rows);
            };
        });
    }

    function initAll() {
        document.querySelectorAll("table.data-table[id]").forEach(initTable);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }
})();
