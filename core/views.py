# core/views.py
from datetime import timedelta
import logging
import uuid

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.models import User, Group
from django.contrib.auth import logout
from django.http import HttpResponseNotAllowed, JsonResponse, Http404
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from django.template import TemplateDoesNotExist

from .forms import CreateUserForm, AttendanceForm, LeaveApplicationForm, DelegationForm
from .models import Attendance, LeaveApplication, Delegation
from rawmaterials.models import Fabric

logger = logging.getLogger(__name__)


# ----------------- small logging helper -----------------
def _log_request_entry(request, tag="REQ"):
    """
    Create a short request id and log basic request info.
    Returns the req_id (string) so callers can include it in later logs.
    """
    req_id = uuid.uuid4().hex[:8]
    remote = request.META.get("REMOTE_ADDR")
    ua = request.META.get("HTTP_USER_AGENT", "")[:256]
    method = request.method
    path = request.path
    user = request.user.username if request.user.is_authenticated else None

    # Light summary of POST data (avoid logging everything or files)
    post_summary = {}
    if method == "POST":
        for k in ("start_date", "end_date", "reason", "action"):
            if k in request.POST:
                post_summary[k] = request.POST.get(k)
    logger.info("[%s] %s START user=%s method=%s path=%s remote=%s ua=%s data=%s",
                req_id, tag, user, method, path, remote, ua, post_summary)
    return req_id


# ----------------- role helpers -----------------
def _in_group(user, group_name):
    return user.groups.filter(name=group_name).exists()


def is_admin(user):
    """Admin = superuser OR group 'Admin'."""
    return user.is_superuser or _in_group(user, "Admin")


def is_manager(user):
    """Manager = group 'Manager' OR admin (admins implicitly act as managers)."""
    return _in_group(user, "Manager") or is_admin(user)


def is_employee(user):
    """
    Employee membership:
      - group 'Employee'
      - managers and admins count as employees for permission purposes
    This simplifies endpoint checks where managers/admins should also be allowed.
    """
    return _in_group(user, "Employee") or is_manager(user)


# ----------------- explicit logout (accepts GET & POST) -----------------
@login_required
def explicit_logout(request):
    """
    Explicit logout endpoint that accepts GET and POST.
    Use this if the default logout view is being shadowed or rejecting methods.
    """
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect(getattr(settings, "LOGOUT_REDIRECT_URL", "/accounts/login/"))


# ----------------- user admin / manager helpers -----------------
@login_required
@user_passes_test(lambda u: is_admin(u) or is_manager(u))
def create_user(request):
    """
    Create a new user and assign to a Group (designation).
    Accessible by Admin and Manager (per your spec).
    Password is provided by the admin/manager via the form (password1/password2).
    """
    req_id = _log_request_entry(request, tag="CREATE_USER") if request.method == "POST" else None

    if request.method == "POST":
        form = CreateUserForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            first_name = form.cleaned_data["first_name"]
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password1"]

            # Create user (hashes password)
            user = User.objects.create_user(username=username, email=email, password=password)
            user.first_name = first_name
            user.is_active = True
            user.save()

            # --- Assign to group (supports both new 'designation' and legacy 'role') ---
            designation_value = form.cleaned_data.get("designation")
            if not designation_value:
                designation_value = form.cleaned_data.get("role")

            assigned_group = None
            try:
                # If form returns a Group instance (ModelChoiceField), use it directly
                if isinstance(designation_value, Group):
                    assigned_group = designation_value
                elif designation_value:
                    # If it's a string like "Manager", get_or_create the Group
                    assigned_group, _ = Group.objects.get_or_create(name=str(designation_value))
            except Exception:
                # Fallback to ensuring there's at least an Employee group
                assigned_group, _ = Group.objects.get_or_create(name=str(designation_value or "Employee"))

            if assigned_group:
                user.groups.add(assigned_group)

            logger.info("[%s] CREATE_USER created user=%s assigned_group=%s", req_id, username, assigned_group.name if assigned_group else None)
            messages.success(request, f"User {username} created successfully and assigned to '{assigned_group.name if assigned_group else '—'}'.")
            return redirect("core:user_list")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = CreateUserForm()
    return render(request, "core/create_user.html", {"form": form})


