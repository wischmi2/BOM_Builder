// "Not purchased" toggle shared by Compare and Shop.
// Buttons: .exclude-part-btn with data-exclude-action="hide"|"restore" and data-part-key.
// Hide buttons sit inside a row that carries data-part-key; name/lib_ref are sent for the saved label.
(function () {
    const url = "/parts/exclude";

    async function setExcluded(partKey, excluded, name, libRef) {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ part_key: partKey, excluded, name, lib_ref: libRef }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.ok) {
            throw new Error(payload.error || "Could not update part.");
        }
    }

    document.addEventListener("click", async (event) => {
        const btn = event.target.closest(".exclude-part-btn");
        if (!btn) return;
        event.preventDefault();
        event.stopPropagation();

        const action = btn.dataset.excludeAction || "hide";
        const partKey = btn.dataset.partKey || btn.closest("[data-part-key]")?.dataset.partKey;
        if (!partKey) return;

        const name = btn.dataset.name || "";
        const libRef = btn.dataset.libRef || "";

        btn.disabled = true;
        try {
            await setExcluded(partKey, action !== "restore", name, libRef);
            window.location.reload();
        } catch (err) {
            btn.disabled = false;
            window.alert(err.message || "Could not update part.");
        }
    });
})();
