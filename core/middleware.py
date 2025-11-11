# core/middleware.py
import re
from django.conf import settings
from django.shortcuts import redirect, resolve_url


class DashboardLoginRequiredMiddleware:
    """
    Redirect anonymous users to the login page for any non-exempt path.

    Enhancements:
    ✅ Respects per-view attribute `login_exempt = True`
    ✅ Also allows skipping enforcement when a request has `_skip_login_required = True`
       (set manually inside a view)
    ✅ Still honors LOGIN_EXEMPT_URLS patterns from settings
    """

    def __init__(self, get_response):
        self.get_response = get_response

        # Get exempt patterns from settings (fall back to sensible defaults)
        exempt_patterns = getattr(settings, "LOGIN_EXEMPT_URLS", None)
        if exempt_patterns is None:
            exempt_patterns = [
                r"^accounts/login/$",
                r"^accounts/logout/$",
                r"^accounts/password_reset/",
                r"^static/",
                r"^media/",
                r"^admin/login/",
                r"^health/?$",
                r"^size-master/ajax/category-sizes/",  # 👈 explicitly allow this AJAX route
            ]

        # Compile regexes for faster matching
        self.exempt_regexes = [re.compile(p) for p in exempt_patterns]

        # Resolve login URL (accepts named URL or raw path)
        self.login_url = resolve_url(getattr(settings, "LOGIN_URL", "/accounts/login/"))

    def _is_exempt(self, path: str) -> bool:
        """
        Determine whether `path` should be accessible without authentication.
        Matches against both the raw path (e.g. "/accounts/login/") and
        the path without the leading slash (e.g. "accounts/login/").
        """
        if not path:
            return False

        normalized = path.lstrip("/")
        for rx in self.exempt_regexes:
            if rx.match(normalized) or rx.match(path):
                return True
        return False

    def __call__(self, request):
        path = request.path  # includes leading slash, e.g. "/dashboard/"

        # ✅ 1. Skip enforcement if the request itself was marked to skip login
        if getattr(request, "_skip_login_required", False):
            return self.get_response(request)

        # ✅ 2. Skip if the view has `login_exempt = True` attribute
        try:
            if hasattr(request, "resolver_match") and request.resolver_match:
                view_func = request.resolver_match.func
                if getattr(view_func, "login_exempt", False):
                    return self.get_response(request)
        except Exception:
            # resolver_match might not be available in very early middleware stages
            pass

        # ✅ 3. Allow if user already authenticated
        if request.user.is_authenticated:
            return self.get_response(request)

        # ✅ 4. Allow if URL matches any exempt pattern (login, static, media, ajax, etc.)
        if self._is_exempt(path):
            return self.get_response(request)

        # 🚫 Otherwise, redirect to login page with ?next=<current_path>
        redirect_url = f"{self.login_url}?next={request.path}"
        return redirect(redirect_url)
