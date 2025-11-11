// Updated component form logic (Nov 2025) — client-side fix applied
// Hardened option construction to prefer label/type and to attach dataset metadata.

(function () {
  const log = (...a) => console.log("[component_form]", ...a);

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

  function initForm() {
    const cfg = window.COMPONENT_FORM_CONFIG || {};
    const urls = cfg.urls || {};
    const sel = cfg.selectors || {};

    log("initForm — urls:", urls, "selectors:", sel);

    // Selectors
    const categoryEl = document.querySelector(sel.categorySelect || "#id_inventory_category");
    const qualityEl = document.querySelector(sel.qualitySelect || "#component_quality_select");
    const productEl = document.querySelector(sel.productSelect || "#component_product_select");

    const logisticsEl = document.querySelector(sel.logisticsInput || "#id_logistics_percent");

    const costEl = document.querySelector(sel.costInput || "#id_cost_per_unit");
    const widthEl = document.querySelector(sel.widthInput || "#id_width");
    const widthUomEl = document.querySelector(sel.widthUomInput || "#id_width_uom");
    const finalPriceEl = document.querySelector(sel.finalPriceInput || "#id_final_price_per_unit");
    const pricePerSqftEl = document.querySelector(sel.pricePerSqftInput || "#id_price_per_sqfoot");
    const finalCostEl = document.querySelector(sel.finalCostInput || "#id_final_cost");

    const hiddenCT = document.querySelector(sel.hiddenCT || "#id_inventory_content_type");
    const hiddenOID = document.querySelector(sel.hiddenOID || "#id_inventory_object_id");

    const typeEl = document.querySelector(sel.typeInput || "#id_type");
    const nameField = document.querySelector("#id_name"); // may not exist in UI but kept for safety

    const CSRF_TOKEN =
      cfg.csrfToken || (document.querySelector('input[name="csrfmiddlewaretoken"]') || {}).value || "";

    // ---------- Helpers ----------
    const clearSelect = (el, placeholder) => {
      if (!el) return;
      el.innerHTML = "";
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = placeholder || "-- Select --";
      el.appendChild(opt);
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
      if (!res.ok) {
        const txt = await res.text().catch(() => "");
        throw new Error(res.status + " on " + full + " " + txt);
      }
      return res.json();
    }

    // ---------- Load Qualities ----------
    async function loadQualitiesByCategory(category) {
      if (!qualityEl) return;

      // remember currently selected value so we can restore it if present
      const prevSelected = qualityEl.value || "";

      clearSelect(qualityEl, "-- Loading qualities... --");
      if (productEl) clearSelect(productEl, "-- Select type after quality --");
      setHidden("", "", "");
      if (!category) {
        clearSelect(qualityEl, "-- Select category first --");
        return;
      }
      try {
        const json = await safeFetch(urls.qualities_by_category, { category });
        const results = json.results || [];
        if (!results.length) {
          clearSelect(qualityEl, "-- No qualities found --");
          return;
        }
        clearSelect(qualityEl, "-- Select quality --");

        results.forEach((r) => {
          // normalize source fields (support many server shapes)
          const id = r.id !== undefined && r.id !== null ? String(r.id) : null;
          const value = r.value !== undefined && r.value !== null ? String(r.value) : id || (r.label !== undefined && r.label !== null ? String(r.label) : "");
          const label = r.label !== undefined && r.label !== null ? String(r.label) : (r.label_text !== undefined && r.label_text !== null ? String(r.label_text) : (id || String(value)));
          const opt = document.createElement("option");

          // value: prefer explicit value, then id, then label
          opt.value = value !== null ? value : "";

          // visible text: prefer label, fall back to id or value
          opt.textContent = label;

          // helpful metadata for debugging/consumers
          if (id) opt.dataset.id = id;
          if (label) opt.dataset.label = label;
          if (r.extra !== undefined) opt.dataset.extra = String(r.extra);

          qualityEl.appendChild(opt);
        });

        // restore previous selection if still valid
        if (prevSelected) {
          try {
            qualityEl.value = prevSelected;
            // force a change event to ensure UI reacts if value restored
            const ev = new Event("change", { bubbles: true });
            qualityEl.dispatchEvent(ev);
          } catch (e) {
            // ignore invalid restore
          }
        }
      } catch (err) {
        console.error("loadQualitiesByCategory error", err);
        clearSelect(qualityEl, "-- Error loading qualities --");
      }
    }

    // ---------- Load Types ----------
    async function loadTypesByQuality(category, quality, search_q) {
      if (!productEl) return;
      const prevSelected = productEl.value || "";

      clearSelect(productEl, "-- Loading product types... --");
      setHidden("", "", "");
      if (!category || !quality) {
        clearSelect(productEl, "-- Select quality first --");
        return;
      }
      try {
        const json = await safeFetch(urls.types_by_quality, { category, quality, q: search_q || "" });
        const results = json.results || [];
        if (!results.length) {
          clearSelect(productEl, "-- No types found --");
          return;
        }
        clearSelect(productEl, "-- Select type --");

        // Build options, preferring an explicit 'type' field from server.
        results.forEach((r) => {
          // normalize common server shapes
          const id = r.id !== undefined && r.id !== null ? String(r.id) : null;
          const value = r.value !== undefined && r.value !== null ? String(r.value) : id || (r.label !== undefined && r.label !== null ? String(r.label) : "");
          const rawType = (r.type !== undefined && r.type !== null) ? String(r.type).trim() : "";
          const label = (r.label !== undefined && r.label !== null) ? String(r.label).trim() : (rawType || (id ? `#${id}` : value));

          const o = document.createElement("option");
          o.value = value !== null ? value : "";

          // prefer explicit type text to show in the UI; fall back to label, then id
          if (rawType) {
            o.textContent = rawType;
            o.dataset.type = rawType;
          } else if (label) {
            o.textContent = label;
            o.dataset.type = label;
          } else {
            o.textContent = id ? `#${id}` : value;
            o.dataset.type = "";
          }

          // content type id mapping (support multiple field names)
          const ctVal = r.content_type_id || r.content_type || r.ct || "";
          if (ctVal !== undefined && ctVal !== null && String(ctVal).trim() !== "") {
            o.dataset.ct = String(ctVal);
          } else {
            o.dataset.ct = "";
          }

          // attach metadata for debugging or future logic
          if (id) o.dataset.id = id;
          if (label) o.dataset.label = label;

          productEl.appendChild(o);
        });

        // restore previous selection if still valid
        if (prevSelected) {
          try {
            productEl.value = prevSelected;
            const ev = new Event("change", { bubbles: true });
            productEl.dispatchEvent(ev);
          } catch (e) {
            // ignore invalid restore
          }
        }
      } catch (err) {
        console.error("loadTypesByQuality error", err);
        clearSelect(productEl, "-- Error loading types --");
      }
    }

    // ---------- Fetch Inventory Item ----------
    async function fetchInventoryItem(ct, oid, quality) {
      try {
        const json = await safeFetch(urls.inventory_item, {
          content_type_id: ct,
          object_id: oid,
          quality: quality || "",
          logistics_percent: logisticsEl ? (logisticsEl.value || "") : "",
        });
        return json;
      } catch (err) {
        console.error("fetchInventoryItem error", err);
        return null;
      }
    }

    // ---------- Local Compute ----------
    function computeClientMetrics(priceStr, widthStr, widthUom, logisticsStr) {
      const parseNum = (v, fallback = 0) => {
        const n = Number(String(v || "").replace(/[^0-9.\-]/g, ""));
        return Number.isFinite(n) ? n : fallback;
      };
      const price = parseNum(priceStr);
      const width = parseNum(widthStr);
      const logistics = parseNum(logisticsStr);
      const finalPricePerUnit = +(price * (1 + logistics / 100)).toFixed(2);
      let widthInInch = width;
      const u = (widthUom || "inch").toLowerCase();
      if (["cm", "centimeter", "centimetre", "cms"].includes(u)) widthInInch = width / 2.54;
      let pricePerSqft = 0;
      try {
        const denom = ((widthInInch * 2.54) / 1.07) / 100;
        if (denom > 0) pricePerSqft = finalPricePerUnit / denom;
      } catch (e) {}
      return {
        final_price_per_unit: finalPricePerUnit.toFixed(2),
        price_per_sqfoot: pricePerSqft.toFixed(4),
        final_cost: finalPricePerUnit.toFixed(2), // size=1 default
      };
    }

    // ---------- Populate Fields ----------
    async function populateFromItemResponse(json) {
      if (!json) return;
      const cost = json.cost_per_unit || json.price || "";
      const width = json.width || "";
      const width_uom = json.width_uom || "inch";
      const final_price_server = json.final_price_per_unit || "";
      const price_per_sqft_server = json.price_per_sqfoot || "";
      const final_cost_server = json.final_cost || "";

      if (costEl && cost !== "") costEl.value = cost;
      if (widthEl && width !== "") widthEl.value = width;
      if (widthUomEl && width_uom !== "") widthUomEl.value = width_uom;
      if (finalPriceEl && final_price_server !== "") finalPriceEl.value = final_price_server;
      if (pricePerSqftEl && price_per_sqft_server !== "") pricePerSqftEl.value = price_per_sqft_server;
      if (finalCostEl && final_cost_server !== "") finalCostEl.value = final_cost_server;

      // --- Fill TYPE (use json.type when available, fallback to label)
      if (typeEl) {
        if (json.type) {
          typeEl.value = json.type;
        } else if (json.label) {
          typeEl.value = json.label;
        } else if (hiddenOID && hiddenOID.value) {
          typeEl.value = "Type #" + hiddenOID.value;
        } else {
          typeEl.value = "";
        }
      }

      // --- Auto-generate NAME = Quality + Type (visible only if form has it)
      try {
        const qualityName = qualityEl ? (qualityEl.value || "").trim() : "";
        const typeName = typeEl ? (typeEl.value || "").trim() : "";
        if (nameField) {
          nameField.value =
            qualityName && typeName ? `${qualityName} ${typeName}` : typeName || qualityName;
        }
      } catch (e) {
        console.warn("Auto-name generation failed", e);
      }

      // compute client metrics if any missing
      const clientMetrics = computeClientMetrics(
        cost || "",
        width || "",
        width_uom || "inch",
        logisticsEl ? logisticsEl.value || "0" : "0"
      );

      if (finalPriceEl && (!finalPriceEl.value || finalPriceEl.value === ""))
        finalPriceEl.value = clientMetrics.final_price_per_unit;
      if (pricePerSqftEl && (!pricePerSqftEl.value || pricePerSqftEl.value === ""))
        pricePerSqftEl.value = clientMetrics.price_per_sqfoot;
      if (finalCostEl && (!finalCostEl.value || finalCostEl.value === ""))
        finalCostEl.value = clientMetrics.final_cost;
    }

    // ---------- Event Handlers ----------
    if (categoryEl) {
      categoryEl.addEventListener("change", (ev) => {
        const category = (ev.target.value || "").toUpperCase();
        loadQualitiesByCategory(category);
        clearSelect(productEl, "-- Select quality first --");
        setHidden("", "", "");
        [costEl, widthEl, widthUomEl, finalPriceEl, pricePerSqftEl, finalCostEl].forEach(
          (el) => el && (el.value = "")
        );
        if (typeEl) typeEl.value = "";
        if (nameField) nameField.value = "";
      });
    }

    if (qualityEl) {
      qualityEl.addEventListener("change", (ev) => {
        const q = (ev.target.value || "").toString();
        const category = categoryEl ? categoryEl.value.toUpperCase() : "";
        loadTypesByQuality(category, q);
        clearSelect(productEl, "-- Loading product types --");
        setHidden("", "", "");
        [costEl, widthEl, widthUomEl, finalPriceEl, pricePerSqftEl, finalCostEl].forEach(
          (el) => el && (el.value = "")
        );
        if (typeEl) typeEl.value = "";
        if (nameField) nameField.value = "";
      });
    }

    if (productEl) {
      productEl.addEventListener("change", async (ev) => {
        const idx = ev.target.selectedIndex;
        const opt = ev.target.options[idx];
        const oid = ev.target.value || "";
        const ct = opt ? opt.dataset.ct || "" : "";
        const label = opt ? (opt.dataset.label || opt.textContent || "") : "";
        const optType = opt ? (opt.dataset.type || "") : "";
        setHidden(ct, oid, optType || label);

        if (ct && oid) {
          const quality = qualityEl ? (qualityEl.value || "") : "";
          const json = await fetchInventoryItem(ct, oid, quality);
          await populateFromItemResponse(json);

          // Regenerate name
          const qualityVal = qualityEl ? (qualityEl.value || "").trim() : "";
          const typeVal = typeEl ? (typeEl.value || "").trim() : "";
          if (nameField)
            nameField.value =
              qualityVal && typeVal ? `${qualityVal} ${typeVal}` : typeVal || qualityVal;
        }
      });
    }

    // Recompute metrics when logistics changes
    if (logisticsEl) {
      logisticsEl.addEventListener("input", () => {
        const price = costEl ? costEl.value || "" : "";
        const width = widthEl ? widthEl.value || "" : "";
        const widthUom = widthUomEl ? widthUomEl.value || "inch" : "inch";
        const logistics = logisticsEl.value || "0";
        const metrics = computeClientMetrics(price, width, widthUom, logistics);
        if (finalPriceEl) finalPriceEl.value = metrics.final_price_per_unit;
        if (pricePerSqftEl) pricePerSqftEl.value = metrics.price_per_sqfoot;
        if (finalCostEl) finalCostEl.value = metrics.final_cost;
      });
    }

    // ---------- Initial Restore ----------
    (async function initialStateRestore() {
      try {
        const initialCategory = categoryEl ? categoryEl.value || "" : "";
        const initialQuality = qualityEl ? qualityEl.value || "" : "";
        const initialProduct = productEl ? productEl.value || "" : "";
        if (initialCategory) {
          await loadQualitiesByCategory(initialCategory.toUpperCase());
          if (initialQuality) {
            qualityEl.value = initialQuality;
            await loadTypesByQuality(initialCategory.toUpperCase(), initialQuality);
            if (initialProduct) {
              productEl.value = initialProduct;
              const opt = productEl.options[productEl.selectedIndex];
              const ct = opt ? opt.dataset.ct || "" : "";
              if (ct && initialProduct) {
                setHidden(ct, initialProduct, opt ? (opt.dataset.type || opt.dataset.label || opt.textContent) : "");
                const json = await fetchInventoryItem(ct, initialProduct, initialQuality);
                await populateFromItemResponse(json);
              }
            }
          }
        }
      } catch (err) {
        log("initialStateRestore error", err);
      }
    })();
  }
})();
