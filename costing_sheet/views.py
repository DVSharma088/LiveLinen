# costing_sheet/views.py
import json
import re
from decimal import Decimal
from typing import Optional, Any, Dict, List

from django.http import JsonResponse, HttpRequest
from django.urls import reverse_lazy, reverse
from django.views.generic import CreateView, ListView
from django.apps import apps
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.db import models as django_models
from django.shortcuts import get_object_or_404, redirect

from .models import CostingSheet
from .forms import get_costing_sheet_form


# ---------------------------
# Utilities
# ---------------------------
def _decimal_to_str(val) -> str:
    try:
        if isinstance(val, Decimal):
            return format(val, "f")
        if val is None:
            return "0"
        return str(val)
    except Exception:
        return "0"


def _get_model(app_label: str, model_name: str):
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def _get_order_field_for_model(model) -> Optional[str]:
    if not model:
        return None
    field_map = {f.name: f for f in model._meta.get_fields() if not (f.many_to_many or f.one_to_many)}
    for candidate in ("name", "size", "title", "label"):
        if candidate in field_map:
            return candidate
    for fname, f in field_map.items():
        if isinstance(f, (django_models.CharField, django_models.TextField)):
            return fname
    if "id" in field_map:
        return "id"
    return None


def _safe_str(v):
    try:
        if v is None:
            return ""
        return str(v)
    except Exception:
        return ""


def _size_row_to_dict(row_obj: Any) -> Optional[Dict]:
    """
    Normalize a size row (model instance or dict-like) into a predictable dict.
    This expects the row to contain stitching/finishing/packaging fields (CategorySize).
    """
    try:
        if row_obj is None:
            return None

        if isinstance(row_obj, dict):
            rid = row_obj.get("id") or row_obj.get("pk") or row_obj.get("size")
            size_label = row_obj.get("size") or row_obj.get("name") or row_obj.get("label") or str(rid)
            stitch = row_obj.get("stitching_cost", row_obj.get("stitching", row_obj.get("stitch", 0)))
            finish = row_obj.get("finishing_cost", row_obj.get("finishing", row_obj.get("finish", 0)))
            pack = row_obj.get("packaging_cost", row_obj.get("packaging", row_obj.get("pack", 0)))
            return {
                "id": str(rid) if rid is not None else "",
                "size": _safe_str(size_label),
                "stitching_cost": _decimal_to_str(stitch),
                "stitching": _decimal_to_str(stitch),
                "finishing_cost": _decimal_to_str(finish),
                "finishing": _decimal_to_str(finish),
                "packaging_cost": _decimal_to_str(pack),
                "packaging": _decimal_to_str(pack),
                "_raw": row_obj
            }

        # model-like object (CategorySize instance)
        rid = getattr(row_obj, "id", getattr(row_obj, "pk", None))
        size_label = getattr(row_obj, "name", None) or getattr(row_obj, "size", None) or str(rid)
        stitch_val = getattr(row_obj, "stitching", None)
        if stitch_val is None:
            stitch_val = getattr(row_obj, "stitching_cost", getattr(row_obj, "stitch", 0))
        finish_val = getattr(row_obj, "finishing", None)
        if finish_val is None:
            finish_val = getattr(row_obj, "finishing_cost", getattr(row_obj, "finish", 0))
        pack_val = getattr(row_obj, "packaging", None)
        if pack_val is None:
            pack_val = getattr(row_obj, "packaging_cost", getattr(row_obj, "pack", 0))

        return {
            "id": str(rid) if rid is not None else "",
            "size": _safe_str(size_label),
            "stitching_cost": _decimal_to_str(stitch_val),
            "stitching": _decimal_to_str(stitch_val),
            "finishing_cost": _decimal_to_str(finish_val),
            "finishing": _decimal_to_str(finish_val),
            "packaging_cost": _decimal_to_str(pack_val),
            "packaging": _decimal_to_str(pack_val),
            "_raw": None
        }
    except Exception:
        return None


