# finished_products/views.py
import json
from decimal import Decimal

from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.utils.safestring import mark_safe
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib import messages
from django.http import JsonResponse  # NEW

from .models import FinishedProduct
from .forms import FinishedProductForm, FinishedProductLineFormSet


# -------------------------
# Role helpers & mixin
# -------------------------
def _in_group(user, group_name):
    return user.groups.filter(name=group_name).exists()


def is_admin(user):
    return user.is_superuser or _in_group(user, "Admin")


def is_manager(user):
    return _in_group(user, "Manager") or is_admin(user)


def is_employee(user):
    return _in_group(user, "Employee") or is_manager(user)


class RoleRequiredMixin:
    """
    Simple mixin for CBVs that checks whether request.user is in any of the
    allowed roles listed in `allowed_roles` (list of strings).
    Superusers always pass.
    """
    allowed_roles = []  # e.g. ["Admin", "Manager", "Employee"]
    raise_exception = True

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            raise PermissionDenied()

        if user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        for role in (self.allowed_roles or []):
            role = (role or "").strip()
            if not role:
                continue
            if role == "Admin" and is_admin(user):
                return super().dispatch(request, *args, **kwargs)
            if role == "Manager" and is_manager(user):
                return super().dispatch(request, *args, **kwargs)
            if role == "Employee" and is_employee(user):
                return super().dispatch(request, *args, **kwargs)
            # fallback: direct group membership
            if user.groups.filter(name=role).exists():
                return super().dispatch(request, *args, **kwargs)

        if self.raise_exception:
            raise PermissionDenied()
        raise PermissionDenied()


