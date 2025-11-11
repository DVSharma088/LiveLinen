# chat/utils.py
from django.contrib.auth import get_user_model
from .models import ChatThread

User = get_user_model()

def thread_slug_for_users(user_a_id: int, user_b_id: int) -> str:
    a, b = sorted([int(user_a_id), int(user_b_id)])
    return f"u{a}-u{b}"

def get_or_create_thread(user_a: User, user_b: User) -> ChatThread:
    slug = thread_slug_for_users(user_a.id, user_b.id)
    thread, created = ChatThread.objects.get_or_create(slug=slug)
    if created or thread.participants.count() < 2:
        thread.participants.set([user_a, user_b])
        thread.save()
    return thread
