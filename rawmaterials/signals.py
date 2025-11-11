# file: rawmaterials/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings

from .models import Fabric, Accessory, Printed


def send_low_stock_email(item_type, item_name, vendor_name, stock_value):
    """
    Sends an email alert when stock falls below the defined threshold.
    """
    subject = f"[Live Linen] Low Stock Alert: {item_name}"
    message = (
        f"Dear Admin,\n\n"
        f"The following {item_type} has low stock:\n\n"
        f"Item: {item_name}\n"
        f"Vendor: {vendor_name}\n"
        f"Current Stock: {stock_value}\n\n"
        f"Please consider restocking soon.\n\n"
        f"Regards,\n"
        f"Live Linen Inventory System"
    )

    recipient_list = getattr(settings, "STOCK_ALERT_RECIPIENTS", [settings.DEFAULT_FROM_EMAIL])
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        fail_silently=True,
    )


@receiver(post_save, sender=Fabric)
def check_fabric_stock(sender, instance, **kwargs):
    """
    Check Fabric stock after every save.
    """
    try:
        if instance.stock_in_mtrs < 10:
            send_low_stock_email(
                item_type="Fabric",
                item_name=instance.item_name,
                vendor_name=str(instance.vendor.vendor_name),
                stock_value=instance.stock_in_mtrs,
            )
    except Exception as e:
        # Fail silently to prevent any interruption in normal DB operations
        print(f"Low stock email failed for Fabric: {e}")


@receiver(post_save, sender=Accessory)
def check_accessory_stock(sender, instance, **kwargs):
    """
    Check Accessory stock after every save.
    """
    try:
        if instance.stock < 10:
            send_low_stock_email(
                item_type="Accessory",
                item_name=instance.item_name,
                vendor_name=str(instance.vendor.vendor_name),
                stock_value=instance.stock,
            )
    except Exception as e:
        print(f"Low stock email failed for Accessory: {e}")


@receiver(post_save, sender=Printed)
def check_printed_stock(sender, instance, **kwargs):
    """
    Check Printed product stock after every save.
    """
    try:
        if instance.stock < 10:
            send_low_stock_email(
                item_type="Printed Product",
                item_name=instance.product,
                vendor_name=str(instance.vendor.vendor_name if instance.vendor else "N/A"),
                stock_value=instance.stock,
            )
    except Exception as e:
        print(f"Low stock email failed for Printed Product: {e}")
