# category_master_new/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction

from category_master_new.models import Category
from category_master.models import CategoryMasterNew


@receiver(post_save, sender=Category)
def create_categorymasternew_from_category(sender, instance, created, **kwargs):
    """
    When a Category is created in category_master_new, ensure a corresponding
    CategoryMasterNew entry exists and is active.
    """
    if not created:
        return

    # Use update_or_create so repeated saves won't duplicate entries.
    CategoryMasterNew.objects.update_or_create(
        name=instance.name.strip(),
        defaults={"active": True},
    )


@receiver(post_delete, sender=Category)
def delete_categorymasternew_on_category_delete(sender, instance, **kwargs):
    """
    When a Category is deleted in category_master_new, delete the corresponding
    CategoryMasterNew row so the Category Master dropdown no longer shows it.

    We match by name (trimmed) because the Category and CategoryMasterNew
    models live in different apps and earlier migrations created rows by id
    in some cases; matching by name is safe and predictable for the UI.
    """
    name = (instance.name or "").strip()
    if not name:
        return

    # Wrap in a small transaction to be tidy (not required but safe).
    try:
        with transaction.atomic():
            CategoryMasterNew.objects.filter(name__iexact=name).delete()
    except Exception:
        # Be tolerant: don't raise to avoid breaking the deletion flow in the UI.
        pass
