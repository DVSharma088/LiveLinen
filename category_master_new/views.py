# category_master_new/views.py
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.views import View
from django.db import transaction

from .models import Category, CategorySize
from .forms import CategoryForm, get_category_forms  # get_category_forms returns (form, formset)


def category_list(request):
    categories = Category.objects.prefetch_related("sizes").all().order_by("name")
    return render(request, "category_master_new/category_list.html", {"categories": categories})


@require_http_methods(["GET", "POST"])
def category_create(request):
    form, formset = get_category_forms(data=request.POST or None, instance=None, prefix="sizes")

    if request.method == "POST":
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    category = form.save()
                    formset.instance = category
                    formset.save()
                messages.success(request, "Category created successfully.")
                return redirect(reverse_lazy("category_master_new:category_list"))
            except Exception as e:
                messages.error(request, f"An error occurred while saving: {e}")
        else:
            messages.error(request, "Please correct the errors below.")

    return render(
        request,
        "category_master_new/category_create.html",
        {"form": form, "formset": formset},
    )


class CategoryUpdateView(View):
    def get(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        form, formset = get_category_forms(data=None, instance=category, prefix="sizes")
        return render(
            request,
            "category_master_new/category_create.html",
            {"form": form, "formset": formset, "category": category},
        )

    def post(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        form, formset = get_category_forms(data=request.POST or None, instance=category, prefix="sizes")

        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    formset.instance = category
                    formset.save()
                messages.success(request, "Category updated successfully.")
                return redirect(reverse_lazy("category_master_new:category_list"))
            except Exception as e:
                messages.error(request, f"An error occurred while saving: {e}")
        else:
            messages.error(request, "Please correct the errors below.")

        return render(
            request,
            "category_master_new/category_create.html",
            {"form": form, "formset": formset, "category": category},
        )


@require_http_methods(["GET"])
def category_sizes_json(request, pk):
    """
    Return JSON list of sizes for the given category id, including stitching,
    finishing and packaging values. Used by AJAX in other pages.
    Example:
      [
        {"id": 1, "name": "S", "stitching_cost": "100.00", "finishing_cost": "20.00", "packaging_cost": "5.00"},
        ...
      ]
    """
    category = get_object_or_404(Category, pk=pk)
    sizes_qs = CategorySize.objects.filter(category=category).order_by("order", "name")
    data = [
        {
            "id": s.id,
            "name": s.name,
            "stitching_cost": str(s.stitching_cost) if s.stitching_cost is not None else None,
            "finishing_cost": str(s.finishing_cost) if s.finishing_cost is not None else None,
            "packaging_cost": str(s.packaging_cost) if s.packaging_cost is not None else None,
        }
        for s in sizes_qs
    ]
    return JsonResponse(data, safe=False)


@require_http_methods(["POST"])
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    try:
        category.delete()
        messages.success(request, "Category deleted successfully.")
    except Exception as e:
        messages.error(request, f"Could not delete category: {e}")
    return redirect(reverse_lazy("category_master_new:category_list"))
