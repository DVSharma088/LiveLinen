from django.contrib import admin
from .models import Dispatch

@admin.register(Dispatch)
class DispatchAdmin(admin.ModelAdmin):
    list_display = ('pk', 'work_order', 'variant', 'order_value', 'dispatch_date', 'courier_company', 'status')
    list_filter = ('status', 'courier_company')
    search_fields = ('work_order__id', 'tracking_number', 'courier_company')
