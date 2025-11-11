from django.apps import AppConfig


class CategoryMasterNewConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "category_master_new"

    def ready(self):
        # Import signals when app is ready
        import category_master_new.signals
