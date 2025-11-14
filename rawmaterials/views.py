from decimal import Decimal, InvalidOperation
import csv
import io

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.db.models.deletion import ProtectedError
from django.db import transaction
from django.http import HttpResponse

# Import models and forms used by the app.
from .models import Fabric, Accessory, Printed
from .forms import FabricForm, AccessoryForm, PrintedForm


# ----------------- role helpers (local to this module) -----------------
def _in_group(user, group_name):
    return user.groups.filter(name=group_name).exists()


def is_admin(user):
    """Admin = superuser OR group 'Admin'."""
    return user.is_superuser or _in_group(user, "Admin")


def is_manager(user):
    """Manager membership (managers implicitly count as employees)."""
    return _in_group(user, "Manager") or is_admin(user)


def is_employee(user):
    """Employee membership: explicit Employee group or managers/admins."""
    return _in_group(user, "Employee") or is_manager(user)


def can_manage_inventory(user):
    """
    Per your spec: Admin, Manager and Employee can view/create inventory and manage items.
    We treat 'manage' here as create/edit operations.
    """
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Admin", "Manager", "Employee"]).exists()


def can_delete_inventory(user):
    """
    Who may delete inventory items?
    - Admin and Manager can delete.
    """
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Admin", "Manager"]).exists()


# -------------------------
# Helpers for defensive rendering
# -------------------------
def _coerce_decimal_or_none(value):
    """Convert to Decimal for safe rendering."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


# -------------------------
# CSV helper
# -------------------------
def _queryset_to_csv_response(queryset, field_getters, filename):
    """
    Build an HttpResponse with CSV content.

    - queryset: iterable of model instances
    - field_getters: list of tuples (column_name, getter_callable)
        getter_callable(instance) -> string/number
    - filename: suggested filename for download
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    # header
    headers = [col for col, _ in field_getters]
    writer.writerow(headers)

    # rows
    for obj in queryset:
        row = []
        for _, getter in field_getters:
            try:
                val = getter(obj)
            except Exception:
                val = ""
            # Ensure no problems with Decimal or None
            if isinstance(val, Decimal):
                val = str(val)
            if val is None:
                val = ""
            row.append(val)
        writer.writerow(row)

    resp = HttpResponse(buffer.getvalue(), content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# ------------------------------
# Inventory list / overview
# ------------------------------
@login_required
def inventory_list(request):
    """
    Unified inventory page. Renders partials for accessories, fabrics, and printeds.
    Query param 'type' can be 'accessory', 'fabric', 'printed' or omitted for 'all'.
    """
    qtype = (request.GET.get("type") or "").lower()
    active_type = "all" if qtype not in ("accessory", "fabric", "printed") else qtype

    accessories = Accessory.objects.select_related("vendor").all().order_by("-id")
    fabrics = Fabric.objects.select_related("vendor").all().order_by("-id")
    printeds = Printed.objects.select_related("fabric", "fabric__vendor", "vendor").all().order_by("-id")

    can_edit = can_manage_inventory(request.user)
    can_create = can_manage_inventory(request.user)
    can_delete = can_delete_inventory(request.user)

    accessory_numeric_fields = ("quality", "width", "stock", "cost_per_unit")
    fabric_numeric_fields = ("fabric_width", "cost_per_unit")
    printed_numeric_fields = ("cost_per_unit", "width")

    for acc in accessories:
        for field in accessory_numeric_fields:
            if hasattr(acc, field):
                raw = getattr(acc, field)
                setattr(acc, field, _coerce_decimal_or_none(raw))

    for f in fabrics:
        for field in fabric_numeric_fields:
            if hasattr(f, field):
                raw = getattr(f, field)
                setattr(f, field, _coerce_decimal_or_none(raw))

    for p in printeds:
        for field in printed_numeric_fields:
            if hasattr(p, field):
                raw = getattr(p, field)
                setattr(p, field, _coerce_decimal_or_none(raw))

    context = {
        "accessories": accessories,
        "fabrics": fabrics,
        "printeds": printeds,
        "active_type": active_type,
        "can_edit": can_edit,
        "can_create": can_create,
        "can_delete": can_delete,
    }
    return render(request, "rawmaterials/inventory_list.html", context)


# ------------------------------
# CSV download views
# ------------------------------
@login_required
@user_passes_test(is_employee)
def accessory_download_csv(request):
    """
    Download all Accessory records as CSV. Allowed for employees and above.
    """
    qs = Accessory.objects.select_related("vendor").all().order_by("id")

    def vendor_name(obj):
        v = getattr(obj, "vendor", None)
        if v is None:
            return ""
        # try common vendor fields
        return getattr(v, "vendor_name", None) or getattr(v, "name", None) or str(v)

    field_getters = [
        ("id", lambda o: getattr(o, "id", "")),
        ("name", lambda o: getattr(o, "name", "") or getattr(o, "item_name", "") or getattr(o, "product", "")),
        ("quality", lambda o: getattr(o, "quality", "")),
        ("width", lambda o: getattr(o, "width", "") or getattr(o, "fabric_width", "")),
        ("stock", lambda o: getattr(o, "stock", "")),
        ("cost_per_unit", lambda o: getattr(o, "cost_per_unit", "")),
        ("vendor", vendor_name),
    ]

    return _queryset_to_csv_response(qs, field_getters, "accessories.csv")


@login_required
@user_passes_test(is_employee)
def fabric_download_csv(request):
    """
    Download all Fabric records as CSV. Allowed for employees and above.
    """
    qs = Fabric.objects.select_related("vendor").all().order_by("id")

    def vendor_name(obj):
        v = getattr(obj, "vendor", None)
        if v is None:
            return ""
        return getattr(v, "vendor_name", None) or getattr(v, "name", None) or str(v)

    field_getters = [
        ("id", lambda o: getattr(o, "id", "")),
        ("item_name", lambda o: getattr(o, "item_name", "") or getattr(o, "name", "") or getattr(o, "product", "")),
        ("fabric_width", lambda o: getattr(o, "fabric_width", "") or getattr(o, "width", "")),
        ("quality", lambda o: getattr(o, "quality", "")),
        ("stock", lambda o: getattr(o, "stock", "")),
        ("cost_per_unit", lambda o: getattr(o, "cost_per_unit", "")),
        ("base_color", lambda o: getattr(o, "base_color", "")),
        ("type", lambda o: getattr(o, "type", "") or getattr(o, "product_type", "")),
        ("use_in", lambda o: getattr(o, "use_in", "")),
        ("vendor", vendor_name),
    ]

    return _queryset_to_csv_response(qs, field_getters, "fabrics.csv")


@login_required
@user_passes_test(is_employee)
def printed_download_csv(request):
    """
    Download all Printed records as CSV. Allowed for employees and above.
    """
    qs = Printed.objects.select_related("fabric", "vendor").all().order_by("id")

    def vendor_name(obj):
        v = getattr(obj, "vendor", None)
        if v is None:
            return ""
        return getattr(v, "vendor_name", None) or getattr(v, "name", None) or str(v)

    def fabric_ref(obj):
        f = getattr(obj, "fabric", None)
        if not f:
            return ""
        return getattr(f, "item_name", None) or getattr(f, "name", None) or str(f)

    field_getters = [
        ("id", lambda o: getattr(o, "id", "")),
        ("name", lambda o: getattr(o, "name", "") or getattr(o, "product", "") or getattr(o, "item_name", "")),
        ("fabric_id", lambda o: getattr(getattr(o, "fabric", None), "id", "")),
        ("fabric_item_name", fabric_ref),
        ("base_color", lambda o: getattr(o, "base_color", "")),
        ("product_type", lambda o: getattr(o, "product_type", "") or getattr(o, "type", "")),
        ("width", lambda o: getattr(o, "width", "")),
        ("cost_per_unit", lambda o: getattr(o, "cost_per_unit", "")),
        ("vendor", vendor_name),
    ]

    return _queryset_to_csv_response(qs, field_getters, "printeds.csv")


# ------------------------------
# Create / Edit views
# ------------------------------
@login_required
@user_passes_test(can_manage_inventory)
def accessory_create(request):
    if request.method == "POST":
        form = AccessoryForm(request.POST, request.FILES or None)
        if form.is_valid():
            form.save()
            messages.success(request, "Accessory created successfully.")
            return redirect(reverse("rawmaterials:inventory"))
    else:
        form = AccessoryForm()
    return render(request, "rawmaterials/accessory_form.html", {"form": form, "accessory": None})


@login_required
@user_passes_test(can_manage_inventory)
def accessory_edit(request, pk):
    accessory = get_object_or_404(Accessory, pk=pk)
    if request.method == "POST":
        form = AccessoryForm(request.POST, request.FILES or None, instance=accessory)
        if form.is_valid():
            form.save()
            messages.success(request, "Accessory updated successfully.")
            return redirect(reverse("rawmaterials:inventory"))
    else:
        form = AccessoryForm(instance=accessory)
    return render(request, "rawmaterials/accessory_form.html", {"form": form, "accessory": accessory})


@login_required
@user_passes_test(can_manage_inventory)
def fabric_create(request):
    if request.method == "POST":
        form = FabricForm(request.POST, request.FILES or None)
        if form.is_valid():
            form.save()
            messages.success(request, "Fabric created successfully.")
            return redirect(reverse("rawmaterials:inventory"))
    else:
        form = FabricForm()
    return render(request, "rawmaterials/fabric_form.html", {"form": form, "fabric": None, "can_delete": False})


@login_required
@user_passes_test(can_manage_inventory)
def fabric_edit(request, pk):
    fabric = get_object_or_404(Fabric, pk=pk)
    if request.method == "POST":
        form = FabricForm(request.POST, request.FILES or None, instance=fabric)
        if form.is_valid():
            form.save()
            messages.success(request, "Fabric updated successfully.")
            return redirect(reverse("rawmaterials:inventory"))
    else:
        form = FabricForm(instance=fabric)

    can_delete_flag = can_delete_inventory(request.user)
    return render(
        request,
        "rawmaterials/fabric_form.html",
        {"form": form, "fabric": fabric, "can_delete": can_delete_flag},
    )


@login_required
@user_passes_test(can_manage_inventory)
def printed_create(request):
    """
    Create Printed. If a 'fabric' GET param (fabric id) is provided, prefill the form's
    fabric-linked metadata from that Fabric (base_color, type, width, use_in, cost, vendor).
    """
    if request.method == "POST":
        form = PrintedForm(request.POST, request.FILES or None)
        if form.is_valid():
            form.save()
            messages.success(request, "Printed item created successfully.")
            return redirect(reverse("rawmaterials:inventory"))
    else:
        initial = {}
        fabric_id = request.GET.get("fabric") or request.GET.get("fabric_id")
        if fabric_id:
            try:
                fabric = Fabric.objects.select_related("vendor").get(pk=fabric_id)
                initial.update({
                    "fabric": fabric.pk,
                    "base_color": fabric.base_color,
                    "product_type": fabric.type,  # updated here
                    "width": fabric.fabric_width,
                    "use_in": fabric.use_in,
                    "cost_per_unit": fabric.cost_per_unit,
                    "vendor": fabric.vendor_id,
                })
            except Fabric.DoesNotExist:
                pass

        form = PrintedForm(initial=initial)

    return render(request, "rawmaterials/printed_form.html", {"form": form, "printed": None})


@login_required
@user_passes_test(can_manage_inventory)
def printed_edit(request, pk):
    printed = get_object_or_404(Printed, pk=pk)
    if request.method == "POST":
        form = PrintedForm(request.POST, request.FILES or None, instance=printed)
        if form.is_valid():
            form.save()
            messages.success(request, "Printed item updated successfully.")
            return redirect(reverse("rawmaterials:inventory"))
    else:
        form = PrintedForm(instance=printed)
    return render(request, "rawmaterials/printed_form.html", {"form": form, "printed": printed})


# ------------------------------
# Delete view for inventory items
# ------------------------------
@login_required
@user_passes_test(can_delete_inventory)
@require_POST
def inventory_delete(request, pk):
    """
    Delete an inventory object (Accessory, Fabric, or Printed) by pk.
    Deletes related Printed items if a Fabric is deleted.
    """
    instance = None
    model_label = None

    for model, label in ((Accessory, "Accessory"), (Fabric, "Fabric"), (Printed, "Printed")):
        try:
            instance = model.objects.get(pk=pk)
            model_label = label
            break
        except model.DoesNotExist:
            continue

    if not instance:
        messages.error(request, "Item not found or already deleted.")
        return redirect(reverse("rawmaterials:inventory"))

    display_name = None
    if model_label == "Fabric":
        display_name = getattr(instance, "item_name", None)
    display_name = display_name or getattr(instance, "name", None) or getattr(instance, "product", None) or str(instance)

    try:
        with transaction.atomic():
            if model_label == "Fabric":
                related_printeds_qs = getattr(instance, "printeds", None)
                related_printeds = list(related_printeds_qs.all()) if related_printeds_qs else list(Printed.objects.filter(fabric=instance))
                if related_printeds:
                    deleted_names = [str(p) for p in related_printeds]
                    if related_printeds_qs:
                        related_printeds_qs.all().delete()
                    else:
                        Printed.objects.filter(fabric=instance).delete()
                    messages.info(request, f"Deleted related Printed items: {', '.join(deleted_names)}")

            instance.delete()
        messages.success(request, f"{model_label} '{display_name}' deleted successfully.")

    except ProtectedError as e:
        protected_objs = getattr(e, "protected_objects", None) or []
        blocked_list = []
        try:
            for obj in protected_objs:
                blocked_list.append(f"{obj._meta.verbose_name.title()}: {str(obj)}")
        except Exception:
            blocked_list = [str(x) for x in protected_objs]

        if blocked_list:
            msg = f"Cannot delete {model_label} '{display_name}' because related records reference it: " + "; ".join(blocked_list)
        else:
            msg = f"Cannot delete {model_label} '{display_name}' because other records reference it."
        messages.error(request, msg)

    except Exception as exc:
        messages.error(request, f"An error occurred while deleting {model_label} '{display_name}': {exc}")

    return redirect(reverse("rawmaterials:inventory"))
