import random
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponseForbidden, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.utils import timezone

from .models import WorkOrder, PackagingStage, Notification

logger = logging.getLogger(__name__)
User = get_user_model()

# Default packaging stages
DEFAULT_STAGES = ["Quality Check", "Folding & Tagging", "Final Bagging"]


# ---------------------------------------------------------------
# WORK ORDER VIEWS
# ---------------------------------------------------------------

class WorkOrderListView(LoginRequiredMixin, ListView):
    """List all work orders."""
    model = WorkOrder
    template_name = 'workorders/workorder_list.html'
    context_object_name = 'workorders'
    paginate_by = 20


class WorkOrderDetailView(LoginRequiredMixin, DetailView):
    """Show details and packaging stages for a work order."""

    model = WorkOrder
    template_name = 'workorders/workorder_detail.html'
    context_object_name = 'workorder'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        workorder = self.object
        user = self.request.user

        # Only provide stages visible to this user.
        # Staff/superuser -> all stages. Employees -> only their assigned stages.
        stages_qs = PackagingStage.objects.for_user(user).filter(work_order=workorder).order_by('id')
        context['stages'] = stages_qs

        # For admin UI: provide list of employees to choose from when assigning stages.
        # Show only non-staff users as employees (adjust if you use a Group/flag instead).
        if user.is_superuser or getattr(user, 'is_staff', False):
            context['employee_choices'] = User.objects.filter(is_staff=False).order_by('first_name', 'username')
        else:
            context['employee_choices'] = User.objects.filter(pk=user.pk)

        return context


class WorkOrderCreateView(LoginRequiredMixin, CreateView):
    """Manual creation of a work order (rarely used; mostly simulation)."""
    model = WorkOrder
    fields = ['order_id', 'variant_ordered', 'quantity_ordered']
    template_name = 'workorders/workorder_form.html'

    def get_success_url(self):
        return self.object.get_absolute_url()


# ---------------------------------------------------------------
# SIMULATE SHOPIFY ORDER
# ---------------------------------------------------------------

@login_required
@transaction.atomic
def create_random_workorder(request):
    """
    Simulates receiving a confirmed Shopify order.
    Creates a WorkOrder with random values and default packaging stages.
    """
    if request.method != 'POST':
        return redirect('workorders:list')

    order_id = f"SHOP-{random.randint(1000, 9999)}"
    variant = random.choice(['Red / S', 'Blue / M', 'Green / L', 'Plain / OneSize'])
    quantity = random.randint(1, 5)

    # Create the Work Order
    wo = WorkOrder.objects.create(
        order_id=order_id,
        variant_ordered=variant,
        quantity_ordered=quantity,
        status=WorkOrder.STATUS_PENDING,
    )

    # Prefer assigning to non-staff (employees) randomly; fallback to any user
    employees = User.objects.filter(is_staff=False)
    for stage_name in DEFAULT_STAGES:
        assigned = employees.order_by('?').first() if employees.exists() else (User.objects.order_by('?').first() if User.objects.exists() else None)
        PackagingStage.objects.create(
            work_order=wo,
            stage_name=stage_name,
            assigned_to=assigned
        )

    return redirect('workorders:detail', pk=wo.pk)


# ---------------------------------------------------------------
# Helper permission util
# ---------------------------------------------------------------

def user_is_allowed_on_stage(user, stage):
    """Return True if `user` is allowed to act on `stage` (staff or assigned user)."""
    if user is None or stage is None:
        return False
    if user.is_superuser or getattr(user, 'is_staff', False):
        return True
    return stage.assigned_to_id == getattr(user, 'id', None)


def _is_ajax(request):
    """
    Basic check for AJAX/JSON requests. Django's request.is_ajax() was removed;
    we check headers instead. This is used to return JSON responses when called from JS.
    """
    accept = request.META.get('HTTP_ACCEPT', '')
    xhr = request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'
    return xhr or 'application/json' in accept


# ---------------------------------------------------------------
# STAGE ACTIONS
# ---------------------------------------------------------------