@login_required
def user_list(request):
    """
    List users with their first group (role) displayed.
    All authenticated users can view (per your spec Managers & Employees can view users).
    Only Admin can delete (template uses `can_delete`).
    """
    users = User.objects.all().order_by("-date_joined")
    users_with_role = []
    for u in users:
        groups = u.groups.all()
        role = groups[0].name if groups else "—"
        users_with_role.append((u, role))

    # let template know whether delete controls should be shown
    can_delete = is_admin(request.user)

    return render(request, "core/user_list.html", {"users_with_role": users_with_role, "can_delete": can_delete})


@login_required
@user_passes_test(is_admin)
def delete_user(request, pk):
    """
    GET: show confirmation page
    POST: perform deletion (only for Admin)
    Safety:
      - Prevent deleting yourself.
      - Prevent a non-superuser from deleting another superuser.
    """
    req_id = _log_request_entry(request, tag="DELETE_USER") if request.method == "POST" else None

    user_to_delete = get_object_or_404(User, pk=pk)

    # Disallow deleting self (accidental lockout)
    if user_to_delete == request.user:
        messages.error(request, "You cannot delete your own account.")
        return redirect(reverse("core:user_list"))

    # If target is superuser, only allow deletion if requester is also superuser
    if user_to_delete.is_superuser and not request.user.is_superuser:
        messages.error(request, "Only a superuser may delete other superuser accounts.")
        return redirect(reverse("core:user_list"))

    if request.method == "GET":
        # Render a confirmation template. Template should POST back to same URL.
        return render(request, "core/user_confirm_delete.html", {"target_user": user_to_delete})

    if request.method == "POST":
        try:
            with transaction.atomic():
                username = user_to_delete.username
                # Optionally: perform any cleanup here (cascade, logs, related object updates)
                user_to_delete.delete()
            logger.info("[%s] DELETE_USER deleted username=%s by=%s", req_id, username, request.user.username)
            messages.success(request, f"User '{username}' has been deleted.")
        except Exception as exc:
            logger.exception("[%s] DELETE_USER failed target=%s by=%s exc=%s", req_id, user_to_delete.username, request.user.username, exc)
            messages.error(request, "Could not delete user right now. " + str(exc))
        return redirect(reverse("core:user_list"))

    return HttpResponseNotAllowed(["GET", "POST"])


# ----------------- Dashboard and supporting views -----------------
@login_required
def dashboard(request):
    """
    Role-aware dashboard. Renders one of:
      - 'core/dashboard_admin.html' for Admin
      - 'core/dashboard_manager.html' for Manager
      - 'core/dashboard_employee.html' for Employee (default)

    If a role-specific template is missing, fall back to the employee dashboard
    to avoid a TemplateDoesNotExist 500.
    """
    # Common metrics
    fabric_count = Fabric.objects.count()
    fabrics_sample = Fabric.objects.select_related("vendor").all()[:5]
    today = timezone.localdate()

    # Attendance: today's record for the current user (if any)
    try:
        today_attendance = Attendance.objects.filter(user=request.user, date=today).first()
    except Exception:
        today_attendance = None

    # Pending leaves (for admins)
    pending_leaves_count = LeaveApplication.objects.filter(status=LeaveApplication.STATUS_PENDING).count()

    # Delegations visible to user
    if is_admin(request.user):
        delegations_qs = Delegation.objects.all().order_by("-created_at")[:10]
    else:
        # be defensive: allow both `request.user.delegations` related_name or filter by assignees
        try:
            delegations_qs = request.user.delegations.filter(active=True).order_by("-created_at")[:10]
        except Exception:
            delegations_qs = Delegation.objects.filter(assignees=request.user, active=True).order_by("-created_at")[:10]

    context = {
        "fabric_count": fabric_count,
        "fabrics_sample": fabrics_sample,
        "today_attendance": today_attendance,
        "pending_leaves_count": pending_leaves_count,
        "delegations": delegations_qs,
    }

    # Choose template by role
    if is_admin(request.user):
        template = "core/dashboard_admin.html"
    elif is_manager(request.user):
        template = "core/dashboard_manager.html"
    else:
        template = "core/dashboard_employee.html"

    # Render with fallback if template missing
    try:
        return render(request, template, context)
    except TemplateDoesNotExist:
        logger.warning("Dashboard template %s not found; falling back to employee dashboard for user=%s", template, request.user.username)
        return render(request, "core/dashboard_employee.html", context)


