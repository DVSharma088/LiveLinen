import logging
import re
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .models import CostComponent, ComponentMaster, Color
from rawmaterials.models import Accessory

logger = logging.getLogger(__name__)

# increase precision for intermediate calculations
getcontext().prec = 28


def _extract_int(value):
    """
    Try robustly to extract an integer from `value`.
    Accepts int, digit-strings, and attempts to find first group of digits
    in other strings (e.g. "[34]" -> 34). Returns int or raises ValueError.
    """
    if value is None:
        raise ValueError("No value provided")
    if isinstance(value, int):
        return value
    # If ContentType passed directly, reject here (callers should handle)
    if isinstance(value, ContentType):
        raise ValueError("ContentType instance passed to _extract_int")
    s = str(value).strip()
    if s == "":
        raise ValueError("Empty string")
    try:
        return int(s)
    except (ValueError, TypeError):
        m = re.search(r"(\d+)", s)
        if m:
            return int(m.group(1))
        raise ValueError(f"Cannot extract integer from {repr(value)}")


def _normalize_or_validate_quality(value, allow_blank=True):
    """
    Accept a value that may be Decimal, numeric string, or textual string.
    - If blank and allow_blank True -> returns None
    - If numeric (parsable to Decimal) -> validates 0.00 <= x <= 100.00 and returns a string with 2 decimal places (e.g. "12.50")
    - If not numeric -> returns trimmed string as-is
    Raises ValidationError for out-of-range numeric values or invalid types.
    """
    if value in (None, ""):
        if allow_blank:
            return None
        raise forms.ValidationError(_("Quality is required."))
    if isinstance(value, Decimal):
        qd = value
    else:
        try:
            qd = Decimal(str(value).strip())
        except (InvalidOperation, TypeError, ValueError):
            qd = None

    if qd is not None:
        if qd < Decimal("0.00") or qd > Decimal("100.00"):
            raise forms.ValidationError(_("Quality must be between 0 and 100 (percent)."))
        # quantize to 2 decimal places
        qd = qd.quantize(Decimal("0.01"))
        return format(qd, "f")
    return str(value).strip()


# ---------------------------------------------------------------------
# CostComponentForm (restore expected API)
# ---------------------------------------------------------------------
class CostComponentForm(forms.ModelForm):
    class Meta:
        model = CostComponent
        fields = [
            "name",
            "value_type",
            "value",
            "description",
            "is_active",
            "inventory_category",
            "inventory_content_type",
            "inventory_object_id",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "value_type": forms.Select(attrs={"class": "form-select"}),
            "value": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "description": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "inventory_category": forms.Select(attrs={"class": "form-select"}),
            "inventory_content_type": forms.HiddenInput(),
            "inventory_object_id": forms.HiddenInput(),
        }

    def clean_value(self):
        val = self.cleaned_data.get("value")
        vtype = self.cleaned_data.get("value_type") or self.instance.value_type
        if vtype == CostComponent.ValueType.PERCENTAGE:
            if val is None:
                raise forms.ValidationError(_("Provide a percentage value."))
            try:
                if val < 0 or val > 100:
                    raise forms.ValidationError(_("Percentage must be between 0 and 100."))
            except TypeError:
                raise forms.ValidationError(_("Provide a valid numeric percentage value."))
        else:
            if val is None:
                raise forms.ValidationError(_("Provide a monetary value."))
            try:
                if val < 0:
                    raise forms.ValidationError(_("Value must be non-negative."))
            except TypeError:
                raise forms.ValidationError(_("Provide a valid numeric monetary value."))
        return val

    def clean(self):
        """
        Validate inventory fields similarly to ComponentMasterForm:
        - If inventory_category != NONE, ensure content type and object id resolve to an instance.
        - Otherwise, clear the two hidden fields.
        """
        cleaned = super().clean()
        category = cleaned.get("inventory_category")
        ct_value = cleaned.get("inventory_content_type")
        obj_value = cleaned.get("inventory_object_id")

        if ct_value in ("", None):
            ct_value = None
            cleaned["inventory_content_type"] = None
        if obj_value in ("", None):
            obj_value = None
            cleaned["inventory_object_id"] = None

        if category and category != CostComponent.InventoryCategory.NONE:
            if not ct_value or not obj_value:
                raise forms.ValidationError(_("Select an inventory item for the chosen category."))

            content_type = None
            if isinstance(ct_value, ContentType):
                content_type = ct_value
            else:
                try:
                    ct_pk = _extract_int(ct_value)
                except ValueError:
                    logger.debug("CostComponentForm.clean: invalid inventory_content_type %r", ct_value)
                    raise forms.ValidationError(_("Invalid inventory item selected (content type)."))

                try:
                    content_type = ContentType.objects.get(pk=ct_pk)
                except ContentType.DoesNotExist:
                    logger.debug("CostComponentForm.clean: ContentType with pk %s does not exist", ct_pk)
                    raise forms.ValidationError(_("Invalid inventory item selected (content type)."))

            model_class = content_type.model_class()
            if model_class is None:
                logger.debug("CostComponentForm.clean: content type %r has no model_class()", content_type)
                raise forms.ValidationError(_("Invalid inventory item selected."))

            try:
                obj_pk = _extract_int(obj_value)
            except ValueError:
                logger.debug("CostComponentForm.clean: invalid inventory_object_id %r", obj_value)
                raise forms.ValidationError(_("Invalid inventory item selected (object id)."))

            try:
                instance = model_class.objects.get(pk=obj_pk)
            except model_class.DoesNotExist:
                logger.debug(
                    "CostComponentForm.clean: referenced inventory object not found: %s (ct=%s)",
                    obj_pk, content_type
                )
                raise forms.ValidationError(_("Selected inventory item does not exist."))

            cleaned["inventory_content_type"] = content_type
            cleaned["inventory_object_id"] = int(obj_pk)

        else:
            cleaned["inventory_content_type"] = None
            cleaned["inventory_object_id"] = None

        return cleaned


