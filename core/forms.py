# core/forms.py
from django import forms
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Attendance, LeaveApplication, Delegation


# We keep a small legacy ROLE_CHOICES only for fallback text (not used when Groups exist).
FALLBACK_ROLE_CHOICES = [
    ('Admin', 'Admin'),
    ('Manager', 'Manager'),
    ('Employee', 'Employee'),
]


class CreateUserForm(forms.Form):
    username = forms.CharField(label='Username', max_length=150, help_text='Unique username')
    first_name = forms.CharField(label='Full name', max_length=150)
    email = forms.EmailField(label='Email')
    # designation will be initialised dynamically in __init__:
    # - prefer a ModelChoiceField over Group if those Groups exist,
    # - otherwise fallback to a ChoiceField with static options so form remains usable.
    designation = None

    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput,
        help_text='Minimum 8 characters'
    )
    password2 = forms.CharField(
        label='Confirm password',
        widget=forms.PasswordInput,
        help_text='Enter the same password again'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Preferred groups in order
        preferred_groups = ["Admin", "Manager", "Employee"]

        # Try to use a ModelChoiceField bound to the preferred Group objects.
        try:
            groups_qs = Group.objects.filter(name__in=preferred_groups)
            # If we found all or some groups, prefer ModelChoiceField so view can get the Group instance
            if groups_qs.exists():
                # Reorder queryset to match preferred_groups order
                # (simple approach: annotate with ordering using Python list)
                ordered_groups = sorted(list(groups_qs), key=lambda g: preferred_groups.index(g.name) if g.name in preferred_groups else len(preferred_groups))
                # Use a QuerySet-like object for ModelChoiceField; we'll use the original queryset but set choices manually.
                self.fields['designation'] = forms.ModelChoiceField(
                    queryset=groups_qs,
                    empty_label=None,
                    label="Designation",
                    help_text="Choose the role/designation for this user",
                    required=True
                )
                # If you want to display the preferred order in the select widget, set choices manually:
                self.fields['designation'].choices = [(g.pk, g.name) for g in ordered_groups]
            else:
                # No groups found yet — fallback to static choices
                self.fields['designation'] = forms.ChoiceField(
                    choices=FALLBACK_ROLE_CHOICES,
                    label="Designation",
                    help_text="Choose the role/designation for this user",
                    required=True
                )
        except Exception:
            # If something goes wrong (migrations not run, DB unavailable), fallback to simple choices
            self.fields['designation'] = forms.ChoiceField(
                choices=FALLBACK_ROLE_CHOICES,
                label="Designation",
                help_text="Choose the role/designation for this user",
                required=True
            )

    def clean_username(self):
        uname = self.cleaned_data['username']
        if User.objects.filter(username=uname).exists():
            raise ValidationError("Username already exists")
        return uname

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise ValidationError("Email already in use")
        return email

    def clean_password2(self):
        pw1 = self.cleaned_data.get('password1')
        pw2 = self.cleaned_data.get('password2')
        if not pw1 or not pw2:
            raise ValidationError("Both password fields are required")
        if pw1 != pw2:
            raise ValidationError("Passwords do not match")
        if len(pw1) < 8:
            raise ValidationError("Password must be at least 8 characters long")
        return pw2


# ----------------------------
# New Forms for Dashboard
# ----------------------------

class AttendanceForm(forms.ModelForm):
    """Optional form to manually mark or edit attendance (admin use)."""
    class Meta:
        model = Attendance
        fields = ['user', 'date', 'login_time', 'logout_time', 'status', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'login_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'logout_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class LeaveApplicationForm(forms.ModelForm):
    """Form for employees to apply for leave."""
    class Meta:
        model = LeaveApplication
        fields = ['leave_type', 'start_date', 'end_date', 'reason', 'attachment']
        widgets = {
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'attachment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            raise ValidationError("End date cannot be before start date.")
        if start and start < timezone.localdate():
            raise ValidationError("Start date cannot be in the past.")
        return cleaned


class DelegationForm(forms.ModelForm):
    """Form for Admin/CEO to create new delegations and assign to employees."""
    class Meta:
        model = Delegation
        fields = ['title', 'description', 'start_date', 'end_date', 'assignees', 'priority', 'active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Delegation title'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'assignees': forms.SelectMultiple(attrs={'class': 'form-select'}),
            'priority': forms.NumberInput(attrs={'min': 1, 'class': 'form-control'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            raise ValidationError("End date cannot be before start date.")
        return cleaned
