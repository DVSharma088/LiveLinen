# file: rawmaterials/apps.py

from django.apps import AppConfig


class RawmaterialsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "rawmaterials"

    def ready(self):
        """
        Import signals when the app is ready.
        Ensures low stock email notifications are registered.
        """
        import rawmaterials.signals
