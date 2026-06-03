(function () {
    const table = document.getElementById("compare-table");
    if (!table) return;

    const searchInput = document.getElementById("compare-search");
    const filterMissing = document.getElementById("filter-missing");
    const filterPartial = document.getElementById("filter-partial");
    const filterHideOk = document.getElementById("filter-hide-ok");
    const filterHideDni = document.getElementById("filter-hide-dni");
    const emptyMsg = document.getElementById("compare-empty");
    const rows = Array.from(table.querySelectorAll("tbody tr.compare-row"));

    function applyFilters() {
        const query = (searchInput?.value || "").trim().toLowerCase();
        const missingOnly = filterMissing?.checked ?? false;
        const partialOnly = filterPartial?.checked ?? false;
        const hideOk = filterHideOk?.checked ?? false;
        const hideDni = filterHideDni?.checked ?? false;
        let visible = 0;

        rows.forEach((row) => {
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

        if (emptyMsg) emptyMsg.hidden = visible > 0;
    }

    [searchInput, filterMissing, filterPartial, filterHideOk, filterHideDni].forEach((el) => {
        el?.addEventListener("input", applyFilters);
        el?.addEventListener("change", applyFilters);
    });

    applyFilters();
})();
