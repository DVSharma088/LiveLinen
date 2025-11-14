(function () {
  "use strict";

  // CSRF helpers
  function getCookie(name) {
    if (!document.cookie) return null;
    const cookies = document.cookie.split(";").map(c => c.trim());
    for (let cookie of cookies) {
      if (cookie.startsWith(name + "=")) {
        return decodeURIComponent(cookie.split("=")[1]);
      }
    }
    return null;
  }
  const csrftoken = getCookie("csrftoken");

  function setLoading(btn, isLoading) {
    if (!btn) return;
    if (isLoading) {
      btn.dataset.orig = btn.innerHTML;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Please wait';
      btn.disabled = true;
    } else {
      if (btn.dataset.orig) btn.innerHTML = btn.dataset.orig;
      btn.disabled = false;
    }
  }

  // Login/Logout button
  document.addEventListener("click", function (ev) {
    const btn = ev.target.closest && ev.target.closest("#login-time-btn");
    if (!btn) return;
    ev.preventDefault();

    const form = document.querySelector("#login-time-form");
    const feedback = document.querySelector("#login-time-feedback");

    setLoading(btn, true);
    if (feedback) feedback.textContent = "Saving...";

    // always post to /dashboard/login-time/
    const action = form ? form.getAttribute("action") : "/dashboard/login-time/";

    const headers = {
      "X-CSRFToken": csrftoken,
      Accept: "application/json",
    };

    fetch(action, {
      method: "POST",
      credentials: "same-origin",
      headers,
    })
      .then(async (res) => {
        if (!res.ok) {
          const txt = await res.text().catch(() => "");
          throw new Error("Server error: " + (txt || res.statusText));
        }
        return res.json().catch(() => {
          throw new Error("Invalid JSON response");
        });
      })
      .then((data) => {
        if (data && data.ok && data.attendance) {
          const att = data.attendance;
          // update UI: change button label and show times
          if (att.logout_time && att.login_time) {
            btn.innerText = "Login";
            if (feedback) feedback.innerText = `Logged out at ${new Date(att.logout_time).toLocaleString()}`;
          } else if (att.login_time && !att.logout_time) {
            btn.innerText = "Logout";
            if (feedback) feedback.innerText = `Logged in at ${new Date(att.login_time).toLocaleString()}`;
          } else {
            if (feedback) feedback.innerText = "Attendance recorded";
          }
          // reload to update other widgets
          setTimeout(() => window.location.reload(), 900);
        } else {
          throw new Error((data && data.error) || "Unexpected server response");
        }
      })
      .catch((err) => {
        console.error("Attendance error", err);
        if (feedback) feedback.innerText = err.message || "Could not record attendance";
      })
      .finally(() => setLoading(btn, false));
  });

  // Generic AJAX form submit handler for forms with class "ajax-form"
  document.addEventListener("submit", function (ev) {
    const form = ev.target;
    if (!form.classList || !form.classList.contains("ajax-form")) return; // ignore non-ajax forms
    ev.preventDefault();

    const submitBtn = form.querySelector('button[type="submit"]') || form.querySelector('input[type="submit"]');
    setLoading(submitBtn, true);

    const url = form.getAttribute("action") || window.location.href;
    const method = (form.getAttribute("method") || "POST").toUpperCase();

    const fd = new FormData(form);

    const headers = {
      "X-CSRFToken": csrftoken,
      Accept: "text/html, application/json",
    };

    fetch(url, {
      method,
      credentials: "same-origin",
      headers,
      body: fd,
    })
      .then(async (res) => {
        if (res.redirected) {
          window.location.href = res.url;
          return;
        }
        if (!res.ok) {
          const text = await res.text().catch(() => "");
          throw new Error(text || res.statusText);
        }
        window.location.reload();
      })
      .catch((err) => {
        console.error("Form submit error", err);
        let errBox = form.querySelector(".form-submit-error");
        if (!errBox) {
          errBox = document.createElement("div");
          errBox.className = "form-submit-error alert alert-danger mt-3";
          form.prepend(errBox);
        }
        errBox.innerText = err.message || "Could not submit form";
      })
      .finally(() => setLoading(submitBtn, false));
  });

  // ------------------------------
  // Chart rendering (Chart.js)
  // ------------------------------
  function safeGet(obj, path, fallback) {
    try {
      return path.split(".").reduce((o, p) => (o && o[p] !== undefined ? o[p] : undefined), obj) ?? fallback;
    } catch (e) {
      return fallback;
    }
  }

  function renderDashboardCharts() {
    // Ensure Chart.js is loaded
    if (typeof Chart === "undefined") {
      // Chart may be loaded via template CDN; if missing just skip gracefully.
      // Developer note: ensure template includes Chart.js before this script.
      console.warn("Chart.js not found — skip rendering dashboard charts.");
      return;
    }

    // Read chart state injected by template into window.__LIVE_LINEN_CHARTS
    const chartsState = window.__LIVE_LINEN_CHARTS || {};
    const inventoryPie = chartsState.inventoryPie || null;
    const ordersLine = chartsState.ordersLine || null;

    // Keep created chart instances so we can destroy/recreate if needed
    window.__LIVE_LINEN_CHARTS._instances = window.__LIVE_LINEN_CHARTS._instances || {};

    // ---------- PIE CHART (Inventory) ----------
    try {
      const pieEl = document.getElementById("inventoryPieChart");
      if (pieEl && inventoryPie && Array.isArray(inventoryPie.labels) && Array.isArray(inventoryPie.values)) {
        // if an instance exists, destroy to avoid duplication
        if (window.__LIVE_LINEN_CHARTS._instances.inventoryPie instanceof Chart) {
          try { window.__LIVE_LINEN_CHARTS._instances.inventoryPie.destroy(); } catch (e) { /* ignore */ }
        }

        const pieConfig = {
          type: "pie",
          data: {
            labels: inventoryPie.labels,
            datasets: [{
              label: "Items added (last 7 days)",
              data: inventoryPie.values.map(v => Number(v) || 0),
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: "bottom" },
              tooltip: { enabled: true }
            }
          }
        };

        // Set the canvas parent to a fixed height so Chart.js can size correctly
        pieEl.style.maxHeight = "320px";
        pieEl.style.width = "100%";
        window.__LIVE_LINEN_CHARTS._instances.inventoryPie = new Chart(pieEl.getContext("2d"), pieConfig);
      } else {
        // no data or no element — skip quietly
      }
    } catch (err) {
      console.error("Error rendering inventory pie chart:", err);
    }

    // ---------- LINE CHART (Orders per week) ----------
    try {
      const lineEl = document.getElementById("ordersLineChart");
      if (lineEl && ordersLine && Array.isArray(ordersLine.labels) && Array.isArray(ordersLine.values)) {
        if (window.__LIVE_LINEN_CHARTS._instances.ordersLine instanceof Chart) {
          try { window.__LIVE_LINEN_CHARTS._instances.ordersLine.destroy(); } catch (e) { /* ignore */ }
        }

        // Try to coerce labels to readable strings and values to numbers
        const labels = ordersLine.labels.map(l => (l === null || l === undefined) ? "" : String(l));
        const values = ordersLine.values.map(v => {
          const n = Number(v);
          return Number.isFinite(n) ? n : 0;
        });

        const lineConfig = {
          type: "line",
          data: {
            labels: labels,
            datasets: [{
              label: "Issues per week",
              data: values,
              fill: false,
              tension: 0.25,
              pointRadius: 4,
              pointHoverRadius: 6,
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: "top" },
              tooltip: { enabled: true }
            },
            scales: {
              x: {
                display: true,
                title: { display: true, text: "Week starting" }
              },
              y: {
                display: true,
                title: { display: true, text: "Count" },
                beginAtZero: true,
                ticks: { precision: 0 }
              }
            }
          }
        };

        lineEl.style.maxHeight = "320px";
        lineEl.style.width = "100%";
        window.__LIVE_LINEN_CHARTS._instances.ordersLine = new Chart(lineEl.getContext("2d"), lineConfig);
      } else {
        // no data or no element — skip quietly
      }
    } catch (err) {
      console.error("Error rendering orders line chart:", err);
    }
  }

  // Render charts on DOMContentLoaded (and also attempt again if Chart.js loads later)
  function tryInitCharts() {
    try {
      renderDashboardCharts();
    } catch (e) {
      console.error("Failed to initialize charts:", e);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", tryInitCharts);
  } else {
    tryInitCharts();
  }

  // Also observe if Chart.js is added dynamically later (rare) — then re-run rendering
  // This is conservative: if Chart becomes available after initial load, we still render.
  (function watchForChartJs() {
    if (typeof Chart !== "undefined") return;
    let attempts = 0;
    const maxAttempts = 10;
    const interval = setInterval(function () {
      attempts += 1;
      if (typeof Chart !== "undefined") {
        tryInitCharts();
        clearInterval(interval);
      } else if (attempts >= maxAttempts) {
        clearInterval(interval);
      }
    }, 500);
  })();

})();
