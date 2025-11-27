from decimal import Decimal, InvalidOperation
from datetime import datetime
from django import forms
from django.apps import apps
from django.forms import modelform_factory
from django.core.exceptions import ValidationError

"""
CostingSheet form factory (modified).
- Adds a 'colors' MultipleChoiceField to accept multiple selected colors (posted as colors[]).
- Keeps legacy 'color' field for backward compatibility (UI may hide it).
- Defensive: only includes model fields that actually exist.
- Exposes category_new/size_master and stitching/finishing/packaging so JS can populate/select sizes.
"""

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")


def _safe_str(v):
    try:
        return "" if v is None else str(v)
    except Exception:
        return ""


def _to_decimal_safe(v, default=Decimal("0")):
    try:
        if v is None or v == "":
            return default
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return default


def get_costing_sheet_form():
    CostingSheet = apps.get_model("costing_sheet", "CostingSheet")

    # Desired fields for the form — include category_new/size_master and stitching/finishing/packaging
    desired = [
        "category", "category_new", "size_master", "name", "component_master",
        "width", "width_uom", "price_per_sqft", "final_cost",
        "collection", "color",  # color kept for backward-compatibility (single-color)
        "average", "price_source", "hand_work",
        "accessory", "accessory_quantity",
        "shipping_cost_india", "shipping_cost_us", "shipping_cost_europe",
        # computed/readonly
        "total", "new_final_price", "gf_overhead_cost", "texas_buying_cost",
        "texas_retail", "texas_us_selling_cost", "us_buying_cost_usd", "us_wholesale_cost",
        # S/F/P snapshot fields we want exposed
        "stitching", "finishing", "packaging",
        # SKU visible (read-only) so user can see the result that model will compute
        "sku",
    ]

    # filter desired by what actually exists on the model
    available = []
    for f in desired:
        try:
            CostingSheet._meta.get_field(f)
            available.append(f)
        except Exception:
            continue

    # Ensure category present defensively
    if "category" not in available:
        try:
            CostingSheet._meta.get_field("category")
            available.insert(0, "category")
        except Exception:
            pass

    BaseForm = modelform_factory(CostingSheet, fields=available)

    class CostingSheetForm(BaseForm):
        """
        Form returned by get_costing_sheet_form()

        New additions:
          - colors: MultipleChoiceField (hidden widget by default) that accepts a list of selected color ids.
                    JS should populate choices or submit colors[] directly. This allows server to receive
                    which colors the user ticked to generate multiple SKUs.
        """
        colors = forms.MultipleChoiceField(
            required=False,
            widget=forms.MultipleHiddenInput(),  # JS can change to checkboxes in the template or keep hidden and POST array
            help_text="Selected color ids (for multi-SKU generation)."
        )

        class Meta(BaseForm.Meta):
            pass

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            # --- Basic widget attributes ---
            if "category" in self.fields:
                self.fields["category"].widget.attrs.update({
                    "id": "id_category_select",
                    "class": "form-select",
                })

            if "category_new" in self.fields:
                # try to set queryset from category_master_new app if it's a ModelChoiceField
                try:
                    CategoryNew = apps.get_model("category_master_new", "Category")
                except LookupError:
                    CategoryNew = None

                if CategoryNew and hasattr(self.fields["category_new"], "queryset"):
                    try:
                        self.fields["category_new"].queryset = CategoryNew.objects.all().order_by("id")
                    except Exception:
                        try:
                            self.fields["category_new"].queryset = CategoryNew.objects.all()
                        except Exception:
                            pass

                self.fields["category_new"].widget.attrs.update({
                    "id": "id_category_master_new_select",
                    "class": "form-select",
                })

            if "size_master" in self.fields:
                try:
                    # Point the form field's queryset to the correct model
                    SizeModel = apps.get_model("category_master_new", "CategorySize")
                    if SizeModel and hasattr(self.fields["size_master"], "queryset"):
                        self.fields["size_master"].queryset = SizeModel.objects.all()
                except LookupError:
                    pass  # Model not found, let it be

                self.fields["size_master"].widget.attrs.update({
                    "id": "id_size_master_select",
                    "class": "form-select",
                })
                # Clear all choices. JS will populate this dropdown.
                try:
                    self.fields["size_master"].widget.choices = [("", "-- select size --")]
                except Exception:
                    pass

            # drop legacy explicit "size" field from form (we keep model column but hide it in UI)
            if "size" in self.fields:
                try:
                    del self.fields["size"]
                except Exception:
                    pass

            # basic text widgets that affect SKU
            if "name" in self.fields:
                self.fields["name"].widget.attrs.update({
                    "id": "id_name",
                    "class": "form-control",
                    "placeholder": "e.g., Linen Mate Shoes",
                })
            if "collection" in self.fields:
                self.fields["collection"].widget.attrs.update({
                    "id": "id_collection",
                    "class": "form-control",
                    "placeholder": "e.g., Solid Color",
                })
            # legacy single color input (kept for compatibility)
            if "color" in self.fields:
                self.fields["color"].widget.attrs.update({
                    "id": "id_color",
                    "class": "form-control",
                    "placeholder": "e.g., Angora White",
                })

            if "sku" in self.fields:
                # Show SKU as read-only; model will compute on save if blank
                self.fields["sku"].widget.attrs.update({
                    "id": "id_sku",
                    "class": "form-control",
                    "readonly": "readonly",
                    "placeholder": "Auto-generated",
                })

            # component_master widget
            if "component_master" in self.fields:
                ComponentModel = None
                try:
                    ComponentModel = apps.get_model("components", "ComponentMaster")
                except LookupError:
                    try:
                        ComponentModel = apps.get_model("component_master", "ComponentMaster")
                    except LookupError:
                        ComponentModel = None
                try:
                    if ComponentModel and hasattr(self.fields["component_master"], "queryset"):
                        self.fields["component_master"].queryset = ComponentModel.objects.all().order_by("id")
                    self.fields["component_master"].widget.attrs.update({
                        "id": "id_component_master_select",
                        "class": "form-select",
                        "data-autofill-targets": "id_width,id_price_per_sqft,id_final_cost"
                    })
                except Exception:
                    pass

            # numeric snapshot fields
            for num_field, step, places in (
                ("width", "0.01", 2),
                ("price_per_sqft", "0.0001", 4),
                ("final_cost", "0.01", 2),
            ):
                if num_field in self.fields:
                    try:
                        self.fields[num_field].widget.attrs.update({
                            "id": f"id_{num_field}",
                            "class": "form-control",
                            "step": step,
                            "min": "0"
                        })
                    except Exception:
                        pass

            # stitching / finishing / packaging widgets (exposed, readonly by default but included in POST)
            for f in ("stitching", "finishing", "packaging"):
                if f in self.fields:
                    try:
                        self.fields[f].widget.attrs.update({
                            "id": f"id_new_{f}" if f != "packaging" else "id_new_packaging",
                            "class": "form-control",
                            "step": "0.01",
                            "min": "0",
                            # keep them editable if you want; default readonly in UI can be toggled
                            # set readonly so JS controls values (but they will still POST)
                            "readonly": "readonly"
                        })
                    except Exception:
                        pass

            # average widget
            if "average" in self.fields:
                try:
                    self.fields["average"].widget.attrs.update({
                        "id": "id_average",
                        "class": "form-control",
                        "step": "0.001",
                        "min": "0"
                    })
                except Exception:
                    pass

            # shipping inputs
            for f in ("shipping_cost_india", "shipping_cost_us", "shipping_cost_europe"):
                if f in self.fields:
                    try:
                        self.fields[f].widget.attrs.update({
                            "id": f"id_{f}",
                            "class": "form-control",
                            "step": "0.01",
                            "min": "0"
                        })
                    except Exception:
                        pass

            # computed/read-only fields: make them readonly in UI if present
            for f in (
                "total", "new_final_price", "gf_overhead_cost", "texas_buying_cost",
                "texas_retail", "texas_us_selling_cost", "us_buying_cost_usd", "us_wholesale_cost"
            ):
                if f in self.fields:
                    try:
                        self.fields[f].widget.attrs.update({
                            "id": f"id_{f}",
                            "class": "form-control",
                            "readonly": "readonly"
                        })
                    except Exception:
                        pass

            # accessory widget attrs
            if "accessory_quantity" in self.fields:
                try:
                    self.fields["accessory_quantity"].widget.attrs.update({
                        "id": "id_accessory_quantity",
                        "class": "form-control",
                        "min": "0",
                        "step": "1"
                    })
                except Exception:
                    pass

            # Build master_data: categories, sizes_by_category, components
            self.master_data = {"categories": [], "sizes_by_category": {}, "components": {}}

            # Components
            ComponentModel = None
            try:
                ComponentModel = apps.get_model("components", "ComponentMaster")
            except LookupError:
                try:
                    ComponentModel = apps.get_model("component_master", "ComponentMaster")
                except LookupError:
                    ComponentModel = None

            if ComponentModel:
                try:
                    comps_qs = ComponentModel.objects.all().order_by("id")
                except Exception:
                    try:
                        comps_qs = ComponentModel.objects.all()
                    except Exception:
                        comps_qs = []
                for cm in comps_qs:
                    try:
                        display = str(cm)
                    except Exception:
                        display = getattr(cm, "name", "") or getattr(cm, "quality", "") or getattr(cm, "pk", "")
                    self.master_data["components"][str(getattr(cm, "id", ""))] = {
                        "id": getattr(cm, "id", None),
                        "display_name": _safe_str(display),
                        "width": _safe_str(getattr(cm, "width", "0.00")),
                        "width_uom": _safe_str(getattr(cm, "width_uom", "inch")),
                        "price_per_sqfoot": _safe_str(getattr(cm, "price_per_sqfoot", getattr(cm, "price_per_sqft", "0.0000"))),
                        "final_cost": _safe_str(getattr(cm, "final_cost", "0.00")),
                    }

            # Categories (legacy) or new Category Master
            CategoryModel = None
            try:
                CategoryModel = apps.get_model("category_master", "CategoryMaster")
            except LookupError:
                try:
                    CategoryModel = apps.get_model("category_master_new", "Category")
                except LookupError:
                    CategoryModel = None

            if CategoryModel:
                try:
                    cats_qs = CategoryModel.objects.all().order_by("id")
                    if "category" in self.fields and hasattr(self.fields["category"], "queryset"):
                        try:
                            self.fields["category"].queryset = cats_qs
                        except Exception:
                            pass
                except Exception:
                    try:
                        cats_qs = CategoryModel.objects.all()
                    except Exception:
                        cats_qs = []

                for c in cats_qs:
                    try:
                        display_name = None
                        for attr in ("name", "title", "component"):
                            try:
                                val = getattr(c, attr)
                            except Exception:
                                val = None
                            if val is None:
                                continue
                            if hasattr(val, "__class__") and not isinstance(val, (str, bytes, int, float, Decimal)):
                                for n in ("name", "title"):
                                    try:
                                        v2 = getattr(val, n)
                                        if v2 is not None:
                                            display_name = _safe_str(v2)
                                            break
                                    except Exception:
                                        continue
                                if display_name:
                                    break
                                try:
                                    display_name = _safe_str(val)
                                except Exception:
                                    display_name = ""
                                    break
                            else:
                                display_name = _safe_str(val)
                                break

                        cat_item = {
                            "id": getattr(c, "id", None),
                            "name": display_name or _safe_str(getattr(c, "name", getattr(c, "title", ""))),
                            "description": _safe_str(getattr(c, "description", "") or ""),
                            "gf_percent": _safe_str(getattr(c, "gf_overhead", getattr(c, "gf_percent", 0) or 0)),
                            "texas_buying_percent": _safe_str(getattr(c, "texas_buying_cost", getattr(c, "texas_buying_percent", 0) or 0)),
                            "texas_retail_percent": _safe_str(getattr(c, "texas_retail", getattr(c, "texas_retail_percent", 0) or 0)),
                            "shipping_inr": _safe_str(getattr(c, "shipping_cost_inr", getattr(c, "shipping_inr", 0) or 0)),
                            "tx_to_us_percent": _safe_str(getattr(c, "texas_to_us_selling_cost", getattr(c, "tx_to_us_percent", 0) or 0)),
                            "import_percent": _safe_str(getattr(c, "import_cost", getattr(c, "import_percent", 0) or 0)),
                            "new_tariff_percent": _safe_str(getattr(c, "new_tariff", getattr(c, "new_tariff_percent", 0) or 0)),
                            "reciprocal_tariff_percent": _safe_str(getattr(c, "reciprocal_tariff", getattr(c, "reciprocal_tariff_percent", 0) or 0)),
                            "ship_us_percent": _safe_str(getattr(c, "shipping_us", getattr(c, "ship_us_percent", 0) or 0)),
                            "us_wholesale": _safe_str(getattr(c, "us_wholesale_margin", getattr(c, "us_wholesale_percent", 0) or 0)),
                        }
                    except Exception:
                        cat_item = {
                            "id": getattr(c, "id", None),
                            "name": _safe_str(c),
                            "description": "",
                            "gf_percent": "0",
                            "texas_buying_percent": "0",
                            "texas_retail_percent": "0",
                            "shipping_inr": "0",
                            "tx_to_us_percent": "0",
                            "import_percent": "0",
                            "new_tariff_percent": "0",
                            "reciprocal_tariff_percent": "0",
                            "ship_us_percent": "0",
                            "us_wholesale": "0",
                        }

                    self.master_data["categories"].append(cat_item)

            # Build sizes_by_category from category_master_new.Category if possible
            try:
                CatNewModel = apps.get_model("category_master_new", "Category")
            except LookupError:
                CatNewModel = None

            if CatNewModel:
                try:
                    cat_objs = CatNewModel.objects.all()
                except Exception:
                    try:
                        cat_objs = CatNewModel.objects.all().order_by("id")
                    except Exception:
                        cat_objs = []

                # helper to extract sizes list from a category instance
                def _extract_sizes_from_cat(cat):
                    sizes_list = []
                    candidate_attrs = ("sizes", "size_set", "size_list", "sizes_all", "size_master_set", "sizes_data", "sizes_json", "size_data")
                    for attr in candidate_attrs:
                        if hasattr(cat, attr):
                            try:
                                candidate = getattr(cat, attr)
                                if hasattr(candidate, "all"):
                                    seq = list(candidate.all())
                                else:
                                    try:
                                        seq = list(candidate)
                                    except Exception:
                                        seq = [candidate]
                                for item in seq:
                                    try:
                                        if isinstance(item, dict):
                                            s_label = item.get("size") or item.get("label") or item.get("name") or _safe_str(item)
                                            stitch = _safe_str(item.get("stitch") or item.get("stitching") or item.get("stitching_cost") or 0)
                                            finish = _safe_str(item.get("finish") or item.get("finishing") or item.get("finish_cost") or 0)
                                            pack = _safe_str(item.get("pack") or item.get("packaging") or item.get("pack_cost") or 0)
                                            sizes_list.append({
                                                "size": s_label,
                                                "stitch": stitch,
                                                "finish": finish,
                                                "pack": pack
                                            })
                                        else:
                                            s_label = getattr(item, "size", None) or getattr(item, "label", None) or getattr(item, "name", None) or _safe_str(item)
                                            stitch = getattr(item, "stitch", None) or getattr(item, "stitching", None) or getattr(item, "stitching_cost", None) or 0
                                            finish = getattr(item, "finish", None) or getattr(item, "finishing", None) or getattr(item, "finish_cost", None) or 0
                                            pack = getattr(item, "pack", None) or getattr(item, "packaging", None) or getattr(item, "pack_cost", None) or 0
                                            sizes_list.append({
                                                "size": _safe_str(s_label),
                                                "stitch": _safe_str(stitch),
                                                "finish": _safe_str(finish),
                                                "pack": _safe_str(pack)
                                            })
                                    except Exception:
                                        continue
                                if sizes_list:
                                    return sizes_list
                            except Exception:
                                continue
                    try:
                        raw = getattr(cat, "sizes", None) or getattr(cat, "sizes_json", None) or getattr(cat, "sizes_data", None)
                        if raw:
                            if isinstance(raw, str):
                                import re
                                for part in raw.splitlines():
                                    m = re.search(r"^(.+?)\s+[—-]\s*([\d\.]+)\s*\/\s*([\d\.]+)\s*\/\s*([\d\.]+)", part.strip())
                                    if m:
                                        sizes_list.append({
                                            "size": m.group(1).strip(),
                                            "stitch": m.group(2).strip(),
                                            "finish": m.group(3).strip(),
                                            "pack": m.group(4).strip()
                                        })
                            else:
                                try:
                                    for item in raw:
                                        sizes_list.append({
                                            "size": _safe_str(item.get("size") or item.get("label") or item.get("name") or item),
                                            "stitch": _safe_str(item.get("stitch") or item.get("stitching") or 0),
                                            "finish": _safe_str(item.get("finish") or item.get("finishing") or 0),
                                            "pack": _safe_str(item.get("pack") or item.get("packaging") or 0),
                                        })
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    return sizes_list

                for c in cat_objs:
                    try:
                        sizes = _extract_sizes_from_cat(c)
                        key = getattr(c, "id", None) or getattr(c, "pk", None) or _safe_str(getattr(c, "name", getattr(c, "title", c)))
                        if key is None:
                            key = _safe_str(c)
                        self.master_data["sizes_by_category"][str(key)] = sizes
                        display_key = _safe_str(getattr(c, "name", getattr(c, "title", None) or c))
                        if display_key:
                            if str(display_key) not in self.master_data["sizes_by_category"]:
                                self.master_data["sizes_by_category"][str(display_key)] = sizes
                    except Exception:
                        continue

            # -----------------------
            # Colors: populate choices with ComponentColor-ish model if present
            # -----------------------
            try:
                # Try common possible models/locations for colors
                ColorModel = None
                for attempt in (
                    ("components", "ComponentColor"),
                    ("component_master", "ComponentColor"),
                    ("components", "Color"),
                    ("component_master", "Color"),
                    ("components", "Component"),
                    ("component_master", "Component"),
                ):
                    try:
                        ColorModel = apps.get_model(attempt[0], attempt[1])
                        if ColorModel:
                            break
                    except Exception:
                        ColorModel = None
                choices = []
                if ColorModel:
                    # If model has 'name' or 'color' attribute use it, else str()
                    qs = ColorModel.objects.all().order_by("id")
                    for col in qs:
                        try:
                            label = getattr(col, "name", None) or getattr(col, "color", None) or _safe_str(col)
                            choices.append((str(getattr(col, "id", _safe_str(label))), _safe_str(label)))
                        except Exception:
                            continue
                # set choices (can be empty)
                self.fields["colors"].choices = choices
                # expose widget attrs for potential JS use
                try:
                    self.fields["colors"].widget.attrs.update({"id": "id_colors"})
                except Exception:
                    pass
            except Exception:
                # On any failure, keep empty choices
                try:
                    self.fields["colors"].choices = []
                except Exception:
                    pass

        # ---- validators and cleaning methods ----
        def clean_average(self):
            if "average" not in self.cleaned_data:
                return Decimal("0")
            val = self.cleaned_data.get("average") or Decimal("0")
            try:
                v = Decimal(str(val))
            except Exception:
                raise ValidationError("Invalid average value.")
            if v < 0:
                raise ValidationError("Average cannot be negative.")
            return v

        def clean_price_per_sqft(self):
            if "price_per_sqft" not in self.cleaned_data:
                return Decimal("0.0000")
            val = self.cleaned_data.get("price_per_sqft") or Decimal("0.0000")
            d = _to_decimal_safe(val, default=Decimal("0.0000"))
            if d < 0:
                raise ValidationError("Price per sq.ft cannot be negative.")
            try:
                return d.quantize(Decimal("0.0001"))
            except Exception:
                return d

        def clean_final_cost(self):
            if "final_cost" not in self.cleaned_data:
                return Decimal("0.00")
            val = self.cleaned_data.get("final_cost") or Decimal("0.00")
            d = _to_decimal_safe(val, default=Decimal("0.00"))
            if d < 0:
                raise ValidationError("Final cost cannot be negative.")
            try:
                return d.quantize(Decimal("0.01"))
            except Exception:
                return d

        def clean_width(self):
            if "width" not in self.cleaned_data:
                return Decimal("0.00")
            val = self.cleaned_data.get("width") or Decimal("0.00")
            d = _to_decimal_safe(val, default=Decimal("0.00"))
            if d < 0:
                raise ValidationError("Width cannot be negative.")
            try:
                return d.quantize(Decimal("0.01"))
            except Exception:
                return d

        # small validators for stitching/finishing/packaging to ensure >= 0
        def clean_stitching(self):
            if "stitching" not in self.cleaned_data:
                return Decimal("0.00")
            val = self.cleaned_data.get("stitching") or Decimal("0.00")
            d = _to_decimal_safe(val, default=Decimal("0.00"))
            if d < 0:
                raise ValidationError("Stitching cannot be negative.")
            try:
                return d.quantize(Decimal("0.01"))
            except Exception:
                return d

        def clean_finishing(self):
            if "finishing" not in self.cleaned_data:
                return Decimal("0.00")
            val = self.cleaned_data.get("finishing") or Decimal("0.00")
            d = _to_decimal_safe(val, default=Decimal("0.00"))
            if d < 0:
                raise ValidationError("Finishing cannot be negative.")
            try:
                return d.quantize(Decimal("0.01"))
            except Exception:
                return d

        def clean_packaging(self):
            if "packaging" not in self.cleaned_data:
                return Decimal("0.00")
            val = self.cleaned_data.get("packaging") or Decimal("0.00")
            d = _to_decimal_safe(val, default=Decimal("0.00"))
            if d < 0:
                raise ValidationError("Packaging cannot be negative.")
            try:
                return d.quantize(Decimal("0.01"))
            except Exception:
                return d

        def clean_sku(self):
            """
            Keep SKU uppercase and stripped if user provided one.
            The model will auto-generate if left blank and inputs are present.
            """
            val = self.cleaned_data.get("sku", "")
            if not val:
                return val
            try:
                return str(val).strip().upper()
            except Exception:
                return val

        def clean(self):
            cleaned = super().clean()

            # If a ComponentMaster is selected but numeric snapshot fields are missing/zero,
            # fill from the ComponentMaster to ensure server-side consistency.
            if "component_master" in self.cleaned_data and getattr(self, "instance", None):
                try:
                    inst = self.instance
                    cm = self.cleaned_data.get("component_master")
                    if cm and (not inst.final_cost or _to_decimal_safe(inst.final_cost) == Decimal("0")):
                        try:
                            inst._copy_from_component_master_if_missing()
                        except Exception:
                            pass
                except Exception:
                    pass

            # Normalize incoming colors: ensure list of strings (ids)
            try:
                colors_val = cleaned.get("colors")
                if colors_val is None:
                    # If client posted as colors (string comma separated), try parsing
                    raw = (self.data.getlist("colors") if hasattr(self.data, "getlist") else None) or self.data.get("colors")
                    if raw is None:
                        cleaned["colors"] = []
                    else:
                        if isinstance(raw, (list, tuple)):
                            cleaned["colors"] = [str(x) for x in raw if x is not None and str(x).strip()]
                        else:
                            # comma separated
                            cleaned["colors"] = [s.strip() for s in str(raw).split(",") if s.strip()]
            except Exception:
                # keep as-is on failure
                pass

            return cleaned

    return CostingSheetForm