@login_required
def login_time_toggle(request):
    """
    AJAX/POST endpoint called when user presses Login button.
    - Creates login_time if none exists for today.
    - Sets logout_time if login exists but logout empty.
    Returns JSON with status and timestamps.
    """
    req_id = _log_request_entry(request, tag="LOGIN_TOGGLE") if request.method == "POST" else None

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    # basic permission: only employees and higher can use it
    if not is_employee(request.user):
        return JsonResponse({"error": "Permission denied."}, status=403)

    ip = request.META.get("REMOTE_ADDR")
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:512]

    # Record login/logout
    try:
        attendance = Attendance.record_login(request.user, ip_address=ip, user_agent=user_agent)
        logger.info("[%s] LOGIN_TOGGLE recorded attendance id=%s user=%s", req_id, attendance.id, request.user.username)
    except Exception as exc:
        logger.exception("[%s] LOGIN_TOGGLE failed user=%s exc=%s", req_id, request.user.username, exc)
        return JsonResponse({"error": "Could not record attendance.", "details": str(exc)}, status=500)

    data = {
        "id": attendance.id,
        "date": attendance.date.isoformat(),
        "login_time": attendance.login_time.isoformat() if attendance.login_time else None,
        "logout_time": attendance.logout_time.isoformat() if attendance.logout_time else None,
        "status": attendance.status,
    }
    return JsonResponse({"ok": True, "attendance": data})


@login_required
def attendance_list(request):
    """
    Shows attendance records.
    - Admin: all records (optionally filter by user via GET param ?user_id=)
    - Manager/Employee: their own records
    """
    if is_admin(request.user):
        qs = Attendance.objects.select_related("user").order_by("-date", "-login_time")
        user_id = request.GET.get("user_id")
        if user_id:
            qs = qs.filter(user__id=user_id)
    else:
        qs = Attendance.objects.filter(user=request.user).order_by("-date", "-login_time")

    attendances = qs[:200]
    return render(request, "core/attendance_list.html", {"attendances": attendances})


# ----------------- Leave application & approval -----------------
@login_required
def apply_leave(request):
    """Employee applies for leave via LeaveApplicationForm.

    Defensive guards:
    - Prevents exact duplicates (same applicant + same start/end).
    - Prevents very recent duplicate submissions (within RECENT_SECONDS_GUARD).
    - Saves inside a DB transaction.
    """
    req_id = _log_request_entry(request, tag="APPLY_LEAVE") if request.method == "POST" else None

    if request.method == "POST":
        form = LeaveApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.applicant = request.user

            # Defensive duplicate checks
            exact_exists = LeaveApplication.objects.filter(
                applicant=request.user,
                start_date=leave.start_date,
                end_date=leave.end_date,
            ).exists()

            RECENT_SECONDS_GUARD = 10
            recent_threshold = timezone.now() - timedelta(seconds=RECENT_SECONDS_GUARD)
            recent_exists = LeaveApplication.objects.filter(
                applicant=request.user,
                start_date=leave.start_date,
                end_date=leave.end_date,
                applied_at__gte=recent_threshold,
            ).exists()

            if exact_exists or recent_exists:
                logger.warning("[%s] APPLY_LEAVE blocked duplicate exact=%s recent=%s user=%s dates=%s-%s",
                               req_id, exact_exists, recent_exists, request.user.username, leave.start_date, leave.end_date)
                messages.warning(
                    request,
                    "A leave application for these dates was just submitted. If you submitted it once, no further action is needed.",
                )
                return redirect("core:leave_list")

            try:
                with transaction.atomic():
                    leave.save()
                    form.save_m2m()
                logger.info("[%s] APPLY_LEAVE saved leave_id=%s user=%s dates=%s-%s", req_id, leave.pk, request.user.username, leave.start_date, leave.end_date)
                messages.success(request, "Your leave application has been submitted.")
            except Exception as exc:
                logger.exception("[%s] APPLY_LEAVE save failed user=%s exc=%s", req_id, request.user.username, exc)
                messages.error(request, "Could not submit your leave application right now. Please try again.")
            return redirect("core:dashboard")
        else:
            logger.warning("[%s] APPLY_LEAVE invalid form user=%s errors=%s", req_id, request.user.username, form.errors)
            messages.error(request, "Please fix the errors in the leave form.")
    else:
        form = LeaveApplicationForm()
    return render(request, "core/leave_form.html", {"form": form})


