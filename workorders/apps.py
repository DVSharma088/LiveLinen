from django.apps import AppConfig

class WorkordersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'workorders'

    def ready(self):
        # optional: import signals here if you created workorders/signals.py
        try:
            import workorders.signals  # noqa
        except Exception:
            # avoid hard failure during some checks; remove in prod after testing
            pass
