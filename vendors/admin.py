from django.contrib import admin
from .models import Vendor

@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('product','item_type','rate','created_at')
    list_filter = ('item_type',)
    search_fields = ('product',)
