# file: core/models.py
from datetime import timedelta, date

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator


class Attendance(models.Model):
    """
    Stores a user's daily attendance record. Use Attendance.record_login(user, **meta)
    to handle the "press button to login" behavior (it will create a record for today
    or set logout_time if login already exists).
    """
    STATUS_PRESENT = "present"
    STATUS_ABSENT = "absent"
    STATUS_ON_LEAVE = "on_leave"

    STATUS_CHOICES = [
        (STATUS_PRESENT, "Present"),
        (STATUS_ABSENT, "Absent"),
        (STATUS_ON_LEAVE, "On Leave"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attendances")
    date = models.DateField(default=timezone.localdate)
    login_time = models.DateTimeField(null=True, blank=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PRESENT)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ("user", "date")
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["user", "date"]),
        ]

    def __str__(self):
        return f"Attendance: {self.user} — {self.date} ({self.status})"

    @property
    def worked_duration(self):
        """Return worked timedelta if both login & logout are present, else None."""
        if self.login_time and self.logout_time:
            return self.logout_time - self.login_time
        return None

    @classmethod
    def get_or_create_for_today(cls, user):
        """Return (attendance_obj, created_bool) for today's attendance."""
        today = timezone.localdate()
        obj, created = cls.objects.get_or_create(user=user, date=today, defaults={"status": cls.STATUS_PRESENT})
        return obj, created

    @classmethod
    def record_login(cls, user, ip_address=None, user_agent=None):
        """
        Called when user presses the Login button.
        - If no attendance for today -> sets login_time.
        - If login_time exists and logout_time is empty -> sets logout_time.
        - If both exist -> creates a new record for today with new login_time (rare).
        Returns the attendance instance.
        """
        now = timezone.now()
        attendance, created = cls.get_or_create_for_today(user)
        if attendance.login_time is None:
            attendance.login_time = now
            attendance.ip_address = ip_address
            attendance.user_agent = user_agent or attendance.user_agent
            attendance.status = cls.STATUS_PRESENT
            attendance.save(update_fields=["login_time", "ip_address", "user_agent", "status", "updated_at"])
            return attendance
        if attendance.login_time and attendance.logout_time is None:
            attendance.logout_time = now
            attendance.save(update_fields=["logout_time", "updated_at"])
            return attendance
        # both login and logout exist; create a new attendance row for the same day with new login_time
        # (handles edge cases like multiple sessions)
        new_att = cls.objects.create(
            user=user,
            date=timezone.localdate(),
            login_time=now,
            ip_address=ip_address,
            user_agent=user_agent or "",
            status=cls.STATUS_PRESENT,
        )
        return new_att


class LeaveApplication(models.Model):
    """
    Employee leave application. Admin/CEO should approve/reject.
    """
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    LEAVE_SICK = "sick"
    LEAVE_CASUAL = "casual"
    LEAVE_EARNED = "earned"
    LEAVE_OTHER = "other"

    LEAVE_TYPE_CHOICES = [
        (LEAVE_SICK, "Sick Leave"),
        (LEAVE_CASUAL, "Casual Leave"),
        (LEAVE_EARNED, "Earned Leave"),
        (LEAVE_OTHER, "Other"),
    ]

    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="leave_applications")
    leave_type = models.CharField(max_length=16, choices=LEAVE_TYPE_CHOICES, default=LEAVE_OTHER)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    attachment = models.FileField(upload_to="leave_attachments/", null=True, blank=True)

    applied_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="processed_leaves")
    processed_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-applied_at"]
        indexes = [
            models.Index(fields=["applicant", "status"]),
            models.Index(fields=["start_date", "end_date"]),
        ]

    def __str__(self):
        return f"LeaveApplication: {self.applicant} — {self.start_date} to {self.end_date} ({self.status})"

    @property
    def duration_days(self):
        """Inclusive count of days in the leave range."""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0

    def approve(self, processed_by_user, notes=""):
        """Mark leave as approved and record processor and time."""
        self.status = self.STATUS_APPROVED
        self.processed_by = processed_by_user
        self.processed_at = timezone.now()
        self.processed_notes = notes
        self.save(update_fields=["status", "processed_by", "processed_at", "processed_notes"])

    def reject(self, processed_by_user, notes=""):
        """Mark leave as rejected and record processor and time."""
        self.status = self.STATUS_REJECTED
        self.processed_by = processed_by_user
        self.processed_at = timezone.now()
        self.processed_notes = notes
        self.save(update_fields=["status", "processed_by", "processed_at", "processed_notes"])

    def overlaps_user_attendance(self):
        """Return True if any attendance for applicant exists on any day in the leave range."""
        return Attendance.objects.filter(
            user=self.applicant,
            date__gte=self.start_date,
            date__lte=self.end_date
        ).exists()


class Delegation(models.Model):
    """
    Delegation created by Admin/CEO to assign tasks / responsibilities to employees.
    Employees can view delegations where they are assignees.
    """
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_delegations")
    assignees = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="delegations")
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    # optional priority/weight
    priority = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["start_date", "end_date"]),
        ]

    def __str__(self):
        return f"Delegation: {self.title} (active={self.active})"

    def is_active_on(self, on_date: date = None):
        """Return True if delegation is active for the provided date (or today)."""
        on_date = on_date or timezone.localdate()
        if not self.active:
            return False
        if self.start_date and on_date < self.start_date:
            return False
        if self.end_date and on_date > self.end_date:
            return False
        return True
