# dispatch/apps.py
from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class DispatchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dispatch"

    def ready(self):
        """
        Import and register signals safely.
        The signals module should expose a `register()` function that uses
        apps.get_model(...) and connects signal handlers at runtime.
        Wrapping in try/except prevents app startup from crashing during development
        if signals import fails.
        """
        try:
            # local import to avoid top-level import cycles
            from . import signals as _signals  # noqa: F401

            # If signals module exposes a register() function, call it to attach handlers.
            if hasattr(_signals, "register"):
                try:
                    _signals.register()
                except Exception:
                    logger.exception("dispatch.signals.register() raised an exception")
        except Exception:
            logger.exception("Failed to import dispatch.signals in DispatchConfig.ready()")