# ---------------------------
# SKU helpers (for live AJAX preview)
# ---------------------------
def _clean_words(s: str) -> List[str]:
    if not s:
        return []
    s = re.sub(r"[^A-Za-z0-9]+", " ", str(s)).strip()
    if not s:
        return []
    return [w for w in s.split() if w]


def _initials_from_phrase(phrase: str, max_letters: int = 2) -> str:
    words = _clean_words(phrase)
    if not words:
        return ""
    initials = "".join(w[0] for w in words[:max_letters])
    return initials.upper()


def _first_n_from_word(word: str, n: int = 3) -> str:
    if not word:
        return ""
    w = re.sub(r"[^A-Za-z0-9]", "", str(word))
    return w[:n].upper()


def _compute_sku_server(category_label: str, name_val: str, collection_val: str, color_val: str, size_val: str) -> str:
    """
    Mirrors the model's SKU logic so the client can preview without save():
      - cat2 (initials of Category words, up to 2)  e.g. Women Top -> WT, Dress -> D
      - col2 (initials of Collection words, up to 2) e.g. Solid Color -> SC, Solid -> S
      - name2nd3 (first 3 letters of SECOND word of Name) e.g. Linen Mate Shoes -> MAT, Linen White -> WHI; if only 1 word -> ""
      - color2 (initials of Color words, up to 2) e.g. Angora White -> AW, White -> W
      - size (as-is, uppercased, spaces stripped) e.g. S, XL, XXL
      Concatenate without separators. Only return non-empty if *all five* inputs are present.
    """
    category_label = (category_label or "").strip()
    name_val = (name_val or "").strip()
    collection_val = (collection_val or "").strip()
    color_val = (color_val or "").strip()
    size_val = (size_val or "").strip()

    if not (category_label and name_val and collection_val and color_val and size_val):
        return ""

    cat2 = _initials_from_phrase(category_label, 2)
    col2 = _initials_from_phrase(collection_val, 2)

    name_words = _clean_words(name_val)
    name2nd3 = _first_n_from_word(name_words[1], 3) if len(name_words) >= 2 else ""

    color2 = _initials_from_phrase(color_val, 2)
    size_block = re.sub(r"\s+", "", size_val).upper()

    return "".join([p for p in (cat2, col2, name2nd3, color2, size_block) if p])