@login_required
def stage_action(request, pk):
    """
    Handles POST actions from each packaging stage:
    - in_progress: mark stage as 'In Progress' (allowed for assignee or staff)
    - complete: mark as 'Completed' with optional image (allowed for assignee or staff)
    - confirm_received: confirm handoff receipt (allowed for assignee or staff)
    - assign: assign stage to a user (admin/staff only)

    Returns:
      - If non-AJAX: redirect back to workorder detail with messages (existing flow).
      - If AJAX/JSON: returns JsonResponse with {ok: bool, message: str, data: {...}}.
    """
    # Only allow POST for actions
    if request.method != 'POST':
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'message': 'Invalid request method (POST required).'}, status=405)
        messages.error(request, "Invalid request method.")
        return redirect('workorders:list')

    stage = get_object_or_404(PackagingStage, pk=pk)
    action = request.POST.get('action')

    # Debug/logging line to help trace problems (prints user + assignment + state)
    logger.info(
        "stage_action called: user=%s (id=%s, is_staff=%s) action=%s stage=%s assigned_to=%s stage_status=%s",
        getattr(request.user, 'username', None),
        getattr(request.user, 'id', None),
        getattr(request.user, 'is_staff', False),
        action,
        stage.pk,
        stage.assigned_to_id,
        stage.stage_status,
    )

    # Assign action -> only staff/admin can perform
    if action == 'assign':
        if not (request.user.is_superuser or getattr(request.user, 'is_staff', False)):
            msg = "Only staff or admin may assign stages."
            logger.warning("Unauthorized assign attempt: user=%s stage=%s", request.user, stage.pk)
            if _is_ajax(request):
                return JsonResponse({'ok': False, 'message': msg}, status=403)
            messages.error(request, msg)
            return redirect('workorders:detail', pk=stage.work_order.pk)

        user_id = request.POST.get('assigned_to')
        if user_id:
            try:
                assigned_user = User.objects.get(pk=int(user_id))
            except (User.DoesNotExist, ValueError):
                assigned_user = None
        else:
            assigned_user = None

        stage.assigned_to = assigned_user
        stage.save(update_fields=['assigned_to'])
        msg = "Assignment updated."
        if _is_ajax(request):
            return JsonResponse({'ok': True, 'message': msg, 'assigned_to': assigned_user.pk if assigned_user else None})
        messages.success(request, msg)
        return redirect('workorders:detail', pk=stage.work_order.pk)

    # For other actions, ensure the acting user is allowed to operate on this stage.
    if not user_is_allowed_on_stage(request.user, stage):
        msg = "You are not authorized to perform actions on this stage."
        logger.warning(
            "Unauthorized stage action attempt. user=%s (id=%s), stage=%s assigned_to=%s",
            getattr(request.user, 'username', None),
            getattr(request.user, 'id', None),
            stage.pk,
            stage.assigned_to_id,
        )
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'message': msg}, status=403)
        messages.error(request, msg)
        return redirect('workorders:detail', pk=stage.work_order.pk)

    # Use DB lock for safety
    with transaction.atomic():
        stage = PackagingStage.objects.select_for_update().get(pk=stage.pk)

        try:
            if action == 'in_progress':
                if stage.stage_status != PackagingStage.STATUS_PENDING:
                    msg = "Stage cannot be started because it is not in pending state."
                    if _is_ajax(request):
                        return JsonResponse({'ok': False, 'message': msg}, status=400)
                    messages.warning(request, msg)
                else:
                    stage.mark_in_progress(by_user=request.user)
                    msg = f"Stage '{stage.stage_name}' marked In Progress."
                    if _is_ajax(request):
                        return JsonResponse({'ok': True, 'message': msg, 'new_status': stage.stage_status})
                    messages.success(request, msg)

            elif action == 'complete':
                image_file = request.FILES.get('image')
                if stage.stage_status == PackagingStage.STATUS_COMPLETED:
                    msg = "Stage is already completed."
                    if _is_ajax(request):
                        return JsonResponse({'ok': False, 'message': msg}, status=400)
                    messages.warning(request, msg)
                else:
                    stage.mark_completed(by_user=request.user, image_file=image_file)
                    msg = f"Stage '{stage.stage_name}' marked Completed."
                    # If AJAX, we can return info about the next stage (if any) so frontend can enable Received button
                    next_stage = None
                    try:
                        # assume PackagingStage has a helper get_next_stage; if not, compute
                        next_stage = stage.get_next_stage()
                    except Exception:
                        # fallback: find next by id ordering
                        next_stage = PackagingStage.objects.filter(work_order=stage.work_order, id__gt=stage.id).order_by('id').first()

                    next_info = None
                    if next_stage:
                        next_info = {
                            'id': next_stage.pk,
                            'stage_name': next_stage.stage_name,
                            'assigned_to': next_stage.assigned_to.pk if next_stage.assigned_to else None,
                            'stage_status': next_stage.stage_status,
                        }
                    if _is_ajax(request):
                        return JsonResponse({'ok': True, 'message': msg, 'next_stage': next_info})
                    messages.success(request, msg)

            elif action == 'confirm_received':
                if stage.received_confirmed:
                    msg = "Stage already confirmed received."
                    if _is_ajax(request):
                        return JsonResponse({'ok': False, 'message': msg, 'already_confirmed': True}, status=400)
                    messages.warning(request, msg)
                else:
                    stage.confirm_received(by_user=request.user)
                    msg = f"Stage '{stage.stage_name}' handoff confirmed."

                    # Create notifications: notify the previous stage's user that task was sent successfully
                    try:
                        prev_stage = PackagingStage.objects.filter(work_order=stage.work_order, id__lt=stage.id).order_by('-id').first()
                        if prev_stage and prev_stage.assigned_to:
                            Notification.objects.create(
                                to_user=prev_stage.assigned_to,
                                from_user=request.user,
                                message=f"Task Sent Successfully for stage '{stage.stage_name}' on WO #{stage.work_order.pk}",
                                stage=stage,
                            )
                    except Exception:
                        logger.exception("Could not create ack notification for previous stage.")

                    if _is_ajax(request):
                        return JsonResponse({'ok': True, 'message': msg})
                    messages.success(request, msg)

            else:
                msg = "Unknown action."
                logger.error("Unknown action '%s' for stage %s by user %s", action, stage.pk, request.user)
                if _is_ajax(request):
                    return JsonResponse({'ok': False, 'message': msg}, status=400)
                messages.error(request, msg)

        except Exception as exc:
            logger.exception("Error while performing stage action '%s' on stage %s: %s", action, stage.pk, exc)
            msg = "An unexpected error occurred."
            if _is_ajax(request):
                return JsonResponse({'ok': False, 'message': msg}, status=500)
            messages.error(request, msg)

    # Default non-AJAX redirect
    return redirect('workorders:detail', pk=stage.work_order.pk)


