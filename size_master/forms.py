# size_master/forms.py

from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.apps import apps

from .models import SizeMaster


def get_category_models():
    """
    Lazily fetch the Category and CategorySize models from the Category_Master(New) app.
    Adjust the app_label ("category_master_new") below if your app label differs.
    Returns (CategoryModel, CategorySizeModel) or (None, None) on failure.
    """
    try:
        Category = apps.get_model("category_master_new", "Category")
        CategorySize = apps.get_model("category_master_new", "CategorySize")
        return Category, CategorySize
    except Exception:
        return None, None


class EmptyQuerysetFallback:
    """
    Minimal object that mimics the small QuerySet API pieces ModelChoiceField expects:
      - .all() -> returns itself (iterable)
      - .none() -> returns itself
      - .order_by(...) -> returns itself
      - iteration -> yields nothing
    This prevents Django from calling .all() on a plain list and throwing AttributeError.
    """
    def all(self):
        return self

    def none(self):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False

    def __len__(self):
        return 0


class SizeMasterForm(forms.ModelForm):
    # form-only readonly field to show calculated sqmt
    sqmt = forms.DecimalField(
        label="SqMT",
        required=False,
        disabled=True,
        max_digits=12,
        decimal_places=6,
        widget=forms.NumberInput(attrs={"class": "form-control", "readonly": "readonly", "id": "id_sqmt"}),
    )

    # category: ModelChoiceField (queryset set at runtime in __init__)
    category = forms.ModelChoiceField(
        queryset=None,  # will be set in __init__
        widget=forms.Select(attrs={"class": "form-control", "id": "id_category"}),
        required=True,
        label="Category",
    )

    # size: CharField (free text) but we render it as a select for UX.
    # We will populate the widget.choices in __init__ so the select is populated,
    # but validation won't restrict to the widget choices.
    size = forms.CharField(
        required=True,
        label="Size",
        widget=forms.Select(attrs={"class": "form-control", "id": "id_size"}),
    )

    class Meta:
        model = SizeMaster
        fields = [
            "category",
            "size",
            "length",
            "breadth",
            "stitching",
            "finishing",
            "packaging",
        ]
        widgets = {
            "length": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "oninput": "calculateSqmt()", "id": "id_length"}
            ),
            "breadth": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "oninput": "calculateSqmt()", "id": "id_breadth"}
            ),
            "stitching": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "finishing": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "packaging": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        """
        Populate category queryset and size choices based on:
         - POST data (args[0] if present),
         - initial data (kwargs.get('initial')),
         - instance (when editing).
        Uses lazy model resolution to avoid import-time issues.
        """
        super().__init__(*args, **kwargs)

        # Lazy-resolve models from the Category_Master(New) app
        Category, CategorySize = get_category_models()

        # populate category queryset safely
        if Category is not None:
            try:
                self.fields["category"].queryset = Category.objects.all().order_by("name")
            except Exception:
                # fallback to a safe empty queryset-like object
                self.fields["category"].queryset = EmptyQuerysetFallback()
        else:
            # can't resolve model right now (app registry not ready?), assign safe fallback
            self.fields["category"].queryset = EmptyQuerysetFallback()

        # determine selected category id (priority: POST data -> initial -> instance)
        category_id = None

        # 1) POST data (args[0]) may be a QueryDict
        data = args[0] if args else None
        if data and hasattr(data, "get"):
            raw = data.get(self.add_prefix("category")) or data.get("category")
            if raw:
                try:
                    category_id = int(raw)
                except (ValueError, TypeError):
                    category_id = None

        # 2) initial
        if category_id is None:
            initial = kwargs.get("initial") or {}
            init_cat = initial.get("category")
            if init_cat is not None:
                if hasattr(init_cat, "pk"):
                    category_id = getattr(init_cat, "pk", None)
                else:
                    try:
                        category_id = int(init_cat)
                    except Exception:
                        category_id = None

        # 3) instance
        if category_id is None and hasattr(self, "instance") and getattr(self.instance, "category", None):
            try:
                category_id = int(getattr(self.instance, "category").pk)
            except Exception:
                category_id = None

        # Now populate size choices based on category_id
        # We'll set widget.choices so the select shows options, but the form field
        # itself will accept any string value.
        widget_choices = []
        if category_id and CategorySize is not None:
            try:
                sizes_qs = CategorySize.objects.filter(category_id=category_id).order_by("order", "name")
                # first blank option
                widget_choices = [("", "---------")] + [(s.name, s.name) for s in sizes_qs]
            except Exception:
                widget_choices = [("", "---------")]
        else:
            # no category selected yet
            widget_choices = [("", "Select a category first")]

        # Ensure existing instance.size remains selectable when editing
        if getattr(self, "instance", None) and getattr(self.instance, "size", None):
            cur_val = self.instance.size
            # if current value is non-empty and not already present as an option, append it
            if cur_val and (cur_val not in [c for c, _ in widget_choices]):
                widget_choices.append((cur_val, cur_val))

        # assign choices to the widget so <select> displays them
        try:
            self.fields["size"].widget.choices = widget_choices
        except Exception:
            # If something odd happens, fallback to a minimal placeholder
            self.fields["size"].widget.choices = [("", "Select a category first")]

    def clean(self):
        cleaned_data = super().clean()
        length = cleaned_data.get("length")
        breadth = cleaned_data.get("breadth")

        if length is not None and breadth is not None:
            try:
                sqmt_val = (Decimal(length) * Decimal(breadth)).quantize(Decimal("0.0001"))
                cleaned_data["sqmt"] = sqmt_val
            except Exception:
                raise ValidationError("Invalid numeric values for Length or Breadth.")
        else:
            cleaned_data["sqmt"] = Decimal("0.0")

        # ensure size value stored as string and not empty
        size_val = cleaned_data.get("size")
        if not size_val:
            raise ValidationError("Please select a size.")
        cleaned_data["size"] = str(size_val)

        return cleaned_data
