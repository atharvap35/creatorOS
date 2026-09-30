const year = document.getElementById("current-year");
if (year) year.textContent = new Date().getFullYear();

// --- destructive action guard -------------------------------------------
document.querySelectorAll("form[method='post']").forEach((form) => {
    form.addEventListener("submit", (event) => {
        const submitter = event.submitter || form.querySelector("button[type='submit']");
        if (!submitter) return;
        if (submitter.classList.contains("danger") && !window.confirm("Delete this? This cannot be undone.")) {
            event.preventDefault();
        }
    });
});

// --- toasts --------------------------------------------------------------
function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[ch]);
}

function toast(message) {
    const region = document.querySelector("[data-toast-region]");
    if (!region) return;
    const node = document.createElement("div");
    node.className = "toast";
    node.textContent = message;
    region.appendChild(node);
    setTimeout(() => node.remove(), 3200);
}

const params = new URLSearchParams(window.location.search);
if (params.get("saved")) toast("Saved");
if (params.get("created")) toast(`${params.get("created")} task(s) added to your workflow`);
if (params.get("converted")) toast("Idea converted into a content plan");

// --- mobile sidebar ------------------------------------------------------
const sidebar = document.getElementById("sidebar");
document.querySelectorAll("[data-toggle-sidebar]").forEach((button) => {
    button.addEventListener("click", () => sidebar.classList.toggle("open"));
});

// --- command palette -----------------------------------------------------
const backdrop = document.querySelector("[data-palette]");
const input = document.querySelector("[data-palette-input]");
const results = document.querySelector("[data-palette-results]");

function openPalette() {
    if (!backdrop) return;
    backdrop.hidden = false;
    input.value = "";
    input.focus();
    results.innerHTML = '<p class="palette-hint">Type to search, or pick a command below.</p>';
    loadCommands();
}

function closePalette() {
    if (backdrop) backdrop.hidden = true;
}

async function loadCommands() {
    const response = await fetch("/api/commands");
    if (!response.ok) return;
    const { commands } = await response.json();
    results.innerHTML = `
        <div class="palette-group">
            <h4>Commands</h4>
            ${commands.map((c) => `<a class="palette-item" href="${escapeHtml(c.url)}">${escapeHtml(c.label)}<small>${escapeHtml(c.hint || "")}</small></a>`).join("")}
        </div>`;
}

async function runSearch(term) {
    if (term.trim().length < 2) {
        loadCommands();
        return;
    }
    const response = await fetch(`/api/search?q=${encodeURIComponent(term)}`);
    const { results: found } = await response.json();
    if (!found.length) {
        results.innerHTML = `<p class="palette-hint">Nothing found for “${escapeHtml(term)}”. Try another word, or capture it as an idea.</p>`;
        return;
    }
    const groups = {};
    found.forEach((item) => {
        (groups[item.group] = groups[item.group] || []).push(item);
    });
    results.innerHTML = Object.entries(groups)
        .map(([group, items]) => `
            <div class="palette-group">
                <h4>${escapeHtml(group)}</h4>
                ${items.map((i) => `<a class="palette-item" href="${escapeHtml(i.url)}">${escapeHtml(i.title)}<small>${escapeHtml(i.subtitle || "")}</small></a>`).join("")}
            </div>`)
        .join("");
}

document.querySelectorAll("[data-open-palette]").forEach((el) => el.addEventListener("click", openPalette));
if (backdrop) {
    backdrop.addEventListener("click", (event) => {
        if (event.target === backdrop) closePalette();
    });
}
if (input) {
    input.addEventListener("input", (event) => runSearch(event.target.value));
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            const first = results.querySelector("a");
            if (first) window.location.href = first.href;
        }
    });
}

document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        backdrop && backdrop.hidden ? openPalette() : closePalette();
    }
    if (event.key === "Escape") closePalette();
});
