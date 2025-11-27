# workorders/views.py
import random
import logging
import json
import base64
import hmac
import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponseForbidden, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from .models import WorkOrder, PackagingStage, Notification

logger = logging.getLogger(__name__)
User = get_user_model()

# Default packaging stages
DEFAULT_STAGES = ["Quality Check", "Folding & Tagging", "Packaging"]


# ------------------------
# Helpers
# ------------------------
def _is_ajax(request):
    accept = request.META.get('HTTP_ACCEPT', '')
    xhr = request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'
    return xhr or 'application/json' in accept


def user_is_allowed_on_stage(user, stage):
    """Return True if `user` is allowed to act on `stage` (staff or assigned user)."""
    if user is None or stage is None:
        return False
    if user.is_superuser or getattr(user, 'is_staff', False):
        return True
    return stage.assigned_to_id == getattr(user, 'id', None)


# ---------------------------------------------------------------
# WORK ORDER VIEWS
# ---------------------------------------------------------------

class WorkOrderListView(LoginRequiredMixin, ListView):
    model = WorkOrder
    template_name = 'workorders/workorder_list.html'
    context_object_name = 'workorders'
    paginate_by = 20


class WorkOrderDetailView(LoginRequiredMixin, DetailView):
    model = WorkOrder
    template_name = 'workorders/workorder_detail.html'
    context_object_name = 'workorder'

    def get_context_data(self, **kwargs):
        """
        Provide:
         - 'stages': list of PackagingStage objects visible to the user
         - annotate each stage with:
            - can_act (bool): whether current user can act on stage
            - assigned_to_pk (int or None): quick compare value for template
        """
        context = super().get_context_data(**kwargs)
        workorder = self.object
        user = self.request.user

        # Query stages visible to this user
        stages_qs = PackagingStage.objects.for_user(user).filter(work_order=workorder).order_by('id')

        stages = []
        for s in stages_qs:
            assigned_to_id = getattr(s, 'assigned_to_id', None)
            can_act = False
            if user:
                if user.is_superuser or getattr(user, 'is_staff', False):
                    can_act = True
                elif assigned_to_id is not None and assigned_to_id == getattr(user, 'id', None):
                    can_act = True

            setattr(s, 'can_act', can_act)
            setattr(s, 'assigned_to_pk', assigned_to_id)
            stages.append(s)

        context['stages'] = stages

        if user.is_superuser or getattr(user, 'is_staff', False):
            context['employee_choices'] = User.objects.filter(is_staff=False).order_by('first_name', 'username')
        else:
            context['employee_choices'] = User.objects.filter(pk=user.pk)

        return context


class WorkOrderCreateView(LoginRequiredMixin, CreateView):
    model = WorkOrder
    fields = ['order_id', 'variant_ordered', 'quantity_ordered']
    template_name = 'workorders/workorder_form.html'

    def get_success_url(self):
        return reverse('workorders:detail', kwargs={'pk': self.object.pk})


# ---------------------------------------------------------------
# DELETE WORKORDER
# ---------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def workorder_delete(request, pk):
    """
    Confirm (GET) and delete (POST) a WorkOrder.
    Only staff or superuser can delete.
    """
    wo = get_object_or_404(WorkOrder, pk=pk)

    # Permission check
    if not (request.user.is_superuser or getattr(request.user, 'is_staff', False)):
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'message': 'Forbidden'}, status=403)
        messages.error(request, "You are not authorized to delete work orders.")
        return redirect('workorders:detail', pk=wo.pk)

    if request.method == "POST":
        try:
            # keep the order identifier for message after deletion
            identifier = wo.order_id or f"id:{wo.pk}"
            wo.delete()
            messages.success(request, f"WorkOrder {identifier} deleted.")
            if _is_ajax(request):
                return JsonResponse({'ok': True, 'message': 'Deleted'})
            return redirect('workorders:list')
        except Exception:
            logger.exception("Error deleting WorkOrder %s", wo.pk)
            if _is_ajax(request):
                return JsonResponse({'ok': False, 'message': 'Could not delete'}, status=500)
            messages.error(request, "Could not delete the work order.")
            return redirect('workorders:detail', pk=wo.pk)

    # GET -> render confirmation template
    return render(request, 'workorders/workorder_confirm_delete.html', {'workorder': wo})


