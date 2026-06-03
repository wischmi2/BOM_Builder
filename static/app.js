// Shared UI helpers for BOM Builder pages.

document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
        const message = form.getAttribute("data-confirm");
        if (message && !window.confirm(message)) event.preventDefault();
    });
});