# ---------------------------
# Views
# ---------------------------
@method_decorator(login_required, name="dispatch")
class CostingSheetCreateView(CreateView):
    model = CostingSheet
    template_name = "costing_sheet/costing_form.html"
    success_url = reverse_lazy("costing_sheet:list")

    def get_form_class(self):
        return get_costing_sheet_form()

    def form_valid(self, form):
        """
        Keep legacy behaviour: snapshot size label if size_master posted, and accept legacy category_new POST.
        """
        inst = form.instance
        try:
            cd = self.request.POST
            if "category_new" in form.fields and not getattr(inst, "category_new_id", None):
                val = cd.get("category_new") or cd.get("category_master_new")
                if val:
                    try:
                        inst.category_new_id = int(val)
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            if "size_master" in form.fields:
                size_val = self.request.POST.get("size_master") or self.request.POST.get("size")
                if size_val:
                    SM = _get_model("category_master_new", "CategorySize")
                    found = None
                    if SM:
                        try:
                            found = SM.objects.filter(pk=size_val).first()
                        except Exception:
                            found = None
                    if found:
                        label = getattr(found, "name", None) or getattr(found, "size", None) or str(getattr(found, "id", found))
                        inst.size = label
                        try:
                            inst.size_master_id = getattr(found, "id", getattr(found, "pk", None))
                        except Exception:
                            pass
                    else:
                        inst.size = size_val
        except Exception:
            pass

        # Let the model compute SKU on save() if it's blank and inputs exist.
        return super().form_valid(form)

    def get_initial(self):
        initial = super().get_initial() or {}
        copy_from = self.request.GET.get("copy_from")
        if not copy_from:
            return initial
        try:
            src = CostingSheet.objects.filter(pk=copy_from).first()
        except Exception:
            src = None
        if not src:
            return initial
        initial.update({
            "category": getattr(src, "category_id", None) or getattr(src, "category", None),
            "name": getattr(src, "name", None),
            "collection": getattr(src, "collection", None),
            "color": getattr(src, "color", None),
            "sku": getattr(src, "sku", None),
            "component_master": getattr(src, "component_master_id", None) or getattr(src, "component_master", None),
            "accessory": getattr(src, "accessory_id", None) or getattr(src, "accessory", None),
            "accessory_quantity": getattr(src, "accessory_quantity", None),
            "final_cost": getattr(src, "final_cost", None),
            "price_per_sqft": getattr(src, "price_per_sqft", None),
            "width": getattr(src, "width", None),
            "category_new": getattr(src, "category_new_id", None) or getattr(src, "category_new", None),
            "size_master": getattr(src, "size_master_id", None) or getattr(src, "size_master", None),
        })
        return initial

    def get_context_data(self, **kwargs):
        """
        Strict behavior (no fallbacks):
        1) ctx['categories'] = categories from category_master.CategoryMaster (first dropdown).
           First dropdown auto-fill fields (GF, Texas, Shipping, Import) should be obtained
           by calling ajax_get_category_details which reads CategoryMaster only.

        2) ctx['costing_master_json'] = categories & sizes from category_master_new.Category
           and category_master_new.CategorySize. Each size contains stitching/finishing/packaging
           (used to fill Stitching (INR), Finishing (INR), Packaging (INR) for the second dropdown).
        """
        ctx = super().get_context_data(**kwargs)
        form = ctx.get("form")
        if not form:
            FormClass = self.get_form_class()
            form = FormClass(initial=self.get_initial())
            ctx["form"] = form

        # Models (strict usage)
        CatPrimary = _get_model("category_master", "CategoryMaster")
        CatNew = _get_model("category_master_new", "Category")
        CatSize = _get_model("category_master_new", "CategorySize")

        # ordering decision
        cat_order_field = _get_order_field_for_model(CatPrimary) or _get_order_field_for_model(CatNew)

        # -------------------------
        # First dropdown (CategoryMaster) — server-rendered list
        # -------------------------
        categories_list: List[Dict] = []
        if CatPrimary:
            try:
                qs = CatPrimary.objects.all()
                if cat_order_field:
                    try:
                        qs = qs.order_by(cat_order_field)
                    except Exception:
                        pass
                for c in qs:
                    try:
                        cid = getattr(c, "id", None)
                        name = getattr(c, "name", None) or getattr(c, "title", None) or str(c)
                        categories_list.append({"id": str(cid) if cid is not None else "", "name": _safe_str(name)})
                    except Exception:
                        continue
            except Exception:
                categories_list = []
        ctx["categories"] = categories_list

        # keep server-side size_masters empty — second dropdown sizes come from costing_master_json (CatNew)
        ctx["size_masters"] = []

        # -------------------------
        # Second dropdown: build costing_master_json from category_master_new (strict)
        # -------------------------
        try:
            normalized_cats: List[Dict] = []
            normalized_sizes: Dict[str, List[Dict]] = {}
            normalized_components: Dict = {}

            if CatNew:
                qs = CatNew.objects.all()
                if cat_order_field:
                    try:
                        qs = qs.order_by(cat_order_field)
                    except Exception:
                        pass
                for c in qs:
                    try:
                        cid = getattr(c, "id", None)
                        name = getattr(c, "name", None) or getattr(c, "title", None) or str(c)
                        normalized_cats.append({
                            "id": str(cid) if cid is not None else "",
                            "name": _safe_str(name),
                            "description": _safe_str(getattr(c, "description", "") or "")
                        })
                    except Exception:
                        continue

                # For each category (CatNew), load sizes from CategorySize only
                if CatSize:
                    for cat in normalized_cats:
                        cid = cat.get("id")
                        arr: List[Dict] = []
                        try:
                            rows = CatSize.objects.filter(category_id=cid)
                        except Exception:
                            rows = CatSize.objects.none()
                        for r in rows:
                            rd = _size_row_to_dict(r)
                            if rd:
                                arr.append(rd)
                        normalized_sizes[str(cid)] = arr

            # Ensure there is at least 'none' key
            if "none" not in normalized_sizes:
                normalized_sizes["none"] = []

            normalized_master = {
                "categories": normalized_cats,
                "sizes_by_category": normalized_sizes,
                "components": normalized_components
            }
            ctx["costing_master_json"] = json.dumps(normalized_master)
            ctx["categories_master_json"] = normalized_cats
        except Exception:
            ctx["costing_master_json"] = json.dumps({"categories": [], "sizes_by_category": {}, "components": {}})
            ctx["categories_master_json"] = []

        return ctx


