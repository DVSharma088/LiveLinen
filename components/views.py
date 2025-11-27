# components/views.py
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.http import JsonResponse
from django.db.models import Q, F, ExpressionWrapper, DecimalField, Value
from django.db.models.functions import Coalesce
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, FieldDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.contrib import messages
from django.shortcuts import redirect, render

from .models import CostComponent, ComponentMaster, Color
from .forms import CostComponentForm, ComponentMasterForm

logger = logging.getLogger(__name__)


# ======================================================
# Small helper to extract 'type' text from inventory instances
# ======================================================
def _extract_type_from_instance(instance):
    """
    Try common attribute or method names on the inventory instance to obtain a textual 'type'.
    Returns string (possibly empty) and never raises.
    """
    if instance is None:
        return ""
    # 1) If instance provides a dedicated method that returns type, call it
    for method_name in ("get_type", "get_product_type", "product_type"):
        method = getattr(instance, method_name, None)
        if callable(method):
            try:
                val = method()
                if val not in (None, ""):
                    return str(val)
            except Exception:
                pass
    # 2) Try common attribute names
    for attr in ("fabric_type", "product_type", "type", "material_type", "variant_type", "item_type"):
        val = getattr(instance, attr, None)
        if val not in (None, ""):
            return str(val)
    # 3) Fallback: empty string
    return ""


