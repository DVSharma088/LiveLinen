# core/leave_signals.py
import logging
import traceback
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.db import models
from django.core.cache import cache

from .models import LeaveApplication
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


def _get_admin_emails():
    """
    Return a deduplicated list of admin emails.
    Criteria: superusers OR members of Admin/CEO groups.
    """
    admins_qs = User.objects.filter(is_active=True).filter(
        models.Q(is_superuser=True) | models.Q(groups__name__in=["Admin", "CEO"])
    ).distinct()

    emails = {u.email for u in admins_qs if u.email}
    return sorted(emails)


@receiver(post_save, sender=LeaveApplication, dispatch_uid="core.leave_application_created_v1")
def leave_application_created(sender, instance, created, **kwargs):
    """
    Notify admins when a new LeaveApplication is created.

    - Only runs on create (created=True).
    - Uses dispatch_uid to avoid duplicate registration sends if module imported twice.
    - Uses cache.add to make the send idempotent within/ across repeated handler calls
      in the same process for the same instance.
    - Logs a full stack trace before sending so we can see where the handler was invoked from.
    """
    if not created:
        return

    cache_key = f"leave_notification_sent:{instance.pk}"
    # cache.add returns True only if the key did not previously exist
    # TTL 300 seconds (5 minutes) should be enough for the creation flow.
    added = cache.add(cache_key, "1", timeout=300)

    # Log invocation and stack for debugging (only the first two lines to keep logs readable).
    stack = "".join(traceback.format_stack())
    logger.info("leave_application_created handler invoked for Leave #%s created=%s added_to_cache=%s",
                instance.pk, created, added)
    logger.debug("Call stack at notification time:\n%s", stack)

    # If another call already added the cache key, skip sending (idempotency guard).
    if not added:
        logger.info("Skipping send for Leave #%s because cache key already present (duplicate invocation).", instance.pk)
        return

    # Build message (plain-text). Replace with templated HTML if desired.
    applicant_name = instance.applicant.get_full_name() or instance.applicant.username
    subject = f"[LiveLinen] New leave application from {applicant_name}"
    body = (
        f"Leave application #{instance.pk}\n"
        f"Applicant: {applicant_name}\n"
        f"Type: {instance.get_leave_type_display()}\n"
        f"Range: {instance.start_date} -> {instance.end_date} ({instance.duration_days} days)\n\n"
        f"Reason:\n{instance.reason or '—'}\n\n"
        f"View leave list: {reverse('core:leave_list')}"
    )

    admin_emails = _get_admin_emails()
    if not admin_emails:
        logger.warning("No admin emails found; leaving notification un-sent for Leave #%s", instance.pk)
        return

    # Log just before sending so you can correlate logs with email receipts
    logger.info("Sending leave notification for Leave #%s to admins: %s", instance.pk, admin_emails)

    try:
        num_sent = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, admin_emails)
        logger.info("send_mail returned %s for Leave #%s", num_sent, instance.pk)
    except Exception as exc:
        # If sending fails, we *could* clear the cache key so retry may happen — but for now log error.
        logger.exception("Exception while sending leave notification for Leave #%s: %s", instance.pk, exc)
