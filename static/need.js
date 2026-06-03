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

    if (!table) return;

    const rows = Array.from(table.querySelectorAll("tbody tr.need-row"));

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

        if (emptyFilter) emptyFilter.hidden = visible > 0;
    }

    rows.forEach((row) => {
        const lineId = row.dataset.lineId;
        const checkbox = row.querySelector(".acquired-check");
        const notesInput = row.querySelector(".notes-input");

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

    searchInput?.addEventListener("input", applyFilters);
    hideDni?.addEventListener("change", applyFilters);
    onlyMissing?.addEventListener("change", applyFilters);

    document.querySelectorAll("form[data-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            const message = form.getAttribute("data-confirm");
            if (message && !window.confirm(message)) event.preventDefault();
        });
    });

    applyFilters();
})();
