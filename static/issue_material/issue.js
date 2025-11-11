// issue_material/static/issue_material/issue.js
// Standalone JS for Issue Material formset (depends only on the DOM).
(function () {
  "use strict";

  // Locate the container and read data-* attributes
  const issueLinesContainer = document.getElementById("issue-lines");
  if (!issueLinesContainer) {
    console.warn("issue.js: #issue-lines not found; aborting.");
    return;
  }

  const inventoryUrl = issueLinesContainer.dataset.inventoryUrl || "/issue-material/ajax/items-by-type/";
  const formPrefix = issueLinesContainer.dataset.formPrefix || (window.issueFormPrefix || "issueline_set");
  const addBtn = document.getElementById("add-row");

  function totalFormsEl() {
    return document.getElementById("id_" + formPrefix + "-TOTAL_FORMS");
  }

  function fetchItems(invType) {
    return fetch(inventoryUrl + "?type=" + encodeURIComponent(invType), {
      headers: { "X-Requested-With": "XMLHttpRequest" }
    }).then(resp => {
      if (!resp.ok) return Promise.reject(new Error("Failed to load items"));
      return resp.json();
    }).then(data => data.items || []);
  }

  function populateItemSelect(selectEl, items) {
    selectEl.innerHTML = '<option value="">— choose item —</option>';
    items.forEach(it => {
      const opt = document.createElement("option");
      opt.value = it.id;
      opt.dataset.contentTypeId = it.content_type_id;
      opt.dataset.stock = it.stock;
      opt.textContent = it.name + (it.stock !== null && it.stock !== undefined ? (" — " + it.stock) : "");
      selectEl.appendChild(opt);
    });
  }

  function setHiddenIdsForRow(rowEl, objectId, contentTypeId, stock) {
    const contentField = rowEl.querySelector("input[name$='-content_type_id']");
    const objectField = rowEl.querySelector("input[name$='-object_id']");
    const stockEl = rowEl.querySelector(".available-stock");
    if (contentField) contentField.value = contentTypeId || "";
    if (objectField) objectField.value = objectId || "";
    if (stockEl) stockEl.textContent = (stock !== null && stock !== undefined) ? stock : "—";
  }

  function initRow(rowEl) {
    const invTypeSelect = rowEl.querySelector("select[name$='-inventory_type']");
    const itemSelect = rowEl.querySelector(".item-select");
    const qtyInput = rowEl.querySelector("input[name$='-qty']");
    const removeBtn = rowEl.querySelector(".remove-row");
    const deleteCheckbox = rowEl.querySelector("input[name$='-DELETE']");

    if (invTypeSelect) {
      invTypeSelect.addEventListener("change", function () {
        const type = this.value;
        if (itemSelect) itemSelect.innerHTML = '<option value="">— choose item —</option>';
        setHiddenIdsForRow(rowEl, "", "", "—");
        if (!type) return;
        fetchItems(type).then(items => populateItemSelect(itemSelect, items)).catch(err => {
          console.error("issue.js: fetchItems error", err);
          if (itemSelect) itemSelect.innerHTML = '<option value="">(failed to load)</option>';
        });
      });

      if (invTypeSelect.value) {
        invTypeSelect.dispatchEvent(new Event("change"));
      }
    }

    if (itemSelect) {
      itemSelect.addEventListener("change", function () {
        const opt = this.options[this.selectedIndex];
        if (!opt || !opt.value) {
          setHiddenIdsForRow(rowEl, "", "", "—");
          return;
        }
        setHiddenIdsForRow(rowEl, opt.value, opt.dataset.contentTypeId, opt.dataset.stock);
      });

      (function tryPrefill() {
        const contentField = rowEl.querySelector("input[name$='-content_type_id']");
        const objectField = rowEl.querySelector("input[name$='-object_id']");
        if (contentField && objectField && contentField.value && objectField.value) {
          let attempts = 0;
          const idToSelect = objectField.value;
          const poll = setInterval(() => {
            if (itemSelect.querySelector("option[value='" + idToSelect + "']")) {
              itemSelect.value = idToSelect;
              const opt = itemSelect.options[itemSelect.selectedIndex];
              setHiddenIdsForRow(rowEl, opt.value, opt.dataset.contentTypeId, opt.dataset.stock);
              clearInterval(poll);
            }
            attempts += 1;
            if (attempts > 20) clearInterval(poll);
          }, 150);
        }
      })();
    }

    if (removeBtn) {
      removeBtn.addEventListener("click", function () {
        if (deleteCheckbox) {
          deleteCheckbox.checked = true;
          rowEl.style.display = "none";
        } else {
          rowEl.remove();
          const tot = totalFormsEl();
          if (tot) tot.value = parseInt(tot.value, 10) - 1;
        }
      });
    }

    if (qtyInput) {
      qtyInput.addEventListener("blur", function () {
        const stockEl = rowEl.querySelector(".available-stock");
        const stockText = stockEl ? stockEl.textContent.trim() : "";
        if (!stockText || stockText === "—") return;
        const available = parseFloat(stockText);
        const val = parseFloat(this.value || 0);
        if (!isNaN(available) && val > available) {
          alert("Requested quantity (" + val + ") exceeds available stock (" + available + ").");
          this.focus();
        }
      });
    }
  }

  function addRow() {
    const totEl = totalFormsEl();
    const idx = totEl ? parseInt(totEl.value, 10) : issueLinesContainer.querySelectorAll(".issue-line").length;
    const tpl = document.getElementById("empty-form-template");
    if (!tpl) {
      console.error("issue.js: empty form template (#empty-form-template) not found.");
      return;
    }
    const newHtml = tpl.innerHTML.replace(/__prefix__/g, idx);
    const wrapper = document.createElement("div");
    wrapper.innerHTML = newHtml;
    const newRow = wrapper.firstElementChild;
    issueLinesContainer.appendChild(newRow);

    if (totEl) totEl.value = idx + 1;
    initRow(newRow);
  }

  // initialize existing rows
  document.querySelectorAll("#issue-lines .issue-line").forEach(r => initRow(r));

  // bind add button
  if (addBtn) {
    addBtn.addEventListener("click", addRow);
  } else {
    console.warn("issue.js: #add-row button not found.");
  }

  // final submit validation
  const issueForm = document.getElementById("issue-form");
  if (issueForm) {
    issueForm.addEventListener("submit", function (ev) {
      const rows = document.querySelectorAll("#issue-lines .issue-line");
      for (const r of rows) {
        const del = r.querySelector("input[name$='-DELETE']");
        if (del && del.checked) continue;

        const contentField = r.querySelector("input[name$='-content_type_id']");
        const objectField = r.querySelector("input[name$='-object_id']");
        const qtyField = r.querySelector("input[name$='-qty']");
        if (!contentField || !objectField || !contentField.value || !objectField.value) {
          alert("Please select an Item for every row (Inventory Type → Item).");
          ev.preventDefault();
          return false;
        }
        if (!qtyField || parseFloat(qtyField.value || 0) <= 0) {
          alert("Please enter a quantity greater than 0 for every row.");
          ev.preventDefault();
          return false;
        }
        const stockText = r.querySelector(".available-stock").textContent.trim();
        if (stockText !== "—" && stockText !== "") {
          const available = parseFloat(stockText);
          const val = parseFloat(qtyField.value || 0);
          if (!isNaN(available) && val > available) {
            alert("Requested quantity exceeds available stock for one or more rows.");
            ev.preventDefault();
            return false;
          }
        }
      }
      return true;
    });
  } else {
    console.warn("issue.js: #issue-form not found; skipping submit validation.");
  }

})();
