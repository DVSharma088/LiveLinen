from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, getcontext
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.validators import MinValueValidator, MaxValueValidator

# increase precision a bit for intermediate calculations
getcontext().prec = 28


class CostComponent(models.Model):
    """
    Original CostComponent model (kept for backward compatibility).
    Represents a single cost element that can be a percentage or fixed amount
    and optionally linked to an inventory item.
    """
    class ValueType(models.TextChoices):
        PERCENTAGE = "P", _("Percentage")
        FIXED = "F", _("Fixed Amount")

    class InventoryCategory(models.TextChoices):
        NONE = "NONE", _("None")
        FABRIC = "FABRIC", _("Fabric")
        ACCESSORY = "ACCESSORY", _("Accessory")
        PRINTED = "PRINTED", _("Printed")

    name = models.CharField(max_length=150, unique=True)
    value_type = models.CharField(
        max_length=1,
        choices=ValueType.choices,
        default=ValueType.PERCENTAGE
    )
    value = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    # --- Inventory linking fields (generic) ---
    inventory_category = models.CharField(
        max_length=20,
        choices=InventoryCategory.choices,
        default=InventoryCategory.NONE,
        help_text=_("Choose the inventory category first (Fabric / Accessory / Printed)."),
    )
    inventory_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="components_inventory_ct"
    )
    inventory_object_id = models.PositiveIntegerField(null=True, blank=True)
    inventory_item = GenericForeignKey("inventory_content_type", "inventory_object_id")
    # -------------------------------

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "name"]
        verbose_name = "Cost Component"
        verbose_name_plural = "Cost Components"

    def __str__(self):
        base = ""
        if self.value_type == self.ValueType.PERCENTAGE:
            base = f"{self.name} ({self.value}%)"
        else:
            base = f"{self.name} (₹{self.value})"

        if self.inventory_item:
            try:
                return f"{base} — {self.get_inventory_display()}"
            except Exception:
                return base
        return base

    def display_value(self):
        if self.value_type == self.ValueType.PERCENTAGE:
            return f"{self.value}%"
        return f"₹{self.value}"

    def apply_to_base(self, base_cost: Decimal) -> Decimal:
        if not self.is_active:
            return Decimal("0.00")

        if self.value_type == self.ValueType.PERCENTAGE:
            return (base_cost * (self.value / Decimal("100"))).quantize(Decimal("0.01"))
        else:  # FIXED
            return Decimal(self.value).quantize(Decimal("0.01"))

    def set_inventory_item(self, instance):
        if instance is None:
            self.inventory_content_type = None
            self.inventory_object_id = None
            self.inventory_category = self.InventoryCategory.NONE
            return

        self.inventory_content_type = ContentType.objects.get_for_model(instance.__class__)
        self.inventory_object_id = instance.pk

        model_name = instance.__class__.__name__.lower()
        if "fabric" in model_name:
            self.inventory_category = self.InventoryCategory.FABRIC
        elif "printed" in model_name:
            self.inventory_category = self.InventoryCategory.PRINTED
        else:
            self.inventory_category = self.InventoryCategory.ACCESSORY

    def get_inventory_display(self):
        if not self.inventory_item:
            return ""

        model_verbose = getattr(self.inventory_item._meta, "verbose_name", self.inventory_item.__class__.__name__)
        return f"{model_verbose.title()}: {str(self.inventory_item)}"