# -------------------------
# Views
# -------------------------
class FinishedProductListView(LoginRequiredMixin, ListView):
    model = FinishedProduct
    template_name = "finished_products/finishedproduct_list.html"
    context_object_name = "products"
    paginate_by = 25

    def get_queryset(self):
        # fetch only the necessary fields for the list view (small optimization)
        return (
            FinishedProduct.objects.all()
            .only(
                "id",
                "name",
                "sku",
                "size",
                "product_category",
                "product_price",
                "fabric_color_name",
                "fabric_pattern",
                "total_manufacturing_cost",
                "created_at",
            )
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        # Permission flags for template (both Manager and Employee may manage finished products)
        ctx["can_create"] = user.is_authenticated and (is_admin(user) or is_manager(user) or is_employee(user))
        ctx["can_edit"] = ctx["can_create"]  # no separate edit view here; adjust if you add one
        ctx["can_delete"] = ctx["can_create"]
        return ctx


class FinishedProductCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    """
    Create a FinishedProduct along with its inline FinishedProductLine formset.
    Allowed roles: Admin, Manager, Employee
    """
    model = FinishedProduct
    form_class = FinishedProductForm
    template_name = "finished_products/finishedproduct_form.html"
    success_url = reverse_lazy("finished_products:product_list")
    allowed_roles = ["Admin", "Manager", "Employee"]
    raise_exception = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.method == "POST":
            context["line_formset"] = FinishedProductLineFormSet(self.request.POST)
        else:
            context["line_formset"] = FinishedProductLineFormSet()

        # Build mapping: content_type_id -> list of items for frontend JS
        material_map = {}
        try:
            for ct in ContentType.objects.filter(app_label="rawmaterials").order_by("model"):
                model_cls = ct.model_class()
                if not model_cls:
                    continue
                items = []
                qs = model_cls.objects.all()
                for obj in qs:
                    label = getattr(obj, "name", None) or getattr(obj, "product", None) or str(obj)
                    unit = getattr(obj, "unit", "") if hasattr(obj, "unit") else ""
                    unit_cost = None
                    if hasattr(obj, "unit_cost"):
                        try:
                            unit_cost = getattr(obj, "unit_cost")
                        except Exception:
                            unit_cost = None
                    elif hasattr(obj, "rate"):
                        try:
                            unit_cost = getattr(obj, "rate")
                        except Exception:
                            unit_cost = None
                    else:
                        for attr in ("cost_per_unit", "total_cost", "price"):
                            if hasattr(obj, attr):
                                try:
                                    unit_cost = getattr(obj, attr)
                                except Exception:
                                    unit_cost = None
                                break

                    cost_str = ""
                    if unit_cost is not None and unit_cost != "":
                        try:
                            cost_str = str(unit_cost)
                        except Exception:
                            cost_str = ""

                    stock_val = ""
                    if hasattr(obj, "stock"):
                        try:
                            stock_val = str(getattr(obj, "stock") or "")
                        except Exception:
                            stock_val = ""

                    items.append({
                        "id": obj.pk,
                        "label": label,
                        "unit": unit,
                        "cost": cost_str,
                        "rate": cost_str,
                        "stock": stock_val,
                    })
                if items:
                    material_map[str(ct.pk)] = items
        except Exception:
            material_map = {}

        context["material_items_json"] = mark_safe(json.dumps(material_map))

        # Provide SKU preview endpoint for client-side JS to call.
        try:
            context["sku_preview_url"] = reverse_lazy("finished_products:sku_preview")
        except Exception:
            context["sku_preview_url"] = "/finished-products/sku-preview/"

        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context["line_formset"]

        if not formset.is_valid():
            return self.form_invalid(form)

        grand_total = None
        try:
            with transaction.atomic():
                # Save product
                product = form.save(commit=False)
                product.save()

                # Save formset lines pointing to the saved product
                formset.instance = product
                formset.save()

                # Call model method to process deductions
                deduction_result = product.process_deduction(reason=f"Manufacturing - created by {self.request.user}")

                if isinstance(deduction_result, dict):
                    grand_total = deduction_result.get("grand_total")
                else:
                    grand_total = getattr(product, "total_manufacturing_cost", None)
        except ValidationError as e:
            if hasattr(e, "message_dict"):
                for field, msgs in e.message_dict.items():
                    for msg in msgs:
                        form.add_error(field if field in form.fields else None, msg)
            else:
                msgs = getattr(e, "messages", [str(e)])
                for m in msgs:
                    form.add_error(None, m)
            return self.form_invalid(form)
        except Exception as e:
            form.add_error(None, f"An unexpected error occurred: {e}")
            return self.form_invalid(form)

        try:
            if grand_total is not None:
                messages.success(self.request, f"Finished product created. Total manufacturing cost: ₹ {grand_total}")
            else:
                messages.success(self.request, "Finished product created.")
        except Exception:
            pass

        self.object = product
        return redirect(self.get_success_url())


class FinishedProductDeleteView(LoginRequiredMixin, RoleRequiredMixin, DeleteView):
    """
    Confirm and delete a FinishedProduct. Uses a small confirmation template.
    Allowed roles: Admin, Manager, Employee (per spec both Manager and Employee manage finished products)
    """
    model = FinishedProduct
    template_name = "finished_products/finishedproduct_confirm_delete.html"
    success_url = reverse_lazy("finished_products:product_list")
    allowed_roles = ["Admin", "Manager", "Employee"]
    raise_exception = True

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        messages.success(request, f"Finished product '{obj.name}' (SKU: {obj.sku}) deleted.")
        return super().delete(request, *args, **kwargs)


# ------------------------------
# Small JSON endpoint for SKU preview
# ------------------------------
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required as login_required_fn


@login_required_fn
@require_GET
def sku_preview(request):
    """
    GET params expected:
      - product_type
      - fabric_collection
      - name
      - fabric_color_name
      - size

    Returns: {"sku": "<SKU string>"}
    """
    # Allow any authenticated user (employees/managers/admins)
    pt = request.GET.get("product_type", "") or ""
    coll = request.GET.get("fabric_collection", "") or ""
    name = request.GET.get("name", "") or ""
    color = request.GET.get("fabric_color_name", "") or ""
    size = request.GET.get("size", "") or ""

    # create a transient FinishedProduct to reuse model SKU logic
    fp = FinishedProduct(
        product_type=pt,
        fabric_collection=coll,
        name=name,
        fabric_color_name=color,
        size=size,
    )

    # base SKU (not guaranteed unique). Use model helper to generate base.
    base = fp._generate_sku_base().upper()

    # If you want to return a unique SKU candidate (same uniqueness routine as save),
    # attempt to ensure uniqueness by checking DB. This mirrors model _ensure_unique_sku.
    candidate = base
    suffix = 0
    while True:
        qs = FinishedProduct.objects.filter(sku=candidate)
        if not qs.exists():
            break
        suffix += 1
        candidate = f"{base}-{suffix}"

    return JsonResponse({"sku": candidate})
