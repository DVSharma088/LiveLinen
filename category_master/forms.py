from django import forms
from .models import CategoryMaster, CategoryMasterNew


class CategoryMasterForm(forms.ModelForm):
    """
    Updated Category Master form with new percentage and INR fields.
    Dynamically loads active categories for the dropdown.
    """
    component = forms.ModelChoiceField(
        queryset=CategoryMasterNew.objects.filter(active=True).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        empty_label="Select a category",
        required=True,
        label="Category",
    )

    class Meta:
        model = CategoryMaster
        fields = [
            "component",
            "gf_overhead",
            "texas_buying_cost",
            "texas_retail",
            "shipping_cost_inr",
            "texas_to_us_selling_cost",
            "import_cost",
            "new_tariff",
            "reciprocal_tariff",
            "shipping_us",
            "us_wholesale_margin",
        ]

        labels = {
            "gf_overhead": "GF Overhead (%)",
            "texas_buying_cost": "Texas Buying Cost (%)",
            "texas_retail": "Texas Retail (%)",
            "shipping_cost_inr": "Shipping Cost (INR)",
            "texas_to_us_selling_cost": "Texas → US Selling Cost (%)",
            "import_cost": "Import (%)",
            "new_tariff": "New Tariff (%)",
            "reciprocal_tariff": "Reciprocal Tariff (%)",
            "shipping_us": "Shipping US (%)",
            "us_wholesale_margin": "US Wholesale Margin (%)",
        }

        widgets = {
            # Component field handled separately above.
            **{
                field: forms.NumberInput(
                    attrs={
                        "class": "form-control",
                        "step": "0.01",
                        "min": "0",
                        "placeholder": f"Enter {label}"
                    }
                )
                for field, label in {
                    "gf_overhead": "GF Overhead (%)",
                    "texas_buying_cost": "Texas Buying Cost (%)",
                    "texas_retail": "Texas Retail (%)",
                    "shipping_cost_inr": "Shipping Cost (INR)",
                    "texas_to_us_selling_cost": "Texas → US Selling Cost (%)",
                    "import_cost": "Import (%)",
                    "new_tariff": "New Tariff (%)",
                    "reciprocal_tariff": "Reciprocal Tariff (%)",
                    "shipping_us": "Shipping US (%)",
                    "us_wholesale_margin": "US Wholesale Margin (%)",
                }.items()
            }
        }

    def __init__(self, *args, **kwargs):
        """
        Ensure active CategoryMasterNew queryset is always fresh.
        """
        super().__init__(*args, **kwargs)
        try:
            self.fields["component"].queryset = CategoryMasterNew.objects.filter(active=True).order_by("name")
        except Exception:
            # fallback if DB is not available yet (e.g., migrations)
            pass

    def clean(self):
        """
        Basic validation — ensure percentages are between 0 and 100.
        """
        cleaned_data = super().clean()
        percent_fields = [
            "gf_overhead",
            "texas_buying_cost",
            "texas_retail",
            "texas_to_us_selling_cost",
            "import_cost",
            "new_tariff",
            "reciprocal_tariff",
            "shipping_us",
            "us_wholesale_margin",
        ]

        for field in percent_fields:
            value = cleaned_data.get(field)
            if value is not None and (value < 0 or value > 100):
                self.add_error(field, f"{self.fields[field].label} must be between 0 and 100.")
        return cleaned_data
