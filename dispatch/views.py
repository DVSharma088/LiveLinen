# dispatch/views.py
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, NoReverseMatch
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.apps import apps

try:
    # finished_products import is optional — keep at top only if harmless.
    # We'll still attempt lazy import inside functions to be safe.
    pass
except Exception:
    pass


def _normalize_to_int_pk(val, model_cls=None):
    """
    Safely convert val into an integer PK.
    - If val is a model instance, return val.pk
    - If val is an integer, return int(val)
    - If val is a string that looks like an int, return int(val)
    - Otherwise return None
    """
    if val is None:
        return None
    # model instance
    try:
        pk = getattr(val, "pk", None)
        if pk is not None:
            return int(pk)
    except Exception:
        pass
    # already int-like
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _get_model(app_label: str, model_name: str):
    """
    Helper to lazily fetch a model class from the app registry.
    """
    return apps.get_model(app_label, model_name)


# -------------------------
# Role helpers (local)
# -------------------------
def _in_group(user, group_name):
    return user.groups.filter(name=group_name).exists()


def is_admin(user):
    return user.is_superuser or _in_group(user, "Admin")


def is_manager(user):
    return _in_group(user, "Manager") or is_admin(user)


def is_employee(user):
    """
    Employee includes explicit Employee group, managers, and admins.
    This mirrors the permission model used in other apps: managers/admins
    implicitly have employee privileges.
    """
    return _in_group(user, "Employee") or is_manager(user)


