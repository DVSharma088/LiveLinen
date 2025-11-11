# scripts/send_test_email.py
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hrms.settings")
import django
django.setup()

from django.conf import settings
from django.core.mail import send_mail

print("EMAIL_BACKEND:", settings.EMAIL_BACKEND)
print("DEFAULT_FROM_EMAIL:", getattr(settings, "DEFAULT_FROM_EMAIL", None))
print("EMAIL_HOST_USER:", getattr(settings, "EMAIL_HOST_USER", None))

try:
    res = send_mail(
        "LiveLinen SMTP test",
        "This is a SMTP test via Gmail.",
        settings.DEFAULT_FROM_EMAIL,
        ["devvrat@livelinen.com"],
        fail_silently=False,
    )
    print("send_mail returned:", res)
except Exception as e:
    print("Exception during send_mail:", type(e), e)
