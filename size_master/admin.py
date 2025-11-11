from django.contrib import admin
from .models import SizeMaster


@admin.register(SizeMaster)
class SizeMasterAdmin(admin.ModelAdmin):
    list_display = (
        "category",
        "size",
        "length",
        "breadth",
        "sqmt",
        "stitching",
        "finishing",
        "packaging",
    )
    list_filter = ("category",)
    search_fields = ("size", "category__name")
