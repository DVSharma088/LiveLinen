from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator

from vendors.models import Vendor

UNIT_CHOICES = [
    ('m', 'Meters'),
    ('cm', 'Centimeters'),
    ('ft', 'Feet'),
]


class Fabric(models.Model):
    """
    Fabric model updated:
      - 'quality' is a CharField (can contain 'A1', 'Fine', '350', etc).
      - 'type' is mapped to DB column 'fabric_type'.
    """
    item_name = models.CharField(max_length=200)
    # quality as CharField to allow alphanumeric/textual values
    quality = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name="Quality",
        help_text='Quality can be numeric (0 - 100) or textual (e.g., "A1", "Fine").'
    )
    base_color = models.CharField(max_length=100, blank=True, null=True)
    # Use 'type' as the python attribute / field name but store in DB column 'fabric_type'
    type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Type",
        db_column='fabric_type',
        help_text='Type/category of fabric (e.g., cotton, linen)'
    )
    fabric_width = models.DecimalField(max_digits=7, decimal_places=2, help_text='Width (e.g., 1.20)')
    use_in = models.CharField(max_length=200, blank=True, null=True, help_text='Intended use (e.g., shirts, upholstery)')
    stock_in_mtrs = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text='Current stock in meters'
    )
    cost_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Cost per unit (per meter)'
    )
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='fabrics')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.item_name} ({self.vendor.vendor_name})"

    @property
    def quality_display(self):
        """
        Preferred textual representation of quality:
        - If a textual override exists (quality_text) prefer it (not present on Fabric by default).
        - Otherwise return the quality field (string, possibly numeric string).
        """
        return getattr(self, "quality_text", None) or self.quality

    def get_quality_display(self):
        return self.quality_display

    @property
    def unit_cost(self):
        return self.cost_per_unit or Decimal('0.00')

    def reduce_stock(self, quantity):
        if quantity is None:
            raise ValidationError(_("Quantity to reduce cannot be None."))
        try:
            qty = Decimal(quantity)
        except Exception:
            raise ValidationError(_("Invalid quantity value."))
        if qty <= 0:
            raise ValidationError(_("Quantity to reduce must be greater than zero."))
        if self.stock_in_mtrs < qty:
            raise ValidationError(_("Insufficient stock for %(name)s: required %(req)s, available %(avail)s") % {
                'name': self.item_name, 'req': qty, 'avail': self.stock_in_mtrs
            })
        self.stock_in_mtrs = self.stock_in_mtrs - qty
        return self.stock_in_mtrs

    def increment_stock(self, quantity):
        if quantity is None:
            raise ValidationError(_("Quantity to increase cannot be None."))
        try:
            qty = Decimal(quantity)
        except Exception:
            raise ValidationError(_("Invalid quantity value."))
        if qty <= 0:
            raise ValidationError(_("Quantity to increase must be greater than zero."))
        self.stock_in_mtrs = self.stock_in_mtrs + qty
        return self.stock_in_mtrs


class Accessory(models.Model):
    """
    Accessory model:
    - 'quality' is a CharField to allow text or numeric strings.
    - 'quality_text' is a separate persistent field used to store explicit textual quality values
      (e.g., "wooden"). This is populated by forms when user enters non-numeric quality.
    """
    item_name = models.CharField(max_length=200)
    quality = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name="Quality",
        help_text='Quality can be numeric (0 - 100) or textual (e.g., "A1", "Fine").'
    )
    # persistent textual quality (optional) — used to store freeform strings like "wooden"
    quality_text = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        verbose_name="Quality (text)",
        help_text='Optional textual quality/variant (e.g., "wooden").'
    )
    base_color = models.CharField(max_length=100, blank=True, null=True)
    item_type = models.CharField(max_length=100, blank=True, null=True, help_text='Type/category of accessory')
    width = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True, help_text='Width if applicable')
    use_in = models.CharField(max_length=200, blank=True, null=True, help_text='Where this accessory is used (e.g., cushion, bedsheet)')
    stock = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text='Current stock in units (or meters if applicable)'
    )
    cost_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Cost per unit'
    )
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='accessories')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        """
        Human-friendly string representation. Prefer showing an explicit textual quality
        (quality_text) when available so ModelChoiceField / admin displays are readable.
        Examples:
            "Button — Plastic (Print Wala)"
            "Button (Print Wala)"
        """
        q = self.quality_display or ""
        if q:
            return f"{self.item_name} — {q} ({self.vendor.vendor_name})"
        return f"{self.item_name} ({self.vendor.vendor_name})"

    @property
    def quality_display(self):
        """
        Return persistent textual quality if set, otherwise fall back to the general 'quality' field.
        """
        # prefer explicit textual quality field if present
        if self.quality_text and str(self.quality_text).strip() != "":
            return str(self.quality_text).strip()
        # fallback to quality (which is a CharField in this design)
        return self.quality

    def get_quality_display(self):
        return self.quality_display

    @property
    def unit_cost(self):
        """Standardized accessor used elsewhere."""
        return self.cost_per_unit or Decimal('0.00')

    def reduce_stock(self, quantity):
        if quantity is None:
            raise ValidationError(_("Quantity to reduce cannot be None."))
        try:
            qty = Decimal(quantity)
        except Exception:
            raise ValidationError(_("Invalid quantity value."))
        if qty <= 0:
            raise ValidationError(_("Quantity to reduce must be greater than zero."))
        if self.stock < qty:
            raise ValidationError(_("Insufficient accessory stock for %(name)s: required %(req)s, available %(avail)s") % {
                'name': self.item_name, 'req': qty, 'avail': self.stock
            })
        self.stock = self.stock - qty
        return self.stock

    def increment_stock(self, quantity):
        if quantity is None:
            raise ValidationError(_("Quantity to increase cannot be None."))
        try:
            qty = Decimal(quantity)
        except Exception:
            raise ValidationError(_("Invalid quantity value."))
        if qty <= 0:
            raise ValidationError(_("Quantity to increase must be greater than zero."))
        self.stock = self.stock + qty
        return self.stock


