# dispatch/signals.py
import logging
from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)

# Temporary hardcoded recipient (you requested this for now)
TEST_RECIPIENT = "devvrat@livelinen.com"


def _is_instance_dispatched(instance) -> bool:
    """
    Heuristic to determine dispatched state.
    Checks common fields without importing model at module-level.
    """
    try:
        if hasattr(instance, "dispatched_at"):
            return bool(getattr(instance, "dispatched_at"))
        if hasattr(instance, "status"):
            try:
                return str(getattr(instance, "status")).lower() == "dispatched"
            except Exception:
                pass
        if hasattr(instance, "is_dispatched"):
            return bool(getattr(instance, "is_dispatched"))
        if hasattr(instance, "tracking_number"):
            return bool(getattr(instance, "tracking_number"))
    except Exception:
        logger.exception("Error while checking dispatched state for Dispatch id=%s", getattr(instance, "pk", None))
    return False


def _render_and_send_email(dispatch_obj, recipient_email: str):
    """
    Render templates and send email. Run inside transaction.on_commit.
    """
    try:
        subject = f"Your order has been dispatched — Dispatch #{getattr(dispatch_obj, 'pk', '')}"
        context = {
            "dispatch": dispatch_obj,
            "site_name": getattr(settings, "SITE_NAME", "LiveLinen"),
            "recipient": recipient_email,
        }

        # Render text and html; fallback to simple text if templates missing
        try:
            text_body = render_to_string("dispatch/dispatch_email.txt", context)
        except Exception:
            text_body = f"Your order (Dispatch #{getattr(dispatch_obj,'pk','')}) has been dispatched.\n\nThank you,\n{context['site_name']}"

        html_body = None
        try:
            html_body = render_to_string("dispatch/dispatch_email.html", context)
        except Exception:
            # It's fine to continue without HTML body
            html_body = None

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@livelinen.com")
        msg = EmailMultiAlternatives(subject=subject, body=text_body, from_email=from_email, to=[recipient_email])
        if html_body:
            msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        logger.info("Dispatch email sent for Dispatch id=%s to %s", getattr(dispatch_obj, "pk", ""), recipient_email)
    except Exception:
        logger.exception("Failed to send dispatch email for Dispatch id=%s", getattr(dispatch_obj, "pk", None))


def _dispatch_post_save_handler(sender, instance, created, **kwargs):
    """
    The actual post_save handler connected at runtime.
    Sends email on create or when toggled from not-dispatched -> dispatched.
    """
    try:
        current_dispatched = _is_instance_dispatched(instance)
        send_email = False

        if created:
            send_email = True
        else:
            # Fetch previous state from DB to detect transition
            try:
                prev = sender.objects.filter(pk=getattr(instance, "pk")).first()
                if prev:
                    prev_dispatched = _is_instance_dispatched(prev)
                else:
                    prev_dispatched = False
            except Exception:
                prev_dispatched = False

            if not prev_dispatched and current_dispatched:
                send_email = True

        if not send_email:
            return

        recipient = TEST_RECIPIENT

        # Send after DB commit to avoid race conditions
        transaction.on_commit(lambda: _render_and_send_email(instance, recipient))

    except Exception:
        logger.exception("Error in dispatch post_save handler for Dispatch id=%s", getattr(instance, "pk", None))


def register():
    """
    Register signal handlers. This should be called from AppConfig.ready().
    Uses apps.get_model to avoid importing models at module import time.
    """
    try:
        Dispatch = apps.get_model("dispatch", "Dispatch")
        if Dispatch is None:
            logger.warning("dispatch.Dispatch model not found when registering signals")
            return
        post_save.connect(_dispatch_post_save_handler, sender=Dispatch, dispatch_uid="dispatch_post_save_handler")
        logger.debug("Registered dispatch.post_save handler for dispatch.Dispatch")
    except Exception:
        logger.exception("Failed to register dispatch signals")
