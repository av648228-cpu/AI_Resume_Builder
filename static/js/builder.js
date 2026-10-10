"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const repeaters = document.querySelectorAll("[data-repeater]");
    const rowTemplates = new Map();

    function reindexRows(sectionName, container) {
        const rows = Array.from(container.querySelectorAll("[data-row]"));
        rows.forEach((row, index) => {
            row.dataset.rowIndex = String(index);
            row.querySelectorAll("[name]").forEach((field) => {
                field.name = field.name.replace(
                    new RegExp(`^${sectionName}-\\d+-`),
                    `${sectionName}-${index}-`
                );
            });
            const number = row.querySelector("[data-entry-number]");
            if (number) number.textContent = String(index + 1);
            const heading = row.querySelector(".repeat-row-heading h3");
            if (heading && !number) heading.textContent = `${sectionName} entry ${index + 1}`;
        });
    }

    repeaters.forEach((container) => {
        const sectionName = container.dataset.repeater;
        const firstRow = container.querySelector("[data-row]");
        if (firstRow) rowTemplates.set(sectionName, firstRow.cloneNode(true));
        reindexRows(sectionName, container);
    });

    document.querySelectorAll("[data-add-row]").forEach((button) => {
        button.addEventListener("click", () => {
            const sectionName = button.dataset.addRow;
            const container = document.querySelector(`[data-repeater="${sectionName}"]`);
            const template = rowTemplates.get(sectionName);
            if (!container || !template) return;

            const newRow = template.cloneNode(true);
            newRow.querySelectorAll("input, textarea, select").forEach((field) => {
                if (field.type === "checkbox" || field.type === "radio") {
                    field.checked = false;
                } else if (field.type !== "button" && field.type !== "submit") {
                    field.value = "";
                }
            });
            newRow.querySelectorAll(".ai-status").forEach((status) => {
                status.textContent = "";
            });
            container.appendChild(newRow);
            reindexRows(sectionName, container);
            const firstField = newRow.querySelector("input:not([type='file']), textarea");
            if (firstField) firstField.focus();
        });
    });

    document.addEventListener("click", (event) => {
        const removeButton = event.target.closest("[data-remove-row]");
        if (removeButton) {
            const row = removeButton.closest("[data-row]");
            const container = removeButton.closest("[data-repeater]");
            if (!row || !container) return;
            const sectionName = container.dataset.repeater;
            row.remove();
            reindexRows(sectionName, container);
            return;
        }

        const improveButton = event.target.closest(".improve-description");
        if (improveButton) improveDescription(improveButton);
    });

    async function improveDescription(button) {
        const row = button.closest("[data-row]");
        const field = row ? row.querySelector(".description-field") : null;
        const status = row ? row.querySelector(".ai-status") : null;
        if (!field || !status) return;

        const description = field.value.trim();
        if (!description) {
            status.textContent = "Add a description first.";
            return;
        }

        const tokenElement = document.querySelector('meta[name="csrf-token"]');
        const csrfToken = tokenElement ? tokenElement.content : "";
        const heading = row.querySelector(".repeat-row-heading h3");
        const originalLabel = button.textContent;
        button.disabled = true;
        button.textContent = "Working…";
        status.textContent = "";

        try {
            const response = await fetch("/api/improve-description", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify({
                    description,
                    context: heading ? heading.textContent : "Student resume",
                }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.message || "Request failed.");
            if (result.success && result.text) field.value = result.text;
            status.textContent = result.message || "Done.";
        } catch (error) {
            status.textContent = error.message || "Could not improve the description.";
        } finally {
            button.disabled = false;
            button.textContent = originalLabel;
        }
    }
});
