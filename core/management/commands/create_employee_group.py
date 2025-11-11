# core/management/commands/create_employee_group.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.apps import apps

class Command(BaseCommand):
    help = "Create or update 'Employee' group with view-only permissions for models."

    def handle(self, *args, **options):
        group, created = Group.objects.get_or_create(name="Employee")
        self.stdout.write(f"Group 'Employee' {'created' if created else 'already exists'}")

        # Clear previous perms and reassign view perms
        group.permissions.clear()

        skip_apps = {"admin", "auth", "contenttypes", "sessions"}
        for model in apps.get_models():
            app_label = model._meta.app_label
            if app_label in skip_apps:
                continue

            codename = f"view_{model._meta.model_name}"
            try:
                perm = Permission.objects.get(content_type__app_label=app_label, codename=codename)
                group.permissions.add(perm)
                self.stdout.write(f"  added {app_label}.{codename}")
            except Permission.DoesNotExist:
                self.stdout.write(f"  permission not found: {app_label}.{codename}")

        self.stdout.write(self.style.SUCCESS("Employee group configured with view permissions."))
