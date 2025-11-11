# size_master/models.py
from decimal import Decimal, InvalidOperation, getcontext
from django.db import models
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _

# reference the Category model from the Category_Master(New) app
CATEGORY_MODEL = "category_master_new.Category"

# increase decimal precision for intermediate calculations
getcontext().prec = 28


class SizeMaster(models.Model):
    """
    SizeMaster represents a size entry tied to a Category (Category_Master(New)).
    SqMT is derived (length * breadth) and stored in the DB as a non-editable field.
    """

    category = models.ForeignKey(
        CATEGORY_MODEL,
        on_delete=models.CASCADE,
        # changed related_name so it does not clash with CategorySize.related_name='sizes'
        related_name="size_entries",
        null=True,   # if you already used a temporary nullable migration; remove if you want non-nullable
        blank=True,
        help_text=_("Select the Category (from Category_Master(New)) this size belongs to."),
    )

    size = models.CharField(_("Size name"), max_length=100)

    length = models.DecimalField(
        _("Length"),
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        help_text=_("Length in units (decimal allowed)."),
    )

    breadth = models.DecimalField(
        _("Breadth"),
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        help_text=_("Breadth in units (decimal allowed)."),
    )

    # stored sqmt, non-editable (calculated in save())
    sqmt = models.DecimalField(
        _("SqMT"),
        max_digits=12,
        decimal_places=6,
        editable=False,
        default=Decimal("0.0"),
        help_text=_("Automatically calculated as Length × Breadth."),
    )

    stitching = models.DecimalField(
        _("Stitching"),
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        default=Decimal("0.0"),
    )

    finishing = models.DecimalField(
        _("Finishing"),
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        default=Decimal("0.0"),
    )

    packaging = models.DecimalField(
        _("Packaging"),
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        default=Decimal("0.0"),
    )

    class Meta:
        verbose_name = _("Size Master")
        verbose_name_plural = _("Size Masters")
        ordering = ["category__name", "size"]
        indexes = [
            models.Index(fields=["size"]),
            models.Index(fields=["category"]),
        ]

    def save(self, *args, **kwargs):
        """
        Compute sqmt = length * breadth server-side before saving.
        Quantize to 4 decimal places (0.0001) for storage consistency.
        """
        try:
            length_val = self.length or Decimal("0")
            breadth_val = self.breadth or Decimal("0")
            sqmt_val = (Decimal(length_val) * Decimal(breadth_val)).quantize(Decimal("0.0001"))
            self.sqmt = sqmt_val
        except (InvalidOperation, TypeError):
            self.sqmt = Decimal("0.0")

        super().save(*args, **kwargs)

    def __str__(self):
        try:
            cat_name = getattr(self.category, "name", None) or "Unassigned"
        except Exception:
            cat_name = "Unassigned"
        return f"{cat_name} - {self.size}"