# ---------------------------------------------------------------
# E-COM INDEX & PROVIDER LIST VIEWS
# ---------------------------------------------------------------

@login_required
def ecom_index(request):
    return render(request, 'workorders/ecom_index.html')


@login_required
def shopify_list(request):
    qs = WorkOrder.objects.filter(source='shopify').order_by('-created_at')
    paginator = Paginator(qs, 50)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    return render(request, 'workorders/workorder_list.html', {'workorders': page_obj})


@login_required
def faire_list(request):
    qs = WorkOrder.objects.filter(source='faire').order_by('-created_at')
    paginator = Paginator(qs, 50)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    return render(request, 'workorders/workorder_list.html', {'workorders': page_obj})


@login_required
def custom_order_list(request):
    qs = WorkOrder.objects.filter(source='custom').order_by('-created_at')
    paginator = Paginator(qs, 50)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    return render(request, 'workorders/workorder_list.html', {'workorders': page_obj})


@login_required
def custom_order_create(request):
    if request.method == 'POST':
        order_id = request.POST.get('order_id') or f'CUSTOM-{random.randint(1000,9999)}'
        variant = request.POST.get('variant_ordered') or 'Manual Variant'
        qty = int(request.POST.get('quantity_ordered') or 1)

        wo = WorkOrder.objects.create(
            order_id=order_id,
            variant_ordered=variant,
            quantity_ordered=qty,
            source='custom'
        )

        employees = User.objects.filter(is_staff=False)
        for stage_name in DEFAULT_STAGES:
            assigned = employees.order_by('?').first() if employees.exists() else None
            PackagingStage.objects.create(work_order=wo, stage_name=stage_name, assigned_to=assigned)

        messages.success(request, "Custom order created.")
        return redirect('workorders:detail', pk=wo.pk)

    return render(request, 'workorders/custom_create.html')


# ---------------------------------------------------------------
# SIMULATE SHOPIFY ORDER (existing)
# ---------------------------------------------------------------

@login_required
@transaction.atomic
def create_random_workorder(request):
    if request.method != 'POST':
        return redirect('workorders:list')

    order_id = f"SHOP-{random.randint(1000, 9999)}"
    variant = random.choice(['Red / S', 'Blue / M', 'Green / L', 'Plain / OneSize'])
    quantity = random.randint(1, 5)

    wo = WorkOrder.objects.create(
        order_id=order_id,
        variant_ordered=variant,
        quantity_ordered=quantity,
        status=WorkOrder.STATUS_PENDING,
        source='shopify'
    )

    employees = User.objects.filter(is_staff=False)
    for stage_name in DEFAULT_STAGES:
        assigned = employees.order_by('?').first() if employees.exists() else (User.objects.order_by('?').first() if User.objects.exists() else None)
        PackagingStage.objects.create(work_order=wo, stage_name=stage_name, assigned_to=assigned)

    return redirect('workorders:detail', pk=wo.pk)


# ---------------------------------------------------------------
# STAGE ACTIONS (assign/start/complete/confirm_received)
# ---------------------------------------------------------------