@login_required
def leave_list(request):
    """
    Shows leave applications.
    - Admin: sees all (optionally filter by status)
    - Manager/Employee: sees only their own applications
    """
    status_filter = request.GET.get("status")
    if is_admin(request.user):
        qs = LeaveApplication.objects.select_related("applicant").order_by("-applied_at")
        if status_filter:
            qs = qs.filter(status=status_filter)
    else:
        qs = LeaveApplication.objects.filter(applicant=request.user).order_by("-applied_at")

    leaves = qs[:200]

    # Provide a boolean flag for templates so template logic stays simple
    is_admin_user = is_admin(request.user)

    return render(request, "core/leave_list.html", {"leaves": leaves, "is_admin_user": is_admin_user})


@login_required
@user_passes_test(is_admin)
def approve_leave(request, pk):
    """
    Approve or reject a leave application. POST with action=approve|reject and optional notes.
    Only Admin may perform this action.
    """
    req_id = _log_request_entry(request, tag="APPROVE_LEAVE") if request.method == "POST" else None

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    leave = get_object_or_404(LeaveApplication, pk=pk)

    action = request.POST.get("action")
    notes = request.POST.get("notes", "")

    try:
        if action == "approve":
            leave.approve(processed_by_user=request.user, notes=notes)
            logger.info("[%s] APPROVE_LEAVE approved leave_id=%s by=%s", req_id, leave.pk, request.user.username)
            messages.success(request, f"Leave application {leave.pk} approved.")
        elif action == "reject":
            leave.reject(processed_by_user=request.user, notes=notes)
            logger.info("[%s] APPROVE_LEAVE rejected leave_id=%s by=%s", req_id, leave.pk, request.user.username)
            messages.success(request, f"Leave application {leave.pk} rejected.")
        else:
            logger.warning("[%s] APPROVE_LEAVE unknown action=%s by=%s", req_id, action, request.user.username)
            messages.error(request, "Unknown action.")
    except Exception as exc:
        logger.exception("[%s] APPROVE_LEAVE failed leave_id=%s by=%s exc=%s", req_id, leave.pk, request.user.username, exc)
        messages.error(request, "Could not process leave action right now.")

    return redirect(request.POST.get("next") or reverse("core:leave_list"))


# ----------------- Delegation create/list -----------------
@login_required
@user_passes_test(is_admin)
def delegation_create(request):
    """Admin can create delegations and assign employees."""
    req_id = _log_request_entry(request, tag="DELEGATION_CREATE") if request.method == "POST" else None

    if request.method == "POST":
        form = DelegationForm(request.POST)
        if form.is_valid():
            delegation = form.save(commit=False)
            delegation.created_by = request.user
            delegation.save()
            form.save_m2m()
            logger.info("[%s] DELEGATION_CREATE created id=%s by=%s", req_id, delegation.pk, request.user.username)
            messages.success(request, "Delegation created.")
            return redirect("core:dashboard")
        else:
            logger.warning("[%s] DELEGATION_CREATE invalid form by=%s errors=%s", req_id, request.user.username, form.errors)
            messages.error(request, "Please fix the errors in the delegation form.")
    else:
        form = DelegationForm()
    return render(request, "core/delegation_form.html", {"form": form})


@login_required
def delegation_list(request):
    """
    List delegations.
    - Admin: sees all delegations (optionally filtered)
    - Manager/Employee: sees only those assigned to them
    """
    if is_admin(request.user):
        qs = Delegation.objects.order_by("-created_at")
    else:
        # be defensive about relationship presence
        try:
            qs = request.user.delegations.order_by("-created_at")
        except Exception:
            qs = Delegation.objects.filter(assignees=request.user).order_by("-created_at")

    delegations = qs[:200]
    return render(request, "core/delegation_list.html", {"delegations": delegations})
