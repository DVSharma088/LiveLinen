# category_master_new/models.py
from django.db import models


class Category(models.Model):
    """
    Category of product (e.g., Shirt, Kurta).
    Stores category-level costing parameters used elsewhere in the app.
    """
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)

    # ==== Costing Parameters (category-level) ====
    gf_percent = models.DecimalField(
        max_digits=8, decimal_places=4, default=0.0000, verbose_name="GF (%)"
    )
    texas_buying_percent = models.DecimalField(
        max_digits=8, decimal_places=4, default=0.0000, verbose_name="Texas Buying (%)"
    )
    texas_retail_percent = models.DecimalField(
        max_digits=8, decimal_places=4, default=0.0000, verbose_name="Texas Retail (%)"
    )
    shipping_inr = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00, verbose_name="Shipping (INR)"
    )
    tx_to_us_percent = models.DecimalField(
        max_digits=8, decimal_places=4, default=0.0000, verbose_name="TX→US (%)"
    )
    import_percent = models.DecimalField(
        max_digits=8, decimal_places=4, default=0.0000, verbose_name="Import (%)"
    )
    new_tariff_percent = models.DecimalField(
        max_digits=8, decimal_places=4, default=0.0000, verbose_name="New Tariff (%)"
    )
    reciprocal_tariff_percent = models.DecimalField(
        max_digits=8, decimal_places=4, default=0.0000, verbose_name="Recip. Tariff (%)"
    )
    ship_us_percent = models.DecimalField(
        max_digits=8, decimal_places=4, default=0.0000, verbose_name="Ship US (%)"
    )
    us_wholesale_percent = models.DecimalField(
        max_digits=8, decimal_places=4, default=0.0000, verbose_name="US Wholesale (%)"
    )

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CategorySize(models.Model):
    """
    Size entry for a Category (e.g., S, M, L). Each size can have per-size costs
    such as stitching, finishing and packaging which are used in costing calculations.
    """
    category = models.ForeignKey(
        Category, related_name="sizes", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=50)  # e.g. "S", "M", "L"
    order = models.PositiveIntegerField(default=0)

    # Per-size production costs
    stitching_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, verbose_name="Stitching Cost"
    )
    finishing_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, verbose_name="Finishing Cost"
    )
    packaging_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, verbose_name="Packaging Cost"
    )

    class Meta:
        unique_together = ("category", "name")
        ordering = ["order", "name"]
        verbose_name = "Category Size"
        verbose_name_plural = "Category Sizes"

    def __str__(self):
        return f"{self.category.name} - {self.name}"
