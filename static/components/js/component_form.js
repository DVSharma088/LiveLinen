// component_form.js (updated) — improved colors integration, robust fetch helper,
// exposes window.COMPONENT_COLORS with load/render/create/delete API.
// Place this file at static/components/js/component_form.js
(function () {
  const log = (...a) => console.log("[component_form]", ...a);
  const err = (...a) => console.error("[component_form]", ...a);

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

    function getComponentIdFromPath() {
      // parse /master/<pk>/ or /master/<pk>/edit/
      const m = window.location.pathname.match(/\/master\/(\d+)(\/|$)/);
      if (m) return m[1];
      // fallback to hidden field storing the component's own id (rare)
      const hiddenComp = document.querySelector('input[name="component_id"], #id_component_id');
      if (hiddenComp && hiddenComp.value) return hiddenComp.value;
      return "";
    }

    async function safeFetch(url, params = {}, opts = {}) {
      if (!url) throw new Error("URL not configured");
      const method = (opts.method || "GET").toUpperCase();
      let fullUrl = url;
      let fetchOpts = {
        method,
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      };

      // attach CSRF for unsafe methods
      if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
        fetchOpts.headers["X-CSRFToken"] = CSRF_TOKEN;
      }

      if (method === "GET") {
        const q = new URLSearchParams(params || {}).toString();
        fullUrl = url + (q ? "?" + q : "");
      } else {
        // support both JSON and form-encoded bodies depending on opts.contentType
        if (opts.contentType === "json") {
          fetchOpts.headers["Content-Type"] = "application/json";
          fetchOpts.body = JSON.stringify(params || {});
        } else {
          // default: form urlencoded
          fetchOpts.headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8";
          fetchOpts.body = new URLSearchParams(params || {}).toString();
        }
      }

      const res = await fetch(fullUrl, fetchOpts);
      const text = await res.text().catch(() => "");
      // attempt to parse JSON; if not JSON, return text under .raw
      try {
        const json = text ? JSON.parse(text) : {};
        if (!res.ok) {
          const e = new Error(`Fetch ${res.status} ${res.statusText}`);
          e.status = res.status;
          e.body = json;
          throw e;
        }
        return json;
      } catch (parseErr) {
        // if not JSON and not ok -> throw; if ok return raw text
        if (!res.ok) {
          const e = new Error(`Fetch ${res.status} ${res.statusText}`);
          e.status = res.status;
          e.body = text;
          throw e;
        }
        return { raw: text };
      }
    }

    // ---------- Colors integration (client API) ----------
    async function loadColors(compId) {
      if (!urls.colors_list) {
        log("Colors endpoint not configured (urls.colors_list)");
        return [];
      }
      if (!compId) compId = getComponentIdFromPath();
      if (!compId) {
        log("No component id — skipping colors load");
        return [];
      }
      try {
        const json = await safeFetch(urls.colors_list, { component_id: compId });
        return json.results || [];
      } catch (e) {
        err("loadColors error", e);
        return [];
      }
    }

    async function createColor(compId, name) {
      if (!urls.color_create) throw new Error("color_create URL not configured");
      if (!compId) compId = getComponentIdFromPath();
      if (!compId) throw new Error("Missing component id for createColor");
      const payload = { component_id: compId, name: (name || "").trim() };
      if (!payload.name) throw new Error("Empty color name");
      try {
        const resp = await safeFetch(urls.color_create, payload, { method: "POST" });
        return resp;
      } catch (e) {
        err("createColor failed", e);
        throw e;
      }
    }

    async function deleteColor(colorId) {
      if (!urls.color_delete) throw new Error("color_delete URL not configured");
      if (!colorId) throw new Error("Missing color id");
      try {
        const resp = await safeFetch(urls.color_delete, { color_id: colorId }, { method: "POST" });
        return resp;
      } catch (e) {
        err("deleteColor failed", e);
        throw e;
      }
    }

    function buildColorsContainer() {
      // find or create container where colors UI will live
      let container = document.getElementById("component-colors");
      if (!container) {
        // try to append below product select as fallback
        const anchor = document.getElementById("component_product_help") || productEl || document.querySelector("form");
        container = document.createElement("div");
        container.id = "component-colors";
        container.className = "mt-3";
        if (anchor && anchor.parentNode) {
          anchor.parentNode.insertBefore(container, anchor.nextSibling);
        } else {
          document.body.appendChild(container);
        }
      }
      return container;
    }

    function defaultRenderColors(container, colors) {
      container.innerHTML = ""; // clear

      const title = document.createElement("div");
      title.className = "mb-2";
      title.innerHTML = "<strong>Colors</strong>";
      container.appendChild(title);

      // Add create box
      const createWrap = document.createElement("div");
      createWrap.className = "d-flex mb-2";
      const input = document.createElement("input");
      input.type = "text";
      input.placeholder = "Add color (e.g. Red)";
      input.className = "form-control me-2";
      const addBtn = document.createElement("button");
      addBtn.type = "button";
      addBtn.className = "btn btn-sm btn-primary";
      addBtn.textContent = "Add";
      createWrap.appendChild(input);
      createWrap.appendChild(addBtn);
      container.appendChild(createWrap);

      const list = document.createElement("div");
      list.className = "list-group";
      container.appendChild(list);

      // render items
      (colors || []).forEach((c) => {
        const item = document.createElement("div");
        item.className = "list-group-item d-flex align-items-center justify-content-between";
        const left = document.createElement("div");
        left.style.display = "flex";
        left.style.alignItems = "center";

        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.className = "form-check-input me-2 color-checkbox";
        cb.dataset.colorId = c.id;
        cb.id = `color_cb_${c.id}`;
        left.appendChild(cb);

        const lbl = document.createElement("label");
        lbl.htmlFor = cb.id;
        lbl.textContent = c.name;
        left.appendChild(lbl);

        item.appendChild(left);

        const right = document.createElement("div");
        // delete button
        const del = document.createElement("button");
        del.type = "button";
        del.className = "btn btn-sm btn-outline-danger ms-2 color-delete-btn";
        del.textContent = "Delete";
        del.dataset.colorId = c.id;
        right.appendChild(del);

        item.appendChild(right);
        list.appendChild(item);
      });

      // attach behaviors
      addBtn.addEventListener("click", async () => {
        const val = input.value && input.value.trim();
        if (!val) return;
        addBtn.disabled = true;
        try {
          const compId = getComponentIdFromPath();
          await createColor(compId, val);
          input.value = "";
          // reload and re-render
          const newColors = await loadColors();
          defaultRenderColors(container, newColors);
          dispatchColorsChanged(newColors);
        } catch (e) {
          // show friendly inline error
          window.alert((e && e.body && e.body.error) ? e.body.error : "Failed to create color");
          err("Add color error", e);
        } finally {
          addBtn.disabled = false;
        }
      });

      // delete handlers
      Array.from(container.querySelectorAll(".color-delete-btn")).forEach((b) => {
        b.addEventListener("click", async (ev) => {
          const id = ev.currentTarget.dataset.colorId;
          if (!id) return;
          if (!confirm("Delete this color? (will be marked inactive)")) return;
          try {
            await deleteColor(id);
            const newColors = await loadColors();
            defaultRenderColors(container, newColors);
            dispatchColorsChanged(newColors);
          } catch (e) {
            window.alert((e && e.body && e.body.error) ? e.body.error : "Failed to delete color");
            err("Delete color error", e);
          }
        });
      });

      // checkbox change handler -> dispatch
      Array.from(container.querySelectorAll(".color-checkbox")).forEach((cb) => {
        cb.addEventListener("change", () => {
          const checked = Array.from(container.querySelectorAll(".color-checkbox:checked")).map((x) =>
            x.dataset.colorId
          );
          // custom event so other scripts can react (eg. SKU generation)
          const ev = new CustomEvent("colorsChanged", { detail: { checkedIds: checked } });
          window.dispatchEvent(ev);
        });
      });
    }

    function dispatchColorsChanged(colors) {
      // emit event with current active color ids (all present in colors array)
      const ids = (colors || []).map((c) => String(c.id));
      const ev = new CustomEvent("colorsLoaded", { detail: { ids, colors } });
      window.dispatchEvent(ev);
    }

    // Expose a minimal API for other scripts (and templates) to use
    window.COMPONENT_COLORS = {
      load: async function (compId) {
        try {
          const cid = compId || getComponentIdFromPath();
          const colors = await loadColors(cid);
          const container = buildColorsContainer();
          // allow template-level custom renderer if provided
          if (window.COMPONENT_COLORS && typeof window.COMPONENT_COLORS.render === "function" && window.COMPONENT_COLORS._customRendererUsed) {
            // if custom renderer already set by template, call it (but this branch is kept for clarity)
            window.COMPONENT_COLORS.render(colors);
          } else {
            defaultRenderColors(container, colors);
          }
          dispatchColorsChanged(colors);
          return colors;
        } catch (e) {
          err("COMPONENT_COLORS.load failed", e);
          return [];
        }
      },
      render: function (colors) {
        // allow manual render into container
        const container = buildColorsContainer();
        defaultRenderColors(container, colors || []);
        dispatchColorsChanged(colors || []);
      },
      create: async function (name, compId) {
        return createColor(compId || getComponentIdFromPath(), name);
      },
      delete: async function (colorId) {
        return deleteColor(colorId);
      },
      // allow template to override renderer: set window.COMPONENT_COLORS._customRendererUsed = true
      _internal: { safeFetch, loadColors, createColor, deleteColor },
    };

    // ---------- Load Qualities / Types / Initial state ----------
    async function loadQualitiesByCategory(category) {
      if (!qualityEl) return;

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
          const id = r.id !== undefined && r.id !== null ? String(r.id) : null;
          const value =
            r.value !== undefined && r.value !== null
              ? String(r.value)
              : id || (r.label !== undefined && r.label !== null ? String(r.label) : "");
          const label =
            r.label !== undefined && r.label !== null
              ? String(r.label)
              : r.label_text !== undefined && r.label_text !== null
              ? String(r.label_text)
              : id || String(value);
          const opt = document.createElement("option");

          opt.value = value !== null ? value : "";
          opt.textContent = label;

          if (id) opt.dataset.id = id;
          if (label) opt.dataset.label = label;
          if (r.extra !== undefined) opt.dataset.extra = String(r.extra);

          qualityEl.appendChild(opt);
        });

        if (prevSelected) {
          try {
            qualityEl.value = prevSelected;
            const ev = new Event("change", { bubbles: true });
            qualityEl.dispatchEvent(ev);
          } catch (e) {}
        }
      } catch (e) {
        err("loadQualitiesByCategory error", e);
        clearSelect(qualityEl, "-- Error loading qualities --");
      }
    }

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

        results.forEach((r) => {
          const id = r.id !== undefined && r.id !== null ? String(r.id) : null;
          const value =
            r.value !== undefined && r.value !== null
              ? String(r.value)
              : id || (r.label !== undefined && r.label !== null ? String(r.label) : "");
          const rawType = (r.type !== undefined && r.type !== null) ? String(r.type).trim() : "";
          const label = (r.label !== undefined && r.label !== null) ? String(r.label).trim() : (rawType || (id ? `#${id}` : value));

          const o = document.createElement("option");
          o.value = value !== null ? value : "";

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

          const ctVal = r.content_type_id || r.content_type || r.ct || "";
          if (ctVal !== undefined && ctVal !== null && String(ctVal).trim() !== "") {
            o.dataset.ct = String(ctVal);
          } else {
            o.dataset.ct = "";
          }

          if (id) o.dataset.id = id;
          if (label) o.dataset.label = label;

          productEl.appendChild(o);
        });

        if (prevSelected) {
          try {
            productEl.value = prevSelected;
            const ev = new Event("change", { bubbles: true });
            productEl.dispatchEvent(ev);
          } catch (e) {}
        }
      } catch (e) {
        err("loadTypesByQuality error", e);
        clearSelect(productEl, "-- Error loading types --");
      }
    }

    async function fetchInventoryItem(ct, oid, quality) {
      try {
        const json = await safeFetch(urls.inventory_item, {
          content_type_id: ct,
          object_id: oid,
          quality: quality || "",
          logistics_percent: logisticsEl ? (logisticsEl.value || "") : "",
        });
        return json;
      } catch (e) {
        err("fetchInventoryItem error", e);
        return null;
      }
    }

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
        final_cost: finalPricePerUnit.toFixed(2),
      };
    }

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

      try {
        const qualityName = qualityEl ? (qualityEl.value || "").trim() : "";
        const typeName = typeEl ? (typeEl.value || "").trim() : "";
        if (nameField) {
          nameField.value = qualityName && typeName ? `${qualityName} ${typeName}` : typeName || qualityName;
        }
      } catch (e) {
        console.warn("Auto-name generation failed", e);
      }

      const clientMetrics = computeClientMetrics(
        cost || "",
        width || "",
        width_uom || "inch",
        logisticsEl ? logisticsEl.value || "0" : "0"
      );

      if (finalPriceEl && (!finalPriceEl.value || finalPriceEl.value === "")) finalPriceEl.value = clientMetrics.final_price_per_unit;
      if (pricePerSqftEl && (!pricePerSqftEl.value || pricePerSqftEl.value === "")) pricePerSqftEl.value = clientMetrics.price_per_sqfoot;
      if (finalCostEl && (!finalCostEl.value || finalCostEl.value === "")) finalCostEl.value = clientMetrics.final_cost;
    }

    // ---------- Event Handlers ----------
    if (categoryEl) {
      categoryEl.addEventListener("change", (ev) => {
        const category = (ev.target.value || "").toUpperCase();
        loadQualitiesByCategory(category);
        clearSelect(productEl, "-- Select quality first --");
        setHidden("", "", "");
        [costEl, widthEl, widthUomEl, finalPriceEl, pricePerSqftEl, finalCostEl].forEach((el) => el && (el.value = ""));
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
        [costEl, widthEl, widthUomEl, finalPriceEl, pricePerSqftEl, finalCostEl].forEach((el) => el && (el.value = ""));
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

          const qualityVal = qualityEl ? (qualityEl.value || "").trim() : "";
          const typeVal = typeEl ? (typeEl.value || "").trim() : "";
          if (nameField) nameField.value = qualityVal && typeVal ? `${qualityVal} ${typeVal}` : typeVal || qualityVal;

          // After product selection and population, attempt to load and render colors
          try {
            await window.COMPONENT_COLORS.load();
          } catch (e) {
            err("Colors load after product select failed", e);
          }
        }
      });
    }

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

        // After restoring initial state, attempt to load colors (for edit pages)
        try {
          await window.COMPONENT_COLORS.load();
        } catch (e) {
          err("Initial colors load failed", e);
        }
      } catch (e) {
        err("initialStateRestore error", e);
      }
    })();

    // Post-submit hook (defensive)
    const formEl = document.getElementById("component-form");
    if (formEl) {
      formEl.addEventListener("submit", () => {
        setTimeout(() => {
          window.COMPONENT_COLORS.load().catch(() => {});
        }, 1200);
      });
    }
  }
})();