class ComponentMaster(models.Model):
    class InventoryCategory(models.TextChoices):
        NONE = "NONE", _("None")
        FABRIC = "FABRIC", _("Fabric")
        ACCESSORY = "ACCESSORY", _("Accessory")
        PRINTED = "PRINTED", _("Printed")

    # Basic metadata
    name = models.CharField(max_length=200, help_text=_("Optional display name for this component"), blank=True)
    inventory_category = models.CharField(
        max_length=20,
        choices=InventoryCategory.choices,
        default=InventoryCategory.NONE,
        help_text=_("Select the inventory category (Fabric / Accessory / Printed)"),
    )

    # Generic relation to the specific inventory item instance
    inventory_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="component_master_inventory_ct"
    )
    inventory_object_id = models.PositiveIntegerField(null=True, blank=True)
    inventory_item = GenericForeignKey("inventory_content_type", "inventory_object_id")

    # Quality (string to keep it flexible — you can switch to a FK if you have a Quality model)
    quality = models.CharField(max_length=150, blank=True, null=True, help_text=_("Quality / variant of the selected product"))

    # store inventory-derived product type (optional)
    type = models.CharField(max_length=150, blank=True, null=True, help_text=_("Type of the product as fetched from inventory (e.g., 'Solid', 'Printed')"))

    # Size (numeric: units depend on your business; integer or decimal)
    size = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Numeric size / quantity for which the cost will be applied")
    )

    # Costs and logistics
    # cost_per_unit: fetched from inventory (server-calculated), previous behavior preserved
    cost_per_unit = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text=_("Auto-filled cost per unit fetched from inventory (server-calculated).")
    )

    # width and unit (fetched from inventory when available)
    width = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00"),
        help_text=_("Width of the product fetched from inventory (assumed in inches unless width_uom set).")
    )
    width_uom = models.CharField(
        max_length=20, default="inch", blank=True,
        help_text=_("Unit of measure for width (e.g., 'inch', 'cm'). Default is 'inch'.")
    )

    # logistics percentage (user input)
    logistics_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
        help_text=_("Percentage to add on top of base cost (e.g., 10 for 10%).")
    )

    # final price per unit (price fetched from inventory + logistics)
    final_price_per_unit = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"),
        help_text=_("Final price per unit after adding logistics percent (auto-calculated).")
    )

    # final_cost preserves previous meaning: final_price_per_unit * size
    final_cost = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0.00"),
        help_text=_("Final cost after adding logistics percent and multiplying by size. (auto-calculated)")
    )

    # price per square foot as per your formula
    price_per_sqfoot = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal("0.0000"),
        help_text=_("Computed price per square foot using width and the formula provided.")
    )

    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "name"]
        verbose_name = "Component Master"
        verbose_name_plural = "Component Masters"

    def __str__(self):
        """
        Display priority (preferred):
          1. quality + type (prefer fields on this model; fall back to inventory_item attributes)
          2. quality alone
          3. type alone
          4. explicit stored name (if provided)
          5. inventory_item string
          6. "Component" as a final fallback
        """
        # 1) get quality: prefer self.quality, else try inventory_item.quality
        q = (str(self.quality) if self.quality is not None else "").strip()
        if not q and self.inventory_item:
            q = str(getattr(self.inventory_item, "quality", "") or "").strip()

        # 2) get type: prefer self.type, else probe common attrs on inventory_item
        t = (str(self.type) if self.type is not None else "").strip()
        if not t and self.inventory_item:
            for attr in ("fabric_type", "product_type", "type", "material_type", "variant_type"):
                val = getattr(self.inventory_item, attr, None)
                if val not in (None, ""):
                    t = str(val).strip()
                    break

        # 3) build display name preferring quality+type
        if q and t:
            display_name = f"{q} {t}"
        elif q:
            display_name = q
        elif t:
            display_name = t
        else:
            # 4) fall back to explicit stored name if present
            if self.name and str(self.name).strip():
                display_name = str(self.name)
            # 5) then fall back to inventory item string
            elif self.inventory_item:
                display_name = str(self.inventory_item)
            else:
                display_name = "Component"

        return display_name

    # ------------------------------
    # Cost & width fetching helpers
    # ------------------------------
    def _fetch_cost_from_inventory(self) -> Decimal:
        """
        Try multiple strategies to fetch a price/cost from the linked inventory item.
        This preserves the flexible approach you had previously.
        """
        if not self.inventory_item:
            return Decimal("0.00")

        item = self.inventory_item
        q = (str(self.quality) if self.quality is not None else "")

        # 1) Methods that accept quality or not
        for method_name in ("get_cost", "get_price", "get_cost_for_quality", "cost_for_quality"):
            method = getattr(item, method_name, None)
            if callable(method):
                try:
                    if q:
                        val = method(quality=q)
                    else:
                        val = method()
                    if val is not None:
                        return Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                except TypeError:
                    # method doesn't accept quality
                    try:
                        val = method()
                        if val is not None:
                            return Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    except Exception:
                        pass
                except Exception:
                    pass

        # 2) Direct attributes
        for attr in ("cost_per_unit", "price", "cost", "base_price"):
            val = getattr(item, attr, None)
            if val is not None:
                try:
                    return Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                except (InvalidOperation, TypeError):
                    pass

        # 3) Dict / mapping style (e.g., item.costs = {"A": 100, "B": 120})
        costs = getattr(item, "costs", None)
        if isinstance(costs, dict) and q:
            try:
                val = costs.get(q) or costs.get(q.lower()) or costs.get(q.upper())
                if val is not None:
                    return Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except Exception:
                pass

        # 4) Related quality objects, if present (e.g., item.qualities)
        try:
            quals = getattr(item, "qualities", None)
            if hasattr(quals, "filter") and q:
                q_obj = quals.filter(name__iexact=q).first()
                if q_obj:
                    for a in ("price", "cost_per_unit", "cost"):
                        v = getattr(q_obj, a, None)
                        if v is not None:
                            return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            pass

        return Decimal("0.00")

    def _fetch_width_from_inventory(self):
        """
        Try to fetch width and its unit of measure from the inventory item. Return
        (width_decimal, width_uom_string). If unavailable, returns (Decimal('0.00'), 'inch').
        Tries similar flexible strategies as cost fetcher.
        """
        default_uom = "inch"
        if not self.inventory_item:
            return Decimal("0.00"), default_uom

        item = self.inventory_item
        q = (str(self.quality) if self.quality is not None else "")

        # 1) Methods that may return width
        for method_name in ("get_width", "width_for_quality", "get_width_for_quality"):
            method = getattr(item, method_name, None)
            if callable(method):
                try:
                    if q:
                        val = method(quality=q)
                    else:
                        val = method()
                    if val is not None:
                        # method might return tuple (width, uom) or single numeric
                        if isinstance(val, (list, tuple)) and len(val) >= 1:
                            w = Decimal(val[0])
                            uom = val[1] if len(val) > 1 else default_uom
                            return w.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), str(uom)
                        else:
                            return Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), default_uom
                except Exception:
                    pass

        # 2) Direct attributes
        for attr in ("width", "g_width", "fabric_width", "w"):
            val = getattr(item, attr, None)
            if val is not None:
                try:
                    return Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), default_uom
                except Exception:
                    pass

        # 3) Quality-specific related objects
        try:
            quals = getattr(item, "qualities", None)
            if hasattr(quals, "filter") and q:
                q_obj = quals.filter(name__iexact=q).first()
                if q_obj:
                    for a in ("width", "fabric_width"):
                        v = getattr(q_obj, a, None)
                        if v is not None:
                            try:
                                return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), default_uom
                            except Exception:
                                pass
        except Exception:
            pass

        return Decimal("0.00"), default_uom

    # ------------------------------
    # Computation methods
    # ------------------------------
    def compute_final_costs_and_metrics(self):
        """
        Central method to compute:
         - cost_per_unit (base price from inventory, previous semantics)
         - final_price_per_unit = cost_per_unit + (logistics% * cost_per_unit)
         - final_cost = final_price_per_unit * size
         - price_per_sqfoot using your formula:
             price_per_sqfoot = final_price_per_unit / (((width_in_inch * 2.54) / 1.07) / 100)
        Note: width conversion assumed inches by default; width_uom preserved.
        """
        # fetch unit cost and width from inventory
        try:
            unit_cost = self._fetch_cost_from_inventory()
        except Exception:
            unit_cost = Decimal("0.00")

        # Ensure decimals and rounding
        try:
            unit_cost = Decimal(unit_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            unit_cost = Decimal("0.00")

        self.cost_per_unit = unit_cost

        # Fetch width and unit
        try:
            fetched_width, fetched_uom = self._fetch_width_from_inventory()
        except Exception:
            fetched_width, fetched_uom = Decimal("0.00"), "inch"

        try:
            fetched_width = Decimal(fetched_width).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            fetched_width = Decimal("0.00")

        self.width = fetched_width
        self.width_uom = fetched_uom or "inch"

        # compute final price per unit (price + logistics%)
        try:
            multiplier = (Decimal("1.00") + (Decimal(self.logistics_percent) / Decimal("100.00")))
        except Exception:
            multiplier = Decimal("1.00")

        raw_final_price_per_unit = (unit_cost * multiplier)
        try:
            final_price_per_unit = Decimal(raw_final_price_per_unit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            final_price_per_unit = Decimal("0.00")

        self.final_price_per_unit = final_price_per_unit

        # final cost (multiply by size) - maintain previous behavior
        try:
            raw_final_cost = final_price_per_unit * (Decimal(self.size) if self.size else Decimal("1.00"))
            self.final_cost = Decimal(raw_final_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            self.final_cost = Decimal("0.00")

        # compute price per sq foot using provided formula:
        # price_per_sqfoot = final_price_per_unit / (((width_in_inch * 2.54) / 1.07) / 100)
        # Ensure width is in inches. If width_uom is 'cm', convert to inches.
        try:
            width_in_inch = self.width
            if self.width_uom and self.width_uom.lower() in ("cm", "centimeter", "centimetre", "cms"):
                # convert cm to inches
                width_in_inch = (Decimal(self.width) / Decimal("2.54"))
            # If width_uom is something else and not 'inch', we assume width is already in inches as a fallback.

            # denom = (((width_in_inch * 2.54) / 1.07) / 100)
            # careful with decimal arithmetic
            if width_in_inch and width_in_inch != Decimal("0.00"):
                numer = Decimal(self.final_price_per_unit)
                denom = ((Decimal(width_in_inch) * Decimal("2.54")) / Decimal("1.07")) / Decimal("100")
                if denom == Decimal("0"):
                    self.price_per_sqfoot = Decimal("0.0000")
                else:
                    ppsf = (numer / denom)
                    # set a reasonable precision for price per sqft (4 decimal places)
                    self.price_per_sqfoot = ppsf.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            else:
                self.price_per_sqfoot = Decimal("0.0000")
        except Exception:
            self.price_per_sqfoot = Decimal("0.0000")

    def save(self, *args, **kwargs):
        # ensure defaults
        if self.size in (None, ""):
            self.size = Decimal("1.00")
        if self.logistics_percent in (None, ""):
            self.logistics_percent = Decimal("0.00")

        # If there is an inventory item available, try to extract its 'type' and fill into self.type
        try:
            if self.inventory_item:
                # attempt common attribute names for 'type' on inventory items
                for attr in ("fabric_type", "product_type", "type", "material_type", "variant_type"):
                    val = getattr(self.inventory_item, attr, None)
                    if val not in (None, ""):
                        # only set if not already set explicitly
                        if not self.type:
                            self.type = str(val)
                        break
        except Exception:
            # ignore failure to probe inventory_item
            pass

        try:
            self.compute_final_costs_and_metrics()
        except Exception:
            # safe fallbacks
            try:
                self.cost_per_unit = Decimal(self.cost_per_unit or "0.00")
            except Exception:
                self.cost_per_unit = Decimal("0.00")
            try:
                self.final_price_per_unit = Decimal(self.final_price_per_unit or "0.00")
            except Exception:
                self.final_price_per_unit = Decimal("0.00")
            try:
                self.final_cost = Decimal(self.final_cost or "0.00")
            except Exception:
                self.final_cost = Decimal("0.00")
            self.price_per_sqfoot = Decimal("0.0000")

        # Auto-generate name if name not provided: prefer "quality + type"
        try:
            if not (self.name and str(self.name).strip()):
                q = (str(self.quality) if self.quality is not None else "").strip()
                t = (str(self.type) if self.type is not None else "").strip()
                if q and t:
                    self.name = f"{q} {t}"
                elif q:
                    self.name = q
                elif t:
                    self.name = t
                else:
                    # leave name empty; __str__ will fallback to inventory_item
                    self.name = self.name or ""
        except Exception:
            # fail silently on name generation
            pass

        super().save(*args, **kwargs)

    def set_inventory_item(self, instance):
        """
        Link a model instance as inventory_item via generic foreign key,
        and set the inventory_category field appropriately (fabric/printed/accessory).
        """
        if instance is None:
            self.inventory_content_type = None
            self.inventory_object_id = None
            self.inventory_category = self.InventoryCategory.NONE
            return
        self.inventory_content_type = ContentType.objects.get_for_model(instance.__class__)
        self.inventory_object_id = instance.pk
        model_name = instance.__class__.__name__.lower()
        if "fabric" in model_name:
            self.inventory_category = self.InventoryCategory.FABRIC
        elif "printed" in model_name:
            self.inventory_category = self.InventoryCategory.PRINTED
        else:
            self.inventory_category = self.InventoryCategory.ACCESSORY
