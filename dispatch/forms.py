# dispatch/forms.py
from django import forms
from .models import Dispatch


class DispatchForm(forms.ModelForm):
    """
    Form for creating a Dispatch record.
    - work_order: hidden (linked to the WorkOrder)
    - variant / order_value / quantity prefilled and shown as read-only
    - remaining fields (courier_company, tracking_number, remarks) editable by user
    """

    # Extra visible read-only info fields (not part of Dispatch model, for display only)
    order_no = forms.CharField(label="Order No.", required=False, disabled=True)
    product_name = forms.CharField(label="Product Name", required=False, disabled=True)
    price = forms.DecimalField(label="Price", required=False, disabled=True, decimal_places=2, max_digits=12)
    quantity = forms.IntegerField(label="Quantity", required=False, disabled=True)

    class Meta:
        model = Dispatch
        fields = [
            "work_order",
            "variant",
            "order_value",
            "dispatch_date",
            "courier_company",
            "tracking_number",
            "remarks",
        ]
        widgets = {
            # work_order hidden (we pass it via GET/POST automatically)
            "work_order": forms.HiddenInput(),
            # optional styling for remarks
            "remarks": forms.Textarea(attrs={"rows": 3, "placeholder": "Any remarks about the dispatch..."}),
        }

    def __init__(self, *args, **kwargs):
        """
        Initialize form with optional prefill values for Order No, Product, Price, Quantity.
        These can be passed via `initial` dict when rendering the form in GET request.
        """
        super().__init__(*args, **kwargs)

        # mark variant and order_value as read-only in form widgets if they exist
        if "variant" in self.fields:
            self.fields["variant"].widget.attrs["readonly"] = True
        if "order_value" in self.fields:
            self.fields["order_value"].widget.attrs["readonly"] = True

        # add Bootstrap classes for clean styling (optional)
        for field in self.fields.values():
            existing_classes = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing_classes} form-control".strip()