@login_required
def stage_action(request, pk):
    if request.method != 'POST':
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'message': 'Invalid request method (POST required).'}, status=405)
        messages.error(request, "Invalid request method.")
        return redirect('workorders:list')

    stage = get_object_or_404(PackagingStage, pk=pk)
    action = request.POST.get('action')

    logger.info(
        "stage_action called: user=%s id=%s is_staff=%s action=%s stage=%s assigned_to=%s status=%s",
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
            if _is_ajax(request):
                return JsonResponse({'ok': False, 'message': msg}, status=403)
            messages.error(request, msg)
            return redirect('workorders:detail', pk=stage.work_order.pk)

        user_id = request.POST.get('assigned_to')
        time_limit = request.POST.get('time_limit_hours')

        if user_id:
            try:
                assigned_user = User.objects.get(pk=int(user_id))
            except (User.DoesNotExist, ValueError):
                assigned_user = None
        else:
            assigned_user = None

        try:
            if hasattr(stage, 'assign') and callable(getattr(stage, 'assign')):
                stage.assign(user=assigned_user, time_limit_hours=time_limit, assigned_by=request.user)
            else:
                stage.assigned_to = assigned_user
                if time_limit:
                    try:
                        tl = int(time_limit)
                        stage.time_limit_hours = tl
                        stage.due_by = timezone.now() + timezone.timedelta(hours=tl)
                    except Exception:
                        pass
                stage.save(update_fields=['assigned_to', 'time_limit_hours', 'due_by'])
                if assigned_user:
                    Notification.create(to_user=assigned_user, from_user=request.user,
                                        message=f"You were assigned stage '{stage.stage_name}' for WO {stage.work_order.order_id}")
            msg = "Assignment updated."
            if _is_ajax(request):
                return JsonResponse({
                    'ok': True,
                    'message': msg,
                    'assigned_to': assigned_user.pk if assigned_user else None,
                    'time_limit_hours': getattr(stage, 'time_limit_hours', None),
                    'due_by': getattr(stage, 'due_by', None).isoformat() if getattr(stage, 'due_by', None) else None
                })
            messages.success(request, msg)
            return redirect('workorders:detail', pk=stage.work_order.pk)
        except Exception:
            logger.exception("Error in assigning stage %s", stage.pk)
            if _is_ajax(request):
                return JsonResponse({'ok': False, 'message': 'Could not assign stage.'}, status=500)
            messages.error(request, "Could not assign stage.")
            return redirect('workorders:detail', pk=stage.work_order.pk)

    # For other actions, ensure the acting user is allowed to operate on this stage.
    if not user_is_allowed_on_stage(request.user, stage):
        msg = "You are not authorized to perform actions on this stage."
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'message': msg}, status=403)
        messages.error(request, msg)
        return redirect('workorders:detail', pk=stage.work_order.pk)

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
                    next_stage = stage.get_next_stage()
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
                    prev_stage = stage.get_previous_stage()
                    if prev_stage and prev_stage.assigned_to:
                        Notification.create(
                            to_user=prev_stage.assigned_to,
                            from_user=request.user,
                            message=f"Task Sent Successfully for stage '{stage.stage_name}' on WO #{stage.work_order.pk}",
                            stage=stage,
                        )
                    if _is_ajax(request):
                        return JsonResponse({'ok': True, 'message': msg})
                    messages.success(request, msg)

            else:
                msg = "Unknown action."
                if _is_ajax(request):
                    return JsonResponse({'ok': False, 'message': msg}, status=400)
                messages.error(request, msg)

        except Exception as exc:
            logger.exception("Error while performing stage action '%s' on stage %s: %s", action, stage.pk, exc)
            msg = "An unexpected error occurred."
            if _is_ajax(request):
                return JsonResponse({'ok': False, 'message': msg}, status=500)
            messages.error(request, msg)

    return redirect('workorders:detail', pk=stage.work_order.pk)


# ---------------------------------------------------------------
# NOTIFICATIONS VIEWS
# ---------------------------------------------------------------

@login_required
def notifications_list(request):
    qs = Notification.objects.filter(to_user=request.user).select_related('from_user', 'stage', 'stage__work_order').order_by('-created_at')
    paginator = Paginator(qs, 50)
    page_number = request.GET.get('page', 1)
    page = paginator.get_page(page_number)
    try:
        unread_count = qs.filter(is_read=False).count()
    except Exception:
        unread_count = 0
    context = {
        'notifications': page,
        'page_obj': page,
        'paginator': paginator,
        'unread_count': unread_count,
    }
    return render(request, 'workorders/notifications_list.html', context)


@login_required
def notification_mark_read(request, pk):
    if request.method != 'POST':
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'message': 'POST required'}, status=405)
        raise Http404()

    notif = get_object_or_404(Notification, pk=pk, to_user=request.user)
    try:
        if hasattr(notif, 'mark_read') and callable(getattr(notif, 'mark_read')):
            notif.mark_read()
        else:
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
    if request.method != 'POST':
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'message': 'POST required'}, status=405)
        return redirect('workorders:notifications')

    try:
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


# ---------------------------------------------------------------
# COMPLETE & DISPATCH (existing)
# ---------------------------------------------------------------

