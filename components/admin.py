from django.contrib import admin
from .models import CostComponent


@admin.register(CostComponent)
class CostComponentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "value_type",
        "display_value",
        "inventory_category",
        "linked_inventory",
        "is_active",
        "updated_at",
    )
    list_filter = ("value_type", "is_active", "inventory_category")
    search_fields = ("name", "description")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at", "linked_inventory_display")

    fieldsets = (
        (None, {
            "fields": (
                "name",
                "value_type",
                "value",
                "description",
                "is_active",
            )
        }),
        ("Inventory Link", {
            "fields": (
                "inventory_category",
                "inventory_content_type",
                "inventory_object_id",
                "linked_inventory_display",
            ),
            "description": "Link this component to a specific inventory item (Fabric / Accessory / Printed).",
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    def linked_inventory(self, obj):
        """Short label for list_display"""
        return obj.get_inventory_display() or "—"
    linked_inventory.short_description = "Linked Item"

    def linked_inventory_display(self, obj):
        """Read-only version for the admin form view"""
        return obj.get_inventory_display() or "—"
    linked_inventory_display.short_description = "Linked Item"
