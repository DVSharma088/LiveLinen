# issue_material/forms.py
from decimal import Decimal

from django import forms
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from .models import Issue, IssueLine


class IssueForm(forms.ModelForm):
    class Meta:
        model = Issue
        fields = ["product", "order_no", "notes"]


class IssueLineForm(forms.ModelForm):
    # We'll accept content_type_id and object_id from the client (JS fills them
    # when user selects an item). Keep them as hidden fields in the formset rows.
    content_type_id = forms.IntegerField(widget=forms.HiddenInput(), required=False)
    object_id = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = IssueLine
        fields = ["inventory_type", "content_type_id", "object_id", "qty"]

    def clean(self):
        cleaned = super().clean()
        inventory_type = cleaned.get("inventory_type")
        content_type_id = cleaned.get("content_type_id")
        object_id = cleaned.get("object_id")
        qty = cleaned.get("qty") or Decimal("0")

        if not inventory_type:
            raise ValidationError("Inventory type is required for each line.")

        if not content_type_id or not object_id:
            raise ValidationError("Select a valid inventory item.")

        # ensure referenced object exists and has stock
        try:
            ct = ContentType.objects.get_for_id(content_type_id)
        except ContentType.DoesNotExist:
            raise ValidationError("Invalid inventory content type selected.")

        model_class = ct.model_class()
        if model_class is None:
            raise ValidationError("Invalid inventory model selected.")

        try:
            obj = model_class.objects.get(pk=object_id)
        except model_class.DoesNotExist:
            raise ValidationError("Selected inventory item does not exist.")

        # check stock >= qty
        stock = getattr(obj, "stock", None)
        if stock is None:
            raise ValidationError("Selected inventory item has no stock attribute.")
        if isinstance(stock, (int, float)):
            stock = Decimal(str(stock))
        if isinstance(qty, (int, float)):
            qty = Decimal(str(qty))

        if qty <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        if stock - qty < 0:
            raise ValidationError(f"Not enough stock for {getattr(obj, 'name', str(obj))} (available {stock}).")

        # set item_name snapshot (optional)
        cleaned["item_name"] = getattr(obj, "name", getattr(obj, "title", str(obj)))

        return cleaned


# formset for IssueLine objects related to Issue
IssueLineFormSet = inlineformset_factory(
    Issue,
    IssueLine,
    form=IssueLineForm,
    extra=1,
    can_delete=True,
)