def complete_and_proceed_to_dispatch(request):
    if request.method != 'POST':
        return redirect('workorders:list')

    order_id = request.POST.get('order_id')
    stage_id = request.POST.get('stage_id')

    order = get_object_or_404(WorkOrder, pk=order_id)

    with transaction.atomic():
        if stage_id:
            try:
                stage = PackagingStage.objects.get(pk=stage_id)
                stage.stage_status = PackagingStage.STATUS_COMPLETED
                stage.completion_date = timezone.now()
                stage.save(update_fields=['stage_status', 'completion_date'])
            except PackagingStage.DoesNotExist:
                pass

        order.status = WorkOrder.STATUS_READY
        order.save()

        prefill = {
            'work_order': order.pk,
            'variant': getattr(order, 'variant_ordered', '') or '',
            'order_value': getattr(order, 'total_price', '') or '',
        }

        request.session['dispatch_prefill'] = prefill

    messages.success(request, "Packaging marked complete. Opened dispatch form with pre-filled data.")
    return redirect(reverse('dispatch:new_dispatch'))


# ---------------------------------------------------------------
# SHOPIFY WEBHOOK (real-time sync)
# ---------------------------------------------------------------

@csrf_exempt
def shopify_webhook(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    secret = getattr(settings, 'SHOPIFY_WEBHOOK_SECRET', None)
    if not secret:
        logger.error("SHOPIFY_WEBHOOK_SECRET not configured.")
        return HttpResponse(status=500)

    try:
        hmac_header = request.META.get('HTTP_X_SHOPIFY_HMAC_SHA256', '')
        body = request.body or b''
        digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
        computed_hmac = base64.b64encode(digest).decode()
        if not hmac.compare_digest(computed_hmac, hmac_header):
            logger.warning("Invalid Shopify webhook HMAC. Header=%s computed=%s", hmac_header, computed_hmac)
            return HttpResponseForbidden("Invalid HMAC signature")
    except Exception:
        logger.exception("Error verifying Shopify webhook HMAC.")
        return HttpResponseForbidden("HMAC verification failed")

    try:
        payload = json.loads(request.body.decode('utf-8') or "{}")
    except Exception:
        logger.exception("Could not parse Shopify webhook payload.")
        return HttpResponse(status=400)

    shopify_id = str(payload.get('id') or payload.get('order_number') or '')
    order_name = payload.get('name') or payload.get('order_number') or ''
    created_at = payload.get('created_at')
    total_price = payload.get('total_price') or payload.get('subtotal_price') or 0
    currency = payload.get('currency') or payload.get('currency_code') or payload.get('currency') or ''
    customer = payload.get('customer') or {}
    customer_name = ' '.join(filter(None, [customer.get('first_name'), customer.get('last_name')])) or payload.get('customer_name') or ''
    email = payload.get('email') or customer.get('email') or ''

    created_dt = None
    if created_at:
        try:
            created_dt = parse_datetime(created_at)
        except Exception:
            created_dt = None

    try:
        wo, created = WorkOrder.objects.update_or_create(
            shopify_order_id=shopify_id,
            defaults={
                'order_id': order_name or f"SHOP-{shopify_id}",
                'variant_ordered': ', '.join([li.get('title', '') for li in payload.get('line_items', [])]) or '',
                'quantity_ordered': sum(int(li.get('quantity', 1)) for li in payload.get('line_items', [])) or 1,
                'source': 'shopify',
                'customer_name': customer_name,
                'email': email,
                'total_price': total_price,
                'currency': currency or 'USD',
                'created_at': created_dt or timezone.now(),
                'raw': payload,
            }
        )
    except Exception:
        logger.exception("Error creating/updating WorkOrder from Shopify payload.")
        return HttpResponse(status=500)

    try:
        if created or not wo.stages.exists():
            employees = User.objects.filter(is_staff=False)
            for stage_name in DEFAULT_STAGES:
                assigned = employees.order_by('?').first() if employees.exists() else None
                PackagingStage.objects.create(work_order=wo, stage_name=stage_name, assigned_to=assigned)
    except Exception:
        logger.exception("Error creating default stages for WorkOrder %s", wo.pk)

    logger.info("Shopify order synced into WorkOrder id=%s shopify_id=%s created=%s", wo.pk, shopify_id, created)
    return HttpResponse(status=200)


# Placeholder for Faire webhook (future)
@csrf_exempt
def faire_webhook(request):
    return HttpResponse(status=204)
