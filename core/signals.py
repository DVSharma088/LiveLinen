# core/signals.py
from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()

@receiver(post_save, sender=User)
def add_user_to_employee_group(sender, instance, created, **kwargs):
    """
    When a new user is created, add to 'Employee' group by default.
    If you don't want auto-assign, remove this file or comment it out.
    """
    if created:
        try:
            group = Group.objects.get(name="Employee")
            instance.groups.add(group)
        except Group.DoesNotExist:
            # group missing — management command should create it; ignore silently
            pass
