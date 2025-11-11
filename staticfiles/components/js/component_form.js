// static/components/js/component_form.js
// Robust frontend logic for the component form (product + quality + cost).
// Waits for DOM and COMPONENT_FORM_CONFIG before running.

(function () {
  // Utility logger
  const log = (...a) => console.log("[component_form]", ...a);

  // --- Wait until DOM is ready and config is available ---
  function ready(fn) {
    if (document.readyState === "complete" || document.readyState === "interactive") {
      setTimeout(fn, 0);
    } else {
      document.addEventListener("DOMContentLoaded", fn);
    }
  }

  function waitForConfig(callback, tries = 0) {
    if (window.COMPONENT_FORM_CONFIG && window.COMPONENT_FORM_CONFIG.urls) {
      callback();
      return;
    }
    if (tries > 40) {
      console.error("[component_form] COMPONENT_FORM_CONFIG never found.");
      return;
    }
    setTimeout(() => waitForConfig(callback, tries + 1), 100);
  }

  ready(() => waitForConfig(initForm));

  // -------------------------------------------------------------------

  function initForm() {
    const cfg = window.COMPONENT_FORM_CONFIG || {};
    const urls = cfg.urls || {};
    const sel = cfg.selectors || {};
    log("Initialized with URLs", urls);

    const categoryEl = document.querySelector(sel.categorySelect || "#id_inventory_category");
    const productSelect = document.querySelector(sel.productSelect || "#component_product_select");
    const qualitySelect = document.querySelector(sel.qualitySelect || "#component_quality_select");
    const sizeInput = document.querySelector(sel.sizeInput || "#id_size");
    const logisticsInput = document.querySelector(sel.logisticsInput || "#id_logistics_percent");
    const costInput = document.querySelector(sel.costInput || "#id_cost_per_unit");
    const finalCostInput = document.querySelector(sel.finalCostInput || "#id_final_cost");
    const hiddenCT = document.querySelector(sel.hiddenCT || "#id_inventory_content_type");
    const hiddenOID = document.querySelector(sel.hiddenOID || "#id_inventory_object_id");
    const CSRF_TOKEN =
      cfg.csrfToken || (document.querySelector('input[name="csrfmiddlewaretoken"]') || {}).value;

    const clearSelect = (el, text) => {
      if (!el) return;
      el.innerHTML = "";
      const o = document.createElement("option");
      o.value = "";
      o.textContent = text || "-- Select --";
      el.appendChild(o);
    };

    const setHidden = (ct, oid, label) => {
      if (hiddenCT) hiddenCT.value = ct || "";
      if (hiddenOID) hiddenOID.value = oid || "";
      const help = document.getElementById("component_product_help");
      if (help) help.textContent = label || "";
    };

    async function safeFetch(url, params) {
      if (!url) throw new Error("URL not configured");
      const q = new URLSearchParams(params || {}).toString();
      const full = url + (q ? "?" + q : "");
      const res = await fetch(full, {
        credentials: "same-origin",
        headers: { "X-CSRFToken": CSRF_TOKEN, Accept: "application/json" },
      });
      if (!res.ok) throw new Error(res.status + " on " + full);
      return res.json();
    }

    async function loadProducts(category) {
      log("loadProducts", category);
      if (!urls.inventory_items) {
        clearSelect(productSelect, "-- Error: missing endpoint --");
        console.error("inventory_items URL missing in COMPONENT_FORM_CONFIG");
        return;
      }
      clearSelect(productSelect, "-- Loading products... --");
      clearSelect(qualitySelect, "-- Select quality --");
      setHidden("", "", "");

      if (!category) {
        clearSelect(productSelect, "-- Select product (choose category first) --");
        return;
      }

      try {
        const json = await safeFetch(urls.inventory_items, { category });
        const results = json.results || [];
        if (!results.length) {
          clearSelect(productSelect, "-- No products found --");
          return;
        }
        results.forEach((r) => {
          const opt = document.createElement("option");
          opt.value = r.id;
          opt.textContent = r.label || r.name || `#${r.id}`;
          if (r.content_type_id) opt.dataset.ct = r.content_type_id;
          productSelect.appendChild(opt);
        });
      } catch (e) {
        console.error("loadProducts error", e);
        clearSelect(productSelect, "-- Error loading products --");
      }
    }

    async function loadQualities(ct, oid) {
      if (!urls.inventory_qualities) return;
      clearSelect(qualitySelect, "-- Loading qualities... --");
      try {
        const json = await safeFetch(urls.inventory_qualities, {
          content_type_id: ct,
          object_id: oid,
        });
        const results = json.results || [];
        clearSelect(qualitySelect, results.length ? "-- Select quality --" : "-- None --");
        results.forEach((r) => {
          const opt = document.createElement("option");
          opt.value = r.id;
          opt.textContent = r.label || r.id;
          qualitySelect.appendChild(opt);
        });
      } catch (e) {
        console.error("loadQualities error", e);
        clearSelect(qualitySelect, "-- Error --");
      }
    }

    async function refreshCost() {
      if (!urls.inventory_cost) return;
      const ct = hiddenCT?.value, oid = hiddenOID?.value;
      if (!ct || !oid) return;
      try {
        const data = await safeFetch(urls.inventory_cost, {
          content_type_id: ct,
          object_id: oid,
          quality: qualitySelect?.value || "",
          size: sizeInput?.value || "",
          logistics_percent: logisticsInput?.value || "",
        });
        if (costInput && data.cost_per_unit) costInput.value = data.cost_per_unit;
        if (finalCostInput && data.final_cost) finalCostInput.value = data.final_cost;
      } catch (e) {
        console.error("refreshCost", e);
      }
    }

    // Event bindings
    if (categoryEl)
      categoryEl.addEventListener("change", (e) =>
        loadProducts(e.target.value.toUpperCase())
      );
    if (productSelect)
      productSelect.addEventListener("change", (e) => {
        const opt = e.target.options[e.target.selectedIndex];
        const ct = opt?.dataset.ct || "";
        const oid = e.target.value || "";
        setHidden(ct, oid, opt?.textContent);
        if (ct && oid) loadQualities(ct, oid).then(refreshCost);
      });
    if (qualitySelect) qualitySelect.addEventListener("change", refreshCost);
    if (sizeInput) sizeInput.addEventListener("input", refreshCost);
    if (logisticsInput) logisticsInput.addEventListener("input", refreshCost);
  }
})();
