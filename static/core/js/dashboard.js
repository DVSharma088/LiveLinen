(function () {
  "use strict";

  // -------------------------
  // Helpers
  // -------------------------
  function ensureCanvasHeight(canvasEl, px) {
    if (!canvasEl) return;
    try {
      canvasEl.style.height = px + "px";
      canvasEl.style.maxHeight = px + "px";
      canvasEl.style.width = "100%";
      canvasEl.height = px; // actual drawing buffer
    } catch (e) {
      console.warn("ensureCanvasHeight failed", e);
    }
  }

  function padArrayToLength(arr, len) {
    const a = Array.isArray(arr) ? arr.slice(0) : [];
    while (a.length < len) a.push(0);
    if (a.length > len) return a.slice(a.length - len);
    return a;
  }

  function makeDataset(label, dataArr, opts = {}) {
    return {
      label: label,
      data: (dataArr || []).map((v) => {
        const n = Number(v);
        return Number.isFinite(n) ? n : 0;
      }),
      tension: opts.tension !== undefined ? opts.tension : 0.25,
      fill: opts.fill !== undefined ? opts.fill : false,
      pointRadius: opts.pointRadius !== undefined ? opts.pointRadius : 3,
      hidden: !!opts.hidden,
      borderDash: opts.borderDash || undefined,
    };
  }

  function createPie(canvasId, payload) {
    const el = document.getElementById(canvasId);
    if (!el) {
      console.warn("Missing canvas:", canvasId);
      return null;
    }
    ensureCanvasHeight(el, 260);
    const ctx = el.getContext && el.getContext("2d");
    if (!ctx) {
      console.error("No 2D context for", canvasId);
      return null;
    }
    try {
      return new Chart(ctx, {
        type: "pie",
        data: {
          labels: payload.labels || [],
          datasets: [{ data: (payload.values || []).map((v) => Number(v) || 0) }],
        },
        options: { responsive: true, maintainAspectRatio: false },
      });
    } catch (e) {
      console.error("createPie error", e);
      return null;
    }
  }

  function createLine(canvasId, labels, dataArr, opts) {
    const el = document.getElementById(canvasId);
    if (!el) {
      console.warn("Missing canvas:", canvasId);
      return null;
    }
    ensureCanvasHeight(el, 260);
    const ctx = el.getContext && el.getContext("2d");
    if (!ctx) {
      console.error("No 2D context for", canvasId);
      return null;
    }
    try {
      return new Chart(ctx, {
        type: "line",
        data: {
          labels: labels || [],
          datasets: [
            {
              label: opts.label || "",
              data: (dataArr || []).map((v) => Number(v) || 0),
              tension: opts.tension || 0.25,
              fill: false,
              pointRadius: opts.pointRadius || 3,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: { y: { beginAtZero: true } },
        },
      });
    } catch (e) {
      console.error("createLine error", e);
      return null;
    }
  }

  // -------------------------
  // Stock chart builder (no Totals line)
  // -------------------------
  function createStockUsedChart(payload) {
    const el = document.getElementById("stockUsedChart");
    if (!el) {
      console.warn("Missing canvas: stockUsedChart");
      return null;
    }
    ensureCanvasHeight(el, 260);
    const ctx = el.getContext && el.getContext("2d");
    if (!ctx) {
      console.error("No 2D context for stockUsedChart");
      return null;
    }

    const labels = payload.labels || [];
    const len = labels.length || 0;

    // new series (ensure padded to same length)
    const fabricSeries = padArrayToLength(payload.fabric_added || [], len);
    const accessoriesSeries = padArrayToLength(payload.accessories_used || [], len);
    const printedSeries = padArrayToLength(payload.printed_added || [], len);

    // build datasets in deterministic order:
    // 0: Fabric added
    // 1: Accessories used
    // 2: Printed added
    // 3..: Orders (hidden)
    const datasets = [];
    datasets.push(makeDataset("Fabric added", fabricSeries, { tension: 0.2, pointRadius: 3, hidden: false }));
    datasets.push(makeDataset("Accessories used", accessoriesSeries, { tension: 0.2, pointRadius: 3, hidden: false, borderDash: [6, 4] }));
    datasets.push(makeDataset("Printed added", printedSeries, { tension: 0.2, pointRadius: 3, hidden: false }));

    // append per-order datasets (kept hidden by default)
    const ordersObj = payload.orders || {};
    const orderKeys = Object.keys(ordersObj || {});
    orderKeys.forEach((orderNo) => {
      const arr = padArrayToLength(ordersObj[orderNo] || [], len);
      datasets.push(
        makeDataset("Order #" + orderNo, arr, { hidden: true, tension: 0.2, pointRadius: 3, borderDash: [6, 4] })
      );
    });

    try {
      return new Chart(ctx, {
        type: "line",
        data: { labels: labels, datasets: datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "nearest", axis: "x", intersect: false },
          plugins: {
            legend: { position: "top" },
            tooltip: {
              callbacks: {
                label: function (context) {
                  const val = context.raw;
                  return (context.dataset.label || "") + ": " + (val === null ? "0" : val);
                },
              },
            },
          },
          scales: {
            x: { title: { display: true, text: "Date" }, ticks: { autoSkip: false } },
            y: { title: { display: true, text: "Quantity" }, beginAtZero: true },
          },
        },
      });
    } catch (e) {
      console.error("createStockUsedChart error", e);
      return null;
    }
  }

  // -------------------------
  // Initialization (wait for Chart & DOM)
  // -------------------------
  function initWhenReady(fn) {
    function readyCheck() {
      if (typeof Chart !== "undefined" && document.readyState !== "loading") {
        try {
          fn();
        } catch (err) {
          console.error("initWhenReady fn error", err);
        }
        return true;
      }
      return false;
    }
    if (!readyCheck()) {
      let attempts = 0;
      const max = 40;
      const interval = setInterval(() => {
        attempts++;
        if (readyCheck() || attempts >= max) clearInterval(interval);
      }, 200);
    }
  }

  initWhenReady(function () {
    const state = window.__LIVE_LINEN_CHARTS || {};

    // destroy previous instances if any (defensive)
    if (window.__dashboard_instances) {
      Object.values(window.__dashboard_instances).forEach((inst) => {
        try {
          inst.destroy();
        } catch (e) {
          /* ignore */
        }
      });
    }
    window.__dashboard_instances = window.__dashboard_instances || {};

    // inventory pie
    try {
      window.__dashboard_instances.inventoryPie = createPie(
        "inventoryPieChart",
        state.inventoryPie || { labels: [], values: [] }
      );
    } catch (e) {
      console.error(e);
    }

    // orders line
    try {
      const ord = state.ordersLine || { labels: [], values: [] };
      window.__dashboard_instances.ordersLine = createLine(
        "ordersLineChart",
        ord.labels || [],
        ord.values || [],
        { label: "Issues per week" }
      );
    } catch (e) {
      console.error(e);
    }

    // stock used (without Totals)
    try {
      window.__dashboard_instances.stockUsed = createStockUsedChart(state.stockUsed || { labels: [], totals: [], orders: {} });
    } catch (e) {
      console.error(e);
    }

    // ---------- wire orderSelect behavior ----------
    try {
      const sel = document.getElementById("orderSelect");
      const chart = window.__dashboard_instances.stockUsed;
      if (sel && chart) {
        // populate select
        sel.innerHTML = '<option value="__none__">— Show totals only —</option>';
        const orders = state.stockUsed && state.stockUsed.orders ? Object.keys(state.stockUsed.orders) : [];
        orders.forEach((orderNo) => {
          const o = document.createElement("option");
          o.value = orderNo;
          o.textContent = orderNo;
          sel.appendChild(o);
        });

        sel.addEventListener("change", function () {
          const val = sel.value;
          if (!chart || !chart.data || !Array.isArray(chart.data.datasets)) return;

          // datasets layout: [Fabric, Accessories, Printed, ... orders]
          const baseOrderIndex = 3; // first order dataset index
          // hide all order datasets
          for (let i = baseOrderIndex; i < chart.data.datasets.length; i++) {
            chart.data.datasets[i].hidden = true;
          }
          if (val && val !== "__none__") {
            const targetLabel = "Order #" + val;
            for (let i = baseOrderIndex; i < chart.data.datasets.length; i++) {
              if (chart.data.datasets[i].label === targetLabel) {
                chart.data.datasets[i].hidden = false;
                break;
              }
            }
          }
          try {
            chart.update();
          } catch (e) {
            console.warn("chart.update() failed after orderSelect change:", e);
          }
        });
      }
    } catch (e) {
      console.error("orderSelect wiring error", e);
    }

    // ---------- wire checkboxes for the three series ----------
    try {
      const chart = window.__dashboard_instances.stockUsed;
      if (chart && chart.data && Array.isArray(chart.data.datasets)) {
        function toggleByLabel(lbl, checked) {
          for (let i = 0; i < chart.data.datasets.length; i++) {
            if (chart.data.datasets[i].label === lbl) {
              chart.data.datasets[i].hidden = !checked;
            }
          }
          try {
            chart.update();
          } catch (e) {
            console.warn("chart.update failed on toggle", e);
          }
        }

        const cbFabric = document.getElementById("toggleFabric");
        const cbAccessories = document.getElementById("toggleAccessories");
        const cbPrinted = document.getElementById("togglePrinted");

        if (cbFabric) {
          cbFabric.addEventListener("change", function (ev) {
            toggleByLabel("Fabric added", ev.target.checked);
          });
        }
        if (cbAccessories) {
          cbAccessories.addEventListener("change", function (ev) {
            toggleByLabel("Accessories used", ev.target.checked);
          });
        }
        if (cbPrinted) {
          cbPrinted.addEventListener("change", function (ev) {
            toggleByLabel("Printed added", ev.target.checked);
          });
        }
      }
    } catch (e) {
      console.error("checkbox wiring error", e);
    }
  });
})();