# ---------------------------------------------------------------------
# ComponentMasterForm (updated to include readonly 'type' and auto-name)
# ---------------------------------------------------------------------
class ComponentMasterForm(forms.ModelForm):
    """
    Form for creating/editing ComponentMaster.

    - 'name' is a hidden field so JS can populate it; model.save() will also fill it as fallback.
    - 'type' is a readonly CharField displayed to users (populated by JS / server).
    - `colors_qs` and `colors_json` are provided on the form instance for template/JS consumption.
      Color creation/removal should be handled by AJAX endpoints, not by this form.save().
    """
    # hidden name field so JS can populate before submit; id required by component_form.js
    name = forms.CharField(required=False, widget=forms.HiddenInput(attrs={"id": "id_name"}))

    type = forms.CharField(required=False, label=_("Type"), widget=forms.TextInput(attrs={
        "readonly": "readonly",
        "class": "form-control",
        "placeholder": _("Auto-filled from inventory"),
        "id": "id_type",
    }))

    class Meta:
        model = ComponentMaster
        fields = [
            # include hidden 'name' so it is accepted on submit (JS fills it)
            "name",
            "inventory_category",
            "inventory_content_type",
            "inventory_object_id",
            "quality",
            "type",
            "cost_per_unit",
            "width",
            "width_uom",
            "logistics_percent",
            "final_price_per_unit",
            "price_per_sqfoot",
            "final_cost",
            "notes",
        ]
        widgets = {
            "inventory_category": forms.Select(attrs={"class": "form-select"}),
            "inventory_content_type": forms.HiddenInput(),
            "inventory_object_id": forms.HiddenInput(),
            # IMPORTANT: render quality as a Select by default (empty choices). JS will populate it.
            "quality": forms.Select(attrs={"class": "form-select", "id": "component_quality_select"}),
            "cost_per_unit": forms.TextInput(attrs={"readonly": "readonly", "class": "form-control", "aria-readonly": "true"}),
            "width": forms.TextInput(attrs={"readonly": "readonly", "class": "form-control", "aria-readonly": "true"}),
            "width_uom": forms.TextInput(attrs={"readonly": "readonly", "class": "form-control", "aria-readonly": "true"}),
            "logistics_percent": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "max": "100"}),
            "final_price_per_unit": forms.TextInput(attrs={"readonly": "readonly", "class": "form-control", "aria-readonly": "true"}),
            "price_per_sqfoot": forms.TextInput(attrs={"readonly": "readonly", "class": "form-control", "aria-readonly": "true"}),
            "final_cost": forms.TextInput(attrs={"readonly": "readonly", "class": "form-control", "aria-readonly": "true"}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        """
        Initialize the form. If inventory_category indicates ACCESSORY, replace the 'quality'
        text input with a Select populated from Accessory.quality_text (preferred) or Accessory.quality.
        Also ensure the 'quality' widget always has the id/class/aria attributes expected by the JS.

        Additionally, expose colors for the current instance via:
          - self.colors_qs   -> queryset (or empty list) of Color objects (active only)
          - self.colors_json -> JSON string for client-side consumption
        """
        super().__init__(*args, **kwargs)

        # Make readonly fields not required
        for fld in ("cost_per_unit", "width", "width_uom", "final_price_per_unit", "price_per_sqfoot", "final_cost"):
            if fld in self.fields:
                self.fields[fld].required = False

        # numeric validators
        # size is no longer exposed on the form; the model default (1.00) will be used
        self.fields["logistics_percent"].validators = [MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))]

        # --------- Dynamic quality field population for ACCESSORY ----------
        try:
            inv_cat = None
            data = None
            if len(args) > 0:
                # args[0] may be POST data when form is instantiated as ComponentMasterForm(request.POST)
                data = args[0]
            if data and hasattr(data, "get"):
                inv_cat = data.get("inventory_category") or None

            # also consider bound data in kwargs (less common)
            if inv_cat is None:
                inv_cat = kwargs.get("initial", {}).get("inventory_category", None)

            # if still None, fall back to instance's stored inventory_category
            if inv_cat is None and self.instance and getattr(self.instance, "inventory_category", None):
                inv_cat = self.instance.inventory_category

            # Normalize string values if necessary
            if isinstance(inv_cat, str):
                inv_cat_val = inv_cat.strip()
            else:
                inv_cat_val = inv_cat

            if inv_cat_val in (ComponentMaster.InventoryCategory.ACCESSORY, "ACCESSORY"):
                # Fetch distinct non-empty textual labels from Accessory.quality_text first
                labels = list(
                    Accessory.objects
                    .exclude(Q(quality_text__isnull=True) | Q(quality_text__exact=""))
                    .values_list("quality_text", flat=True)
                    .distinct()
                )
                # If no textual labels, fallback to non-empty quality field values
                if not labels:
                    labels = list(
                        Accessory.objects
                        .exclude(Q(quality__isnull=True) | Q(quality__exact=""))
                        .values_list("quality", flat=True)
                        .distinct()
                    )

                # Normalize and filter empties
                labels = [str(x).strip() for x in labels if x is not None and str(x).strip() != ""]

                # Build choices
                choices = [("", "---------")] + [(lbl, lbl) for lbl in labels]

                # Replace the quality field with a ChoiceField + Select widget
                if "quality" in self.fields:
                    try:
                        # Only change widget/field if we actually have choices; otherwise leave the Select (JS will populate)
                        if len(choices) > 1:
                            self.fields["quality"] = forms.ChoiceField(
                                choices=choices,
                                required=False,
                                widget=forms.Select(attrs={"class": "form-select", "id": "component_quality_select"})
                            )
                            # If an instance exists with a quality value, set initial so it selects
                            if self.instance and getattr(self.instance, "quality", None):
                                self.fields["quality"].initial = getattr(self.instance, "quality")
                    except Exception:
                        logger.exception("Failed to replace quality field with ChoiceField for ACCESSORY")
        except Exception:
            # Non-fatal — keep quality as select input (JS will populate it)
            logger.exception("Error while preparing dynamic quality choices in ComponentMasterForm.__init__")

        # ---------------------------
        # Ensure quality widget attrs
        # ---------------------------
        try:
            if "quality" in self.fields:
                wattrs = self.fields["quality"].widget.attrs
                # id expected by JS
                wattrs.setdefault("id", "component_quality_select")
                # ensure form-select class present (don't clobber existing classes)
                existing_cls = wattrs.get("class", "")
                cls_parts = existing_cls.split()
                if "form-select" not in cls_parts:
                    cls_parts.append("form-select")
                wattrs["class"] = " ".join([p for p in cls_parts if p.strip() != ""]).strip()
                # aria-label for accessibility and JS clarity
                wattrs.setdefault("aria-label", "Quality select")
        except Exception:
            logger.exception("Failed to ensure quality widget attributes in ComponentMasterForm.__init__")

        # ---------------------------
        # Colors: expose for template/JS
        # ---------------------------
        try:
            # default empty values
            self.colors_qs = []
            self.colors_json = "[]"
            # if this is an existing ComponentMaster instance, load its colors
            if self.instance and getattr(self.instance, "pk", None):
                try:
                    qs = Color.objects.filter(component_master=self.instance)
                    # return active colors first by default
                    active_qs = qs.filter(is_active=True).order_by("name")
                    self.colors_qs = active_qs
                    # prepare simple JSON array for client consumption
                    items = []
                    for c in active_qs:
                        items.append({"id": getattr(c, "id", None), "name": getattr(c, "name", ""), "is_active": getattr(c, "is_active", True)})
                    self.colors_json = json.dumps(items)
                except Exception:
                    # fallback: try to access reverse relation if Color class not imported correctly
                    try:
                        rev_qs = getattr(self.instance, "colors", None)
                        if rev_qs is not None:
                            active_qs = rev_qs.filter(is_active=True).order_by("name")
                            self.colors_qs = active_qs
                            items = [{"id": getattr(c, "id", None), "name": getattr(c, "name", ""), "is_active": getattr(c, "is_active", True)} for c in active_qs]
                            self.colors_json = json.dumps(items)
                    except Exception:
                        self.colors_qs = []
                        self.colors_json = "[]"
        except Exception:
            logger.exception("Failed to prepare colors data on ComponentMasterForm")
            self.colors_qs = []
            self.colors_json = "[]"

    def _resolve_inventory_instance(self, ct_value, obj_value):
        """
        Resolve content type and object id into a model instance.
        Returns (content_type_instance, model_instance)
        Raises forms.ValidationError on failure.
        """
        if ct_value in ("", None):
            raise forms.ValidationError(_("Missing inventory content type."))
        if obj_value in ("", None):
            raise forms.ValidationError(_("Missing inventory object id."))

        # Normalize to ContentType instance
        if isinstance(ct_value, ContentType):
            content_type = ct_value
        else:
            try:
                ct_pk = _extract_int(ct_value)
            except ValueError:
                logger.debug("ComponentMasterForm._resolve_inventory_instance: invalid ct %r", ct_value)
                raise forms.ValidationError(_("Invalid inventory item selected (content type)."))
            try:
                content_type = ContentType.objects.get(pk=ct_pk)
            except ContentType.DoesNotExist:
                logger.debug("ComponentMasterForm._resolve_inventory_instance: ContentType %s not found", ct_pk)
                raise forms.ValidationError(_("Invalid inventory item selected (content type)."))

        model_class = content_type.model_class()
        if model_class is None:
            logger.debug("ComponentMasterForm._resolve_inventory_instance: content type has no model_class() %r", content_type)
            raise forms.ValidationError(_("Invalid inventory item selected."))

        try:
            obj_pk = _extract_int(obj_value)
        except ValueError:
            logger.debug("ComponentMasterForm._resolve_inventory_instance: invalid obj id %r", obj_value)
            raise forms.ValidationError(_("Invalid inventory item selected (object id)."))

        try:
            instance = model_class.objects.get(pk=obj_pk)
        except model_class.DoesNotExist:
            logger.debug("ComponentMasterForm._resolve_inventory_instance: object %s (ct=%s) not found", obj_pk, content_type)
            raise forms.ValidationError(_("Selected inventory item does not exist."))

        return content_type, instance

    def _compute_price_per_sqfoot(self, width_value: Decimal, width_uom: str, final_price_per_unit: Decimal) -> Decimal:
        """
        Compute price per sqft using:
            price_per_sqfoot = final_price_per_unit / (((width_in_inch * 2.54) / 1.07) / 100)
        width_value assumed numeric; width_uom informs conversion (if 'cm' convert -> inches).
        Returns Decimal quantized to 4 decimal places.
        """
        try:
            if width_value is None:
                return Decimal("0.0000")
            width = Decimal(width_value)
        except (InvalidOperation, TypeError):
            return Decimal("0.0000")

        uom = (width_uom or "").strip().lower()
        width_in_inch = width
        try:
            if uom in ("cm", "centimeter", "centimetre", "cms"):
                # convert cm to inches
                width_in_inch = (width / Decimal("2.54"))
        except Exception:
            width_in_inch = width

        try:
            if width_in_inch == Decimal("0") or final_price_per_unit == Decimal("0"):
                return Decimal("0.0000")
            numer = Decimal(final_price_per_unit)
            denom = ((Decimal(width_in_inch) * Decimal("2.54")) / Decimal("1.07")) / Decimal("100")
            if denom == Decimal("0"):
                return Decimal("0.0000")
            ppsf = numer / denom
            return ppsf.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        except Exception:
            return Decimal("0.0000")

    def clean_logistics_percent(self):
        lp = self.cleaned_data.get("logistics_percent")
        if lp in (None, ""):
            return Decimal("0.00")
        try:
            dec = Decimal(lp)
        except (InvalidOperation, TypeError):
            raise forms.ValidationError(_("Logistics percent must be a valid number."))
        if dec < 0 or dec > 100:
            raise forms.ValidationError(_("Logistics percent must be between 0 and 100."))
        return dec

    def clean(self):
        """
        Validate inventory linking and compute derived fields that the form should display.
        Also normalizes/validates the 'quality' input so downstream logic gets a string or None.
        """
        cleaned = super().clean()

        category = cleaned.get("inventory_category")
        ct_value = cleaned.get("inventory_content_type")
        obj_value = cleaned.get("inventory_object_id")
        # Normalize quality early so fetchers get a consistent string or None
        try:
            quality_raw = cleaned.get("quality")
            quality = _normalize_or_validate_quality(quality_raw, allow_blank=True)
        except forms.ValidationError as ve:
            # re-raise as form-level validation error for the 'quality' field
            self.add_error("quality", ve)
            # return early so we don't proceed with inventory-dependent work
            return cleaned

        logistics_percent = cleaned.get("logistics_percent") or Decimal("0.00")

        # If inventory category selected, resolve instance and compute derived values
        if category and category != ComponentMaster.InventoryCategory.NONE:
            if not ct_value or not obj_value:
                raise forms.ValidationError(_("Select an inventory item for the chosen category."))

            # Resolve inventory instance (raises ValidationError on bad input)
            content_type, inventory_instance = self._resolve_inventory_instance(ct_value, obj_value)

            # Build temp ComponentMaster to use model helpers for fetching
            temp_cm = ComponentMaster(
                inventory_content_type=content_type,
                inventory_object_id=getattr(inventory_instance, "pk", None),
                quality=quality,
                size=Decimal("1.00"),
                logistics_percent=logistics_percent,
            )

            # Fetch unit cost
            try:
                unit_cost = temp_cm._fetch_cost_from_inventory()
                unit_cost = Decimal(unit_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except Exception as e:
                logger.exception("Error fetching cost from inventory: %s", e)
                raise forms.ValidationError(_("Could not determine cost for selected inventory item."))

            # Fetch width + uom
            try:
                fetched_width, fetched_uom = temp_cm._fetch_width_from_inventory()
                fetched_width = Decimal(fetched_width).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                fetched_uom = fetched_uom or "inch"
            except Exception as e:
                logger.exception("Error fetching width from inventory: %s", e)
                fetched_width, fetched_uom = Decimal("0.00"), "inch"

            # Get type from inventory instance if possible (server-side probe)
            fetched_type = ""
            try:
                for attr in ("fabric_type", "product_type", "type", "material_type", "variant_type"):
                    val = getattr(inventory_instance, attr, None)
                    if val not in (None, ""):
                        fetched_type = str(val)
                        break
            except Exception:
                fetched_type = ""

            # Compute final_price_per_unit
            try:
                multiplier = (Decimal("1.00") + (Decimal(logistics_percent) / Decimal("100.00")))
                final_price_per_unit = (unit_cost * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except Exception as e:
                logger.exception("Error computing final_price_per_unit: %s", e)
                final_price_per_unit = Decimal("0.00")

            # Compute final_cost (size default 1.00)
            try:
                final_cost = (final_price_per_unit * Decimal("1.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except Exception:
                final_cost = Decimal("0.00")

            # Compute price per sqft
            price_per_sqfoot = self._compute_price_per_sqfoot(fetched_width, fetched_uom, final_price_per_unit)

            # Place resolved/derived values into cleaned_data for template/view/save use
            cleaned["inventory_content_type"] = content_type
            cleaned["inventory_object_id"] = int(getattr(inventory_instance, "pk", inventory_instance))
            cleaned["cost_per_unit"] = unit_cost
            cleaned["width"] = fetched_width
            cleaned["width_uom"] = fetched_uom

            # Prefer client-submitted 'type' (e.g., populated from AJAX / inventory_item_json)
            # but fall back to server-probed fetched_type when client did not provide a value.
            submitted_type = cleaned.get("type")
            submitted_type = (str(submitted_type).strip() if submitted_type not in (None, "") else "")
            if submitted_type:
                cleaned["type"] = submitted_type
            else:
                cleaned["type"] = (fetched_type or "")

            cleaned["final_price_per_unit"] = final_price_per_unit
            cleaned["final_cost"] = final_cost
            cleaned["price_per_sqfoot"] = price_per_sqfoot

            # Put normalized quality back into cleaned_data so save() persists it
            cleaned["quality"] = quality

            # set name auto-generation into cleaned_data (optional - model.save will ensure too)
            q = (quality or "").strip()
            t = (cleaned.get("type") or "").strip()
            if q and t:
                cleaned["name"] = f"{q} {t}"
            elif q:
                cleaned["name"] = q
            elif t:
                cleaned["name"] = t
            else:
                cleaned["name"] = None

        else:
            # No inventory item chosen; clear hidden fields and zero derived numbers
            cleaned["inventory_content_type"] = None
            cleaned["inventory_object_id"] = None
            cleaned["cost_per_unit"] = Decimal("0.00")
            cleaned["width"] = Decimal("0.00")
            cleaned["width_uom"] = "inch"
            cleaned["type"] = ""
            cleaned["final_price_per_unit"] = Decimal("0.00")
            cleaned["final_cost"] = Decimal("0.00")
            cleaned["price_per_sqfoot"] = Decimal("0.0000")
            cleaned["name"] = None
            # ensure blank quality normalized to None
            cleaned["quality"] = None

        return cleaned

    def save(self, commit=True):
        """
        Ensure authoritative computed numeric values and 'name' are assigned to the instance
        before saving.
        """
        instance = super().save(commit=False)
        cd = getattr(self, "cleaned_data", {})

        # Assign computed values if present
        if "cost_per_unit" in cd:
            instance.cost_per_unit = cd.get("cost_per_unit") or Decimal("0.00")
        if "width" in cd:
            instance.width = cd.get("width") or Decimal("0.00")
        if "width_uom" in cd:
            instance.width_uom = cd.get("width_uom") or "inch"
        if "final_price_per_unit" in cd:
            instance.final_price_per_unit = cd.get("final_price_per_unit") or Decimal("0.00")
        if "price_per_sqfoot" in cd:
            instance.price_per_sqfoot = cd.get("price_per_sqfoot") or Decimal("0.0000")
        if "final_cost" in cd:
            instance.final_cost = cd.get("final_cost") or Decimal("0.00")
        if "type" in cd:
            instance.type = cd.get("type") or ""

        # Ensure defaults
        if instance.size in (None, ""):
            instance.size = Decimal("1.00")
        if instance.logistics_percent in (None, ""):
            instance.logistics_percent = Decimal("0.00")

        # Accept normalized quality string (or None) from cleaned_data
        if "quality" in cd:
            instance.quality = cd.get("quality")

        # If form provided a name (via hidden input & JS), prefer it; otherwise auto-generate
        provided_name = (cd.get("name") if isinstance(cd.get("name"), str) else None)
        if provided_name and str(provided_name).strip():
            instance.name = provided_name.strip()
        else:
            # Auto-generate name if not supplied
            if not (instance.name and str(instance.name).strip()):
                q = (str(instance.quality) if instance.quality is not None else "").strip()
                t = (str(instance.type) if instance.type is not None else "").strip()
                instance.name = (f"{q} {t}".strip() or instance.name or "")

        if commit:
            instance.save()
        return instance
