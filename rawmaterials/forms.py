# rawmaterials/forms.py

from decimal import Decimal, InvalidOperation
from django import forms
from django.core.exceptions import ValidationError
from django.conf import settings

from .models import Fabric, Accessory, Printed


def _normalize_or_validate_quality(value, allow_blank=True):
    """
    Accepts a value that may be Decimal, numeric string, or textual string.
    - If blank and allow_blank True -> returns None
    - If numeric (parsable to Decimal) -> validates 0.00 <= x <= 100.00 and returns a string with 2 decimal places (e.g. "12.50")
    - If not numeric -> returns trimmed string as-is
    Raises ValidationError for out-of-range numeric values or invalid types.
    Returns: str or None
    """
    if value in (None, ""):
        if allow_blank:
            return None
        raise ValidationError("Quality is required.")
    # If value already a Decimal, keep it numeric
    if isinstance(value, Decimal):
        qd = value
    else:
        try:
            qd = Decimal(str(value).strip())
        except (InvalidOperation, TypeError, ValueError):
            qd = None

    if qd is not None:
        if qd < Decimal("0.00") or qd > Decimal("100.00"):
            raise ValidationError("Quality must be between 0 and 100 (percent).")
        qd = qd.quantize(Decimal("0.01"))
        return format(qd, "f")  # e.g. "12.50"
    # Non-numeric textual value -> trimmed string
    return str(value).strip()


