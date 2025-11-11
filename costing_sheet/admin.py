# costing_sheet/admin.py
from django.contrib import admin
from .models import CostingSheet


@admin.register(CostingSheet)
class CostingSheetAdmin(admin.ModelAdmin):
    """
    Admin adjusted to not surface size/size_master/stitching/finishing/packaging fields.
    """
    list_display = (
        "id",
        "category",
        "component",
        "gf_percent",
        "texas_buying_percent",
        "shipping_inr",
        "us_wholesale",
        "created_at",
    )
    list_select_related = ("category",)
    list_filter = ("category", "created_at")
    search_fields = ("name", "component", "category__name")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)

    fieldsets = (
        ("Basic", {
            "fields": ("category", "name")
        }),
        ("Component / Category Master values", {
            "fields": (
                "component",
                "gf_percent",
                "texas_buying_percent",
                "texas_retail_percent",
                "shipping_inr",
                "tx_to_us_percent",
                "import_percent",
                "new_tariff_percent",
                "recip_tariff_percent",
                "ship_us_percent",
                "us_wholesale",
            )
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )
