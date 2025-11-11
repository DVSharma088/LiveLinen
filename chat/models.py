from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

User = settings.AUTH_USER_MODEL

class ChatThread(models.Model):
    """
    Conversation thread. By default threads were used for 1:1 chats,
    but this model now supports group threads as well via `is_group`.
    Use ChatThread.get_global() to obtain the single global group chat.
    """
    slug = models.SlugField(max_length=64, unique=True)  # e.g., "u5-u12" or "global"
    name = models.CharField(max_length=120, blank=True, help_text="Human-friendly name for group threads")
    is_group = models.BooleanField(default=False, help_text="True for group chats (global room or named groups)")
    participants = models.ManyToManyField(User, related_name='chat_threads', blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        if self.is_group and self.name:
            return f"Group: {self.name}"
        return f"Thread {self.slug}"

    def save(self, *args, **kwargs):
        # ensure slug exists for named group threads if not provided
        if not self.slug:
            base = (self.name or "thread").strip()
            self.slug = slugify(base)[:64]
        super().save(*args, **kwargs)

    @classmethod
    def get_global(cls):
        """
        Return the single global group chat thread. Creates it if missing.
        Use this thread for "everyone in the system" chat (WhatsApp-group style).
        """
        slug = "global"
        obj, created = cls.objects.get_or_create(
            slug=slug,
            defaults={
                "name": "Global Chat",
                "is_group": True,
            }
        )
        # Optionally, you can ensure that all existing active users are participants,
        # but that can be expensive. Instead, allow participants to be empty and
        # treat group messages as broadcast regardless of membership.
        return obj

    @classmethod
    def create_one_to_one(cls, user_a, user_b):
        """
        Helper: create (or get) a 1:1 thread for two users. The slug format is stable
        so that duplicate threads for same pair are avoided.
        """
        # Accept either User objects or username strings depending on calling code.
        ua = user_a.username if hasattr(user_a, "username") else str(user_a)
        ub = user_b.username if hasattr(user_b, "username") else str(user_b)
        # canonical ordering
        pair = sorted([ua, ub])
        slug = f"{pair[0]}-{pair[1]}"
        thread, created = cls.objects.get_or_create(
            slug=slug,
            defaults={
                "is_group": False,
                "name": "",
            }
        )
        # ensure participants include both users (if provided as User instances)
        try:
            if hasattr(user_a, "pk") and hasattr(user_b, "pk"):
                thread.participants.add(user_a, user_b)
        except Exception:
            # ignore if passed usernames or non-user objects
            pass
        return thread


class Message(models.Model):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    body = models.TextField(blank=True)
    attachment = models.FileField(upload_to='chat_attachments/', blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        thread_label = self.thread.name if (self.thread.is_group and self.thread.name) else self.thread.slug
        return f"Msg by {self.sender} in {thread_label} @ {self.created_at:%Y-%m-%d %H:%M}"