# ======================================================
# ROLE HELPERS
# ======================================================
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
    Restrict access based on allowed_roles.
    Superusers always allowed.
    """
    allowed_roles = []
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
            if user.groups.filter(name=role).exists():
                return super().dispatch(request, *args, **kwargs)

        raise PermissionDenied()


# ======================================================
# COST COMPONENT VIEWS
# ======================================================
class CostComponentListView(LoginRequiredMixin, ListView):
    model = CostComponent
    template_name = "components/component_list.html"
    context_object_name = "components"
    paginate_by = 15

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))

        category = self.request.GET.get("category", "").strip().upper()
        if category:
            valid_categories = {c[0] for c in CostComponent.InventoryCategory.choices}
            if category in valid_categories:
                qs = qs.filter(inventory_category=category)

        if not self.request.GET.get("show_inactive"):
            qs = qs.filter(is_active=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "filter_q": self.request.GET.get("q", "").strip(),
            "filter_category": self.request.GET.get("category", "").strip().upper(),
            "show_inactive": bool(self.request.GET.get("show_inactive")),
            "inventory_category_choices": CostComponent.InventoryCategory.choices,
        })
        user = self.request.user
        ctx["can_create"] = user.is_authenticated and (is_admin(user) or is_manager(user) or is_employee(user))
        ctx["can_edit"] = ctx["can_create"]
        ctx["can_delete"] = user.is_authenticated and is_admin(user)
        return ctx


class CostComponentDetailView(LoginRequiredMixin, DetailView):
    model = CostComponent
    template_name = "components/component_detail.html"
    context_object_name = "component"


class CostComponentCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model = CostComponent
    form_class = CostComponentForm
    template_name = "components/component_form.html"
    success_url = reverse_lazy("components:list")
    allowed_roles = ["Admin", "Manager", "Employee"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Create Cost Component"
        return ctx


class CostComponentUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    model = CostComponent
    form_class = CostComponentForm
    template_name = "components/component_form.html"
    success_url = reverse_lazy("components:list")
    allowed_roles = ["Admin", "Manager", "Employee"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Edit Cost Component"
        return ctx


class CostComponentDeleteView(LoginRequiredMixin, RoleRequiredMixin, DeleteView):
    model = CostComponent
    template_name = "components/component_confirm_delete.html"
    success_url = reverse_lazy("components:list")
    allowed_roles = ["Admin"]


# ======================================================
# COMPONENT MASTER VIEWS
# ======================================================
class ComponentMasterListView(LoginRequiredMixin, ListView):
    model = ComponentMaster
    template_name = "components/master_list.html"
    context_object_name = "components"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(notes__icontains=q))

        # Compute final_price = cost_per_unit + (logistics_percent/100 * cost_per_unit)
        cost_expr = Coalesce(F("cost_per_unit"), Value(0))
        try:
            ComponentMaster._meta.get_field("value")
            multiplier_expr = Coalesce(F("value"), Value(0))
        except FieldDoesNotExist:
            multiplier_expr = ExpressionWrapper(
                Coalesce(F("logistics_percent"), Value(0)) / Value(100),
                output_field=DecimalField(max_digits=12, decimal_places=6),
            )

        final_price_expr = ExpressionWrapper(
            cost_expr + (multiplier_expr * cost_expr),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )
        qs = qs.annotate(final_price=final_price_expr)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["can_create"] = user.is_authenticated and (is_admin(user) or is_manager(user))
        ctx["can_edit"] = ctx["can_create"]
        ctx["can_delete"] = user.is_authenticated and is_admin(user)

        # Debug print to confirm annotation working
        try:
            sample_data = list(ctx["components"].values_list(
                "name", "cost_per_unit", "logistics_percent", "final_price"
            )[:5])
            print("\n🔎 DEBUG ComponentMasterListView sample data:", sample_data, "\n")
        except Exception as e:
            print("\n⚠️ DEBUG Could not print final_price values —", e, "\n")

        return ctx


class ComponentMasterDetailView(LoginRequiredMixin, DetailView):
    model = ComponentMaster
    template_name = "components/master_detail.html"
    context_object_name = "component"


class ComponentMasterCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model = ComponentMaster
    form_class = ComponentMasterForm
    template_name = "components/component_form.html"   # ✅ reuse form
    success_url = reverse_lazy("components:master_list")
    allowed_roles = ["Admin", "Manager"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Create Component Master"
        return ctx


class ComponentMasterUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    model = ComponentMaster
    form_class = ComponentMasterForm
    template_name = "components/component_form.html"   # ✅ reuse form
    success_url = reverse_lazy("components:master_list")
    allowed_roles = ["Admin", "Manager"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Edit Component Master"
        return ctx


class ComponentMasterDeleteView(LoginRequiredMixin, RoleRequiredMixin, DeleteView):
    """
    Render a confirmation page on GET and attempt deletion on POST.
    Catch ProtectedError / IntegrityError and show a friendly message rather than a 500.
    """
    model = ComponentMaster
    template_name = "components/master_confirm_delete.html"
    success_url = reverse_lazy("components:master_list")
    allowed_roles = ["Admin"]

    def dispatch(self, request, *args, **kwargs):
        # Keep defensive permission checks in place (RoleRequiredMixin handles most cases)
        if not request.user.is_authenticated:
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def _user_allowed(self, user):
        """Reuse the same allowed-roles logic used elsewhere (returns True/False)."""
        if user.is_superuser:
            return True
        for role in (self.allowed_roles or []):
            role = (role or "").strip()
            if not role:
                continue
            if role == "Admin" and is_admin(user):
                return True
            if role == "Manager" and is_manager(user):
                return True
            if role == "Employee" and is_employee(user):
                return True
            if user.groups.filter(name=role).exists():
                return True
        return False

    def get(self, request, *args, **kwargs):
        """
        Show a confirmation page (do NOT delete on GET).
        """
        if not self._user_allowed(request.user):
            raise PermissionDenied()
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """
        Attempt to delete. If deletion fails due to FK constraints, catch and show a message.
        """
        if not self._user_allowed(request.user):
            raise PermissionDenied()

        self.object = self.get_object()

        try:
            with transaction.atomic():
                # Try to delete; may raise ProtectedError (Django) or IntegrityError (DB-level)
                self.object.delete()
        except (ProtectedError, IntegrityError) as e:
            # Log and show friendly UI message
            logger.exception("Failed to delete ComponentMaster (pk=%s): %s", getattr(self.object, "pk", "unknown"), e)
            messages.error(
                request,
                "Cannot delete this component because other records depend on it. "
                "Please remove or reassign the related records before deleting."
            )
            # Redirect back to the detail page so user sees the message and can act.
            try:
                return redirect("components:master_detail", pk=self.object.pk)
            except Exception:
                return redirect(self.success_url)

        messages.success(request, "Component deleted successfully.")
        return redirect(self.success_url)


# ======================================================
# AJAX ENDPOINTS
# ======================================================
@login_required
def inventory_items_json(request):
    """
    Returns inventory items for a given category.
    Query params:
      - category (FABRIC / ACCESSORY / PRINTED) [required]
      - q (search text) [optional]
    Response:
      { "results": [ { "id": <pk>, "label": "<str>", "content_type_id": <ct.pk>, "type": "<type>" }, ... ] }
    """
    category = request.GET.get("category", "").upper().strip()
    search_q = request.GET.get("q", "").strip()
    if not category:
        return JsonResponse({"results": []})

    try:
        from rawmaterials.models import Accessory, Fabric, Printed
        model_map = {
            "ACCESSORY": Accessory,
            "FABRIC": Fabric,
            "PRINTED": Printed,
        }
    except Exception as e:
        logger.error("Error importing rawmaterials models: %s", e)
        return JsonResponse({"results": []})

    model_class = model_map.get(category)
    if not model_class:
        return JsonResponse({"results": []})

    qs = model_class.objects_all() if hasattr(model_class, "objects_all") else model_class.objects.all()
    if search_q:
        filters = Q()
        # prefer common text fields
        candidate_fields = [f.name for f in model_class._meta.get_fields()]
        for f in ("item_name", "product", "name", "title", "description"):
            if f in candidate_fields:
                filters |= Q(**{f"{f}__icontains": search_q})
        if filters:
            qs = qs.filter(filters)

    results = []
    for inst in qs.order_by("pk")[:200]:
        ct = ContentType.objects.get_for_model(inst.__class__)
        i_type = _extract_type_from_instance(inst)
        # Prefer readable label fields where available
        label = None
        for fld in ("item_name", "product", "name", "__str__"):
            if fld == "__str__":
                label = str(inst)
                break
            if hasattr(inst, fld):
                try:
                    val = getattr(inst, fld)
                    if val not in (None, ""):
                        label = str(val)
                        break
                except Exception:
                    continue
        if not label:
            label = str(inst)
        display_label = (str(i_type).strip() or label)
        results.append({
            "id": inst.pk,
            "label": display_label,
            "content_type_id": ct.pk,
            "type": i_type,
        })
    return JsonResponse({"results": results})


@login_required
def inventory_qualities_json(request):
    """
    Returns qualities for a single inventory item (by content_type_id & object_id).
    """
    try:
        from rawmaterials.models import Fabric, Accessory, Printed
    except Exception as e:
        logger.error("inventory_qualities_json: cannot import rawmaterials models: %s", e)
        return JsonResponse({"results": []})

    ct_id = request.GET.get("content_type_id")
    obj_id = request.GET.get("object_id")
    if not ct_id or not obj_id:
        return JsonResponse({"results": []})

    try:
        ct = ContentType.objects.get(pk=int(ct_id))
        instance = ct.get_object_for_this_type(pk=int(obj_id))
    except Exception as e:
        logger.warning("inventory_qualities_json: invalid object reference: %s", e)
        return JsonResponse({"results": []})

    results = []

    # Fabrics & Accessories: either related qualities or a 'quality' field
    if isinstance(instance, (Fabric, Accessory)):
        if hasattr(instance, "qualities") and hasattr(instance.qualities, "all"):
            for q in instance.qualities.all():
                try:
                    label = getattr(q, "name", str(q))
                    results.append({"id": getattr(q, "pk", label), "label": str(label)})
                except Exception:
                    continue
        else:
            qv = getattr(instance, "quality", None)
            if qv not in (None, "", []):
                results.append({"id": qv, "label": str(qv)})
    elif isinstance(instance, Printed):
        # Printed may have variant/quality
        if hasattr(instance, "variant") and getattr(instance, "variant"):
            results.append({"id": instance.variant, "label": str(instance.variant)})
        elif getattr(instance, "quality", None) not in (None, ""):
            results.append({"id": instance.quality, "label": str(instance.quality)})

    return JsonResponse({"results": results})


@login_required
def inventory_cost_json(request):
    """
    Extended cost endpoint (content_type_id, object_id, quality, size, logistics_percent).
    """
    ct_id = request.GET.get("content_type_id")
    obj_id = request.GET.get("object_id")
    quality = request.GET.get("quality")
    size = request.GET.get("size", "1")
    logistics = request.GET.get("logistics_percent", "0")

    if not ct_id or not obj_id:
        return JsonResponse({"error": "missing parameters"}, status=400)

    try:
        ct = ContentType.objects.get(pk=int(ct_id))
        instance = ct.get_object_for_this_type(pk=int(obj_id))
    except Exception as e:
        logger.warning("inventory_cost_json: invalid inventory reference: %s", e)
        return JsonResponse({"error": "invalid inventory reference"}, status=400)

    try:
        size = Decimal(size)
        logistics = Decimal(logistics)
    except (InvalidOperation, TypeError):
        size = Decimal("1.00")
        logistics = Decimal("0.00")

    cost_per_unit = Decimal("0.00")
    # flexible lookup similar to model helper
    for attr in ("get_cost", "get_price", "cost_per_unit", "price", "cost", "base_price"):
        val = getattr(instance, attr, None)
        if callable(val):
            try:
                # try passing quality if function accepts it
                if hasattr(val, "__code__") and "quality" in val.__code__.co_varnames:
                    val = val(quality=quality)
                else:
                    val = val()
            except Exception:
                continue
        if val is not None and val != "":
            try:
                cost_per_unit = Decimal(val)
                break
            except Exception:
                continue

    cost_per_unit = cost_per_unit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    final_price_per_unit = (cost_per_unit * (Decimal("1.00") + logistics / Decimal("100.00"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    final_cost = (final_price_per_unit * size).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # try to fetch width using similar heuristics
    width = Decimal("0.00")
    width_uom = "inch"
    for attr in ("get_width", "width_for_quality", "get_width_for_quality", "width", "g_width", "fabric_width", "w"):
        val = getattr(instance, attr, None)
        try:
            if callable(val):
                if hasattr(val, "__code__") and "quality" in val.__code__.co_varnames:
                    val = val(quality=quality)
                else:
                    val = val()
        except Exception:
            continue

        if val is None or val == "":
            continue

        # method might return (width, uom) or just numeric
        try:
            if isinstance(val, (list, tuple)) and len(val) >= 1:
                width_val = Decimal(val[0])
                uom_val = val[1] if len(val) > 1 else "inch"
                width = width_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                width_uom = str(uom_val)
                break
            else:
                width = Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                width_uom = "inch"
                break
        except Exception:
            continue

    # compute price_per_sqfoot using the same formula as ComponentMaster
    price_per_sqfoot = Decimal("0.0000")
    try:
        width_in_inch = width
        if width_uom and width_uom.lower() in ("cm", "centimeter", "centimetre", "cms"):
            width_in_inch = (width / Decimal("2.54"))
        if width_in_inch and width_in_inch != Decimal("0"):
            denom = ((width_in_inch * Decimal("2.54")) / Decimal("1.07")) / Decimal("100")
            if denom != Decimal("0"):
                ppsf = (final_price_per_unit / denom)
                price_per_sqfoot = ppsf.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    except Exception:
        price_per_sqfoot = Decimal("0.0000")

    # extract type heuristically
    i_type = _extract_type_from_instance(instance)

    return JsonResponse({
        "cost_per_unit": str(cost_per_unit),
        "final_price_per_unit": str(final_price_per_unit),
        "final_cost": str(final_cost),
        "width": str(width),
        "width_uom": str(width_uom),
        "price_per_sqfoot": str(price_per_sqfoot),
        "type": i_type,
    })


# ---------------------------
# New endpoints for redesigned UI
# ---------------------------
@login_required
def qualities_by_category_json(request):
    """
    Return distinct qualities available across inventory items in a category.
    Query params:
      - category (FABRIC / ACCESSORY / PRINTED) [required]
    Response:
      { "results": [ { "id": "<value>", "label": "<display>" }, ... ] }
    """
    category = request.GET.get("category", "").upper().strip()
    if not category:
        return JsonResponse({"results": []})

    try:
        from rawmaterials.models import Accessory, Fabric, Printed
        model_map = {
            "ACCESSORY": Accessory,
            "FABRIC": Fabric,
            "PRINTED": Printed,
        }
    except Exception as e:
        logger.error("qualities_by_category_json: error importing rawmaterials models: %s", e)
        return JsonResponse({"results": []})

    model_class = model_map.get(category)
    if not model_class:
        return JsonResponse({"results": []})

    qualities_set = set()

    try:
        # If model has related 'qualities', collect them
        sample = model_class.objects.first()
        if sample is None:
            return JsonResponse({"results": []})

        if hasattr(sample, "qualities") and hasattr(sample.qualities, "all"):
            for inst in model_class.objects.all():
                try:
                    for q in getattr(inst, "qualities").all():
                        name = getattr(q, "name", None) or str(q)
                        if name not in (None, ""):
                            qualities_set.add(str(name))
                except Exception:
                    continue
        else:
            # fallback: try distinct values from 'quality' attribute/field
            fields = [f.name for f in model_class._meta.get_fields()]
            if "quality" in fields:
                # Query DB for distinct non-empty values, then coerce to str
                raw_qs = model_class.objects.exclude(quality__isnull=True).exclude(quality__exact="").values_list("quality", flat=True).distinct()
                for v in raw_qs:
                    if v not in (None, ""):
                        qualities_set.add(str(v))
            else:
                # No quality info
                pass
    except Exception as e:
        logger.exception("qualities_by_category_json: error while collecting qualities: %s", e)
        return JsonResponse({"results": []})

    # sort intelligently: try numeric sort where possible, else lexical (case-insensitive)
    def sort_key(s):
        try:
            return (0, Decimal(str(s)))
        except Exception:
            return (1, str(s).lower())

    results = [{"id": q, "label": q} for q in sorted(qualities_set, key=sort_key)]
    return JsonResponse({"results": results})


@login_required
def types_by_quality_json(request):
    """
    Given a category and a quality, return matching inventory items (types).
    Query params:
      - category (FABRIC / ACCESSORY / PRINTED) [required]
      - quality (string) [required]
      - q (optional search substring)
    """
    category = request.GET.get("category", "").upper().strip()
    quality = request.GET.get("quality", "").strip()
    search_q = request.GET.get("q", "").strip()

    if not category or not quality:
        return JsonResponse({"results": []})

    try:
        from rawmaterials.models import Accessory, Fabric, Printed
        model_map = {
            "ACCESSORY": Accessory,
            "FABRIC": Fabric,
            "PRINTED": Printed,
        }
    except Exception as e:
        logger.error("types_by_quality_json: error importing rawmaterials models: %s", e)
        return JsonResponse({"results": []})

    model_class = model_map.get(category)
    if not model_class:
        return JsonResponse({"results": []})

    qs = model_class.objects.all()

    try:
        sample = model_class.objects.first()
        if sample is None:
            return JsonResponse({"results": []})

        # If model has related qualities, use them
        if hasattr(sample, "qualities") and hasattr(sample.qualities, "filter"):
            matched_pks = set()
            for inst in model_class.objects.all():
                try:
                    for q in getattr(inst, "qualities").all():
                        name = getattr(q, "name", None)
                        if name and str(name).strip().lower() == quality.strip().lower():
                            matched_pks.add(inst.pk)
                            break
                except Exception:
                    continue
            qs = qs.filter(pk__in=matched_pks)
        else:
            # If model has a 'quality' field, try matches:
            fields = [f.name for f in model_class._meta.get_fields()]
            if "quality" in fields:
                # Build Q: case-insensitive string match OR numeric equality (if incoming quality numeric)
                filters = Q(quality__iexact=quality)
                # Try parse incoming quality as Decimal; if succeeds, include numeric equality filter
                try:
                    q_dec = Decimal(quality)
                    filters |= Q(quality=q_dec)
                except (InvalidOperation, TypeError, ValueError):
                    q_dec = None
                qs = qs.filter(filters)
            else:
                # fallback: fuzzy search in common text fields
                fuzzy_filters = Q()
                for f in ("item_name", "product", "name", "title", "description"):
                    if f in [f.name for f in model_class._meta.get_fields()]:
                        fuzzy_filters |= Q(**{f"{f}__icontains": quality})
                if fuzzy_filters:
                    qs = qs.filter(fuzzy_filters)
                else:
                    qs = qs.none()

        # apply optional search substring to further narrow types
        if search_q:
            search_filters = Q()
            for f in ("item_name", "product", "name", "title", "description"):
                if f in [f.name for f in model_class._meta.get_fields()]:
                    search_filters |= Q(**{f"{f}__icontains": search_q})
            if search_filters:
                qs = qs.filter(search_filters)
    except Exception as e:
        logger.exception("types_by_quality_json: error filtering by quality: %s", e)
        return JsonResponse({"results": []})

    results = []
    for inst in qs.order_by("pk")[:500]:
        ct = ContentType.objects.get_for_model(inst.__class__)
        i_type = _extract_type_from_instance(inst)
        display_label = (str(i_type).strip() or str(inst))
        results.append({
            "id": inst.pk,
            "label": display_label,
            "content_type_id": ct.pk,
            "type": i_type,
        })

    return JsonResponse({"results": results})


@login_required
def inventory_item_json(request):
    """
    Given content_type_id & object_id return detailed inventory item info and computed metrics.
    """
    ct_id = request.GET.get("content_type_id")
    obj_id = request.GET.get("object_id")
    quality = request.GET.get("quality")
    logistics = request.GET.get("logistics_percent", "0")
    size = request.GET.get("size", "1")

    if not ct_id or not obj_id:
        return JsonResponse({"error": "missing parameters"}, status=400)

    try:
        ct = ContentType.objects.get(pk=int(ct_id))
        instance = ct.get_object_for_this_type(pk=int(obj_id))
    except Exception as e:
        logger.warning("inventory_item_json: invalid inventory reference: %s", e)
        return JsonResponse({"error": "invalid inventory reference"}, status=400)

    try:
        logistics = Decimal(logistics)
    except (InvalidOperation, TypeError):
        logistics = Decimal("0.00")
    try:
        size = Decimal(size)
    except (InvalidOperation, TypeError):
        size = Decimal("1.00")

    # Use a temporary ComponentMaster to leverage existing fetch & compute logic.
    try:
        temp_cm = ComponentMaster(
            inventory_content_type=ct,
            inventory_object_id=getattr(instance, "pk", None),
            quality=quality,
            size=size,
            logistics_percent=logistics,
        )
        # compute metrics using your model helper
        # note: older code used compute_final_costs_and_metrics(), adapt if your method name differs
        if hasattr(temp_cm, "compute_final_costs_and_metrics"):
            temp_cm.compute_final_costs_and_metrics()
        else:
            # fallback to any implemented helper on the model
            if hasattr(temp_cm, "_fetch_cost_from_inventory"):
                # emulate partly the logic used in the form clean
                try:
                    temp_cm.cost_per_unit = Decimal(temp_cm._fetch_cost_from_inventory() or "0.00")
                except Exception:
                    temp_cm.cost_per_unit = Decimal("0.00")
                temp_cm.final_price_per_unit = (temp_cm.cost_per_unit * (Decimal("1.00") + Decimal(logistics) / Decimal("100.00"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                temp_cm.final_cost = (temp_cm.final_price_per_unit * size).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                # best-effort width/price_per_sqfoot
                try:
                    w, wu = temp_cm._fetch_width_from_inventory()
                    temp_cm.width = Decimal(w)
                    temp_cm.width_uom = wu or "inch"
                except Exception:
                    temp_cm.width = Decimal("0.00")
                    temp_cm.width_uom = "inch"
                # compute price_per_sqfoot if possible
                temp_cm.price_per_sqfoot = Decimal("0.0000")
            else:
                # If no helper, rely on fallback below after exception
                pass

        i_type = (getattr(temp_cm, "type", "") or "").strip() or _extract_type_from_instance(instance)

        return JsonResponse({
            "id": int(getattr(instance, "pk", None)),
            "content_type_id": ct.pk,
            "label": str(instance),
            "cost_per_unit": str(getattr(temp_cm, "cost_per_unit", "0.00")),
            "final_price_per_unit": str(getattr(temp_cm, "final_price_per_unit", "0.00")),
            "final_cost": str(getattr(temp_cm, "final_cost", "0.00")),
            "width": str(getattr(temp_cm, "width", "0.00")),
            "width_uom": str(getattr(temp_cm, "width_uom", "inch") or "inch"),
            "price_per_sqfoot": str(getattr(temp_cm, "price_per_sqfoot", "0.0000")),
            "type": i_type,
        })
    except Exception as e:
        logger.exception("inventory_item_json: error computing metrics with temp ComponentMaster: %s", e)
        # fallback to best-effort extraction
        cost_per_unit = Decimal("0.00")
        for attr in ("get_cost", "get_price", "cost_per_unit", "price", "cost", "base_price"):
            val = getattr(instance, attr, None)
            if callable(val):
                try:
                    if hasattr(val, "__code__") and "quality" in val.__code__.co_varnames:
                        val = val(quality=quality)
                    else:
                        val = val()
                except Exception:
                    continue
            if val is not None and val != "":
                try:
                    cost_per_unit = Decimal(val)
                    break
                except Exception:
                    continue

        cost_per_unit = cost_per_unit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        final_price_per_unit = (cost_per_unit * (Decimal("1.00") + logistics / Decimal("100.00"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        final_cost = (final_price_per_unit * size).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # width fallback
        width = Decimal("0.00")
        width_uom = "inch"
        for attr in ("get_width", "width_for_quality", "get_width_for_quality", "width", "g_width", "fabric_width", "w"):
            val = getattr(instance, attr, None)
            try:
                if callable(val):
                    if hasattr(val, "__code__") and "quality" in val.__code__.co_varnames:
                        val = val(quality=quality)
                    else:
                        val = val()
            except Exception:
                continue

            if val is None or val == "":
                continue

            try:
                if isinstance(val, (list, tuple)) and len(val) >= 1:
                    width_val = Decimal(val[0])
                    uom_val = val[1] if len(val) > 1 else "inch"
                    width = width_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    width_uom = str(uom_val)
                    break
                else:
                    width = Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    width_uom = "inch"
                    break
            except Exception:
                continue

        price_per_sqfoot = Decimal("0.0000")
        try:
            width_in_inch = width
            if width_uom and width_uom.lower() in ("cm", "centimeter", "centimetre", "cms"):
                width_in_inch = (width / Decimal("2.54"))
            if width_in_inch and width_in_inch != Decimal("0"):
                denom = ((width_in_inch * Decimal("2.54")) / Decimal("1.07")) / Decimal("100")
                if denom != Decimal("0"):
                    price_per_sqfoot = (final_price_per_unit / denom).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        except Exception:
            price_per_sqfoot = Decimal("0.0000")

        i_type = _extract_type_from_instance(instance)

        return JsonResponse({
            "id": int(getattr(instance, "pk", None)),
            "content_type_id": ct.pk,
            "label": str(instance),
            "cost_per_unit": str(cost_per_unit),
            "final_price_per_unit": str(final_price_per_unit),
            "final_cost": str(final_cost),
            "width": str(width),
            "width_uom": width_uom,
            "price_per_sqfoot": str(price_per_sqfoot),
            "type": i_type,
        })


# ---------------------------------------------------------------
# COLOR MANAGEMENT ENDPOINTS (NEW)
# ---------------------------------------------------------------
@login_required
def colors_list_json(request):
    """
    Return all active colors for a ComponentMaster.
    Params:
        component_id = ComponentMaster.pk
    Response:
        { "results": [ {"id":1, "name":"Red"}, ... ] }
    """
    comp_id = request.GET.get("component_id")
    if not comp_id:
        return JsonResponse({"results": []})

    try:
        comp = ComponentMaster.objects.get(pk=comp_id)
    except ComponentMaster.DoesNotExist:
        return JsonResponse({"results": []})

    colors = comp.colors.filter(is_active=True).order_by("name")
    data = [{"id": c.id, "name": c.name} for c in colors]
    return JsonResponse({"results": data})


@login_required
def color_create_json(request):
    """
    Create a new Color for a ComponentMaster.
    POST params:
        component_id
        name
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    comp_id = request.POST.get("component_id")
    name = (request.POST.get("name") or "").strip()

    if not comp_id or not name:
        return JsonResponse({"error": "Missing component_id or name"}, status=400)

    try:
        comp = ComponentMaster.objects.get(pk=comp_id)
    except ComponentMaster.DoesNotExist:
        return JsonResponse({"error": "ComponentMaster not found"}, status=404)

    # Avoid duplicates (case-insensitive)
    if comp.colors.filter(name__iexact=name).exists():
        return JsonResponse({"error": "Color already exists"}, status=409)

    try:
        color = Color.objects.create(component_master=comp, name=name)
        return JsonResponse({
            "success": True,
            "color": {"id": color.id, "name": color.name}
        })
    except Exception as e:
        logger.exception("color_create_json failed: %s", e)
        return JsonResponse({"error": "Failed to create color"}, status=500)


@login_required
def color_delete_json(request):
    """
    Soft-delete a Color.
    POST params:
        color_id
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    color_id = request.POST.get("color_id")
    if not color_id:
        return JsonResponse({"error": "Missing color_id"}, status=400)

    try:
        color = Color.objects.get(pk=color_id)
        color.is_active = False
        color.save()
        return JsonResponse({"success": True})
    except Color.DoesNotExist:
        return JsonResponse({"error": "Color not found"}, status=404)
    except Exception as e:
        logger.exception("color_delete_json failed: %s", e)
        return JsonResponse({"error": "Failed to delete color"}, status=500)
