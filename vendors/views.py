# vendors/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.db.models.deletion import ProtectedError

from .models import Vendor
from .forms import VendorForm


# ----------------- role helpers (local to this module) -----------------
def _in_group(user, group_name):
    return user.groups.filter(name=group_name).exists()


def is_admin(user):
    """Admin = superuser OR group 'Admin'."""
    return user.is_superuser or _in_group(user, "Admin")


def can_create_vendor(user):
    """
    Per spec: Admin, Manager and Employee can create vendors.
    """
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Admin", "Manager", "Employee"]).exists()


def can_edit_vendor(user):
    """
    Allow Admin and Manager to edit vendor records.
    Employees can create vendors but not edit existing ones (safer default).
    """
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Admin", "Manager"]).exists()


def can_delete_vendor(user):
    """
    Only Admin may delete vendors (prevent accidental data loss).
    """
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
    # compute permission flags for the current user and pass to template
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
    Attempt to delete a vendor. If deletion is blocked by PROTECT foreign keys,
    catch ProtectedError and inform the user about the related objects.
    """
    vendor = get_object_or_404(Vendor, pk=pk)
    vendor_name = getattr(vendor, "vendor_name", str(pk))

    try:
        vendor.delete()
        messages.success(request, f"Vendor '{vendor_name}' deleted successfully.")
    except ProtectedError as e:
        # e.protected_objects may be provided (depending on Django version)
        protected_objs = getattr(e, "protected_objects", None)
        if protected_objs is None:
            # Fallback: try to extract from exception args if available
            protected_objs = e.args[1] if len(e.args) > 1 else []

        # Format a friendly list of blocking records
        blocked_list = []
        try:
            for obj in protected_objs:
                # Use verbose_name and str(obj) to create a readable description
                meta_name = getattr(obj._meta, "verbose_name", None)
                if meta_name:
                    blocked_list.append(f"{meta_name.title()}: {str(obj)}")
                else:
                    blocked_list.append(str(obj))
        except Exception:
            # On any unexpected shape, fallback to repr of protected objects
            blocked_list = [str(x) for x in protected_objs]

        if blocked_list:
            msg = (
                f"Cannot delete vendor '{vendor_name}' because the following related records "
                f"reference it (reassign or remove them first): " + "; ".join(blocked_list)
            )
        else:
            msg = (
                f"Cannot delete vendor '{vendor_name}' because other records reference it. "
                "Reassign or remove dependent records before deleting."
            )

        messages.error(request, msg)
    except Exception as ex:
        # Generic fallback to avoid 500s for unexpected errors
        messages.error(request, f"An error occurred while deleting vendor '{vendor_name}': {ex}")

    return redirect(reverse("vendors:list"))
