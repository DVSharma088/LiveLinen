# category_master_new/admin.py
from django.contrib import admin
from .models import Category, CategorySize


class CategorySizeInline(admin.TabularInline):
    model = CategorySize
    extra = 1
    fields = (
        "name",
        "order",
        "stitching_cost",
        "finishing_cost",
        "packaging_cost",
    )
    ordering = ("order", "name")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "sizes_display")
    search_fields = ("name",)
    inlines = [CategorySizeInline]

    def sizes_display(self, obj):
        qs = obj.sizes.all()
        parts = []
        for s in qs:
            pieces = [s.name]
            if s.stitching_cost is not None:
                pieces.append(f"Stitch:{s.stitching_cost}")
            if s.finishing_cost is not None:
                pieces.append(f"Finish:{s.finishing_cost}")
            if s.packaging_cost is not None:
                pieces.append(f"Pack:{s.packaging_cost}")
            parts.append(" — ".join(pieces))
        return ", ".join(parts) if parts else "-"
    sizes_display.short_description = "Sizes (Stitch / Finish / Pack)"


@admin.register(CategorySize)
class CategorySizeAdmin(admin.ModelAdmin):
    list_display = (
        "category",
        "name",
        "order",
        "stitching_cost",
        "finishing_cost",
        "packaging_cost",
    )
    list_filter = ("category",)
    search_fields = ("name", "category__name")
