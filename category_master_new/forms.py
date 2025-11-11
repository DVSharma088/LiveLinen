# category_master_new/forms.py
from decimal import Decimal, InvalidOperation

from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError

from .models import Category, CategorySize


class CategoryForm(forms.ModelForm):
    """
    Simple ModelForm for Category. Add or remove fields from `Meta.fields`
    depending on which category-level fields you want editable in the UI.
    """
    class Meta:
        model = Category
        # keep this list short for the create/update UI; add other category-level
        # costing fields here if you want them editable from the same form.
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Category name"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Optional description"}),
        }


class CategorySizeForm(forms.ModelForm):
    """
    Form for CategorySize rows. Used in an inline formset so admin/users can
    add/edit sizes and per-size costs like stitching_cost, finishing_cost and packaging_cost.
    """
    class Meta:
        model = CategorySize
        fields = ["name", "order", "stitching_cost", "finishing_cost", "packaging_cost"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., S"}),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "stitching_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0}),
            "finishing_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0}),
            "packaging_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0}),
        }

    def _clean_cost_field(self, field_name, human_label):
        val = self.cleaned_data.get(field_name)
        if val is None:
            return val
        try:
            d = Decimal(val)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError(f"Enter a valid number for {human_label}.")
        if d < 0:
            raise ValidationError(f"{human_label} cannot be negative.")
        # normalize to 2 decimal places (optional)
        # return d.quantize(Decimal('0.01'))
        return d

    def clean_stitching_cost(self):
        return self._clean_cost_field("stitching_cost", "stitching cost")

    def clean_finishing_cost(self):
        return self._clean_cost_field("finishing_cost", "finishing cost")

    def clean_packaging_cost(self):
        return self._clean_cost_field("packaging_cost", "packaging cost")


# Inline formset: Category -> CategorySize
CategorySizeFormSet = inlineformset_factory(
    parent_model=Category,
    model=CategorySize,
    form=CategorySizeForm,
    fields=["name", "order", "stitching_cost", "finishing_cost", "packaging_cost"],
    extra=1,
    can_delete=True,
    min_num=0,   # set to 1 if you require at least one size
    validate_min=False,
)


def get_category_forms(data=None, instance=None, prefix="sizes"):
    """
    Helper to instantiate a CategoryForm and its CategorySizeFormSet.

    Parameters:
        data: request.POST or None
        instance: Category instance for edit, or None for create
        prefix: formset prefix (useful if multiple formsets on the page)

    Returns:
        (category_form, size_formset)
    """
    if instance:
        form = CategoryForm(data or None, instance=instance)
    else:
        form = CategoryForm(data or None)

    formset = CategorySizeFormSet(
        data or None,
        instance=instance,
        prefix=prefix
    )
    return form, formset
