# core/signals.py
import logging
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=User)
def add_user_to_employee_group(sender, instance, created, **kwargs):
    """
    When a new user is created, add to 'Employee' group *only if the user
    currently has no groups*. This prevents the signal from overriding or
    making 'Employee' the only role when admins/managers explicitly assign roles.
    """
    if not created:
        return

    try:
        # If user already has any group assigned (e.g., Manager), do nothing.
        if instance.groups.exists():
            logger.debug("User %s created but already has groups; not auto-assigning Employee.", instance)
            return

        # Try to fetch the Employee group; if missing, silently ignore.
        group = Group.objects.get(name="Employee")
        instance.groups.add(group)
        logger.info("Auto-assigned new user %s to Employee group.", instance)
    except Group.DoesNotExist:
        # If the Employee group doesn't exist (setup not done), ignore gracefully.
        logger.warning("Employee group does not exist; could not auto-assign for user %s.", instance)
    except Exception as exc:
        # Catch-all to avoid letting signal crash user creation
        logger.exception("Unexpected error in add_user_to_employee_group for user %s: %s", instance, exc)
