# size_master/views.py
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView
from django.db.models import Q

from .forms import SizeMasterForm
from .models import SizeMaster


def get_category_models():
    """
    Lazily return (CategoryModel, CategorySizeModel) from the Category_Master(New) app.
    Adjust the app label if your app is named differently.
    """
    try:
        Category = apps.get_model("category_master_new", "Category")
    except LookupError:
        Category = None

    try:
        CategorySize = apps.get_model("category_master_new", "CategorySize")
    except LookupError:
        CategorySize = None

    return Category, CategorySize


def login_exempt(view_func):
    """
    Middleware-safe decorator to mark a view as exempt from login enforcement.
    It sets `login_exempt = True` on:
      - the original function,
      - the returned wrapper (this is what resolver_match.func will be),
      - and on view_class if the function is a CBV method wrapper.
    """
    # mark on the original function too
    try:
        setattr(view_func, "login_exempt", True)
    except Exception:
        pass

    @wraps(view_func)
    def _wrapped(*args, **kwargs):
        return view_func(*args, **kwargs)

    # mark on the wrapper (this is important for resolver_match.func)
    try:
        setattr(_wrapped, "login_exempt", True)
    except Exception:
        pass

    # if view_func is a class-based view attribute, mark the class as well
    try:
        if hasattr(view_func, "view_class"):
            setattr(view_func.view_class, "login_exempt", True)
    except Exception:
        pass

    return _wrapped


class SizeMasterCreateView(LoginRequiredMixin, CreateView):
    model = SizeMaster
    form_class = SizeMasterForm
    template_name = "size_master/size_form.html"
    success_url = reverse_lazy("size_master:list")

    def form_valid(self, form):
        length = form.cleaned_data.get("length") or Decimal("0")
        breadth = form.cleaned_data.get("breadth") or Decimal("0")
        try:
            sqmt = (Decimal(length) * Decimal(breadth)).quantize(Decimal("0.0001"))
        except (InvalidOperation, TypeError):
            sqmt = Decimal("0.0")
        instance = form.save(commit=False)
        instance.sqmt = sqmt
        instance.save()
        form.save_m2m()
        messages.success(self.request, "Size Master created successfully.")
        return super().form_valid(form)


class SizeMasterListView(LoginRequiredMixin, ListView):
    model = SizeMaster
    template_name = "size_master/size_list.html"
    context_object_name = "sizes"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().select_related("category").order_by("category__name", "size")

        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(size__icontains=q))

        # filter by category id
        category_id = self.request.GET.get("category")
        if category_id:
            qs = qs.filter(category_id=category_id)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        Category, _ = get_category_models()
        if Category is not None:
            try:
                ctx["categories"] = Category.objects.all().order_by("name")
            except Exception:
                ctx["categories"] = []
        else:
            ctx["categories"] = []
        ctx["current_q"] = self.request.GET.get("q", "")
        ctx["current_category"] = int(self.request.GET.get("category")) if self.request.GET.get("category") else None
        return ctx


@require_POST
def size_master_delete(request, pk):
    """
    POST-only delete endpoint for SizeMaster.
    Keep permission checks inline so anonymous users get redirected to login.
    """
    obj = get_object_or_404(SizeMaster, pk=pk)

    if not (request.user.is_superuser or request.user.has_perm("size_master.delete_sizemaster")):
        from django.contrib.auth.views import redirect_to_login

        if not request.user.is_authenticated:
            return redirect_to_login(next=request.path)
        from django.contrib import messages as _m

        _m.error(request, "You do not have permission to delete this item.")
        return redirect("size_master:list")

    obj.delete()
    messages.success(request, "Size master deleted.")
    return redirect("size_master:list")


@csrf_exempt
@login_exempt
def ajax_category_sizes(request, category_id):
    """
    Public JSON endpoint returning sizes for a given category id.
    Response: [{"name": "S"}, {"name": "M"}, ...] or [] on error.
    """
    _, CategorySize = get_category_models()
    if CategorySize is None:
        return JsonResponse([], safe=False)

    try:
        sizes_qs = CategorySize.objects.filter(category_id=category_id).order_by("order", "name").values("name")
        return JsonResponse(list(sizes_qs), safe=False)
    except Exception:
        return JsonResponse([], safe=False)
