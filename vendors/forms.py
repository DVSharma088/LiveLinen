from django import forms
from .models import Vendor

class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = ['vendor_name', 'mobile_no', 'email', 'address', 'item_type', 'product', 'rate']
