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
    const expandAllBtn = document.getElementById("shop-expand-all");
    const collapseAllBtn = document.getElementById("shop-collapse-all");
    const collapseKey = "bom-builder-shop-collapsed";
    const rows = Array.from(table.querySelectorAll("tbody tr.shop-row:not(.shop-alt-row)"));
    const altRowByParent = new Map();
    table.querySelectorAll("tbody tr.shop-alt-row").forEach((altRow) => {
        const key = altRow.dataset.parentStorageKey;
        if (key) altRowByParent.set(key, altRow);
    });
    const categoryHeaders = Array.from(table.querySelectorAll("tbody tr.category-header"));

    function altRowFor(parentRow) {
        return altRowByParent.get(parentRow.dataset.storageKey || "");
    }

    function setAlternateVisible(parentRow, visible) {
        const altRow = altRowFor(parentRow);
        if (!altRow) return;
        altRow.hidden = !visible;
        parentRow.classList.toggle("has-alternate", Boolean(visible));
    }

    function updateDistLinks(row, mpn) {
        if (!mpn) return;
        const encoded = encodeURIComponent(mpn);
        row.querySelectorAll(".dist-actions a.dist-link").forEach((link, index) => {
            if (index === 0) {
                link.href = `https://www.digikey.com/en/products/result?keywords=${encoded}`;
            } else if (index === 1) {
                link.href = `https://www.mouser.com/c/?q=${encoded}`;
            }
        });
    }

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
            const altRow = altRowFor(row);
            if (altRow) altRow.classList.toggle("category-collapsed", collapsed);
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
        const toggle = header.querySelector(".category-toggle");
        toggle?.addEventListener("click", () => {
            const categoryId = header.dataset.category;
            const next = !header.classList.contains("is-collapsed");
            setCategoryCollapsed(categoryId, next);
            applyCategoryCollapse(categoryId, next);
        });
    });

    expandAllBtn?.addEventListener("click", () => setAllCategoriesCollapsed(false));
    collapseAllBtn?.addEventListener("click", () => setAllCategoriesCollapsed(true));

    function insertRowIntoCategory(row, targetCategoryId) {
        const header = headerForCategory(targetCategoryId);
        if (!header) return;

        const oldCategory = row.dataset.categoryGroup;
        row.dataset.categoryGroup = targetCategoryId;

        let insertAfter = header;
        let next = header.nextElementSibling;
        while (next && !next.classList.contains("category-header")) {
            if (next !== row && next.classList.contains("shop-row") && next.dataset.categoryGroup === targetCategoryId) {
                insertAfter = next;
            }
            next = next.nextElementSibling;
        }
        insertAfter.parentNode.insertBefore(row, insertAfter.nextElementSibling);
        const altRow = altRowFor(row);
        if (altRow) {
            row.parentNode.insertBefore(altRow, row.nextElementSibling);
        }

        if (oldCategory && oldCategory !== targetCategoryId) {
            updateCategoryCount(oldCategory);
        }
        updateCategoryCount(targetCategoryId);
    }

    async function saveCategoryOverride(row, targetCategoryId) {
        const partKey = row.dataset.partKey;
        const autoCategory = row.dataset.autoCategory;
        const response = await fetch(config.categoryOverrideUrl, {
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

        rows.forEach((row) => {
            row.addEventListener("dragstart", (event) => {
                if (event.target.closest("input, button, a, select, textarea")) {
                    event.preventDefault();
                    return;
                }
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

    function lineUrl(storageKey) {
        return config.updateUrlTemplate.replace("__STORAGE_KEY__", encodeURIComponent(storageKey));
    }

    function receiveLineUrl(storageKey) {
        return config.receiveUrlTemplate.replace("__STORAGE_KEY__", encodeURIComponent(storageKey));
    }

    async function patchLine(storageKey, body) {
        const response = await fetch(lineUrl(storageKey), {
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

    async function receiveLine(storageKey, body) {
        const response = await fetch(receiveLineUrl(storageKey), {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify(body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) {
            throw new Error(data.error || "Could not receive into inventory.");
        }
        return data;
    }

    function updateReceiveUi(row, state, parentRow) {
        row.dataset.receivedQty = String(state.received_qty);
        row.dataset.buyQty = String(state.buy_qty);
        row.classList.toggle("row-received", Boolean(state.fully_received));

        const recvInput = row.querySelector(".receive-qty-input, .alt-receive-qty-input");
        const recvCheck = row.querySelector(".received-check, .alt-received-check");
        if (recvInput) {
            const remaining = Math.max(0, state.remaining_qty);
            recvInput.value = remaining > 0 ? String(remaining) : "1";
            recvInput.disabled = state.fully_received;
        }
        if (recvCheck) {
            recvCheck.checked = state.fully_received;
            recvCheck.disabled = state.fully_received;
        }

        let progress = row.querySelector(".received-progress");
        if (state.received_qty > 0) {
            if (!progress) {
                progress = document.createElement("span");
                progress.className = "muted received-progress";
                row.querySelector(".col-received")?.appendChild(progress);
            }
            progress.textContent = `${state.received_qty} / ${state.buy_qty} in inventory`;
        } else if (progress) {
            progress.remove();
        }

        const buyCell = parentRow?.querySelector(".col-qty");
        if (buyCell) {
            let remainingEl = buyCell.querySelector(".received-remaining");
            if (state.received_qty > 0 && !state.fully_received) {
                if (!remainingEl) {
                    remainingEl = document.createElement("span");
                    remainingEl.className = "muted received-remaining";
                    buyCell.appendChild(remainingEl);
                }
                remainingEl.textContent = `${state.remaining_qty} left to receive`;
            } else if (remainingEl) {
                remainingEl.remove();
            }
        }
    }

    function remainingToReceive(row) {
        const buy = parseInt(row.dataset.buyQty || "0", 10) || 0;
        const received = parseInt(row.dataset.receivedQty || "0", 10) || 0;
        return Math.max(0, buy - received);
    }

    async function resetReceiveTracking(row, storageKey, isAlternate, parentRow) {
        const result = await receiveLine(storageKey, { action: "reset", alternate: isAlternate });
        updateReceiveUi(row, result, isAlternate ? parentRow : row);
        return result;
    }

    function bindReceive(row, storageKey, options) {
        const isAlternate = Boolean(options?.alternate);
        const parentRow = options?.parentRow || row;
        const recvCheck = row.querySelector(isAlternate ? ".alt-received-check" : ".received-check");
        const recvQty = row.querySelector(isAlternate ? ".alt-receive-qty-input" : ".receive-qty-input");
        const mpnInput = row.querySelector(isAlternate ? ".alt-mpn-input" : ".mpn-input");
        const nameInput = row.querySelector(isAlternate ? ".alt-name-input" : ".name-input");
        const notesInput = row.querySelector(isAlternate ? ".alt-notes-input" : ".notes-input");
        const resetBtn = row.querySelector(".reset-received-btn");
        let receiving = false;

        resetBtn?.addEventListener("click", async () => {
            const msg =
                "Clear the receive count for this line? This does not remove parts from Inventory — use Inventory → Delete for that.";
            if (!window.confirm(msg)) return;
            try {
                await resetReceiveTracking(row, storageKey, isAlternate, parentRow);
            } catch (err) {
                alert(err.message || "Could not reset receive tracking.");
            }
        });

        recvCheck?.addEventListener("change", async () => {
            if (!recvCheck.checked) {
                return;
            }
            if (receiving) {
                recvCheck.checked = false;
                return;
            }
            const remaining = remainingToReceive(row);
            if (remaining <= 0) {
                recvCheck.checked = false;
                alert(
                    "Nothing left to receive on this line. Click Reset if you removed stock from Inventory and want to receive again."
                );
                return;
            }
            const raw = parseInt(recvQty?.value, 10);
            let qty = Number.isFinite(raw) && raw > 0 ? raw : 0;
            if (qty > remaining) {
                qty = remaining;
                if (recvQty) recvQty.value = String(remaining);
            }
            if (!qty) {
                recvCheck.checked = false;
                alert("Enter how many to receive (at least 1).");
                return;
            }
            const mpn = (mpnInput?.value || row.dataset.mpn || "").trim();
            if (!mpn) {
                recvCheck.checked = false;
                alert("Enter an MPN before receiving into inventory.");
                return;
            }
            if (!window.confirm(`Add ${qty} of ${mpn} to Inventory now?`)) {
                recvCheck.checked = false;
                return;
            }
            receiving = true;
            recvCheck.disabled = true;
            let fullyReceived = false;
            try {
                const result = await receiveLine(storageKey, {
                    qty,
                    mpn,
                    name: nameInput?.value || "",
                    notes: notesInput?.value || "",
                    alternate: isAlternate,
                });
                fullyReceived = Boolean(result.fully_received);
                updateReceiveUi(row, result, isAlternate ? parentRow : row);
                if (!fullyReceived) {
                    recvCheck.checked = false;
                }
            } catch (err) {
                recvCheck.checked = false;
                alert(err.message || "Could not receive into inventory.");
            } finally {
                receiving = false;
                recvCheck.disabled = fullyReceived;
            }
        });
    }

    function visibleRows() {
        const visible = rows.filter((row) => !row.hidden);
        const withAlts = [];
        visible.forEach((row) => {
            withAlts.push(row);
            const altRow = altRowFor(row);
            if (altRow && !altRow.hidden) withAlts.push(altRow);
        });
        return withAlts;
    }

    function visibleMpns() {
        const mpns = [];
        rows.filter((row) => !row.hidden).forEach((row) => {
            if (row.dataset.mpn) mpns.push(row.dataset.mpn);
            const altRow = altRowFor(row);
            if (altRow && !altRow.hidden && altRow.dataset.mpn) mpns.push(altRow.dataset.mpn);
        });
        return mpns;
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

    function escapeHtml(value) {
        return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        }[c]));
    }

    function detailBodyFor(row) {
        if (!row.__detailRow) {
            const tr = document.createElement("tr");
            tr.className = "shop-detail-row";
            tr.dataset.categoryGroup = row.dataset.categoryGroup || "";
            const td = document.createElement("td");
            td.colSpan = 13;
            const div = document.createElement("div");
            div.className = "shop-detail";
            td.appendChild(div);
            tr.appendChild(td);
            row.__detailRow = tr;
            row.__detailBody = div;
        }
        const alt = altRowFor(row);
        const anchor = alt && !alt.hidden ? alt : row;
        anchor.parentNode.insertBefore(row.__detailRow, anchor.nextElementSibling);
        row.__detailRow.hidden = false;
        return row.__detailBody;
    }

    function closeDetail(row) {
        if (row.__detailRow) row.__detailRow.hidden = true;
    }

    function currentMpn(row) {
        return (row.querySelector(".mpn-input")?.value || row.dataset.mpn || "").trim();
    }

    async function enrichRow(row, storageKey, sourceLineIds) {
        const mpn = currentMpn(row);
        if (!mpn) { alert("Enter an MPN before enriching."); return; }
        const body = detailBodyFor(row);
        body.innerHTML = `<p class="muted">Looking up ${escapeHtml(mpn)}…</p>`;
        try {
            const resp = await fetch(config.enrichUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", Accept: "application/json" },
                body: JSON.stringify({ mpn }),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok || !data.ok) throw new Error(data.error || "Enrich failed.");
            renderEnrich(row, body, storageKey, sourceLineIds, mpn, data.proposal);
        } catch (err) {
            body.innerHTML = `<p class="shop-lookup-error">${escapeHtml(err.message || "Enrich failed.")}</p>`;
        }
    }

    function renderEnrich(row, body, storageKey, sourceLineIds, mpn, proposal) {
        if (!proposal || !proposal.found) {
            body.innerHTML = `<div class="shop-detail-head"><strong>Enrich ${escapeHtml(mpn)}</strong></div>` +
                `<p class="muted">No distributor match. Try the DigiKey/Mouser search links.</p>` +
                `<div class="shop-detail-actions"><button type="button" class="btn btn-secondary btn-sm detail-close">Close</button></div>`;
            body.querySelector(".detail-close").addEventListener("click", () => closeDetail(row));
            return;
        }
        const fields = [
            ["manufacturer", "Manufacturer", proposal.manufacturer],
            ["description", "Description", proposal.description],
            ["datasheet_url", "Datasheet", proposal.datasheet_url],
            ["unit_price", "Unit price", proposal.unit_price != null ? formatPrice(proposal.unit_price) : ""],
            ["stock", "Stock", proposal.stock != null ? String(proposal.stock) : ""],
        ];
        const rowsHtml = fields.map(([key, label, val]) => {
            const has = val != null && String(val).trim() !== "";
            return `<tr>
                <td><label class="filter-check"><input type="checkbox" class="enrich-field" data-field="${key}" ${has ? "checked" : ""} ${has ? "" : "disabled"}> ${label}</label></td>
                <td class="enrich-val">${has ? escapeHtml(val) : '<span class="muted">—</span>'}</td>
            </tr>`;
        }).join("");
        body.innerHTML = `
            <div class="shop-detail-head"><strong>Enrich ${escapeHtml(mpn)}</strong>
                <span class="muted">source: ${escapeHtml(proposal.source || "—")}</span></div>
            <table class="enrich-table"><thead><tr><th>Apply</th><th>Fetched value</th></tr></thead><tbody>${rowsHtml}</tbody></table>
            <div class="shop-detail-actions">
                <button type="button" class="btn btn-primary btn-sm enrich-apply">Apply selected</button>
                <button type="button" class="btn btn-secondary btn-sm detail-close">Close</button>
                <span class="muted enrich-status" hidden></span>
            </div>`;
        body.querySelector(".detail-close").addEventListener("click", () => closeDetail(row));
        body.querySelector(".enrich-apply").addEventListener("click", async () => {
            const toApply = {};
            body.querySelectorAll(".enrich-field:checked").forEach((cb) => {
                toApply[cb.dataset.field] = proposal[cb.dataset.field];
            });
            if (!Object.keys(toApply).length) { alert("Select at least one field to apply."); return; }
            const status = body.querySelector(".enrich-status");
            status.hidden = false;
            status.classList.remove("shop-lookup-error");
            status.textContent = "Saving…";
            try {
                const resp = await fetch(config.enrichApplyUrl, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", Accept: "application/json" },
                    body: JSON.stringify({
                        storage_key: storageKey,
                        source_line_ids: sourceLineIds,
                        source: proposal.source,
                        fields: toApply,
                    }),
                });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok || !data.ok) throw new Error(data.error || "Apply failed.");
                status.textContent = `Saved to ${data.updated} BOM line(s).`;
            } catch (err) {
                status.textContent = err.message || "Apply failed.";
                status.classList.add("shop-lookup-error");
            }
        });
    }

    async function showAlternates(row, storageKey, sourceLineIds) {
        const mpn = currentMpn(row);
        if (!mpn) { alert("Enter an MPN before finding alternates."); return; }
        const body = detailBodyFor(row);
        body.innerHTML = `<p class="muted">Finding alternates for ${escapeHtml(mpn)}…</p>`;
        try {
            const resp = await fetch(config.alternatesUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", Accept: "application/json" },
                body: JSON.stringify({ mpn }),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok || !data.ok) throw new Error(data.error || "Alternates lookup failed.");
            renderAlternates(row, body, storageKey, sourceLineIds, mpn, data.alternates || [], data.errors || {});
        } catch (err) {
            body.innerHTML = `<p class="shop-lookup-error">${escapeHtml(err.message || "Alternates lookup failed.")}</p>`;
        }
    }

    function renderAlternates(row, body, storageKey, sourceLineIds, mpn, alts, errors) {
        const errorKeys = errors ? Object.keys(errors) : [];
        const errorsHtml = errorKeys.length
            ? `<p class="alt-errors">${errorKeys.map((k) => `${escapeHtml(k)}: ${escapeHtml(errors[k])}`).join(" · ")}</p>`
            : "";
        const head = `<div class="shop-detail-head"><strong>Alternates for ${escapeHtml(mpn)}</strong>` +
            `<span class="muted">substitutes come from DigiKey; similar parts from DigiKey + Mouser</span></div>`;
        if (!alts.length) {
            body.innerHTML = head + `<p class="muted">No alternates found.</p>` + errorsHtml +
                `<div class="shop-detail-actions"><button type="button" class="btn btn-secondary btn-sm detail-close">Close</button></div>`;
            body.querySelector(".detail-close").addEventListener("click", () => closeDetail(row));
            return;
        }
        const rowsHtml = alts.map((a, i) => {
            const price = a.price_1 != null ? formatPrice(a.price_1) : "—";
            const stock = a.stock != null ? a.stock : "—";
            const kind = a.kind === "substitute"
                ? '<span class="badge badge-sub">sub</span>'
                : '<span class="muted">similar</span>';
            const ds = a.datasheet_url ? `<a href="${escapeHtml(a.datasheet_url)}" target="_blank" rel="noopener">datasheet</a>` : "";
            const link = a.url ? `<a href="${escapeHtml(a.url)}" target="_blank" rel="noopener">${escapeHtml(a.distributor || "link")}</a>` : "";
            return `<tr data-alt-index="${i}">
                <td><code>${escapeHtml(a.mpn)}</code> ${kind}<span class="alt-source">${escapeHtml(a.distributor || "")}</span></td>
                <td>${escapeHtml(a.manufacturer || "")}</td>
                <td class="alt-desc">${escapeHtml(a.description || "")}</td>
                <td class="dist-price">${price}</td>
                <td>${stock}</td>
                <td class="alt-links">${link} ${ds}</td>
                <td class="alt-actions">
                    <button type="button" class="btn btn-secondary btn-sm alt-sub">Substitute</button>
                    <button type="button" class="btn btn-primary btn-sm alt-replace">Replace</button>
                </td></tr>`;
        }).join("");
        body.innerHTML = head +
            `<table class="alt-table"><thead><tr><th>MPN</th><th>Mfr</th><th>Description</th><th>Price</th><th>Stock</th><th>Links</th><th></th></tr></thead><tbody>${rowsHtml}</tbody></table>` +
            errorsHtml +
            `<div class="shop-detail-actions"><button type="button" class="btn btn-secondary btn-sm detail-close">Close</button><span class="muted alt-status" hidden></span></div>`;
        body.querySelector(".detail-close").addEventListener("click", () => closeDetail(row));
        const status = body.querySelector(".alt-status");
        function setStatus(msg, isError) {
            status.hidden = false;
            status.textContent = msg;
            status.classList.toggle("shop-lookup-error", Boolean(isError));
        }
        body.querySelectorAll(".alt-table tbody tr").forEach((tr) => {
            const a = alts[parseInt(tr.dataset.altIndex, 10)];
            if (!a) return;
            tr.querySelector(".alt-sub")?.addEventListener("click", async () => {
                setStatus(`Setting substitute to ${a.mpn}…`, false);
                try {
                    await patchLine(storageKey, {
                        alternate: { enabled: true, mpn: a.mpn, name: a.description || a.manufacturer || "" },
                    });
                    setStatus(`Substitute set to ${a.mpn}. Reload the list to see the ALT row.`, false);
                } catch (err) {
                    setStatus(err.message || "Could not set substitute.", true);
                }
            });
            tr.querySelector(".alt-replace")?.addEventListener("click", async () => {
                if (!window.confirm(`Replace ${mpn} with ${a.mpn} in the BOM? This updates the part in your list.`)) return;
                setStatus(`Replacing with ${a.mpn}…`, false);
                const fields = { mpn: a.mpn };
                if (a.description) fields.name = a.description;
                if (a.manufacturer) fields.manufacturer = a.manufacturer;
                if (a.datasheet_url) fields.datasheet_url = a.datasheet_url;
                if (a.price_1 != null) fields.unit_price = a.price_1;
                if (a.stock != null) fields.stock = a.stock;
                try {
                    const resp = await fetch(config.enrichApplyUrl, {
                        method: "POST",
                        headers: { "Content-Type": "application/json", Accept: "application/json" },
                        body: JSON.stringify({
                            storage_key: storageKey,
                            source_line_ids: sourceLineIds,
                            source: a.distributor,
                            fields,
                        }),
                    });
                    const data = await resp.json().catch(() => ({}));
                    if (!resp.ok || !data.ok) throw new Error(data.error || "Replace failed.");
                    const mpnInput = row.querySelector(".mpn-input");
                    if (mpnInput) { mpnInput.value = a.mpn; row.dataset.mpn = a.mpn; }
                    const nameInput = row.querySelector(".name-input");
                    if (nameInput && a.description) nameInput.value = a.description;
                    updateDistLinks(row, a.mpn);
                    setStatus(`Replaced with ${a.mpn} (updated ${data.updated} BOM line(s)).`, false);
                } catch (err) {
                    setStatus(err.message || "Replace failed.", true);
                }
            });
        });
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
            const altRow = altRowFor(row);
            if (altRow) {
                const altVisible = show && row.querySelector(".alternate-check")?.checked;
                altRow.hidden = !altVisible;
            }
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

    rows.forEach((row) => {
        const storageKey = row.dataset.storageKey || row.dataset.lineId;
        const mpn = row.dataset.mpn;
        const orderedCheck = row.querySelector(".ordered-check");
        const buyQtyInput = row.querySelector(".buy-qty-input");
        const mpnInput = row.querySelector(".mpn-input");
        const nameInput = row.querySelector(".name-input");
        const notesInput = row.querySelector(".notes-input");
        const lookupBtn = row.querySelector(".shop-lookup-row");
        const alternateCheck = row.querySelector(".alternate-check");
        const sourceLineIds = (row.dataset.sourceLineIds || "")
            .split(",")
            .map((id) => id.trim())
            .filter(Boolean);

        let timer;
        function scheduleSave(body, immediate) {
            clearTimeout(timer);
            const save = async () => {
                try {
                    const payload = { ...body };
                    if (sourceLineIds.length && ("mpn" in body || "name" in body)) {
                        payload.source_line_ids = sourceLineIds;
                    }
                    const result = await patchLine(storageKey, payload);
                    if ("ordered" in body) {
                        row.dataset.ordered = result.ordered ? "1" : "0";
                        row.classList.toggle("row-ordered", result.ordered);
                    }
                    if ("mpn" in body && mpnInput) {
                        const mpn = (result.mpn || mpnInput.value || "").trim();
                        row.dataset.mpn = mpn;
                        if (result.mpn !== undefined) mpnInput.value = mpn;
                        if (mpn) {
                            row.dataset.cacheKey = `mpn:${mpn.toUpperCase()}`;
                            row.querySelectorAll(".dist-actions a.dist-link").forEach((link, index) => {
                                const encoded = encodeURIComponent(mpn);
                                if (index === 0) {
                                    link.href = `https://www.digikey.com/en/products/result?keywords=${encoded}`;
                                } else if (index === 1) {
                                    link.href = `https://www.mouser.com/c/?q=${encoded}`;
                                }
                            });
                        }
                    }
                    if ("name" in body && nameInput && result.name !== undefined) {
                        nameInput.value = result.name;
                    }
                    applyFilters();
                } catch (err) {
                    alert(err.message || "Could not save. Is the server still running?");
                }
            };
            if (immediate) {
                save();
            } else {
                timer = setTimeout(save, 400);
            }
        }

        orderedCheck?.addEventListener("change", () => {
            scheduleSave({ ordered: orderedCheck.checked }, true);
        });

        buyQtyInput?.addEventListener("input", () => {
            const raw = parseInt(buyQtyInput.value, 10);
            const qty = Number.isFinite(raw) && raw >= 0 ? raw : 0;
            scheduleSave({ buy_qty: qty }, false);
        });
        buyQtyInput?.addEventListener("blur", () => {
            const raw = parseInt(buyQtyInput.value, 10);
            const qty = Number.isFinite(raw) && raw >= 0 ? raw : 0;
            scheduleSave({ buy_qty: qty }, true);
        });

        notesInput?.addEventListener("input", () => {
            scheduleSave({ notes: notesInput.value }, false);
        });
        notesInput?.addEventListener("blur", () => {
            scheduleSave({ notes: notesInput.value }, true);
        });

        mpnInput?.addEventListener("input", () => {
            scheduleSave({ mpn: mpnInput.value.trim() }, false);
        });
        mpnInput?.addEventListener("blur", () => {
            scheduleSave({ mpn: mpnInput.value.trim() }, true);
        });

        nameInput?.addEventListener("input", () => {
            scheduleSave({ name: nameInput.value }, false);
        });
        nameInput?.addEventListener("blur", () => {
            scheduleSave({ name: nameInput.value }, true);
        });

        lookupBtn?.addEventListener("click", () => {
            runLookup([mpn], false);
        });

        const enrichBtn = row.querySelector(".shop-enrich-row");
        const altsBtn = row.querySelector(".shop-alts-row");
        enrichBtn?.addEventListener("click", () => enrichRow(row, storageKey, sourceLineIds));
        altsBtn?.addEventListener("click", () => showAlternates(row, storageKey, sourceLineIds));

        alternateCheck?.addEventListener("change", () => {
            setAlternateVisible(row, alternateCheck.checked);
            scheduleSave({ alternate: { enabled: alternateCheck.checked } }, true);
        });

        bindReceive(row, storageKey, { alternate: false });

        const altRow = altRowFor(row);
        if (altRow) {
            bindAlternateRow(altRow, row, storageKey);
            bindReceive(altRow, storageKey, { alternate: true, parentRow: row });
        }
    });

    function bindAlternateRow(altRow, parentRow, storageKey) {
        const altOrdered = altRow.querySelector(".alt-ordered-check");
        const altBuyQty = altRow.querySelector(".alt-buy-qty-input");
        const altMpn = altRow.querySelector(".alt-mpn-input");
        const altName = altRow.querySelector(".alt-name-input");
        const altNotes = altRow.querySelector(".alt-notes-input");
        const altLookup = altRow.querySelector(".shop-lookup-alt");

        let altTimer;
        function scheduleAltSave(altBody, immediate) {
            clearTimeout(altTimer);
            const save = async () => {
                try {
                    const result = await patchLine(storageKey, { alternate: altBody });
                    const alt = result.alternate || {};
                    if ("ordered" in altBody) {
                        altRow.dataset.ordered = alt.ordered ? "1" : "0";
                        altRow.classList.toggle("row-ordered", alt.ordered);
                    }
                    if ("mpn" in altBody && altMpn) {
                        const val = (alt.mpn || altMpn.value || "").trim();
                        altMpn.value = val;
                        altRow.dataset.mpn = val;
                        if (val) {
                            altRow.dataset.cacheKey = `mpn:${val.toUpperCase()}`;
                            updateDistLinks(altRow, val);
                        }
                    }
                    if ("name" in altBody && altName && alt.name !== undefined) {
                        altName.value = alt.name;
                    }
                    applyFilters();
                } catch (err) {
                    alert(err.message || "Could not save alternate part.");
                }
            };
            if (immediate) {
                save();
            } else {
                altTimer = setTimeout(save, 400);
            }
        }

        altOrdered?.addEventListener("change", () => {
            scheduleAltSave({ ordered: altOrdered.checked }, true);
        });
        altBuyQty?.addEventListener("input", () => {
            const raw = parseInt(altBuyQty.value, 10);
            scheduleAltSave({ buy_qty: Number.isFinite(raw) && raw >= 0 ? raw : 0 }, false);
        });
        altBuyQty?.addEventListener("blur", () => {
            const raw = parseInt(altBuyQty.value, 10);
            scheduleAltSave({ buy_qty: Number.isFinite(raw) && raw >= 0 ? raw : 0 }, true);
        });
        altMpn?.addEventListener("input", () => scheduleAltSave({ mpn: altMpn.value.trim() }, false));
        altMpn?.addEventListener("blur", () => scheduleAltSave({ mpn: altMpn.value.trim() }, true));
        altName?.addEventListener("input", () => scheduleAltSave({ name: altName.value }, false));
        altName?.addEventListener("blur", () => scheduleAltSave({ name: altName.value }, true));
        altNotes?.addEventListener("input", () => scheduleAltSave({ notes: altNotes.value }, false));
        altNotes?.addEventListener("blur", () => scheduleAltSave({ notes: altNotes.value }, true));
        altLookup?.addEventListener("click", () => {
            const m = altRow.dataset.mpn || altMpn?.value;
            if (m) runLookup([m], false);
        });
    }

    lookupVisibleBtn?.addEventListener("click", () => {
        runLookup(visibleMpns(), false);
    });

    lookupForceBtn?.addEventListener("click", () => {
        runLookup(visibleMpns(), true);
    });

    searchInput?.addEventListener("input", applyFilters);
    hideOrdered?.addEventListener("change", applyFilters);

    const viewForm = document.querySelector(".compare-select-form");
    viewForm?.querySelectorAll('input[name="view"]').forEach((radio) => {
        radio.addEventListener("change", () => viewForm.requestSubmit());
    });

    initCollapseState();
    setupDragAndDrop();
    applyFilters();
})();
