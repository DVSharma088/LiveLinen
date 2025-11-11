from django.db import models
from django.conf import settings

# Adjust this import if your WorkOrder model has a different path/name
from workorders.models import WorkOrder


class Dispatch(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('ready', 'Ready'),
        ('dispatched', 'Dispatched'),
        ('delivered', 'Delivered'),
    )

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='dispatches')
    # the following fields are pre-filled from WorkOrder when creating a dispatch
    variant = models.CharField(max_length=255, blank=True, null=True)
    order_value = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    # dispatch-specific fields (to be filled by employee)
    dispatch_date = models.DateField(blank=True, null=True)
    courier_company = models.CharField(max_length=200, blank=True)
    tracking_number = models.CharField(max_length=200, blank=True)
    remarks = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Dispatch {self.pk} for Order {self.work_order_id}"