class Printed(models.Model):
    """
    Printed product produced from a Fabric.
    - 'quality' is a CharField that inherits fabric.quality if not provided.
    - If 'quality' is numeric (string that can be parsed to Decimal), the value is validated to be between 0 and 100.
    """
    product = models.CharField(max_length=200)
    fabric = models.ForeignKey(Fabric, on_delete=models.PROTECT, related_name='printeds')

    # Fabric-like metadata (optional; will be copied from Fabric if not provided)
    base_color = models.CharField(max_length=100, blank=True, null=True)
    product_type = models.CharField(max_length=100, blank=True, null=True, help_text='Type/category of printed product')
    width = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True, help_text='Width if applicable')
    use_in = models.CharField(max_length=200, blank=True, null=True, help_text='Intended use (e.g., shirts)')
    # QUALITY field as CharField
    quality = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name="Quality",
        help_text='Quality can be numeric (0 - 100) or textual (e.g., "A1"). Inherited from Fabric if left blank.'
    )
    # stock for printed product in chosen unit
    unit = models.CharField(max_length=5, choices=UNIT_CHOICES, default='m')
    quantity_used = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0.000'),
        help_text='Quantity of fabric consumed (in chosen unit)'
    )
    stock = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal('0.000'),
                                help_text='Current stock of printed product in chosen unit')
    # cost for printed product (if specified); otherwise derived from fabric.cost_per_unit
    cost_per_unit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
                                        help_text='Cost per unit for printed product (falls back to fabric cost if zero)')
    # keep existing 'rate' field for backward compatibility with code that uses `rate`
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'),
                               help_text='Rate (per unit) if needed')
    # vendor can either be provided or inherited from Fabric.vendor
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='printeds', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product} from {self.fabric.item_name}"

    def _quality_is_numeric_and_decimal(self, q):
        """
        Return a Decimal if q is a numeric string / number; otherwise return None.
        """
        if q is None:
            return None
        # If it's already a Decimal, return it
        if isinstance(q, Decimal):
            return q
        # Try to parse string
        try:
            # Allow strings like '12', '12.34'
            qd = Decimal(str(q).strip())
            return qd
        except (InvalidOperation, TypeError, ValueError):
            return None

    @property
    def quality_display(self):
        """
        Prefer persistent textual field 'quality_text' if present on instance (not present by default).
        Fall back to 'quality' (string).
        """
        return getattr(self, "quality_text", None) or self.quality

    def get_quality_display(self):
        return self.quality_display

    def clean(self):
        if self.quantity_used is None or self.quantity_used <= 0:
            raise ValidationError({'quantity_used': 'Quantity used must be greater than zero.'})
        if self.stock is None or self.stock < 0:
            raise ValidationError({'stock': 'Stock cannot be negative.'})
        if self.width is not None and self.width < 0:
            raise ValidationError({'width': 'Width cannot be negative.'})
        if self.cost_per_unit is not None and self.cost_per_unit < 0:
            raise ValidationError({'cost_per_unit': 'Cost per unit cannot be negative.'})

        # If quality can be parsed to Decimal, enforce 0.00 - 100.00 range
        q_decimal = self._quality_is_numeric_and_decimal(self.quality)
        if q_decimal is not None:
            if q_decimal < Decimal('0.00') or q_decimal > Decimal('100.00'):
                raise ValidationError({'quality': 'Quality must be between 0.00 and 100.00 when numeric.'})

    @property
    def unit_cost(self):
        # Prefer explicit rate if present, then explicit cost_per_unit, then fabric cost.
        if self.rate and self.rate > 0:
            return self.rate
        if self.cost_per_unit and self.cost_per_unit > 0:
            return self.cost_per_unit
        return getattr(self.fabric, 'cost_per_unit', Decimal('0.00'))

    def reduce_fabric_stock(self):
        if self.quantity_used is None:
            raise ValidationError("quantity_used cannot be None.")
        return self.fabric.reduce_stock(self.quantity_used)

    def reduce_stock(self, quantity):
        if quantity is None:
            raise ValidationError("Quantity to reduce cannot be None.")
        try:
            qty = Decimal(quantity)
        except Exception:
            raise ValidationError("Invalid quantity value.")
        if qty <= 0:
            raise ValidationError("Quantity to reduce must be greater than zero.")
        if self.stock < qty:
            raise ValidationError(f"Insufficient printed stock for {self.product}: required {qty}, available {self.stock}")
        self.stock = self.stock - qty
        return self.stock

    def increment_stock(self, quantity):
        if quantity is None:
            raise ValidationError("Quantity to increase cannot be None.")
        try:
            qty = Decimal(quantity)
        except Exception:
            raise ValidationError("Invalid quantity value.")
        if qty <= 0:
            raise ValidationError("Quantity to increase must be greater than zero.")
        self.stock = self.stock + qty
        return self.stock

    def save(self, *args, **kwargs):
        creating = self._state.adding
        # Before validation, ensure fields inherit from fabric if empty.
        # We don't overwrite explicitly-provided values.
        try:
            fabric = Fabric.objects.select_for_update().get(pk=self.fabric_id)
        except Fabric.DoesNotExist:
            fabric = None

        # Copy values from fabric if they are not provided (preserve ability to take data from Fabric)
        if fabric is not None:
            if not self.base_color:
                self.base_color = fabric.base_color
            if not self.product_type:
                # map fabric.type -> product_type
                self.product_type = fabric.type
            if self.width is None:
                # map fabric_width -> width
                self.width = fabric.fabric_width
            if not self.use_in:
                self.use_in = fabric.use_in
            # If printed cost_per_unit not given or zero, inherit fabric cost
            if (self.cost_per_unit is None or self.cost_per_unit == Decimal('0.00')) and fabric.cost_per_unit:
                self.cost_per_unit = fabric.cost_per_unit
            # inherit vendor if not provided
            if not self.vendor and fabric.vendor:
                self.vendor = fabric.vendor
            # inherit quality (string) if not provided
            if (self.quality is None or (isinstance(self.quality, str) and self.quality.strip() == "")) and getattr(fabric, 'quality', None) is not None:
                # Copy the string value directly (fabric.quality is now a CharField)
                self.quality = fabric.quality

        # validate
        self.full_clean()

        with transaction.atomic():
            # Re-fetch fabric with lock inside transaction if still None
            fabric = Fabric.objects.select_for_update().get(pk=self.fabric_id)

            if creating:
                # When creating, check fabric stock and deduct quantity_used
                if fabric.stock_in_mtrs < self.quantity_used:
                    raise ValidationError(f"Insufficient fabric stock to produce printed item: required {self.quantity_used}, available {fabric.stock_in_mtrs}")
                fabric.stock_in_mtrs -= self.quantity_used
                fabric.save(update_fields=['stock_in_mtrs', 'updated_at'])

                # If printed item stock not set, initialize it to quantity_used
                if self.stock is None or self.stock == Decimal('0.000'):
                    self.stock = Decimal(self.quantity_used)
                super().save(*args, **kwargs)
            else:
                # Updating: compute difference in quantity_used and adjust fabric stock accordingly
                previous = Printed.objects.select_for_update().get(pk=self.pk)
                prev_qty = previous.quantity_used or Decimal('0.000')
                new_qty = self.quantity_used or Decimal('0.000')
                delta = new_qty - prev_qty

                if delta > 0:
                    if fabric.stock_in_mtrs < delta:
                        raise ValidationError(f"Insufficient fabric stock to increase quantity_used by {delta}. Available: {fabric.stock_in_mtrs}")
                    fabric.stock_in_mtrs -= delta
                elif delta < 0:
                    # delta negative => returning fabric stock
                    fabric.stock_in_mtrs -= delta  # subtracting a negative adds
                fabric.save(update_fields=['stock_in_mtrs', 'updated_at'])
                super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            fabric = Fabric.objects.select_for_update().get(pk=self.fabric_id)
            if self.quantity_used:
                fabric.stock_in_mtrs += self.quantity_used
                fabric.save(update_fields=['stock_in_mtrs', 'updated_at'])
            super().delete(*args, **kwargs)
