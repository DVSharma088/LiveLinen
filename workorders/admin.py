from django.contrib import admin
from .models import WorkOrder, PackagingStage


class PackagingStageInline(admin.TabularInline):
    """
    Inline view of Packaging Stages under each WorkOrder.
    Admins can assign employees here easily.
    """
    model = PackagingStage
    extra = 0
    autocomplete_fields = ['assigned_to']
    readonly_fields = ('stage_status', 'completion_date', 'received_confirmed', 'is_delayed')
    fields = (
        'stage_name',
        'assigned_to',
        'stage_status',
        'completion_date',
        'received_confirmed',
        'is_delayed',
    )


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'order_id',
        'variant_ordered',
        'quantity_ordered',
        'status',
        'created_at',
    )
    list_filter = ('status', 'created_at')
    search_fields = ('order_id', 'variant_ordered')
    inlines = [PackagingStageInline]


@admin.register(PackagingStage)
class PackagingStageAdmin(admin.ModelAdmin):
    """
    Separate admin page for stages — useful for bulk assignment.
    """
    list_display = (
        'id',
        'work_order',
        'stage_name',
        'assigned_to',
        'stage_status',
        'completion_date',
        'received_confirmed',
        'is_delayed',
    )
    list_filter = ('stage_status', 'is_delayed', 'received_confirmed')
    search_fields = ('work_order__order_id', 'stage_name', 'assigned_to__username')
    autocomplete_fields = ['assigned_to', 'work_order']
    list_select_related = ('work_order', 'assigned_to')