@method_decorator(login_required, name="dispatch")
class CostingSheetListView(ListView):
    model = CostingSheet
    template_name = "costing_sheet/list.html"
    context_object_name = "sheets"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        rels = []
        for rel in ("category", "component_master", "accessory"):
            try:
                f = CostingSheet._meta.get_field(rel)
                if hasattr(f, "related_model") and f.related_model is not None:
                    rels.append(rel)
            except Exception:
                continue

        if rels:
            try:
                return qs.select_related(*rels)
            except Exception:
                return qs
        return qs


@login_required
def copy_costing_sheet(request: HttpRequest, pk: int):
    _ = get_object_or_404(CostingSheet, pk=pk)
    url = reverse("costing_sheet:create") + f"?copy_from={pk}"
    return redirect(url)


@login_required
def delete_costing_sheet(request: HttpRequest, pk: int):
    sheet = get_object_or_404(CostingSheet, pk=pk)
    sheet.delete()
    return redirect("costing_sheet:list")


# ---------------------------
# AJAX endpoints (strict)
# ---------------------------
@login_required
def ajax_get_sizes(request: HttpRequest):
    """
    Return sizes for a given category_id from category_master_new.CategorySize only.
    Sizes rows include stitching/finishing/packaging (INR) for the second dropdown.
    Also returns category metadata (id/name/description) from category_master_new.Category only.
    """
    cat_id = request.GET.get("category_id")
    if not cat_id:
        return JsonResponse({"error": "category_id is required"}, status=400)

    CatNew = _get_model("category_master_new", "Category")
    CatSize = _get_model("category_master_new", "CategorySize")

    sizes: List[Dict] = []
    if CatSize:
        try:
            rows = CatSize.objects.filter(category_id=cat_id)
        except Exception:
            rows = CatSize.objects.none()
        for s in rows:
            rd = _size_row_to_dict(s)
            if rd:
                sizes.append(rd)

    # category metadata strictly from CatNew
    category_meta = None
    if CatNew:
        try:
            cat_obj = CatNew.objects.filter(pk=cat_id).first()
        except Exception:
            cat_obj = None
        if cat_obj:
            category_meta = {
                "id": getattr(cat_obj, "id", None),
                "name": getattr(cat_obj, "name", str(cat_obj)),
                "description": getattr(cat_obj, "description", "")
            }

    return JsonResponse({"sizes": sizes, "category": category_meta})


