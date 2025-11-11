# workorders/models.py
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()


class PackagingStageManager(models.Manager):
    """
    Manager helpers for PackagingStage.
    - for_user(user): returns queryset filtered by visibility rules:
        - superusers or staff (is_staff) -> all stages
        - regular users -> only stages where assigned_to == user
    """
    def for_user(self, user):
        if user is None:
            return self.none()
        if user.is_superuser or getattr(user, 'is_staff', False):
            return self.all()
        return self.filter(assigned_to=user)


class WorkOrder(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_READY = 'ready'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Packaging'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_READY, 'Ready for Dispatch'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    order_id = models.CharField(max_length=120, db_index=True)
    variant_ordered = models.CharField(max_length=200)  # could be FK to your product model later
    quantity_ordered = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"WO #{self.pk} ({self.order_id}) - {self.get_status_display()}"

    def check_and_update_status(self):
        """
        Set WorkOrder.status depending on stages.
        - If all stages completed -> Ready for Dispatch
        - If any stage in_progress -> In Progress
        - Else -> Pending Packaging
        """
        stages = list(self.stages.all())
        if stages and all(s.stage_status == PackagingStage.STATUS_COMPLETED for s in stages):
            new_status = self.STATUS_READY
        elif any(s.stage_status == PackagingStage.STATUS_IN_PROGRESS for s in stages):
            new_status = self.STATUS_IN_PROGRESS
        else:
            new_status = self.STATUS_PENDING

        if new_status != self.status:
            self.status = new_status
            self.save(update_fields=['status'])


class Notification(models.Model):
    """
    Simple DB-backed notification for user-to-user messages related to packaging stages.
    Kept minimal: from_user (optional), to_user, message, stage (optional), is_read, created_at.
    """
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        related_name='sent_notifications', on_delete=models.SET_NULL
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=False,
        related_name='notifications', on_delete=models.CASCADE
    )
    stage = models.ForeignKey('PackagingStage', null=True, blank=True, on_delete=models.SET_NULL)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notif to {self.to_user} - {self.message[:50]}"

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])

    @classmethod
    def create(cls, to_user, message, from_user=None, stage=None):
        """
        Convenience method to create a notification.
        """
        if to_user is None:
            return None
        return cls.objects.create(from_user=from_user, to_user=to_user, message=message, stage=stage)


class PackagingStage(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
    ]

    work_order = models.ForeignKey(WorkOrder, related_name='stages', on_delete=models.CASCADE)
    stage_name = models.CharField(max_length=150)
    # admin can set this to assign a stage to a specific employee
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_stages'
    )
    stage_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    completion_date = models.DateTimeField(null=True, blank=True)
    image = models.ImageField(upload_to='packaging/stage_images/', null=True, blank=True)

    # handoff fields
    received_confirmed = models.BooleanField(default=False)
    received_date = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name='received_stages',
        on_delete=models.SET_NULL
    )
    is_delayed = models.BooleanField(default=False)

    objects = PackagingStageManager()

    class Meta:
        ordering = ['id']  # first stage -> last stage

    def __str__(self):
        return f"{self.stage_name} ({self.get_stage_status_display()})"

    def is_visible_to(self, user):
        """
        Returns True if the given `user` should see this stage.
        - staff/superuser -> True
        - assigned user -> True
        - otherwise -> False
        """
        if user is None:
            return False
        if user.is_superuser or getattr(user, 'is_staff', False):
            return True
        return self.assigned_to_id == getattr(user, 'id', None)

    def get_next_stage(self):
        """
        Return next PackagingStage for the same work_order, or None if last.
        Ordering by PK (or other ordering field) is used as stage sequence.
        """
        return PackagingStage.objects.filter(work_order=self.work_order, id__gt=self.id).order_by('id').first()

    def get_previous_stage(self):
        """
        Return previous PackagingStage for the same work_order, or None if first.
        """
        return PackagingStage.objects.filter(work_order=self.work_order, id__lt=self.id).order_by('-id').first()

    def mark_in_progress(self, by_user=None):
        """
        Mark this stage in progress. Optionally check permissions in the view before calling.
        """
        self.stage_status = self.STATUS_IN_PROGRESS
        self.save(update_fields=['stage_status'])
        self.work_order.check_and_update_status()

    def mark_completed(self, by_user=None, image_file=None):
        """
        Mark completed and optionally attach an image. This method will:
         - mark the current stage completed,
         - set completion_date,
         - optionally save image,
         - check and update related WorkOrder status,
         - create a Notification for the next assigned user (if any) informing them that task was sent.

        It's wrapped in a transaction to ensure atomicity when updating multiple models.
        """
        with transaction.atomic():
            # update this stage
            self.stage_status = self.STATUS_COMPLETED
            self.completion_date = timezone.now()
            if image_file:
                # attach image and include it in update_fields
                self.image = image_file
                self.save(update_fields=['stage_status', 'completion_date', 'image'])
            else:
                self.save(update_fields=['stage_status', 'completion_date'])

            # update workorder status
            self.work_order.check_and_update_status()

            # notify next stage's assigned user (if any)
            next_stage = self.get_next_stage()
            if next_stage and next_stage.assigned_to:
                msg = (
                    f"Task received for stage '{next_stage.stage_name}' "
                    f"of WorkOrder {self.work_order.order_id or self.work_order.pk}. "
                    f"Previous stage '{self.stage_name}' completed by "
                    f"{getattr(by_user, 'get_full_name', lambda: str(by_user))() if by_user else 'previous user'}."
                )
                Notification.create(
                    to_user=next_stage.assigned_to,
                    from_user=by_user,
                    message=msg,
                    stage=next_stage
                )

    def confirm_received(self, by_user=None):
        """
        Confirm handoff receipt. Calculate delay using settings threshold.
        This method will:
         - mark received_confirmed=True, set received_by and received_date
         - compute delay flag
         - notify the previous assigned user (if any) that task was received (ack)
        """
        with transaction.atomic():
            self.received_confirmed = True
            self.received_by = by_user or None
            self.received_date = timezone.now()

            # compute delay
            threshold_hr = getattr(settings, 'PACKAGING_HANDOFF_THRESHOLD_HOURS', 2)
            if self.completion_date and self.received_date:
                delta = self.received_date - self.completion_date
                self.is_delayed = delta.total_seconds() > threshold_hr * 3600

            self.save(update_fields=['received_confirmed', 'received_date', 'received_by', 'is_delayed'])

            # notify previous stage assigned user (ack back)
            prev_stage = self.get_previous_stage()
            if prev_stage and prev_stage.assigned_to:
                ack_msg = (
                    f"Task '{self.stage_name}' of WorkOrder {self.work_order.order_id or self.work_order.pk} "
                    f"was received by {getattr(by_user, 'get_full_name', lambda: str(by_user))() if by_user else 'the user'}. "
                    "Task Sent Successfully."
                )
                Notification.create(
                    to_user=prev_stage.assigned_to,
                    from_user=by_user,
                    message=ack_msg,
                    stage=prev_stage
                )
