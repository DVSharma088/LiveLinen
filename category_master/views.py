from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, View
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404

from .models import CategoryMaster, CategoryMasterNew
from .forms import CategoryMasterForm


def _get_category_master_new_qs():
    """
    Central helper returning the queryset used to populate the category dropdown.
    Keeps ordering/filtering logic in one place so form/view/template behavior is consistent.
    """
    qs = CategoryMasterNew.objects.all().order_by("name")
    # Prefer only active entries when available
    try:
        qs = qs.filter(active=True)
    except Exception:
        # If model doesn't have 'active', just return all ordered results
        pass
    return qs


class CategoryMasterCreateView(CreateView):
    model = CategoryMaster
    form_class = CategoryMasterForm
    template_name = "category_master/create_category.html"
    success_url = reverse_lazy("category_master:list")

    def get_form(self, form_class=None):
        """
        Ensure the form's `component` field uses the centralized queryset.
        - Always set the queryset so ModelChoiceField validation works on POST.
        - For fresh GET requests we clear the initial selection so the empty_label shows.
        """
        form = super().get_form(form_class)
        try:
            qs = _get_category_master_new_qs()

            if "component" in form.fields and hasattr(form.fields["component"], "queryset"):
                # always give the field the correct queryset (ensures choices exist)
                form.fields["component"].queryset = qs

                # set friendly empty label if available
                try:
                    if hasattr(form.fields["component"], "empty_label"):
                        form.fields["component"].empty_label = "Select a category"
                except Exception:
                    pass

                # For initial GET request, ensure no preselected initial value
                try:
                    if getattr(self.request, "method", "").upper() == "GET":
                        form.initial["component"] = None
                except Exception:
                    pass
        except Exception:
            # keep form as-is on error
            pass
        return form

    def get_context_data(self, **kwargs):
        """
        Include category_master_new_list so templates (or JS) can access the list
        if manual rendering is ever required.
        """
        ctx = super().get_context_data(**kwargs)
        ctx["category_master_new_list"] = _get_category_master_new_qs()
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Category created successfully!")
        return super().form_valid(form)


class CategoryMasterUpdateView(UpdateView):
    """
    Simple UpdateView allowing editing of existing CategoryMaster entries.
    Reuses the same form and template as create (templates should handle mode differences).
    """
    model = CategoryMaster
    form_class = CategoryMasterForm
    template_name = "category_master/create_category.html"
    success_url = reverse_lazy("category_master:list")

    def get_form(self, form_class=None):
        # reuse same logic as CreateView to ensure component queryset is correct
        form = super().get_form(form_class)
        try:
            qs = _get_category_master_new_qs()
            if "component" in form.fields and hasattr(form.fields["component"], "queryset"):
                form.fields["component"].queryset = qs
        except Exception:
            pass
        return form

    def form_valid(self, form):
        messages.success(self.request, "Category updated successfully!")
        return super().form_valid(form)


class CategoryMasterListView(ListView):
    model = CategoryMaster
    template_name = "category_master/category_list.html"
    context_object_name = "categories"
    paginate_by = 25

    # If `component` is a FK to CategoryMasterNew, select_related improves performance.
    queryset = CategoryMaster.objects.select_related("component").all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["category_master_new_list"] = _get_category_master_new_qs()
        return ctx


class CategoryMasterDeleteView(View):
    """Instant delete view — deletes and redirects to list with success message."""

    def post(self, request, pk):
        category = get_object_or_404(CategoryMaster, pk=pk)
        category.delete()
        messages.success(request, "Category deleted successfully!")
        return redirect("category_master:list")