@login_required
def ajax_get_category_details(request: HttpRequest):
    """
    Return GF/Tax/Shipping/Import fields for a category id — strictly from category_master.CategoryMaster.
    Intended to service the first dropdown's auto-fill fields:
      GF (%), Texas Buying (%), Texas Retail (%), Shipping (INR), TX -> US (%), Import (%).
    """
    category_id = request.GET.get("category_id")
    if not category_id:
        return JsonResponse({"error": "category_id is required"}, status=400)

    CatPrimary = _get_model("category_master", "CategoryMaster")
    if not CatPrimary:
        return JsonResponse({"error": "CategoryMaster model not found"}, status=500)

    category_obj = CatPrimary.objects.filter(pk=category_id).first()
    if not category_obj:
        return JsonResponse({"error": "Category not found"}, status=404)

    # Use actual field names from CategoryMaster model
    component = {
        "component": getattr(category_obj, "name", str(category_obj)),
        "gf_percent": _decimal_to_str(getattr(category_obj, "gf_overhead", 0)),
        "texas_buying_percent": _decimal_to_str(getattr(category_obj, "texas_buying_cost", 0)),
        "texas_retail_percent": _decimal_to_str(getattr(category_obj, "texas_retail", 0)),
        "shipping_inr": _decimal_to_str(getattr(category_obj, "shipping_cost_inr", 0)),
        "tx_to_us_percent": _decimal_to_str(getattr(category_obj, "texas_to_us_selling_cost", 0)),
        "import_percent": _decimal_to_str(getattr(category_obj, "import_cost", 0)),
    }

    # optional: include size info from CategorySize if size_id is provided
    size_payload = None
    size_id = request.GET.get("size_id")
    if size_id:
        CatSize = _get_model("category_master_new", "CategorySize")
        if CatSize:
            try:
                found = CatSize.objects.filter(pk=size_id).first()
            except Exception:
                found = None
            if found:
                size_payload = _size_row_to_dict(found)
                if hasattr(found, "length"):
                    size_payload["length"] = _decimal_to_str(getattr(found, "length", 0))
                if hasattr(found, "breadth"):
                    size_payload["breadth"] = _decimal_to_str(getattr(found, "breadth", 0))
                if hasattr(found, "sqmt"):
                    size_payload["sqmt"] = _decimal_to_str(getattr(found, "sqmt", 0))

    category_meta = {
        "id": getattr(category_obj, "id", None),
        "name": getattr(category_obj, "name", str(category_obj)),
        "description": getattr(category_obj, "description", "")
    }

    resp = {"category": category_meta, "components": [component]}
    if size_payload:
        resp["size"] = size_payload
    return JsonResponse(resp)


@login_required
def ajax_get_component_details(request: HttpRequest):
    comp_id = request.GET.get("component_id")
    if not comp_id:
        return JsonResponse({"error": "component_id is required"}, status=400)

    ComponentModel = _get_model("components", "ComponentMaster") or _get_model("component_master", "ComponentMaster")
    if not ComponentModel:
        return JsonResponse({"error": "Component model not found"}, status=500)

    try:
        comp = ComponentModel.objects.filter(pk=comp_id).first()
    except Exception:
        comp = None

    if not comp:
        return JsonResponse({"error": "Component not found"}, status=404)

    try:
        display_name = str(comp)
    except Exception:
        display_name = getattr(comp, "name", "") or getattr(comp, "quality", "") or str(getattr(comp, "id", ""))

    comp_payload = {
        "id": getattr(comp, "id", None),
        "display_name": display_name,
        "quality": getattr(comp, "quality", ""),
        "width": _decimal_to_str(getattr(comp, "width", 0)),
        "width_uom": getattr(comp, "width_uom", "inch") or "inch",
        "price_per_sqfoot": _decimal_to_str(getattr(comp, "price_per_sqfoot", getattr(comp, "price_per_sqft", 0))),
        "final_cost": _decimal_to_str(getattr(comp, "final_cost", 0)),
        "final_price_per_unit": _decimal_to_str(getattr(comp, "final_price_per_unit", 0)),
    }

    return JsonResponse({"component": comp_payload})