# -------------------------
# Views
# -------------------------
@login_required
@user_passes_test(is_employee)
@require_http_methods(["GET", "POST"])
def new_dispatch(request):
    """
    GET: render a prefilled DispatchForm when ?workorder_id=... is provided.
    POST: save Dispatch safely — normalize workorder to integer PK before assignment.

    Allowed roles: Employee, Manager, Admin (is_employee returns True for manager/admin).
    """
    # Lazy imports to avoid import-time side-effects / circular imports
    Dispatch = _get_model("dispatch", "Dispatch")
    WorkOrder = _get_model("workorders", "WorkOrder")
    try:
        from .forms import DispatchForm
    except Exception:
        # If forms import somehow fails, surface a helpful message rather than crash later
        messages.error(request, "Dispatch form is not available (import error).")
        return redirect(reverse("workorders:list"))

    if request.method == "GET":
        workorder_id = request.GET.get("workorder_id")
        initial = {}

        if workorder_id:
            # allow workorder_id to be passed as string or int
            wo = None
            try:
                wo = get_object_or_404(WorkOrder, pk=int(workorder_id))
            except Exception:
                # fallback: try as-is
                try:
                    wo = get_object_or_404(WorkOrder, pk=workorder_id)
                except Exception:
                    wo = None
            if wo:
                initial["work_order"] = getattr(wo, "pk", "")
                initial["order_no"] = getattr(wo, "order_id", "") or getattr(wo, "order_no", "")
                finished = getattr(wo, "finished_product", None) or getattr(wo, "variant", None) or getattr(wo, "variant_ordered", None)
                product_repr = ""
                if finished:
                    try:
                        product_repr = str(finished)
                    except Exception:
                        product_repr = finished
                initial["product_name"] = product_repr
                initial["price"] = getattr(wo, "order_value", None) or getattr(wo, "price", None) or ""
                qty = getattr(wo, "quantity_to_dispatch", None) or getattr(wo, "quantity_ordered", None) or getattr(wo, "quantity", None)
                if qty is not None:
                    initial["quantity"] = qty

                try:
                    df = DispatchForm()
                    if "variant" in df.fields and finished:
                        initial["variant"] = product_repr
                    if "order_value" in df.fields and initial.get("price") is not None:
                        initial["order_value"] = initial.get("price")
                except Exception:
                    pass

        form = DispatchForm(initial=initial)
        return render(request, "dispatch/dispatch_form.html", {"form": form, "workorder_id": initial.get("work_order")})

    # POST handling
    form = DispatchForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Please correct the errors in the form.")
        return render(request, "dispatch/dispatch_form.html", {"form": form})

    try:
        with transaction.atomic():
            dispatch_obj = form.save(commit=False)

            # --- Normalize work_order input to an integer PK (prevents assigning instance to integer field) ---
            raw_work_order = form.cleaned_data.get("work_order")
            work_order_pk = _normalize_to_int_pk(raw_work_order, WorkOrder)

            if work_order_pk is not None:
                # find FK field on Dispatch that points to WorkOrder (if any)
                model_field_map = {f.name: f for f in Dispatch._meta.get_fields() if hasattr(f, "name")}
                fk_field_name = None
                for name, fobj in model_field_map.items():
                    remote = getattr(fobj, "remote_field", None)
                    if remote and getattr(remote, "model", None) is not None:
                        # remote.model could be a string or model class; normalize comparison
                        try:
                            remote_model = remote.model
                            if isinstance(remote_model, str):
                                # compare string 'app_label.ModelName'
                                if remote_model.lower().endswith("workorder") or "workorder" in remote_model.lower():
                                    fk_field_name = name
                                    break
                            else:
                                if getattr(remote_model, "__name__", "").lower() == "workorder":
                                    fk_field_name = name
                                    break
                        except Exception:
                            continue

                if fk_field_name:
                    # set the integer id safely using <fk_field_name>_id if available
                    if hasattr(dispatch_obj, f"{fk_field_name}_id"):
                        setattr(dispatch_obj, f"{fk_field_name}_id", work_order_pk)
                    else:
                        # fallback: set attribute to pk (less ideal but safe)
                        setattr(dispatch_obj, fk_field_name, work_order_pk)
                else:
                    # fallback: try common candidate names and set <candidate>_id if possible
                    assigned = False
                    for candidate in ("work_order", "workorder", "order", "order_ref", "order_id"):
                        if candidate in model_field_map:
                            if hasattr(dispatch_obj, f"{candidate}_id"):
                                setattr(dispatch_obj, f"{candidate}_id", work_order_pk)
                            else:
                                try:
                                    setattr(dispatch_obj, candidate, work_order_pk)
                                except Exception:
                                    pass
                            assigned = True
                            break
                    # final fallback: set any field ending with _id if present
                    if not assigned:
                        for name in model_field_map.keys():
                            if name.endswith("_id") and hasattr(dispatch_obj, name):
                                try:
                                    setattr(dispatch_obj, name, work_order_pk)
                                    assigned = True
                                    break
                                except Exception:
                                    continue
                    # if still not assigned, nothing else to do

            # --- quantity assignment if model supports it ---
            quantity_val = form.cleaned_data.get("quantity")
            if quantity_val is not None:
                if hasattr(dispatch_obj, "quantity"):
                    setattr(dispatch_obj, "quantity", quantity_val)
                elif hasattr(dispatch_obj, "qty"):
                    setattr(dispatch_obj, "qty", quantity_val)

            # created_by fallback
            if request.user.is_authenticated and hasattr(dispatch_obj, "created_by"):
                try:
                    dispatch_obj.created_by = request.user
                except Exception:
                    pass

            # Save the instance
            dispatch_obj.save()

            # attach uploaded image/file if model has a candidate field
            uploaded_image = request.FILES.get("image")
            if uploaded_image:
                for candidate in ("image", "photo", "attachment", "file"):
                    if hasattr(dispatch_obj, candidate):
                        setattr(dispatch_obj, candidate, uploaded_image)
                        dispatch_obj.save()
                        break

    except Exception as exc:
        messages.error(request, f"Failed to create Dispatch: {exc}")
        return render(request, "dispatch/dispatch_form.html", {"form": form})

    messages.success(request, f"Dispatch #{getattr(dispatch_obj, 'pk', '')} created successfully.")

    # Redirect preference: detail -> tracking -> workorder detail -> fallback to list
    try:
        return redirect(reverse("dispatch:detail", kwargs={"pk": dispatch_obj.pk}))
    except NoReverseMatch:
        try:
            return redirect(reverse("dispatch:tracking"))
        except NoReverseMatch:
            try:
                wk = getattr(dispatch_obj, "work_order") or getattr(dispatch_obj, "workorder", None)
                if wk:
                    return redirect(reverse("workorders:detail", kwargs={"pk": getattr(wk, "pk", wk)}))
            except Exception:
                pass
            return redirect(reverse("workorders:list"))


@login_required
@user_passes_test(is_employee)
def tracking_list(request):
    Dispatch = _get_model("dispatch", "Dispatch")
    # fall back to -pk if created_at not present
    order_by = "-created_at" if "created_at" in [f.name for f in Dispatch._meta.get_fields()] else "-pk"
    dispatches = Dispatch.objects.all().order_by(order_by)
    return render(request, "dispatch/dispatch_list.html", {"dispatches": dispatches})


@login_required
@user_passes_test(is_employee)
def dispatch_detail(request, pk):
    Dispatch = _get_model("dispatch", "Dispatch")
    dispatch = get_object_or_404(Dispatch, pk=pk)
    return render(request, "dispatch/dispatch_detail.html", {"dispatch": dispatch})
