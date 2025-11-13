from django.db import models

class Vendor(models.Model):
    ITEM_CHOICES = [
        ('Fabric', 'Fabric'),
        ('Accessories', 'Accessories'),
        ('Print', 'Print'),
        ('Dyeing', 'Dyeing'),
        
    ]

    vendor_name = models.CharField(max_length=200)
    mobile_no = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)

    item_type = models.CharField(max_length=32, choices=ITEM_CHOICES)
    product = models.CharField(max_length=200)
    rate = models.DecimalField(max_digits=12, decimal_places=2, help_text='Rate per unit')

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.vendor_name} - {self.product} ({self.item_type})"