# ---------- NEW: SKU compute endpoint ----------
@login_required
def ajax_compute_sku(request: HttpRequest):
    """
    Compute SKU from posted inputs without saving:
      Inputs (GET or POST):
        - category_id (legacy CategoryMaster id) OR category_label (string)
        - name
        - collection
        - color
        - size
    Resolution of category label:
      If category_label provided -> use it.
      Else, try to fetch CategoryMaster by category_id and use its name/title/str().
    Returns {"sku": "<computed or empty string>"}.
    """
    method_data = request.POST if request.method == "POST" else request.GET

    category_label = (method_data.get("category_label") or "").strip()
    category_id = method_data.get("category_id")
    name_val = (method_data.get("name") or "").strip()
    collection_val = (method_data.get("collection") or "").strip()
    color_val = (method_data.get("color") or "").strip()
    size_val = (method_data.get("size") or "").strip()

    if not category_label:
        if category_id:
            CatPrimary = _get_model("category_master", "CategoryMaster")
            cat_obj = None
            if CatPrimary:
                try:
                    cat_obj = CatPrimary.objects.filter(pk=category_id).first()
                except Exception:
                    cat_obj = None
            if cat_obj:
                category_label = getattr(cat_obj, "name", None) or getattr(cat_obj, "title", None) or str(cat_obj)

    sku = _compute_sku_server(category_label, name_val, collection_val, color_val, size_val)
    return JsonResponse({"sku": sku})


# ---------- Accessory endpoints (unchanged) ----------
@login_required
def ajax_list_accessories(request: HttpRequest):
    Accessory = _get_model("rawmaterials", "Accessory")
    if not Accessory:
        return JsonResponse({"error": "Accessory model not found"}, status=500)
    q = (request.GET.get("q") or "").strip()
    vendor_id = request.GET.get("vendor_id")
    item_type = request.GET.get("item_type")
    try:
        limit = int(request.GET.get("limit", 50))
        offset = int(request.GET.get("offset", 0))
    except Exception:
        limit = 50
        offset = 0
    qs = Accessory.objects.all()
    if q:
        qs = qs.filter(
            django_models.Q(item_name__icontains=q) |
            django_models.Q(quality__icontains=q) |
            django_models.Q(quality_text__icontains=q)
        )
    if vendor_id:
        qs = qs.filter(vendor_id=vendor_id)
    if item_type:
        qs = qs.filter(item_type__iexact=item_type)
    count = qs.count()
    results = []
    for a in qs.order_by("-created_at")[offset:offset + limit]:
        try:
            text_label = str(a)
        except Exception:
            text_label = f"{getattr(a, 'item_name', '')} ({getattr(a, 'vendor', '')})"
        results.append({
            "id": getattr(a, "id", None),
            "text": text_label,
            "item_name": getattr(a, "item_name", ""),
            "quality": getattr(a, "quality_display", getattr(a, "quality", "")),
            "cost_per_unit": _decimal_to_str(getattr(a, "cost_per_unit", 0)),
            "unit_cost": _decimal_to_str(getattr(a, "unit_cost", 0)),
            "stock": _decimal_to_str(getattr(a, "stock", 0)),
        })
    return JsonResponse({"count": count, "results": results})


