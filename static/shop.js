(function () {
    const config = window.BOM_SHOP;
    const table = document.getElementById("shop-table");
    if (!config || !table) return;

    const searchInput = document.getElementById("shop-search");
    const hideOrdered = document.getElementById("shop-hide-ordered");
    const emptyMsg = document.getElementById("shop-empty");
    const lookupStatus = document.getElementById("shop-lookup-status");
    const lookupVisibleBtn = document.getElementById("shop-lookup-visible");
    const lookupForceBtn = document.getElementById("shop-lookup-force");
    const rows = Array.from(table.querySelectorAll("tbody tr.shop-row"));

    function lineUrl(lineId) {
        return config.updateUrlTemplate.replace("__LINE_ID__", encodeURIComponent(lineId));
    }

    async function patchLine(lineId, body) {
        const response = await fetch(lineUrl(lineId), {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify(body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) {
            throw new Error(data.error || "Could not save.");
        }
        return data;
    }

    function visibleRows() {
        return rows.filter((row) => !row.hidden);
    }

    function setLookupStatus(message, isError) {
        if (!lookupStatus) return;
        lookupStatus.hidden = !message;
        lookupStatus.textContent = message || "";
        lookupStatus.classList.toggle("shop-lookup-error", Boolean(isError));
    }

    function formatPrice(value) {
        if (value == null || Number.isNaN(Number(value))) return "";
        return `$${Number(value).toFixed(4)}`;
    }

    function renderCacheCell(row, cacheKey, results) {
        const container = row.querySelector("[data-dist-cache]");
        if (!container) return;
        const entry = results[cacheKey] || {};
        const dk = entry.digikey;
        const mo = entry.mouser;
        const parts = [];

        const distLinks = row.querySelectorAll(".dist-actions a.dist-link");
        if (dk) {
            const dkBits = ["<div class=\"dist-cache-line dist-dk\"><span class=\"dist-cache-label\">DK</span>"];
            if (dk.found) {
                if (dk.stock != null) dkBits.push(`<span>${dk.stock} in stock</span>`);
                if (dk.price_1 != null) dkBits.push(`<span class="dist-price">${formatPrice(dk.price_1)}</span>`);
            } else if (dk.fetched_at) {
                dkBits.push('<span class="dist-miss">no match</span>');
            }
            if (dk.fetched_at) dkBits.push(`<span class="muted dist-fetched" title="${dk.fetched_at}">· cached</span>`);
            dkBits.push("</div>");
            parts.push(dkBits.join(" "));
            if (dk.url && distLinks[0]) distLinks[0].href = dk.url;
        }
        if (mo) {
            const moBits = ["<div class=\"dist-cache-line dist-mo\"><span class=\"dist-cache-label\">MO</span>"];
            if (mo.found) {
                if (mo.stock != null) moBits.push(`<span>${mo.stock} in stock</span>`);
                else if (mo.stock_text) moBits.push(`<span>${mo.stock_text}</span>`);
                if (mo.price_1 != null) moBits.push(`<span class="dist-price">${formatPrice(mo.price_1)}</span>`);
            } else if (mo.fetched_at) {
                moBits.push('<span class="dist-miss">no match</span>');
            }
            if (mo.fetched_at) moBits.push(`<span class="muted dist-fetched" title="${mo.fetched_at}">· cached</span>`);
            moBits.push("</div>");
            parts.push(moBits.join(" "));
            if (mo.url && distLinks[1]) distLinks[1].href = mo.url;
        }

        container.innerHTML = parts.join("");
    }

    async function runLookup(mpns, force) {
        if (!config.apiConfigured || !config.lookupUrl) return;
        const unique = [];
        const seen = new Set();
        mpns.forEach((mpn) => {
            const key = (mpn || "").trim();
            if (!key) return;
            const upper = key.toUpperCase();
            if (seen.has(upper)) return;
            seen.add(upper);
            unique.push(key);
        });
        if (!unique.length) return;

        setLookupStatus(`Looking up ${unique.length} part(s)…`, false);
        if (lookupVisibleBtn) lookupVisibleBtn.disabled = true;
        if (lookupForceBtn) lookupForceBtn.disabled = true;

        try {
            const response = await fetch(config.lookupUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", Accept: "application/json" },
                body: JSON.stringify({ mpns: unique, force }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.ok) {
                throw new Error(data.error || "Lookup failed.");
            }

            visibleRows().forEach((row) => {
                const cacheKey = row.dataset.cacheKey;
                if (cacheKey && data.results) renderCacheCell(row, cacheKey, data.results);
            });

            const errCount = data.errors ? Object.keys(data.errors).length : 0;
            let msg = `Updated ${Object.keys(data.results || {}).length} part(s).`;
            if (data.limited_to && unique.length >= data.limited_to) {
                msg += ` (max ${data.limited_to} per batch)`;
            }
            if (errCount) msg += ` ${errCount} had errors.`;
            setLookupStatus(msg, errCount > 0);
        } catch (err) {
            setLookupStatus(err.message || "Lookup failed.", true);
        } finally {
            if (lookupVisibleBtn) lookupVisibleBtn.disabled = false;
            if (lookupForceBtn) lookupForceBtn.disabled = false;
        }
    }

    function applyFilters() {
        const query = (searchInput?.value || "").trim().toLowerCase();
        const skipOrdered = hideOrdered?.checked ?? false;
        let visible = 0;

        rows.forEach((row) => {
            const ordered = row.dataset.ordered === "1";
            const searchHay = row.dataset.search || "";
            let show = true;
            if (skipOrdered && ordered) show = false;
            if (query && !searchHay.includes(query)) show = false;
            row.hidden = !show;
            if (show) visible += 1;
        });

        if (emptyMsg) emptyMsg.hidden = visible > 0;
    }

    rows.forEach((row) => {
        const lineId = row.dataset.lineId;
        const mpn = row.dataset.mpn;
        const orderedCheck = row.querySelector(".ordered-check");
        const buyQtyInput = row.querySelector(".buy-qty-input");
        const notesInput = row.querySelector(".notes-input");
        const lookupBtn = row.querySelector(".shop-lookup-row");

        let timer;
        function scheduleSave(body) {
            clearTimeout(timer);
            timer = setTimeout(async () => {
                try {
                    const result = await patchLine(lineId, body);
                    if ("ordered" in body) {
                        row.dataset.ordered = result.ordered ? "1" : "0";
                        row.classList.toggle("row-ordered", result.ordered);
                    }
                    applyFilters();
                } catch (err) {
                    alert(err.message || "Could not save. Is the server still running?");
                }
            }, 400);
        }

        orderedCheck?.addEventListener("change", () => {
            scheduleSave({ ordered: orderedCheck.checked });
        });

        buyQtyInput?.addEventListener("input", () => {
            const raw = parseInt(buyQtyInput.value, 10);
            const qty = Number.isFinite(raw) && raw >= 0 ? raw : 0;
            scheduleSave({ buy_qty: qty });
        });

        notesInput?.addEventListener("input", () => {
            scheduleSave({ notes: notesInput.value });
        });

        lookupBtn?.addEventListener("click", () => {
            runLookup([mpn], false);
        });
    });

    lookupVisibleBtn?.addEventListener("click", () => {
        const mpns = visibleRows().map((row) => row.dataset.mpn).filter(Boolean);
        runLookup(mpns, false);
    });

    lookupForceBtn?.addEventListener("click", () => {
        const mpns = visibleRows().map((row) => row.dataset.mpn).filter(Boolean);
        runLookup(mpns, true);
    });

    searchInput?.addEventListener("input", applyFilters);
    hideOrdered?.addEventListener("change", applyFilters);
    applyFilters();
})();
