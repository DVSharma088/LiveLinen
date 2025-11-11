# issue_material/views.py
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseNotAllowed,
    JsonResponse,
)
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.forms import ModelForm

# Template paths (adjust if you keep templates elsewhere)
TEMPLATE_BASE = "issue_forms"
TEMPLATE_FORM = f"{TEMPLATE_BASE}/issue_form.html"
TEMPLATE_LIST = f"{TEMPLATE_BASE}/issue_list.html"
TEMPLATE_DETAIL = f"{TEMPLATE_BASE}/issue_detail.html"


def _get_issue_model_safe():
    """Return Issue model; accept either 'Issue' or 'IssueMaterial'."""
    try:
        return apps.get_model("issue_material", "Issue")
    except LookupError:
        try:
            return apps.get_model("issue_material", "IssueMaterial")
        except LookupError as e:
            raise LookupError(
                "Model 'Issue' or 'IssueMaterial' not found in app 'issue_material'. "
                "Check issue_material/models.py and INSTALLED_APPS."
            ) from e


def _ensure_form_for_model(model_class):
    """Return a ModelForm for Issue model; use user-supplied form if present."""
    try:
        from .forms import IssueMaterialForm as UserForm  # optional
        return UserForm
    except Exception:
        class AutoForm(ModelForm):
            class Meta:
                model = model_class
                fields = "__all__"

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                for f in self.fields.values():
                    try:
                        f.widget.attrs.setdefault("class", "form-control")
                    except Exception:
                        pass
        return AutoForm


# --------------------------
# Inventory lookup helpers (used by AJAX + create)
# --------------------------
def _guess_model_candidates(inventory_type: str) -> List[Tuple[str, str]]:
    inventory_type = (inventory_type or "").lower()
    if inventory_type == "accessory":
        return [("rawmaterials", "Accessory"), ("raw_materials", "Accessory"), ("inventory", "Accessory")]
    if inventory_type == "fabric":
        return [("rawmaterials", "Fabric"), ("raw_materials", "Fabric"), ("inventory", "Fabric")]
    if inventory_type in ("printed", "print"):
        return [("rawmaterials", "Printed"), ("raw_materials", "Printed"), ("inventory", "Printed")]
    # generic fallbacks
    return [("rawmaterials", inventory_type.title()), ("raw_materials", inventory_type.title()), ("inventory", inventory_type.title())]


def _read_stock_for_obj(obj) -> Optional[Decimal]:
    """
    Read numeric stock from common fields on inventory objects.
    Returns Decimal or None if not available.
    """
    for attr in ("stock", "stock_in_mtrs", "quantity", "quantity_used"):
        if hasattr(obj, attr):
            try:
                val = getattr(obj, attr)
                if val is None:
                    return None
                return Decimal(str(val))
            except Exception:
                return None
    return None


def _serialize_obj_for_ajax(obj) -> Dict[str, Optional[str]]:
    # Try multiple name fields
    name = (
        getattr(obj, "item_name", None)
        or getattr(obj, "name", None)
        or getattr(obj, "title", None)
        or str(obj)
    )
    stock = _read_stock_for_obj(obj)
    stock_str = None
    try:
        if stock is not None:
            stock_str = str(stock)
    except Exception:
        stock_str = None
    return {"id": getattr(obj, "pk", None), "name": name, "stock": stock_str}


# --------------------------
# AJAX endpoint
# --------------------------
@login_required
def inventory_items_by_type(request: HttpRequest) -> JsonResponse:
    """
    /issue-material/ajax/items-by-type/?inventory_type=accessory
    Returns {"results":[{"id":..., "name":..., "stock":...}, ...]}
    """
    app_label = request.GET.get("app_label")
    model_name = request.GET.get("model")
    inventory_type = request.GET.get("inventory_type", "").strip()

    models_to_try: List[Tuple[str, str]] = []
    if app_label and model_name:
        models_to_try.append((app_label, model_name))
    elif inventory_type:
        models_to_try.extend(_guess_model_candidates(inventory_type))
    else:
        return JsonResponse({"results": [], "error": "No inventory_type or app_label+model provided."}, status=400)

    results: List[Dict[str, Optional[str]]] = []
    for (app_lbl, mdl_name) in models_to_try:
        try:
            ModelClass = apps.get_model(app_lbl, mdl_name)
        except LookupError:
            continue

        qs = ModelClass.objects.all()
        if hasattr(ModelClass, "is_active"):
            qs = qs.filter(is_active=True)
        elif hasattr(ModelClass, "active"):
            qs = qs.filter(active=True)

        qs = qs.order_by("pk")[:500]
        for obj in qs:
            results.append(_serialize_obj_for_ajax(obj))
        if results:
            break

    # content-type fallback
    if not results:
        try:
            from django.contrib.contenttypes.models import ContentType as CT
            cts = CT.objects.filter(model__icontains=inventory_type)[:10]
            for ct in cts:
                try:
                    ModelClass = ct.model_class()
                    if ModelClass is None:
                        continue
                    qs = ModelClass.objects.all()[:200]
                    for obj in qs:
                        results.append(_serialize_obj_for_ajax(obj))
                    if results:
                        break
                except Exception:
                    continue
        except Exception:
            pass

    return JsonResponse({"results": results})


