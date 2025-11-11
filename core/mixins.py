# core/mixins.py
from django.core.exceptions import PermissionDenied

class ReadOnlyForEmployeesMixin:
    """
    If `required_permission` is set, user must have that permission.
    Otherwise, non-superusers are prevented from non-safe HTTP methods.
    Use this for class-based Create/Update/Delete views.
    """
    required_permission = None  # e.g. "components.add_component"

    def dispatch(self, request, *args, **kwargs):
        # allow superusers/staff if you want: adjust condition as needed
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        if self.required_permission:
            if not request.user.has_perm(self.required_permission):
                raise PermissionDenied
        else:
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)
