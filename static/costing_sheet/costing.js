(function () {
  "use strict";

  /* ---------- small utilities ---------- */
  function log() { if (window && window.console) console.log.apply(console, ["[costing.js]"].concat(Array.from(arguments))); }
  function warn() { if (window && window.console) console.warn.apply(console, ["[costing.js]"].concat(Array.from(arguments))); }
  function $ (id) { try { return document.getElementById(id); } catch (e) { return null; } }
  function q (sel) { try { return document.querySelector(sel); } catch (e) { return null; } }
  function numeric(v) { var n = Number(v); return isNaN(n) ? 0 : n; }
  function fmt2(v) { return (Number(v) || 0).toFixed(2); }
  function fmt4(v) { return (Number(v) || 0).toFixed(4); }

  function parseJSONFromEl(id) {
    try {
      var el = document.getElementById(id);
      if (!el) return null;
      var txt = el.textContent || el.innerText || "";
      if (!txt) return null;
      return JSON.parse(txt);
    } catch (e) {
      warn("parseJSONFromEl", id, e);
      return null;
    }
  }

  function parseConfig() {
    var defaults = {
      ajax_category_details: "/costing/ajax/category-details/",
      ajax_component_details: "/costing/ajax/component-details/",
      ajax_accessories: "/costing/ajax/accessories/",
      ajax_accessory_detail: "/costing/ajax/accessories/0/",
      ajax_accessories_bulk: "/costing/ajax/accessories/bulk/",
      ajax_compute_accessory_line: "/costing/ajax/accessories/compute/"
    };
    var cfg = parseJSONFromEl("costing-config") || {};
    return {
      ajax_category_details: cfg.ajax_category_details || defaults.ajax_category_details,
      ajax_component_details: cfg.ajax_component_details || defaults.ajax_component_details,
      ajax_accessories: cfg.ajax_accessories || defaults.ajax_accessories,
      ajax_accessory_detail: cfg.ajax_accessory_detail || defaults.ajax_accessory_detail,
      ajax_accessories_bulk: cfg.ajax_accessories_bulk || defaults.ajax_accessories_bulk,
      ajax_compute_accessory_line: cfg.ajax_compute_accessory_line || defaults.ajax_compute_accessory_line
    };
  }

  var master = parseJSONFromEl("costing-master") || { categories: [], sizes_by_category: {}, components: {} };
  var cfg = parseConfig();

  /* ---------- basic fetch helpers ---------- */
  function ajaxGet(url, cb) {
    fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { cb && cb(j); })
      .catch(function (e) { warn("AJAX GET error", url, e); cb && cb(null, e); });
  }

  function getCookie(name) {
    if (!document.cookie) return null;
    var parts = document.cookie.split(";").map(function (x) { return x.trim(); });
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i];
      if (p.indexOf(name + "=") === 0) return decodeURIComponent(p.substring(name.length + 1));
    }
    return null;
  }

  function ajaxPostJSON(url, data, cb) {
    try {
      var csrftoken = getCookie("csrftoken");
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Accept": "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrftoken || ""
        },
        body: JSON.stringify(data || {})
      }).then(function (r) {
        if (!r.ok) {
          return r.text().then(function (txt) {
            var err = ("HTTP " + r.status + " - " + (txt || r.statusText));
            throw new Error(err);
          });
        }
        return r.json();
      }).then(function (j) { cb && cb(j); })
        .catch(function (e) { warn("AJAX POST error", url, e); cb && cb(null, e); });
    } catch (e) { warn("ajaxPostJSON failure", e); cb && cb(null, e); }
  }

  /* ---------- DOM refs (matching the reordered template) ---------- */
  var categorySelect = $("id_category_select") || document.querySelector("select[name='category']");
  var componentSelect = $("id_component_master_select") || document.querySelector("select[name='component_master']");
  var el_width = $("id_width");
  var el_width_uom = $("id_width_uom");
  var el_price_sqft = $("id_price_per_sqft");
  var el_final_cost = $("id_final_cost");

  // new - Category Master (New) UI elements
  var catNewSelect = $("id_category_master_new_select");
  var sizeSelect = $("id_size_master_select");
  var newStitch = $("id_new_stitching");
  var newFinish = $("id_new_finishing");
  var newPack = $("id_new_packaging");
  var categoryInfoBox = $("size-category-info") || q(".size-meta");

  // accessory refs
  var accessorySelect = $("id_accessory_select") || document.querySelector("select[name='accessory']");
  var accessoryQuantityEl = $("id_accessory_quantity") || document.querySelector("input[name='accessory_quantity']");
  var accessoryUnitPriceDisplay = $("id_accessory_unit_price_display") || null;
  var accessoryUnitPriceHidden = $("id_accessory_unit_price") || document.querySelector("input[name='accessory_unit_price']");
  var accessoryLineTotalDisplay = $("id_accessory_line_total_display") || null;
  var accessoryLineTotalHidden = $("id_accessory_line_total") || document.querySelector("input[name='accessory_line_total']");
  var accessoryStockDisplay = $("id_accessory_stock_display") || null;

  // new simple fields we added to template
  var colorEl = $("id_color");
  var handworkEl = $("id_handwork");

  /* ---------- helpers for new section ---------- */
  function clearSelect(sel, placeholder) {
    if (!sel) return;
    sel.innerHTML = "";
    var o = document.createElement("option");
    o.value = "";
    o.text = placeholder || "-- select --";
    sel.appendChild(o);
  }
  function addOption(sel, value, label, data) {
    if (!sel) return;
    var o = document.createElement("option");
    o.value = value == null ? "" : String(value);
    o.text = label == null ? String(o.value) : String(label);
    if (data && typeof data === "object") {
      Object.keys(data).forEach(function (k) {
        try {
          if (data[k] === undefined || data[k] === null) return;
          // store on dataset for quick client-side use
          o.dataset[k] = String(data[k]);
          o.setAttribute("data-" + k, String(data[k]));
        } catch (e) {}
      });
    }
    sel.appendChild(o);
  }

  // normalize a size-row to object with keys: id, size, stitching, finishing, packaging
  function normalizeSizeRow(r) {
    if (!r) return null;
    try {
      var id = r.id || r.pk || r.ID || r.size || null;
      var sizeLabel = r.size || r.name || r.label || (typeof r === "string" ? r : (id ? String(id) : ""));
      var stitch = (r.stitching !== undefined ? r.stitching : (r.stitching_cost !== undefined ? r.stitching_cost : (r.stitchingCost !== undefined ? r.stitchingCost : 0)));
      var finish = (r.finishing !== undefined ? r.finishing : (r.finishing_cost !== undefined ? r.finishing_cost : (r.finishingCost !== undefined ? r.finishingCost : 0)));
      var pack = (r.packaging !== undefined ? r.packaging : (r.packaging_cost !== undefined ? r.packaging_cost : (r.packagingCost !== undefined ? r.packagingCost : 0)));
      return {
        id: id,
        size: sizeLabel,
        stitching: stitch == null ? 0 : stitch,
        finishing: finish == null ? 0 : finish,
        packaging: pack == null ? 0 : pack,
        _raw: r
      };
    } catch (e) { return null; }
  }

  function populateCatNewSelectFromMaster() {
    if (!catNewSelect) return;
    clearSelect(catNewSelect, "-- select category master --");

    var cats = (master && Array.isArray(master.categories) && master.categories.length) ? master.categories : [];
    if (cats.length) {
      cats.forEach(function (c) {
        var id = (c && (c.id || c.pk || c.key)) || String(c || "");
        var name = (c && (c.name || c.title || c.label)) || (typeof c === "string" ? c : String(c || id));
        addOption(catNewSelect, id, name, c);
      });
      // try selecting a prefilled value (server may have initial)
      try {
        var pref = (catNewSelect.getAttribute && catNewSelect.getAttribute("data-initial")) || catNewSelect.value || "";
        if (!pref) autoSelectFirstRealOption(catNewSelect);
      } catch (e) {}
      return;
    }

    // fallback: use server rendered options (do nothing)
  }

  function populateSizeSelectForCategory(catId) {
    if (!sizeSelect) return;
    clearSelect(sizeSelect, "-- select size --");
    if (!catId) return;

    // prefer master.sizes_by_category if present
    var sizesMap = (master && master.sizes_by_category) ? master.sizes_by_category : {};
    var arr = sizesMap[String(catId)] || sizesMap[catId] || sizesMap[String(catId).toLowerCase()] || [];

    if (Array.isArray(arr) && arr.length) {
      arr.forEach(function (r) {
        var s = normalizeSizeRow(r);
        if (!s) return;
        addOption(sizeSelect, s.id || s.size, s.size + (s.stitching ? (" — " + Number(s.stitching).toFixed(2)) : ""), s);
      });
      autoSelectFirstRealOption(sizeSelect);
      return;
    }

    // If master doesn't have sizes, call server AJAX to fetch sizes (ajax_category_details)
    if (typeof cfg.ajax_category_details === "string") {
      var url = cfg.ajax_category_details + "?category_id=" + encodeURIComponent(catId);
      ajaxGet(url, function (payload) {
        if (!payload) return;
        var sizes = payload.sizes || (payload.size ? [payload.size] : []) || [];
        sizes.forEach(function (r) {
          var s = normalizeSizeRow(r);
          if (!s) return;
          addOption(sizeSelect, s.id || s.size, s.size + (s.stitching ? (" — " + Number(s.stitching).toFixed(2)) : ""), s);
        });
        autoSelectFirstRealOption(sizeSelect);
      });
    }
  }

  function setSFPTotalsFromSizeObj(sizeObj) {
    if (!sizeObj) {
      if (newStitch) newStitch.value = "0.00";
      if (newFinish) newFinish.value = "0.00";
      if (newPack) newPack.value = "0.00";
      return;
    }
    var stitch = sizeObj.stitching !== undefined ? sizeObj.stitching : (sizeObj.stitching_cost !== undefined ? sizeObj.stitching_cost : 0);
    var finish = sizeObj.finishing !== undefined ? sizeObj.finishing : (sizeObj.finishing_cost !== undefined ? sizeObj.finishing_cost : 0);
    var pack = sizeObj.packaging !== undefined ? sizeObj.packaging : (sizeObj.packaging_cost !== undefined ? sizeObj.packaging_cost : 0);

    if (newStitch) newStitch.value = fmt2(stitch);
    if (newFinish) newFinish.value = fmt2(finish);
    if (newPack) newPack.value = fmt2(pack);

    // ensure the shared computeAll (in template) runs to reflect changed S/F/P if any formula uses them
    triggerComputeIfPresent();
  }

  function onCatNewChange(ev) {
    var val = (ev && ev.target && ev.target.value) || (catNewSelect ? catNewSelect.value : "");
    if (!val) {
      populateSizeSelectForCategory(null);
      setSFPTotalsFromSizeObj(null);
      return;
    }
    if (categoryInfoBox) {
      var opt = catNewSelect.options[catNewSelect.selectedIndex];
      var label = opt && opt.text ? opt.text : val;
      categoryInfoBox.innerHTML = "<small class='text-muted'><strong>" + label + "</strong></small>";
    }
    populateSizeSelectForCategory(val);
  }

  function onSizeChange(ev) {
    var val = (ev && ev.target && ev.target.value) || (sizeSelect ? sizeSelect.value : "");
    if (!val) {
      setSFPTotalsFromSizeObj(null);
      return;
    }
    // try to read dataset on option (populated earlier)
    try {
      var opt = sizeSelect.options[sizeSelect.selectedIndex];
      if (opt && opt.dataset && Object.keys(opt.dataset || {}).length) {
        var ds = opt.dataset;
        var candidate = {
          id: ds.id || opt.value,
          size: ds.size || opt.text,
          stitching: ds.stitching || ds.stitching_cost || ds.stitchingCost,
          finishing: ds.finishing || ds.finishing_cost || ds.finishingCost,
          packaging: ds.packaging || ds.packaging_cost || ds.packagingCost
        };
        setSFPTotalsFromSizeObj(candidate);
        return;
      }
    } catch (e) {}

    // try master.sizes_by_category
    try {
      var categories = master.categories || [];
      var catVal = (catNewSelect && catNewSelect.value) || null;
      var sizesMap = master.sizes_by_category || {};
      var arr = sizesMap[String(catVal)] || sizesMap[catVal] || [];
      if (Array.isArray(arr)) {
        var found = arr.find(function (s) {
          var sid = s.id || s.pk || s.size || s.name;
          return String(sid) === String(val) || String(s.size || "").toLowerCase() === String(val).toLowerCase();
        });
        if (found) { setSFPTotalsFromSizeObj(found); return; }
      }
    } catch (e) {}

    // fallback: ask server
    if (cfg.ajax_category_details) {
      var url = cfg.ajax_category_details + "?size_id=" + encodeURIComponent(val);
      ajaxGet(url, function (payload) {
        var s = payload && (payload.size || (payload.sizes && payload.sizes.length && payload.sizes[0])) || null;
        if (s) { setSFPTotalsFromSizeObj(s); return; }
        setSFPTotalsFromSizeObj(null);
      });
    }
  }

  function autoSelectFirstRealOption(selectEl) {
    try {
      if (!selectEl) return null;
      if (selectEl.value && String(selectEl.value).trim() !== "") return selectEl.value;
      var first = Array.from(selectEl.options || []).find(function (o) { return o && o.value && String(o.value).trim() !== ""; });
      if (first) {
        selectEl.value = first.value;
        try { selectEl.dispatchEvent(new Event("change")); } catch (e) {}
        return first.value;
      }
    } catch (e) {}
    return null;
  }

  /* ---------- component/category/accessory code (preserved and aligned) ---------- */
  function tryFillComponentFromMasterById(id) {
    if (!master || !master.components) return false;
    var key = String(id);
    var byId = master.components[key] || master.components[id] || null;
    if (!byId && Array.isArray(master.components)) {
      var found = master.components.find(function (x) { return String(x.id || x.pk || x.ID || x.display_name || "").toLowerCase() === String(id).toLowerCase(); });
      if (found) byId = found;
    }
    if (!byId && typeof master.components === "object") {
      var keys = Object.keys(master.components || {});
      for (var i = 0; i < keys.length; i++) {
        var v = master.components[keys[i]];
        if (!v) continue;
        if (String(v.id || keys[i] || v.display_name || "").toLowerCase() === String(id).toLowerCase()) {
          byId = v; break;
        }
      }
    }
    if (!byId) return false;
    try { if (el_width) el_width.value = fmt2(byId.width || byId.width_inch || 0); } catch (e) {}
    try { if (el_width_uom) el_width_uom.value = byId.width_uom || "inch"; } catch (e) {}
    try { if (el_price_sqft) el_price_sqft.value = fmt4(byId.price_per_sqft || byId.price_per_sqfoot || 0); } catch (e) {}
    try { if (el_final_cost) el_final_cost.value = fmt2(byId.final_cost || byId.finalPrice || 0); } catch (e) {}
    triggerComputeIfPresent();
    return true;
  }

  function onComponentChange(ev) {
    var compVal = (ev && ev.target && ev.target.value) || (componentSelect ? componentSelect.value : "");
    if (!compVal) {
      if (el_width) el_width.value = "0.00";
      if (el_width_uom) el_width_uom.value = "inch";
      if (el_price_sqft) el_price_sqft.value = "0.0000";
      if (el_final_cost) el_final_cost.value = "0.00";
      triggerComputeIfPresent();
      return;
    }
    try {
      if (tryFillComponentFromMasterById(compVal)) { return; }
    } catch (e) {}
    var url = cfg.ajax_component_details + "?component_id=" + encodeURIComponent(compVal);
    ajaxGet(url, function (payload) {
      if (!payload || !payload.component) { triggerComputeIfPresent(); return; }
      var comp = payload.component;
      try { if (el_width) el_width.value = fmt2(comp.width || 0); } catch (e) {}
      try { if (el_width_uom) el_width_uom.value = comp.width_uom || "inch"; } catch (e) {}
      try { if (el_price_sqft) el_price_sqft.value = fmt4(comp.price_per_sqfoot || comp.price_per_sqft || 0); } catch (e) {}
      try { if (el_final_cost) el_final_cost.value = fmt2(comp.final_cost || 0); } catch (e) {}
      triggerComputeIfPresent();
    });
  }

  function fillFieldsFromCategorySource(src) {
    if (!src) return;
    var setIf = function(idCandidates, v, formatFn){
      idCandidates.forEach(function(id){
        var el = document.getElementById(id) || document.querySelector("[name='"+id+"']");
        if (!el) return;
        try { el.value = (formatFn ? formatFn(v) : (v == null ? "" : v)); } catch (e) {}
      });
    };
    setIf(["id_gf_percent_display","id_gf_percent"], (src.gf_percent || src.gf || src.gf_overhead), fmt4);
    setIf(["id_texas_buying_percent_display","id_texas_buying_percent"], (src.texas_buying_percent || src.texas_buying_cost || src.texas_buying), fmt4);
    setIf(["id_texas_retail_percent_display","id_texas_retail_percent"], (src.texas_retail_percent || src.texas_retail), fmt4);
    setIf(["id_shipping_inr_display","id_shipping_inr"], (src.shipping_inr || src.shipping_cost_inr || src.shipping), fmt2);
    setIf(["id_tx_to_us_percent_display","id_tx_to_us_percent"], (src.tx_to_us_percent || src.texas_to_us_selling_cost), fmt4);
    setIf(["id_import_percent_display","id_import_percent"], (src.import_percent || src.import_cost), fmt4);
    setIf(["id_new_tariff_percent_display","id_new_tariff_percent"], (src.new_tariff_percent || src.new_tariff), fmt4);
    setIf(["id_recip_tariff_percent_display","id_recip_tariff_percent"], (src.reciprocal_tariff_percent || src.reciprocal_tariff), fmt4);
    setIf(["id_ship_us_percent_display","id_ship_us_percent"], (src.ship_us_percent || src.shipping_us), fmt4);
    setIf(["id_us_wholesale_display","id_us_wholesale"], (src.us_wholesale || src.us_wholesale_percent || src.us_wholesale_margin), fmt4);
    triggerComputeIfPresent();
  }

  function onCategoryChange(ev) {
    var catVal = (ev && ev.target && ev.target.value) || (categorySelect ? categorySelect.value : "");
    ["id_gf_percent_display","id_texas_buying_percent_display","id_texas_retail_percent_display","id_shipping_inr_display"].forEach(function(i){
      var el = document.getElementById(i); if (el) el.value = (i === "id_shipping_inr_display" ? "0.00" : "0.0000");
    });
    if (!catVal) { triggerComputeIfPresent(); return; }
    try {
      if (master && Array.isArray(master.categories)) {
        var found = master.categories.find(function (c) {
          if (!c) return false;
          return (String(c.id || c.pk || c.key || "").toLowerCase() === String(catVal).toLowerCase()) ||
                 (String(c.name || c.title || "").toLowerCase() === String(catVal).toLowerCase());
        });
        if (found) { fillFieldsFromCategorySource(found); return; }
      }
    } catch (e) {}
    var url = cfg.ajax_category_details + "?category_id=" + encodeURIComponent(catVal);
    ajaxGet(url, function (payload) {
      if (!payload) { triggerComputeIfPresent(); return; }
      if (payload.category) { fillFieldsFromCategorySource(payload.category); return; }
      if (Array.isArray(payload.components) && payload.components.length) { fillFieldsFromCategorySource(payload.components[0]); return; }
      triggerComputeIfPresent();
    });
  }

  /* ---------- accessory code preserved & adapted ---------- */
  function accessoryLabel(a) {
    if (!a) return "";
    if (a.text) return String(a.text);
    var name = a.item_name || a.name || a.item || "";
    var q = a.quality || a.quality_display || a.quality_text || "";
    var v = (a.vendor && (a.vendor.vendor_name || a.vendor.name)) ? " (" + (a.vendor.vendor_name || a.vendor.name) + ")" : "";
    if (q) return name + " — " + q + v;
    return name + v;
  }
  function clearOptions(sel, placeholder) { clearSelect(sel, placeholder); }
  function addAccessoryOption(sel, value, label, data) {
    if (!sel) return;
    var o = document.createElement("option");
    o.value = (value === undefined || value === null) ? "" : String(value);
    o.text = (label === undefined || label === null) ? String(o.value) : String(label);
    if (data && typeof data === "object") {
      Object.keys(data).forEach(function (k) {
        try { if (data[k] === undefined || data[k] === null) return; o.dataset[k] = data[k]; o.setAttribute("data-" + k, data[k]); } catch (e) {}
      });
    }
    sel.appendChild(o);
  }
  function populateAccessoryDropdown(qstr) {
    if (!accessorySelect) return;
    clearOptions(accessorySelect, "-- select accessory --");
    var url = cfg.ajax_accessories;
    if (qstr) url += "?q=" + encodeURIComponent(qstr);
    ajaxGet(url, function (payload) {
      if (!payload) return;
      var rows = payload.results || payload.items || payload || [];
      if (Array.isArray(rows)) {
        rows.forEach(function (r) {
          var id = r.id || r.pk || r.ID || "";
          var label = accessoryLabel(r) || (r.text || r.item_name || ("#" + id));
          addAccessoryOption(accessorySelect, id, label, r);
        });
        autoSelectFirstRealOption(accessorySelect);
      } else if (payload.count && Array.isArray(payload.results)) {
        payload.results.forEach(function (r) {
          var id = r.id || r.pk || "";
          var label = accessoryLabel(r) || (r.text || r.item_name || ("#" + id));
          addAccessoryOption(accessorySelect, id, label, r);
        });
        autoSelectFirstRealOption(accessorySelect);
      }
    });
  }

  function accessDetailUrlFor(id) {
    try {
      var base = cfg.ajax_accessory_detail || cfg.ajax_accessory_detail;
      if (!base) return cfg.ajax_accessory_detail + "?accessory_id=" + encodeURIComponent(id);
      if (String(base).indexOf("/0/") !== -1) {
        return String(base).replace("/0/", "/" + encodeURIComponent(id) + "/");
      }
      if (base.match(/0\/?$/)) return String(base).replace(/0\/?$/, String(encodeURIComponent(id)) + "/");
      return base + (base.indexOf("?") === -1 ? "?" : "&") + "accessory_id=" + encodeURIComponent(id);
    } catch (e) {
      return cfg.ajax_accessory_detail + "?accessory_id=" + encodeURIComponent(id);
    }
  }

  function setAccessoryFieldsFromDetail(a) {
    if (!a) return;
    var unitPrice = a.unit_cost || a.cost_per_unit || a.cost || a.price || 0;
    var stock = a.stock || a.available_stock || a.stock_in_mtrs || 0;
    if (accessoryUnitPriceDisplay) accessoryUnitPriceDisplay.value = fmt2(unitPrice);
    if (accessoryUnitPriceHidden) accessoryUnitPriceHidden.value = fmt2(unitPrice);
    if (accessoryStockDisplay) accessoryStockDisplay.value = (String(stock).indexOf(".") !== -1 ? String(stock) : Number(stock).toFixed(3));
    var qty = accessoryQuantityEl ? Number(accessoryQuantityEl.value || accessoryQuantityEl.getAttribute("value") || 0) : 0;
    computeAccessoryLineAndSet(a.id || a.ID || a.pk || accessorySelect.value || null, qty, true);
  }

  function onAccessoryChange(ev) {
    var val = (ev && ev.target && ev.target.value) || (accessorySelect ? accessorySelect.value : "");
    if (!val) {
      if (accessoryUnitPriceDisplay) accessoryUnitPriceDisplay.value = "0.00";
      if (accessoryUnitPriceHidden) accessoryUnitPriceHidden.value = "0.00";
      if (accessoryLineTotalDisplay) accessoryLineTotalDisplay.value = "0.00";
      if (accessoryLineTotalHidden) accessoryLineTotalHidden && (accessoryLineTotalHidden.value = "0.00");
      if (accessoryStockDisplay) accessoryStockDisplay.value = "0.000";
      triggerComputeIfPresent();
      return;
    }
    try {
      var opt = accessorySelect && accessorySelect.options && accessorySelect.options[accessorySelect.selectedIndex];
      if (opt && opt.dataset) {
        var ds = opt.dataset;
        var maybeUnit = ds.unit_cost || ds.cost_per_unit || ds.cost || ds.price;
        var maybeStock = ds.stock || ds.available || ds.qty || ds.quantity;
        if (maybeUnit !== undefined || maybeStock !== undefined) {
          var d = {
            unit_cost: maybeUnit !== undefined ? maybeUnit : undefined,
            cost_per_unit: maybeUnit !== undefined ? maybeUnit : undefined,
            stock: maybeStock !== undefined ? maybeStock : undefined,
            id: opt.value
          };
          setAccessoryFieldsFromDetail(d);
          return;
        }
      }
    } catch (e) {}
    var url = accessDetailUrlFor(val);
    ajaxGet(url, function (payload, err) {
      if (!payload) { warn("Accessory detail fetch failed for id", val); return; }
      var acc = payload.accessory || payload || null;
      if (acc && (acc.id === undefined) && payload[val]) acc = payload[val];
      setAccessoryFieldsFromDetail(acc);
    });
  }

  function computeAccessoryLineAndSet(accessory_id, quantity, preferServer) {
    if (!accessory_id) {
      if (accessoryLineTotalDisplay) accessoryLineTotalDisplay.value = "0.00";
      if (accessoryLineTotalHidden) accessoryLineTotalHidden.value = "0.00";
      triggerComputeIfPresent();
      return;
    }
    var qty = Number(quantity || 0);
    if (qty < 0) qty = 0;

    if (preferServer && cfg.ajax_compute_accessory_line) {
      ajaxPostJSON(cfg.ajax_compute_accessory_line, { accessory_id: accessory_id, quantity: String(qty) }, function (resp, err) {
        if (!resp || resp.error || err) {
          var unit = accessoryUnitPriceHidden ? Number(accessoryUnitPriceHidden.value || accessoryUnitPriceDisplay && accessoryUnitPriceDisplay.value || 0) : (accessoryUnitPriceDisplay ? Number(accessoryUnitPriceDisplay.value || 0) : 0);
          var line = (unit * qty);
          if (accessoryLineTotalDisplay) accessoryLineTotalDisplay.value = fmt2(line);
          if (accessoryLineTotalHidden) accessoryLineTotalHidden.value = fmt2(line);
          // ensure computeAll is called so new_final_price updates
          triggerComputeIfPresent();
          return;
        }
        var unit_price = resp.unit_price || resp.unitPrice || resp.unit || resp.unit_cost || 0;
        var line_total = resp.line_total || resp.lineTotal || resp.total || (Number(unit_price) * Number(resp.quantity || qty));
        if (accessoryUnitPriceDisplay) accessoryUnitPriceDisplay.value = fmt2(unit_price);
        if (accessoryUnitPriceHidden) accessoryUnitPriceHidden.value = fmt2(unit_price);
        if (accessoryLineTotalDisplay) accessoryLineTotalDisplay.value = fmt2(line_total);
        if (accessoryLineTotalHidden) accessoryLineTotalHidden.value = fmt2(line_total);
        // ensure computeAll updates now that accessory line changed
        triggerComputeIfPresent();
      });
      return;
    }

    var unit = accessoryUnitPriceHidden ? Number(accessoryUnitPriceHidden.value || accessoryUnitPriceDisplay && accessoryUnitPriceDisplay.value || 0) : (accessoryUnitPriceDisplay ? Number(accessoryUnitPriceDisplay.value || 0) : 0);
    var line = (unit * qty);
    if (accessoryLineTotalDisplay) accessoryLineTotalDisplay.value = fmt2(line);
    if (accessoryLineTotalHidden) accessoryLineTotalHidden.value = fmt2(line);
    // ensure computeAll updates now that accessory line changed
    triggerComputeIfPresent();
  }

  function onAccessoryQtyChange(ev) {
    var qty = Number((ev && ev.target && ev.target.value) || (accessoryQuantityEl ? accessoryQuantityEl.value : 0)) || 0;
    var accId = accessorySelect ? accessorySelect.value : null;
    computeAccessoryLineAndSet(accId, qty, true);
  }

  function onAccessoryAddClick(ev) {
    ev && ev.preventDefault && ev.preventDefault();
    if (!accessoryQuantityEl) {
      warn("Accessory quantity element not found");
      return;
    }
    var cur = Number(accessoryQuantityEl.value || accessoryQuantityEl.getAttribute("value") || 0) || 0;
    cur = cur + 1;
    accessoryQuantityEl.value = cur;
    onAccessoryQtyChange({ target: accessoryQuantityEl });
  }

  /* ---------- wire up events ---------- */
  if (catNewSelect) {
    populateCatNewSelectFromMaster();
    catNewSelect.addEventListener("change", onCatNewChange);
    log("wired catNewSelect");
  } else {
    warn("catNewSelect not found");
  }

  if (sizeSelect) {
    sizeSelect.addEventListener("change", onSizeChange);
    log("wired sizeSelect");
  } else {
    warn("sizeSelect not found");
  }

  if (componentSelect) {
    componentSelect.addEventListener("change", onComponentChange);
    log("wired componentSelect");
  } else {
    warn("componentSelect not found (Quality dropdown)");
  }

  if (categorySelect) {
    categorySelect.addEventListener("change", onCategoryChange);
    log("wired categorySelect");
  } else {
    warn("categorySelect not found");
  }

  if (accessorySelect) {
    try { populateAccessoryDropdown(); } catch (e) { warn("populateAccessoryDropdown failed", e); }
    accessorySelect.addEventListener("change", onAccessoryChange);
    log("wired accessorySelect");
  } else {
    warn("accessorySelect not found - accessory features disabled");
  }

  if (accessoryQuantityEl) {
    accessoryQuantityEl.addEventListener("change", onAccessoryQtyChange);
    accessoryQuantityEl.addEventListener("input", onAccessoryQtyChange);
  } else {
    warn("accessoryQuantity element not found");
  }

  var accessoryAddBtn = $("btn_add_accessory_qty") || document.getElementById("btn_add_accessory_qty");
  if (accessoryAddBtn) {
    accessoryAddBtn.addEventListener("click", onAccessoryAddClick);
    log("wired accessoryAddBtn (+)");
  } else {
    warn("+ button for accessory quantity not found");
  }

  /* ---------- utility to trigger page computeAll (defined inline in template) ---------- */
  function triggerComputeIfPresent() {
    try { if (typeof computeAll === "function") { computeAll(); return; } } catch (e) {}
    try { var el = $("id_average") || $("id_final_cost"); if (el) { el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true })); } } catch (e) {}
  }

  function init() {
    // if template prefilled a category_new value (e.g. server-side copy_from) attempt to trigger change
    try {
      if (catNewSelect && catNewSelect.value) { setTimeout(function(){ catNewSelect.dispatchEvent(new Event("change")); }, 30); }
    } catch (e) {}
    // if template prefilled a size value attempt to trigger
    try {
      if (sizeSelect && sizeSelect.value) { setTimeout(function(){ sizeSelect.dispatchEvent(new Event("change")); }, 60); }
    } catch (e) {}
    // pretrigger component/category/accessory change if values present
    try { if (componentSelect && componentSelect.value) setTimeout(function(){ componentSelect.dispatchEvent(new Event("change")); }, 150); } catch (e) {}
    try { if (categorySelect && categorySelect.value) setTimeout(function(){ categorySelect.dispatchEvent(new Event("change")); }, 120); } catch (e) {}
    try { if (accessorySelect && accessorySelect.value) setTimeout(function(){ accessorySelect.dispatchEvent(new Event("change")); }, 200); } catch (e) {}

    // optional: wire simple fields to re-run compute when changed (color, handwork are mostly metadata)
    try {
      if (colorEl) { colorEl.addEventListener("change", triggerComputeIfPresent); colorEl.addEventListener("input", triggerComputeIfPresent); }
      if (handworkEl) { handworkEl.addEventListener("change", triggerComputeIfPresent); handworkEl.addEventListener("input", triggerComputeIfPresent); }
    } catch (e) {}

    log("costing.js (updated) initialized - category master new + sizes support active (master present? " + !!master + ")");
  }
  init();

  // expose debug hooks
  window.CostingSheet = window.CostingSheet || {};
  window.CostingSheet.debug = function () { log("master:", master, "cfg:", cfg); };
  window.CostingSheet.populateSizeSelectForCategory = populateSizeSelectForCategory;
  window.CostingSheet.setSFPTotalsFromSizeObj = setSFPTotalsFromSizeObj;

})();
