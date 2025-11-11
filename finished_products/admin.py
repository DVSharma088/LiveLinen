# finished_products/admin.py
from django.contrib import admin, messages
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import FinishedProduct, FinishedProductLine, StockMovement


class FinishedProductLineInline(admin.TabularInline):
    model = FinishedProductLine
    extra = 0
    fields = ("content_type", "object_id", "qty_per_unit", "line_cost")
    readonly_fields = ("line_cost",)
    autocomplete_fields = ()
    show_change_link = False
    can_delete = True


@admin.register(FinishedProduct)
class FinishedProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "size",
        "product_category",
        "product_price",
        "fabric_color_name",
        "fabric_pattern",
        "total_manufacturing_cost",
        "created_at",
    )
    list_display_links = ("name",)
    search_fields = ("name", "sku", "fabric_color_name", "fabric_pattern", "product_category")
    list_filter = ("size", "product_category")
    readonly_fields = ("sku", "total_manufacturing_cost", "created_at")
    inlines = (FinishedProductLineInline,)
    ordering = ("-created_at",)
    actions = ["action_process_stock_and_compute_cost"]

    fieldsets = (
        (None, {
            "fields": ("name", "sku", "size", "average", "product_category", "product_price")
        }),
        ("Fabric / Material", {
            "fields": ("fabric_quality", "fabric_collection", "fabric_width", "fabric_color_name", "fabric_pattern"),
        }),
        ("Manufacturing", {
            "fields": ("total_manufacturing_cost", "created_at"),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("lines")

    @admin.action(description="Process stock & compute cost for selected finished products")
    def action_process_stock_and_compute_cost(self, request, queryset):
        """
        Admin action to run process_deduction() for selected FinishedProduct objects.
        Runs each in its own transaction and reports per-object status.
        """
        processed = 0
        errors = []

        for product in queryset:
            try:
                with transaction.atomic():
                    product.process_deduction(reason=f"Admin action by {request.user}")
                processed += 1
            except ValidationError as ve:
                errors.append(f"{product}: {ve}")
            except Exception as exc:  # pragma: no cover - unexpected
                errors.append(f"{product}: {exc}")

        if processed:
            self.message_user(
                request,
                message=f"Processed {processed} product(s) successfully.",
                level=messages.SUCCESS,
            )
        if errors:
            self.message_user(
                request,
                message="Errors while processing:\n" + "\n".join(errors),
                level=messages.ERROR,
            )


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("material", "qty_change", "reason", "created_at")
    readonly_fields = ("content_type", "object_id", "material", "qty_change", "reason", "created_at")
    list_filter = ("reason", "created_at")
    search_fields = ("reason",)
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        # prevent manually creating StockMovement entries from admin to keep audit integrity
        return False
