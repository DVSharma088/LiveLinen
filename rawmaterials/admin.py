from django.contrib import admin
from .models import Fabric, Accessory, Printed
from .forms import FabricForm, AccessoryForm, PrintedForm


@admin.register(Fabric)
class FabricAdmin(admin.ModelAdmin):
    form = FabricForm
    list_display = (
        "item_name",
        "quality",
        "base_color",
        "type",              # updated field name
        "fabric_width",
        "use_in",
        "stock_in_mtrs",
        "cost_per_unit",
        "vendor",
        "created_at",
    )
    search_fields = ("item_name", "base_color", "type", "use_in", "vendor__vendor_name")
    list_filter = ("type", "vendor")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("vendor",)
    ordering = ("-created_at",)
    list_select_related = ("vendor",)

    fieldsets = (
        (None, {
            "fields": (
                "item_name",
                "quality",
                "base_color",
                "type",           # updated here
                "fabric_width",
                "use_in",
            )
        }),
        ("Stock & Cost", {
            "fields": ("stock_in_mtrs", "cost_per_unit", "vendor")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("vendor")


@admin.register(Accessory)
class AccessoryAdmin(admin.ModelAdmin):
    form = AccessoryForm
    """
    Admin config for the updated Accessory model:
    Fields: item_name, quality, base_color, item_type, width, use_in, stock, cost_per_unit, vendor
    """
    list_display = (
        "item_name",
        "quality",
        "base_color",
        "item_type",
        "width",
        "use_in",
        "stock",
        "cost_per_unit",
        "vendor",
        "created_at",
    )
    search_fields = ("item_name", "item_type", "base_color", "use_in", "vendor__vendor_name")
    list_filter = ("item_type", "vendor")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("vendor",)
    ordering = ("-created_at",)
    list_select_related = ("vendor",)

    fieldsets = (
        (None, {
            "fields": (
                "item_name",
                "quality",
                "base_color",
                "item_type",
                "width",
                "use_in",
            )
        }),
        ("Stock & Cost", {
            "fields": ("stock", "cost_per_unit", "vendor")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("vendor")


@admin.register(Printed)
class PrintedAdmin(admin.ModelAdmin):
    form = PrintedForm
    list_display = (
        "product",
        "fabric",
        "effective_quality",   # show Printed.quality or fallback to Fabric.quality
        "base_color",
        "product_type",
        "width",
        "use_in",
        "unit",
        "quantity_used",
        "stock",
        "cost_per_unit",
        "vendor",
        "rate",
        "created_at",
    )
    search_fields = (
        "product",
        "fabric__item_name",
        "vendor__vendor_name",
        "fabric__vendor__vendor_name",
        "quality",
    )
    list_filter = ("product_type", "unit", "vendor")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("fabric", "vendor")
    ordering = ("-created_at",)

    fieldsets = (
        (None, {
            "fields": (
                "product",
                "fabric",
                "quality",        # added so admin can set Printed.quality
                "base_color",
                "product_type",
                "width",
                "use_in",
            )
        }),
        ("Stock & Pricing", {
            "fields": ("unit", "quantity_used", "stock", "cost_per_unit", "rate", "vendor")
        }),
        ("Timestamps", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # select_related to avoid N+1 when accessing fabric/vendor
        return qs.select_related("fabric", "fabric__vendor", "vendor")

    def effective_quality(self, obj):
        """
        Display Printed.quality when set; otherwise fallback to related Fabric.quality.
        """
        try:
            if obj.quality is not None:
                return obj.quality
            if obj.fabric and getattr(obj.fabric, "quality", None) is not None:
                return obj.fabric.quality
        except Exception:
            pass
        return "-"
    effective_quality.short_description = "Quality"
    # optional: allow ordering by Printed.quality (note: Fabric.quality fallback won't be considered for ordering)
    effective_quality.admin_order_field = "quality"
