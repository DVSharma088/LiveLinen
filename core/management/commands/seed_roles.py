# core/management/commands/seed_roles.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Seed standard roles (Admin, Manager, Employee) and assign permissions.\n\n"
        "Admin: all permissions\n"
        "Manager: create & view users, create/view/change vendors, inventory, components, finished_products, dispatch, workorders, chat\n"
        "Employee: view users, create/view vendors, inventory, components, finished_products, dispatch, chat (no workorder permissions, no user create)\n\n"
        "Usage: python manage.py seed_roles\n"
        "Optional: python manage.py seed_roles --assign-to username  (will add the existing user to Admin group)\n"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--assign-to",
            dest="username",
            help="(optional) existing username to add to Admin group for bootstrap",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Show what would be done without persisting changes.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        assign_to = options.get("username", None)

        # Define which app_labels should receive which action prefixes for each group.
        # Action prefixes used to match permission codenames (e.g., add_, change_, view_, delete_)
        # If exact codenames are needed (like 'view_user'), you can include them as full strings
        # by adding items that contain an underscore after the app label (we handle both startswith and exact).
        role_specs = {
            "Admin": {
                # Admin gets *all* permissions (we'll handle specially)
            },
            "Manager": {
                # app_label : list of action prefixes or exact codenames
                "auth": ["view_user", "add_user"],
                "vendors": ["add_", "change_", "view_", "delete_"],  # vendor CRUD
                "rawmaterials": ["add_", "change_", "view_", "delete_"],  # inventory (fabric/accessory/printed)
                "components": ["add_", "change_", "view_", "delete_"],
                "finished_products": ["add_", "change_", "view_", "delete_"],
                "dispatch": ["add_", "change_", "view_", "delete_"],
                "workorders": ["add_", "change_", "view_", "delete_"],  # Manager can manage workorders
                "chat": ["add_", "change_", "view_"],
            },
            "Employee": {
                "auth": ["view_user"],
                "vendors": ["add_", "view_"],
                "rawmaterials": ["add_", "view_"],
                "components": ["add_", "view_"],
                "finished_products": ["add_", "view_"],
                "dispatch": ["add_", "view_"],
                "chat": ["add_", "view_"],
                # no workorders perms for Employee
            },
        }

        with transaction.atomic():
            # Create groups if they don't exist
            created_groups = []
            for role_name in ("Admin", "Manager", "Employee"):
                group, created = Group.objects.get_or_create(name=role_name)
                if created:
                    created_groups.append(role_name)
                self.stdout.write(self.style.SUCCESS(f"Group: {role_name} (created={created})"))

            if dry_run:
                self.stdout.write(self.style.WARNING("Dry run: no permission changes will be saved."))
            # Assign permissions
            for role_name, specs in role_specs.items():
                group = Group.objects.get(name=role_name)
                # Admin special-case: give all permissions
                if role_name == "Admin":
                    perms_qs = Permission.objects.all()
                    if dry_run:
                        self.stdout.write(self.style.WARNING(f"[Dry-run] Would assign ALL permissions to '{role_name}' ({perms_qs.count()} perms)"))
                    else:
                        group.permissions.set(perms_qs)
                        self.stdout.write(self.style.SUCCESS(f"Assigned ALL permissions to '{role_name}' ({perms_qs.count()} perms)"))
                    continue

                # For Manager and Employee: collect matching permissions
                perms_to_assign = set()
                for app_label, actions in specs.items():
                    # If actions list contains exact codenames (like 'view_user'), we'll fetch them directly,
                    # otherwise we match codenames starting with provided prefixes (like 'add_','view_')
                    # First, get all permissions for the app_label
                    perms_for_app = Permission.objects.filter(content_type__app_label=app_label)
                    if not perms_for_app.exists():
                        self.stdout.write(self.style.WARNING(f"No permissions found for app_label='{app_label}'. (maybe no models or different app_label)"))
                        continue

                    for action in actions:
                        if "_" in action and not action.endswith("_"):
                            # Looks like an exact codename, try to fetch it
                            exact = perms_for_app.filter(codename=action)
                            if exact.exists():
                                perms_to_assign.update(list(exact))
                            else:
                                # Fallback: maybe the permission exists under a different app_label/model
                                # Try global search
                                global_exact = Permission.objects.filter(codename=action)
                                if global_exact.exists():
                                    perms_to_assign.update(list(global_exact))
                                else:
                                    self.stdout.write(self.style.WARNING(f"Exact permission codename '{action}' not found under app '{app_label}'"))
                        else:
                            # Treat action as prefix (e.g., 'add_', 'view_')
                            matched = perms_for_app.filter(codename__startswith=action)
                            if matched.exists():
                                perms_to_assign.update(list(matched))
                            else:
                                self.stdout.write(self.style.WARNING(f"No permissions with prefix '{action}' found for app_label='{app_label}'"))

                if dry_run:
                    self.stdout.write(self.style.WARNING(f"[Dry-run] Would assign {len(perms_to_assign)} permissions to '{role_name}'"))
                else:
                    group.permissions.set(perms_to_assign)
                    self.stdout.write(self.style.SUCCESS(f"Assigned {len(perms_to_assign)} permissions to '{role_name}'"))

            # Optionally assign an existing user to Admin group (bootstrap)
            if assign_to:
                User = get_user_model()
                try:
                    user = User.objects.get(username=assign_to)
                    admin_group = Group.objects.get(name="Admin")
                    if dry_run:
                        self.stdout.write(self.style.WARNING(f"[Dry-run] Would add user '{assign_to}' to Admin group"))
                    else:
                        user.groups.add(admin_group)
                        self.stdout.write(self.style.SUCCESS(f"Added user '{assign_to}' to Admin group"))
                except User.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"User '{assign_to}' not found. Skipping assignment."))

        # Print summary of groups & counts
        self.stdout.write("\nSummary of groups and permission counts:")
        for group in Group.objects.all():
            self.stdout.write(f" - {group.name}: {group.permissions.count()} permissions assigned")

        self.stdout.write(self.style.SUCCESS("Role seeding complete."))
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run was used; no changes persisted."))