# ---------------------------------------------------------------
# NOTIFICATIONS VIEWS
# ---------------------------------------------------------------

@login_required
def notifications_list(request):
    """
    Show recent notifications for the logged-in user.
    Uses Paginator to avoid slicing-then-filtering mistakes.
    Template: workorders/notifications_list.html
    """
    # Filter and order first (no slicing before further QuerySet operations)
    qs = Notification.objects.filter(to_user=request.user).select_related('from_user', 'stage', 'stage__work_order').order_by('-created_at')

    # Paginate (safe)
    paginator = Paginator(qs, 50)  # show 50 per page
    page_number = request.GET.get('page', 1)
    page = paginator.get_page(page_number)

    # Unread count (calculate on full filtered queryset, not on a sliced list)
    try:
        unread_count = qs.filter(is_read=False).count()
    except Exception:
        unread_count = 0

    context = {
        'notifications': page,        # Page object (iterate like usual)
        'page_obj': page,
        'paginator': paginator,
        'unread_count': unread_count,
    }
    return render(request, 'workorders/notifications_list.html', context)


@login_required
def notification_mark_read(request, pk):
    """
    Mark a notification as read. Returns JSON for AJAX calls.
    """
    if request.method != 'POST':
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'message': 'POST required'}, status=405)
        raise Http404()

    notif = get_object_or_404(Notification, pk=pk, to_user=request.user)

    # Prefer model helper if exists
    try:
        if hasattr(notif, 'mark_read') and callable(getattr(notif, 'mark_read')):
            notif.mark_read()
        else:
            # fallback: direct update
            notif.is_read = True
            if hasattr(notif, 'read_at'):
                notif.read_at = timezone.now()
                notif.save(update_fields=['is_read', 'read_at'])
            else:
                notif.save(update_fields=['is_read'])
    except Exception:
        logger.exception("Error marking notification as read: %s", pk)
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'message': 'Could not mark as read'}, status=500)
        messages.error(request, "Could not mark notification as read.")
        return redirect(request.POST.get('next', reverse('workorders:notifications')))

    msg = "Marked as read."
    if _is_ajax(request):
        return JsonResponse({'ok': True, 'message': msg, 'notification_id': notif.pk})

    messages.success(request, msg)
    return redirect(request.POST.get('next', reverse('workorders:notifications')))


