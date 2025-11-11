from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError

from .models import (
    FinishedProduct,
    FinishedProductLine,
    SIZE_CHOICES,
    PRODUCT_NAME_CHOICES,
    PRODUCT_TYPE_CHOICES,
    COLLECTION_CHOICES,
    COLOR_CHOICES,
)


class FinishedProductForm(forms.ModelForm):
    class Meta:
        model = FinishedProduct
        # Include the new dropdown fields and other existing ones
        fields = [
            "name",
            "product_type",
            "fabric_collection",
            "fabric_color_name",
            "size",
            "average",
            "fabric_quality",
            "fabric_width",
            "product_category",
            "fabric_pattern",
            "product_price",
        ]

        widgets = {
            # Dropdown fields
            "name": forms.Select(choices=PRODUCT_NAME_CHOICES, attrs={"class": "form-control"}),
            "product_type": forms.Select(choices=PRODUCT_TYPE_CHOICES, attrs={"class": "form-control"}),
            "fabric_collection": forms.Select(choices=COLLECTION_CHOICES, attrs={"class": "form-control"}),
            "fabric_color_name": forms.Select(choices=COLOR_CHOICES, attrs={"class": "form-control"}),
            "size": forms.Select(choices=SIZE_CHOICES, attrs={"class": "form-control"}),

            # Text/number fields
            "average": forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
            "fabric_quality": forms.TextInput(attrs={"class": "form-control"}),
            "fabric_width": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "product_category": forms.TextInput(attrs={"class": "form-control"}),
            "fabric_pattern": forms.TextInput(attrs={"class": "form-control"}),
            "product_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

    def clean_average(self):
        avg = self.cleaned_data.get("average")
        if avg is None:
            return Decimal("0.000")
        if avg < 0:
            raise ValidationError("Average cannot be negative.")
        return avg

    def clean_product_price(self):
        price = self.cleaned_data.get("product_price")
        if price is None:
            return Decimal("0.00")
        if price < 0:
            raise ValidationError("Product price cannot be negative.")
        return price

    def clean(self):
        cleaned = super().clean()
        return cleaned


class FinishedProductLineForm(forms.ModelForm):
    class Meta:
        model = FinishedProductLine
        fields = [
            "content_type",
            "object_id",
            "qty_per_unit",
        ]
        widgets = {
            "qty_per_unit": forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
            "object_id": forms.NumberInput(attrs={"class": "form-control"}),
            "content_type": forms.Select(attrs={"class": "form-control"}),
        }

    def clean_qty_per_unit(self):
        qty = self.cleaned_data.get("qty_per_unit")
        if qty is None:
            return Decimal("0.000")
        if qty < 0:
            raise ValidationError("Quantity must be non-negative.")
        return qty


# Inline formset for product lines
FinishedProductLineFormSet = inlineformset_factory(
    FinishedProduct,
    FinishedProductLine,
    form=FinishedProductLineForm,
    extra=1,
    can_delete=True,
)
