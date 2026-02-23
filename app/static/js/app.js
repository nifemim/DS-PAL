/* DS-PAL client-side JavaScript */

// --- Theme toggle ---

function getPlotlyThemeOverrides() {
    var isDark = document.documentElement.getAttribute("data-theme") === "dark";
    var gridColor = isDark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.08)";
    return {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: isDark ? "#e0e0e0" : "#333" },
        xaxis: { gridcolor: gridColor, linecolor: gridColor, zerolinecolor: gridColor },
        yaxis: { gridcolor: gridColor, linecolor: gridColor, zerolinecolor: gridColor }
    };
}

function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    var btn = document.getElementById("theme-toggle");
    if (btn) {
        btn.textContent = theme === "dark" ? "\u2600\uFE0E" : "\u263E\uFE0E";
        btn.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
    }
    try { localStorage.setItem("ds-pal-theme", theme); } catch (e) {}

    // Re-render visible Plotly charts with new theme colors
    var overrides = getPlotlyThemeOverrides();
    document.querySelectorAll("[data-plotly]").forEach(function (el) {
        if (typeof Plotly !== "undefined") {
            Plotly.relayout(el, overrides);
        }
    });
}

// Set correct icon and attach click handler on load
(function () {
    var theme = document.documentElement.getAttribute("data-theme") || "light";
    var btn = document.getElementById("theme-toggle");
    if (btn) {
        btn.textContent = theme === "dark" ? "\u2600\uFE0E" : "\u263E\uFE0E";
        btn.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
        btn.addEventListener("click", function () {
            var current = document.documentElement.getAttribute("data-theme");
            applyTheme(current === "dark" ? "light" : "dark");
        });
    }
})();

// Cross-tab sync
window.addEventListener("storage", function (e) {
    if (e.key === "ds-pal-theme" && e.newValue) {
        applyTheme(e.newValue);
    }
});

// --- Sheet selection: radio ↔ checkbox toggle ---
(function () {
    var toggle = document.getElementById("multi-select-toggle");
    if (!toggle) return;

    var radios = document.querySelectorAll(".sheet-radio");
    var checkboxes = document.querySelectorAll(".sheet-checkbox");
    var btnSingle = document.getElementById("btn-single");
    var btnJoin = document.getElementById("btn-join");

    toggle.addEventListener("change", function () {
        var multi = toggle.checked;
        radios.forEach(function (r) { r.style.display = multi ? "none" : ""; r.disabled = multi; });
        checkboxes.forEach(function (c) { c.style.display = multi ? "" : "none"; c.disabled = !multi; });
        btnSingle.style.display = multi ? "none" : "";
        btnJoin.style.display = multi ? "" : "none";
    });
})();

// --- Upload button enable/disable + spinner ---
(function () {
    var fileInput = document.getElementById("upload-file");
    var uploadBtn = document.getElementById("upload-btn");
    var pickBtn = document.getElementById("upload-pick-btn");
    var filenameSpan = document.getElementById("upload-filename");
    var form = document.getElementById("upload-form");
    if (!fileInput || !uploadBtn || !form) return;

    fileInput.addEventListener("change", function () {
        if (fileInput.files.length) {
            if (filenameSpan) filenameSpan.textContent = fileInput.files[0].name;
            uploadBtn.style.display = "";
        } else {
            if (filenameSpan) filenameSpan.textContent = "";
            uploadBtn.style.display = "none";
        }
    });

    form.addEventListener("submit", function () {
        uploadBtn.disabled = true;
        uploadBtn.setAttribute("aria-busy", "true");
        uploadBtn.textContent = "Uploading\u2026";
        if (pickBtn) pickBtn.disabled = true;
    });
})();

// --- Analysis tab switching ---
document.body.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-tab]");
    if (!btn) return;

    var tabId = btn.getAttribute("data-tab");
    var tablist = btn.closest("[role='tablist']");
    if (!tablist) return;

    // Update tab buttons
    tablist.querySelectorAll("[role='tab']").forEach(function (t) {
        t.classList.remove("active");
        t.setAttribute("aria-selected", "false");
    });
    btn.classList.add("active");
    btn.setAttribute("aria-selected", "true");

    // Show/hide panels
    var panels = tablist.parentElement.querySelectorAll("[role='tabpanel']");
    panels.forEach(function (panel) {
        var isTarget = panel.id === "tab-" + tabId;
        panel.style.display = isTarget ? "" : "none";
        // Resize Plotly charts in newly visible panel
        if (isTarget && typeof Plotly !== "undefined") {
            panel.querySelectorAll("[data-plotly]").forEach(function (el) {
                Plotly.Plots.resize(el);
            });
        }
    });
});

// --- HTMX utilities ---

// Clear any stuck htmx-request classes on page load
document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".htmx-request").forEach(function (el) {
        el.classList.remove("htmx-request");
    });
    document.querySelectorAll(".htmx-indicator").forEach(function (el) {
        el.style.display = "none";
    });
});

// Re-render Plotly charts after HTMX swaps content
document.body.addEventListener("htmx:afterSwap", function (event) {
    var charts = event.detail.target.querySelectorAll("[data-plotly]");
    charts.forEach(function (el) {
        try {
            var data = JSON.parse(el.getAttribute("data-plotly"));
            var layout = Object.assign({}, data.layout, getPlotlyThemeOverrides());
            Plotly.newPlot(el, data.data, layout, { responsive: true });
        } catch (e) {
            console.error("Failed to render Plotly chart:", e);
        }
    });

    // Update contamination slider labels
    var sliders = event.detail.target.querySelectorAll(
        'input[name="contamination"]'
    );
    sliders.forEach(function (slider) {
        var label = slider.nextElementSibling;
        if (label && label.tagName === "SMALL") {
            label.textContent =
                Math.round(slider.value * 100) +
                "% — proportion of data expected to be anomalous";
        }
        slider.addEventListener("input", function () {
            var label = this.nextElementSibling;
            if (label && label.tagName === "SMALL") {
                label.textContent =
                    Math.round(this.value * 100) +
                    "% — proportion of data expected to be anomalous";
            }
        });
    });
});

// Handle HTMX response errors
document.body.addEventListener("htmx:responseError", function (event) {
    var target = event.detail.target;
    target.innerHTML =
        '<div class="error-message"><p>An error occurred. Please try again.</p></div>';
});

// Handle HTMX send errors (network failures)
document.body.addEventListener("htmx:sendError", function (event) {
    var target = event.detail.target;
    target.innerHTML =
        '<div class="error-message"><p>Network error. Please check your connection and try again.</p></div>';
});

// Handle HTMX timeout
document.body.addEventListener("htmx:timeout", function (event) {
    var target = event.detail.target;
    target.innerHTML =
        '<div class="error-message"><p>Request timed out. The dataset may be too large or the server is busy.</p></div>';
});
