# core/apps.py
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        """
        Import signal handlers when the app is ready.
        This ensures that user creation signals and leave-notify signals are connected.
        """
        try:
            # user/group signals
            import core.signals  # noqa: F401

            # leave application notification signal (created-only, idempotent)
            import core.leave_signals  # noqa: F401
        except Exception:
            # Avoid crashing app startup if signals.py doesn't exist yet or if import fails.
            # You may want to log the exception in production.
            pass