@login_required
def notification_mark_all_read(request):
    """
    Bulk-mark all unread notifications for current user as read.
    Efficient server-side operation (single UPDATE).
    """
    if request.method != 'POST':
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'message': 'POST required'}, status=405)
        return redirect('workorders:notifications')

    try:
        # Bulk update (filter then update)
        if hasattr(Notification, 'read_at'):
            Notification.objects.filter(to_user=request.user, is_read=False).update(is_read=True, read_at=timezone.now())
        else:
            Notification.objects.filter(to_user=request.user, is_read=False).update(is_read=True)
    except Exception:
        logger.exception("Error bulk-marking notifications read for user %s", request.user)
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'message': 'Could not mark all as read'}, status=500)
        messages.error(request, "Could not mark all notifications as read.")
        return redirect('workorders:notifications')

    if _is_ajax(request):
        return JsonResponse({'ok': True, 'message': 'All notifications marked read'})

    messages.success(request, "All notifications marked read.")
    return redirect('workorders:notifications')

from workorders.models import WorkOrder, PackagingStage  # PackagingStage is an example

def complete_and_proceed_to_dispatch(request):
    """
    POST-only endpoint that marks a packaging stage complete, updates workorder status,
    stores a small prefill dict in session and redirects to the new dispatch form.
    """
    if request.method != 'POST':
        return redirect('workorders:workorder_list')  # or appropriate fallback

    order_id = request.POST.get('order_id')
    stage_id = request.POST.get('stage_id')  # optional; if you track stages individually

    order = get_object_or_404(WorkOrder, pk=order_id)

    with transaction.atomic():
        # 1) finalize packaging stage (if you have a stage model)
        if stage_id:
            try:
                stage = PackagingStage.objects.get(pk=stage_id)
                stage.status = 'Completed'
                stage.save()
            except PackagingStage.DoesNotExist:
                pass

        # 2) update the workorder status
        # Make sure 'Pending Dispatch' or 'Ready for Dispatch' is a valid status in your WorkOrder model
        order.status = 'Pending Dispatch'  # adapt to your status choices
        order.save()

        # 3) prepare a small dict with the fields used to pre-populate the dispatch form
        prefill = {
            'work_order': order.pk,
            # Replace 'variant' and 'order_value' with the real WorkOrder field names in your model
            'variant': getattr(order, 'variant', '') or '',
            'order_value': getattr(order, 'order_value', '') or '',
        }

        # store in session temporarily (per-user)
        request.session['dispatch_prefill'] = prefill

    messages.success(request, "Packaging marked complete. Opened dispatch form with pre-filled data.")
    return redirect(reverse('dispatch:new_dispatch'))