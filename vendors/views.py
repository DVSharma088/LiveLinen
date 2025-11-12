# vendors/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.apps import apps

from .models import Vendor
from .forms import VendorForm


# ----------------- role helpers -----------------
def _in_group(user, group_name):
    return user.groups.filter(name=group_name).exists()


def is_admin(user):
    return user.is_superuser or _in_group(user, "Admin")


def can_create_vendor(user):
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Admin", "Manager", "Employee"]).exists()


def can_edit_vendor(user):
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Admin", "Manager"]).exists()


def can_delete_vendor(user):
    return is_admin(user)


# ----------------- views -----------------
@login_required
@user_passes_test(can_create_vendor)
def vendor_create(request):
    if request.method == "POST":
        form = VendorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Vendor created successfully.")
            return redirect(reverse("vendors:list"))
    else:
        form = VendorForm()
    return render(request, "vendors/vendor_form.html", {"form": form})


@login_required
def vendor_list(request):
    vendors = Vendor.objects.all().order_by("-created_at")
    can_edit = request.user.is_superuser or request.user.groups.filter(name__in=["Admin", "Manager"]).exists()
    can_create = request.user.is_superuser or request.user.groups.filter(name__in=["Admin", "Manager", "Employee"]).exists()
    can_delete = request.user.is_superuser or request.user.groups.filter(name="Admin").exists()

    return render(
        request,
        "vendors/vendor_list.html",
        {
            "vendors": vendors,
            "can_edit": can_edit,
            "can_create": can_create,
            "can_delete": can_delete,
        },
    )


@login_required
@user_passes_test(can_edit_vendor)
def vendor_edit(request, pk):
    vendor = get_object_or_404(Vendor, pk=pk)
    if request.method == "POST":
        form = VendorForm(request.POST, instance=vendor)
        if form.is_valid():
            form.save()
            messages.success(request, "Vendor updated successfully.")
            return redirect(reverse("vendors:list"))
    else:
        form = VendorForm(instance=vendor)
    return render(request, "vendors/vendor_form.html", {"form": form, "vendor": vendor})


@login_required
@user_passes_test(can_delete_vendor)
@require_POST
def vendor_delete(request, pk):
    """
    Robust hard-delete:
    1. Find all reverse relations (one-to-many, many-to-many) that point to Vendor.
    2. Delete child rows via the related model's queryset (so DB constraints won't block vendor deletion).
    3. Delete the vendor.
    This intentionally performs permanent deletion of related rows.
    """
    vendor = get_object_or_404(Vendor, pk=pk)
    vendor_name = getattr(vendor, "vendor_name", str(pk))

    try:
        # Iterate all model fields for reverse relations created by Django
        for rel in vendor._meta.get_fields():
            # target reverse relations only (auto_created & not concrete)
            if getattr(rel, "auto_created", False) and not getattr(rel, "concrete", False):
                # Attempt to get the related model (the child model)
                related_model = getattr(rel, "related_model", None) or getattr(rel, "model", None)
                # rel.field holds the FK field on the related model that points to Vendor (for reverse relations)
                fk_field = getattr(rel, "field", None)

                if related_model is None:
                    # fallback: try to resolve via apps if rel.related_model is a string (rare)
                    try:
                        related_model = apps.get_model(rel.related_model)
                    except Exception:
                        related_model = None

                if related_model is None or fk_field is None:
                    # skip if we can't determine how to filter children
                    continue

                # Build filter kwargs to select children that reference this vendor
                # fk_field.name gives the field name on the child model (e.g., 'vendor')
                filter_kwargs = {fk_field.name: vendor}

                try:
                    # Delete children via queryset (this issues SQL DELETE on child rows)
                    related_model.objects.filter(**filter_kwargs).delete()
                except Exception:
                    # be permissive: ignore errors on specific relations and continue with others
                    # We do this because the goal is a hard delete; we'll attempt vendor.delete() at the end regardless.
                    pass

        # After attempting to remove dependent rows, delete the vendor itself
        vendor.delete()
        messages.success(request, f"Vendor '{vendor_name}' deleted successfully.")
    except Exception as ex:
        # If something still goes wrong, report it but do not show ProtectedError details.
        messages.error(request, f"An error occurred while deleting vendor '{vendor_name}': {ex}")

    return redirect(reverse("vendors:list"))