@login_required
def ajax_get_accessory_detail(request: HttpRequest, pk: Optional[int] = None):
    Accessory = _get_model("rawmaterials", "Accessory")
    if not Accessory:
        return JsonResponse({"error": "Accessory model not found"}, status=500)
    accessory_id = pk or request.GET.get("accessory_id")
    if not accessory_id:
        return JsonResponse({"error": "accessory_id is required"}, status=400)
    a = Accessory.objects.filter(pk=accessory_id).select_related("vendor").first()
    if not a:
        return JsonResponse({"error": "Accessory not found"}, status=404)
    vendor_obj = getattr(a, "vendor", None)
    vendor_payload = None
    if vendor_obj:
        vendor_payload = {"id": getattr(vendor_obj, "id", None), "vendor_name": getattr(vendor_obj, "vendor_name", str(vendor_obj))}
    payload = {
        "id": getattr(a, "id", None),
        "item_name": getattr(a, "item_name", ""),
        "quality_display": getattr(a, "quality_display", getattr(a, "quality", "")),
        "cost_per_unit": _decimal_to_str(getattr(a, "cost_per_unit", 0)),
        "unit_cost": _decimal_to_str(getattr(a, "unit_cost", 0)),
        "stock": _decimal_to_str(getattr(a, "stock", 0)),
        "vendor": vendor_payload,
        "use_in": getattr(a, "use_in", ""),
        "item_type": getattr(a, "item_type", ""),
    }
    return JsonResponse(payload)


@login_required
def ajax_accessories_bulk(request: HttpRequest):
    Accessory = _get_model("rawmaterials", "Accessory")
    if not Accessory:
        return JsonResponse({"error": "Accessory model not found"}, status=500)
    ids = None
    if request.method == "POST":
        try:
            body = json.loads(request.body.decode() or "{}")
            ids = body.get("ids")
        except Exception:
            ids = None
    if ids is None:
        ids_param = request.GET.get("ids") or request.GET.get("id_list")
        if ids_param:
            try:
                ids = [int(x) for x in str(ids_param).split(",") if x.strip()]
            except Exception:
                ids = None
    if not ids:
        return JsonResponse({"error": "ids (list) is required"}, status=400)
    qs = Accessory.objects.filter(pk__in=ids).select_related("vendor")
    result = {}
    for a in qs:
        result[str(a.id)] = {
            "id": a.id,
            "item_name": a.item_name,
            "quality_display": getattr(a, "quality_display", a.quality),
            "cost_per_unit": _decimal_to_str(getattr(a, "cost_per_unit", 0)),
            "unit_cost": _decimal_to_str(getattr(a, "unit_cost", 0)),
            "stock": _decimal_to_str(getattr(a, "stock", 0)),
            "vendor": {"id": getattr(a.vendor, "id", None), "vendor_name": getattr(a.vendor, "vendor_name", "")} if getattr(a, "vendor", None) else None,
        }
    return JsonResponse(result)


@login_required
def ajax_compute_accessory_line(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        body = json.loads(request.body.decode() or "{}")
    except Exception:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)
    accessory_id = body.get("accessory_id")
    quantity_raw = body.get("quantity")
    if accessory_id is None:
        return JsonResponse({"error": "accessory_id is required"}, status=400)
    if quantity_raw is None:
        return JsonResponse({"error": "quantity is required"}, status=400)
    Accessory = _get_model("rawmaterials", "Accessory")
    if not Accessory:
        return JsonResponse({"error": "Accessory model not found"}, status=500)
    acc = Accessory.objects.filter(pk=accessory_id).first()
    if not acc:
        return JsonResponse({"error": "Accessory not found"}, status=404)
    try:
        qty = Decimal(str(quantity_raw))
    except Exception:
        return JsonResponse({"error": "Invalid quantity value"}, status=400)
    if qty < 0:
        return JsonResponse({"error": "Quantity must be non-negative"}, status=400)
    unit_price = getattr(acc, "unit_cost", getattr(acc, "cost_per_unit", Decimal("0.00")))
    try:
        if not isinstance(unit_price, Decimal):
            unit_price = Decimal(str(unit_price))
    except Exception:
        unit_price = Decimal("0.00")
    try:
        line_total = (unit_price * qty).quantize(Decimal("0.01"))
    except Exception:
        line_total = Decimal("0.00")
    resp = {
        "accessory_id": accessory_id,
        "unit_price": _decimal_to_str(unit_price),
        "quantity": _decimal_to_str(qty),
        "line_total": _decimal_to_str(line_total),
    }
    return JsonResponse(resp)