# --------------------------
# Create (multiple lines) with from_waste handling and atomic deduction
# --------------------------
@login_required
def create_issue(request: HttpRequest) -> HttpResponse:
    """
    GET: render minimal multi-line form.
    POST: accept arrays: inventory_type[], item_id[], qty[] along with name & order_no & from_waste[].
    After creating Issue + IssueLines it will attempt to apply the Issue (deduct stock for non-waste lines)
    inside the same transaction to ensure atomicity.
    """
    if request.method != "POST":
        return render(request, TEMPLATE_FORM, {})

    name = (request.POST.get("name") or "").strip()
    order_no = (request.POST.get("order_no") or "").strip()

    inventory_types = request.POST.getlist("inventory_type")
    item_ids = request.POST.getlist("item_id")
    qtys = request.POST.getlist("qty")
    # getlist of from_waste; frontend sets hidden inputs so there will be exactly one value per row
    from_waste_list = request.POST.getlist("from_waste")

    # Build validated lines
    lines: List[Dict[str, Any]] = []
    max_len = max(len(inventory_types), len(item_ids), len(qtys), len(from_waste_list))
    for i in range(max_len):
        itype = (inventory_types[i] if i < len(inventory_types) else "").strip().lower()
        iid = (item_ids[i] if i < len(item_ids) else "").strip()
        qraw = (qtys[i] if i < len(qtys) else "").strip()
        # determine from_waste for this index: tolerant parsing
        fw_val = (from_waste_list[i] if i < len(from_waste_list) else "")
        from_waste_flag = str(fw_val).lower() in ("1", "true", "on", "yes", "y", "t")

        # skip blank rows
        if not itype and not iid and not qraw:
            continue
        if not itype or not iid:
            messages.error(request, f"Line {i+1}: missing inventory type or item.")
            return redirect(reverse("issue_material:create_issue"))
        try:
            q = Decimal(qraw or "0")
            if q <= 0:
                raise ValueError()
        except Exception:
            messages.error(request, f"Line {i+1}: quantity must be a positive number.")
            return redirect(reverse("issue_material:create_issue"))
        lines.append({"inventory_type": itype, "item_id": iid, "qty": q, "from_waste": from_waste_flag})

    if not lines:
        messages.error(request, "Please add at least one item line.")
        return redirect(reverse("issue_material:create_issue"))

    # Resolve each line to a real object
    resolved: List[Dict[str, Any]] = []
    for idx, ln in enumerate(lines, start=1):
        itype = ln["inventory_type"]
        iid = ln["item_id"]
        qty = ln["qty"]
        fw = ln["from_waste"]
        found = None
        for app_label, model_name in _guess_model_candidates(itype):
            try:
                ModelClass = apps.get_model(app_label, model_name)
            except LookupError:
                continue
            if ModelClass is None:
                continue
            try:
                obj = ModelClass.objects.get(pk=iid)
                found = (app_label, model_name, obj)
                break
            except ModelClass.DoesNotExist:
                continue
        if not found:
            messages.error(request, f"Line {idx}: selected item not found on server (type={itype}, id={iid}).")
            return redirect(reverse("issue_material:create_issue"))
        app_label, model_name, obj = found
        resolved.append({"app_label": app_label, "model_name": model_name, "obj": obj, "inventory_type": itype, "qty": qty, "from_waste": fw})

    # Create Issue + IssueLine atomically and attempt to apply (deduct) for non-waste lines
    try:
        IssueModel = _get_issue_model_safe()
        IssueLineModel = apps.get_model("issue_material", "IssueLine")
    except LookupError:
        messages.error(request, "Issue models not configured properly.")
        return redirect(reverse("issue_material:create_issue"))

    try:
        with transaction.atomic():
            product_name = name or (" / ".join([getattr(r["obj"], "item_name", getattr(r["obj"], "name", getattr(r["obj"], "title", str(r["obj"])))) for r in resolved])[:200])
            issue = IssueModel.objects.create(product=product_name, order_no=order_no or None, created_by=request.user if request.user.is_authenticated else None)

            created_lines = []
            for r in resolved:
                ct = ContentType.objects.get(app_label=r["app_label"], model=r["model_name"].lower())
                line = IssueLineModel.objects.create(
                    issue=issue,
                    inventory_type=r["inventory_type"],
                    content_type=ct,
                    object_id=getattr(r["obj"], "pk"),
                    qty=r["qty"],
                    item_name=str(getattr(r["obj"], "item_name", getattr(r["obj"], "name", getattr(r["obj"], "title", str(r["obj"]))))),
                    stock_at_issue=_read_stock_for_obj(r["obj"]),
                    from_waste=r["from_waste"],
                )
                created_lines.append(line)

            # Now attempt deductions (apply_issue handles from_waste internally)
            issue.apply_issue()

        messages.success(request, "Issue created with linked lines.")
        return redirect(reverse("issue_material:issue_list"))
    except ValidationError as ve:
        # Specific validation from stock deduction or model validation
        messages.error(request, f"Could not apply issue: {ve}")
        return redirect(reverse("issue_material:create_issue"))
    except Exception as e:
        messages.error(request, f"Could not create issue: {e}")
        return redirect(reverse("issue_material:create_issue"))