# ----------------------------
# FabricForm
# ----------------------------
class FabricForm(forms.ModelForm):
    quality = forms.CharField(
        required=False,
        max_length=64,
        label="Quality",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 85.50 or A1"}),
        help_text='Quality may be numeric (0-100) or textual (e.g., "A1", "Fine").'
    )
    fabric_width = forms.DecimalField(
        required=True,
        max_digits=7,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        help_text="Fabric width (required)."
    )
    stock_in_mtrs = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=3,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
        help_text="Stock in meters."
    )
    cost_per_unit = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
        help_text="Cost per unit."
    )

    class Meta:
        model = Fabric
        fields = [
            "item_name",
            "quality",
            "base_color",
            "type",
            "fabric_width",
            "use_in",
            "stock_in_mtrs",
            "cost_per_unit",
            "vendor",
        ]
        widgets = {
            "item_name": forms.TextInput(attrs={"class": "form-control"}),
            "base_color": forms.TextInput(attrs={"class": "form-control"}),
            "type": forms.TextInput(attrs={"class": "form-control", "placeholder": "Type of fabric"}),
            "use_in": forms.TextInput(attrs={"class": "form-control"}),
            "vendor": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_quality(self):
        """
        Normalize quality (returns str like "12.50" or "A1" or None).
        """
        q_raw = self.cleaned_data.get("quality")
        try:
            normalized = _normalize_or_validate_quality(q_raw, allow_blank=True)
        except ValidationError:
            raise
        return normalized

    def save(self, commit=True):
        inst = super().save(commit=False)
        # Persist normalized quality string into model's CharField
        q = self.cleaned_data.get("quality")
        if q is None or (isinstance(q, str) and q.strip() == ""):
            inst.quality = None
        else:
            inst.quality = str(q).strip()
            # also set quality_text if model has it (backwards compatibility)
            if hasattr(inst, "quality_text"):
                try:
                    inst.quality_text = str(q).strip()
                except Exception:
                    pass
        if commit:
            inst.save()
        return inst

    def clean_fabric_width(self):
        w = self.cleaned_data.get("fabric_width")
        if w in (None, ""):
            raise ValidationError("Fabric width is required.")
        try:
            wd = Decimal(w)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Invalid fabric width.")
        if wd <= 0:
            raise ValidationError("Fabric width must be greater than zero.")
        return wd

    def clean_stock_in_mtrs(self):
        s = self.cleaned_data.get("stock_in_mtrs")
        if s in (None, ""):
            return Decimal("0.000")
        try:
            sd = Decimal(s)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Invalid stock value.")
        if sd < 0:
            raise ValidationError("Stock cannot be negative.")
        return sd

    def clean_cost_per_unit(self):
        c = self.cleaned_data.get("cost_per_unit")
        if c in (None, ""):
            return Decimal("0.00")
        try:
            cd = Decimal(c)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Invalid cost value.")
        if cd < 0:
            raise ValidationError("Cost per unit cannot be negative.")
        return cd


# ----------------------------
# AccessoryForm
# ----------------------------
class AccessoryForm(forms.ModelForm):
    quality = forms.CharField(
        required=False,
        max_length=64,
        label="Quality",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 85.00 or A1"}),
        help_text='Quality may be numeric (0-100) or textual (e.g., "A1", "Fine").'
    )
    width = forms.DecimalField(
        required=False,
        max_digits=7,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        help_text="Width (optional)"
    )
    stock = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=3,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
        help_text="Stock (units or meters)"
    )
    cost_per_unit = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
        help_text="Cost per unit"
    )

    class Meta:
        model = Accessory
        fields = [
            "item_name",
            "quality",
            "base_color",
            "item_type",
            "width",
            "use_in",
            "stock",
            "cost_per_unit",
            "vendor",
        ]
        widgets = {
            "item_name": forms.TextInput(attrs={"class": "form-control"}),
            "base_color": forms.TextInput(attrs={"class": "form-control"}),
            "item_type": forms.TextInput(attrs={"class": "form-control", "placeholder": "Type / category"}),
            "use_in": forms.TextInput(attrs={"class": "form-control", "placeholder": "Where used"}),
            "vendor": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_item_name(self):
        name = self.cleaned_data.get("item_name")
        if not name or str(name).strip() == "":
            raise ValidationError("Item name is required.")
        return str(name).strip()

    def clean_quality(self):
        """
        Normalize to string (or None) and persist textual qualities as strings.
        """
        q_raw = self.cleaned_data.get("quality")
        try:
            normalized = _normalize_or_validate_quality(q_raw, allow_blank=True)
        except ValidationError:
            raise
        return normalized

    def save(self, commit=True):
        inst = super().save(commit=False)
        q = self.cleaned_data.get("quality")
        if q is None or (isinstance(q, str) and q.strip() == ""):
            inst.quality = None
        else:
            inst.quality = str(q).strip()
            if hasattr(inst, "quality_text"):
                try:
                    inst.quality_text = str(q).strip()
                except Exception:
                    pass
        if commit:
            inst.save()
        return inst

    def clean_width(self):
        w = self.cleaned_data.get("width")
        if w in (None, ""):
            return None
        try:
            wd = Decimal(w)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Invalid width value.")
        if wd <= 0:
            raise ValidationError("Width must be greater than zero if provided.")
        return wd

    def clean_stock(self):
        s = self.cleaned_data.get("stock")
        if s in (None, ""):
            return Decimal("0.000")
        try:
            sd = Decimal(s)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Invalid stock value.")
        if sd < 0:
            raise ValidationError("Stock cannot be negative.")
        return sd

    def clean_cost_per_unit(self):
        c = self.cleaned_data.get("cost_per_unit")
        if c in (None, ""):
            return Decimal("0.00")
        try:
            cd = Decimal(c)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Invalid cost per unit value.")
        if cd < 0:
            raise ValidationError("Cost per unit cannot be negative.")
        return cd

    def clean_use_in(self):
        u = self.cleaned_data.get("use_in")
        if u in (None, ""):
            return ""
        return str(u).strip()


# ----------------------------
# PrintedForm
# ----------------------------
class PrintedForm(forms.ModelForm):
    quantity_used = forms.DecimalField(
        required=True,
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
        help_text="Quantity of fabric used (required)."
    )
    stock = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=3,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
        help_text="Stock of printed product"
    )
    cost_per_unit = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
        help_text="Cost per unit (optional)"
    )
    rate = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
        help_text="Rate (optional)"
    )
    width = forms.DecimalField(
        required=False,
        max_digits=7,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    quality = forms.CharField(
        required=False,
        max_length=64,
        label="Quality",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 85.00 or A1"}),
        help_text='Quality may be numeric (0-100) or textual (e.g., "A1"). Leave blank to inherit from Fabric.'
    )

    class Meta:
        model = Printed
        fields = [
            "product",
            "fabric",
            "base_color",
            "product_type",
            "width",
            "use_in",
            "quality",
            "unit",
            "quantity_used",
            "stock",
            "cost_per_unit",
            "rate",
            "vendor",
        ]
        widgets = {
            "product": forms.TextInput(attrs={"class": "form-control"}),
            "fabric": forms.Select(attrs={"class": "form-select"}),
            "base_color": forms.TextInput(attrs={"class": "form-control"}),
            "product_type": forms.TextInput(attrs={"class": "form-control"}),
            "use_in": forms.TextInput(attrs={"class": "form-control"}),
            "unit": forms.Select(attrs={"class": "form-select"}),
            "vendor": forms.Select(attrs={"class": "form-select"}),
            "quality": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 85.00 or A1"}),
        }

    def clean_quantity_used(self):
        qty = self.cleaned_data.get("quantity_used")
        if qty is None or qty == "":
            raise ValidationError("Quantity used is required.")
        try:
            qty_d = Decimal(qty)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Invalid quantity value.")
        if qty_d <= 0:
            raise ValidationError("Quantity used must be greater than zero.")
        return qty_d

    def clean_stock(self):
        stk = self.cleaned_data.get("stock")
        if stk in (None, ""):
            return Decimal("0.000")
        try:
            stk_d = Decimal(stk)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Invalid stock value.")
        if stk_d < 0:
            raise ValidationError("Stock cannot be negative.")
        return stk_d

    def clean_cost_per_unit(self):
        c = self.cleaned_data.get("cost_per_unit")
        if c in (None, ""):
            return Decimal("0.00")
        try:
            cd = Decimal(c)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Invalid cost per unit value.")
        if cd < 0:
            raise ValidationError("Cost per unit cannot be negative.")
        return cd

    def clean_rate(self):
        r = self.cleaned_data.get("rate")
        if r in (None, ""):
            return Decimal("0.00")
        try:
            rd = Decimal(r)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Invalid rate value.")
        if rd < 0:
            raise ValidationError("Rate cannot be negative.")
        return rd

    def clean_width(self):
        w = self.cleaned_data.get("width")
        if w in (None, ""):
            return None
        try:
            wd = Decimal(w)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Invalid width value.")
        if wd <= 0:
            raise ValidationError("Width must be greater than zero if provided.")
        return wd

    def clean_quality(self):
        """
        Normalize quality to a string (or None). Printed.save() / model will inherit Fabric if None.
        """
        q_raw = self.cleaned_data.get("quality")
        try:
            normalized = _normalize_or_validate_quality(q_raw, allow_blank=True)
        except ValidationError:
            raise
        return normalized

    def save(self, commit=True):
        inst = super().save(commit=False)
        q = self.cleaned_data.get("quality")
        if q is None or (isinstance(q, str) and q.strip() == ""):
            inst.quality = None
        else:
            inst.quality = str(q).strip()
            if hasattr(inst, "quality_text"):
                try:
                    inst.quality_text = str(q).strip()
                except Exception:
                    pass
        if commit:
            inst.save()
        return inst

    def clean(self):
        cleaned = super().clean()
        qty = cleaned.get("quantity_used")
        stock = cleaned.get("stock")

        if qty is not None and stock is not None:
            try:
                if stock > Decimal("0") and (qty is None or qty <= Decimal("0")):
                    raise ValidationError("quantity_used must be > 0 when providing stock.")
            except Exception:
                pass

        return cleaned


# ----------------------------
# CSV Upload Form (for bulk import)
# ----------------------------
class CSVUploadForm(forms.Form):
    """
    Simple form to upload CSV files. Keeps validation basic:
      - ensures extension endswith .csv
      - optional 'target' to choose which model to import into (fabric/accessory/printed)
      - size limit (default 5 MB) to avoid huge uploads; adjust MAX_CSV_UPLOAD_SIZE in settings if needed.
    The heavy lifting (parsing, header checks, per-row validation) should be done in the view or a service helper.
    """
    MODEL_CHOICES = (
        ("fabric", "Fabric"),
        ("accessory", "Accessory"),
        ("printed", "Printed"),
    )

    csv_file = forms.FileField(
        label="CSV file",
        help_text="Upload a UTF-8 .csv file. Required headers depend on chosen target model.",
    )
    target = forms.ChoiceField(
        choices=MODEL_CHOICES,
        label="Import target",
        help_text="Select which model this CSV will import into."
    )

    # default max upload size 5 MB (can override by setting MAX_CSV_UPLOAD_SIZE in settings)
    DEFAULT_MAX_SIZE = 5 * 1024 * 1024

    def clean_csv_file(self):
        f = self.cleaned_data.get("csv_file")
        if not f:
            raise ValidationError("No file uploaded.")
        name = getattr(f, "name", "")
        # extension check
        if not name.lower().endswith(".csv"):
            raise ValidationError("Please upload a file with .csv extension.")
        # size check
        max_size = getattr(settings, "MAX_CSV_UPLOAD_SIZE", self.DEFAULT_MAX_SIZE)
        if hasattr(f, "size") and f.size > max_size:
            raise ValidationError(f"CSV file is too large. Max allowed size is {max_size // (1024*1024)} MB.")
        # content-type is not reliable across clients/servers, so do not rely solely on it.
        return f
