/* DS-PAL client-side JavaScript */

// Re-render Plotly charts after HTMX swaps content
document.body.addEventListener("htmx:afterSwap", function (event) {
    var charts = event.detail.target.querySelectorAll("[data-plotly]");
    charts.forEach(function (el) {
        try {
            var data = JSON.parse(el.getAttribute("data-plotly"));
            Plotly.newPlot(el, data.data, data.layout, { responsive: true });
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
