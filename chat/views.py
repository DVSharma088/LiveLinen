from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponseServerError

from .models import ChatThread


def chat_home(request):
    """
    Redirect to the single global chat room.
    """
    return redirect("chat:room")


@login_required
def chat_room(request):
    """
    Render the global chat room page.
    Ensures the global ChatThread exists. If ChatThread provides a helper
    `get_global()`, we use it. Otherwise, we fall back to creating/fetching
    a thread with slug 'global'.
    """
    try:
        # Prefer the model-provided helper if it exists
        if hasattr(ChatThread, "get_global") and callable(getattr(ChatThread, "get_global")):
            thread = ChatThread.get_global()
        else:
            # Fallback: try to get or create a thread with slug 'global'
            thread, _ = ChatThread.objects.get_or_create(slug="global", defaults={"name": "Global Chat"})
    except Exception as exc:
        # Log/notify and return a 500 page (or show friendly message)
        # Use Django messages to show a short note in UI if templates render messages
        messages.error(request, "Unable to initialize chat. Please try again later.")
        return HttpResponseServerError("Chat initialization error.")  # developer-friendly response

    return render(request, "chat/chat_room.html", {
        "username": request.user.username,
        "thread_slug": getattr(thread, "slug", "global"),
        "thread_id": getattr(thread, "id", None),
    })