# --------------------------
# Edit, delete, detail, list
# --------------------------
@login_required
def _edit_issue_impl(request: HttpRequest, pk: int) -> HttpResponse:
    try:
        Issue = _get_issue_model_safe()
    except LookupError as e:
        return HttpResponse(f"<h2>Configuration error</h2><p>{e}</p>", status=500)
    instance = get_object_or_404(Issue, pk=pk)
    FormClass = _ensure_form_for_model(Issue)
    if request.method == "POST":
        form = FormClass(request.POST, request.FILES or None, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)
            if hasattr(obj, "updated_by"):
                obj.updated_by = request.user
            obj.save()
            form.save_m2m()
            messages.success(request, "Issue updated successfully.")
            return redirect(reverse("issue_material:issue_list"))
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = FormClass(instance=instance)
    context = {"form": form, "object": instance, "is_edit": True}
    return render(request, TEMPLATE_FORM, context)


@login_required
def delete_issue_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Accept POST only to delete an Issue.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    try:
        Issue = _get_issue_model_safe()
    except LookupError as e:
        return HttpResponse(f"<h2>Configuration error</h2><p>{e}</p>", status=500)
    instance = get_object_or_404(Issue, pk=pk)
    instance.delete()
    messages.success(request, "Issue deleted.")
    return redirect(reverse("issue_material:issue_list"))


@login_required
def detail_issue_view(request: HttpRequest, pk: int) -> HttpResponse:
    try:
        Issue = _get_issue_model_safe()
    except LookupError as e:
        return HttpResponse(f"<h2>Configuration error</h2><p>{e}</p>", status=500)
    instance = get_object_or_404(Issue, pk=pk)
    return render(request, TEMPLATE_DETAIL, {"object": instance})


def _list_issues_impl(request: HttpRequest) -> HttpResponse:
    try:
        Issue = _get_issue_model_safe()
    except LookupError as e:
        return HttpResponse(f"<h2>Configuration error</h2><p>{e}</p>", status=500)
    qs = Issue.objects.all().order_by("-id")
    page = request.GET.get("page", 1)
    per_page = request.GET.get("per_page", 25)
    try:
        per_page = int(per_page)
    except Exception:
        per_page = 25
    paginator = Paginator(qs, per_page)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    context = {"object_list": page_obj.object_list, "page_obj": page_obj, "paginator": paginator}
    return render(request, TEMPLATE_LIST, context)


# --------------------------
# Public aliases (names your urls.py may reference)
# --------------------------
# list
issue_list = _list_issues_impl
list_issues = _list_issues_impl
list_issue = _list_issues_impl

# create
issue_create = create_issue
create_issue = create_issue

# edit / update
issue_edit = _edit_issue_impl
edit_issue = _edit_issue_impl
issue_update = _edit_issue_impl
update_issue = _edit_issue_impl

# delete (provide both names)
issue_delete = delete_issue_view
delete_issue = delete_issue_view

# detail
issue_detail = detail_issue_view
detail_issue = detail_issue_view

# ajax
inventory_items_by_type = inventory_items_by_type
