from django.db import models
from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.urls import reverse


class CategoryMasterNew(models.Model):
    """
    Master list of category names used to populate dropdowns.
    """
    name = models.CharField(_("Name"), max_length=255, unique=True)
    active = models.BooleanField(_("Active"), default=True, help_text=_("Uncheck to hide from dropdowns"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Category (master list)")
        verbose_name_plural = _("Category (master lists)")
        ordering = ["name"]

    def __str__(self):
        return self.name


class CategoryMaster(models.Model):
    """
    Updated Category Master model with simplified and percentage-based costing fields.
    """
    component = models.ForeignKey(
        "category_master.CategoryMasterNew",
        on_delete=models.CASCADE,
        related_name="categories",
        help_text=_("Select the category this entry belongs to."),
    )

    # === Updated Fields ===
    gf_overhead = models.DecimalField(
        _("GF Overhead (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00"))
        ],
        help_text=_("Enter GF Overhead as a percentage (0–100).")
    )

    texas_buying_cost = models.DecimalField(
        _("Texas Buying Cost (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00"))
        ],
        help_text=_("Enter Texas Buying Cost as a percentage (0–100).")
    )

    texas_retail = models.DecimalField(
        _("Texas Retail (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00"))
        ],
        help_text=_("Enter Texas Retail as a percentage (0–100).")
    )

    shipping_cost_inr = models.DecimalField(
        _("Shipping Cost (INR)"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Shipping cost in INR.")
    )

    texas_to_us_selling_cost = models.DecimalField(
        _("Texas → US Selling Cost (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00"))
        ],
        help_text=_("Enter Texas to US Selling Cost as a percentage (0–100).")
    )

    import_cost = models.DecimalField(
        _("Import (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00"))
        ],
        help_text=_("Enter Import cost as a percentage (0–100).")
    )

    new_tariff = models.DecimalField(
        _("New Tariff (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00"))
        ],
        help_text=_("Enter New Tariff as a percentage (0–100).")
    )

    reciprocal_tariff = models.DecimalField(
        _("Reciprocal Tariff (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00"))
        ],
        help_text=_("Enter Reciprocal Tariff as a percentage (0–100).")
    )

    shipping_us = models.DecimalField(
        _("Shipping US (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00"))
        ],
        help_text=_("Enter Shipping cost (US) as a percentage (0–100).")
    )

    us_wholesale_margin = models.DecimalField(
        _("US Wholesale Margin (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00"))
        ],
        help_text=_("Enter US Wholesale Margin as a percentage (0–100).")
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Category Master")
        verbose_name_plural = _("Category Masters")
        ordering = ["-created_at"]

    def __str__(self):
        """Readable representation for admin/list."""
        comp_name = getattr(self.component, "name", str(self.component))
        return f"{comp_name} — GF Overhead: {self.gf_overhead}%"

    def get_absolute_url(self):
        return reverse("category_master:list")
