# core/context_processors.py
def unread_notifications_count(request):
    """
    Adds unread_notifications_count to templates.
    Returns 0 for anonymous users or on any error.
    """
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'unread_notifications_count': 0}

    try:
        # 'notifications' is the related_name on Notification.to_user FK in models.py
        unread = request.user.notifications.filter(is_read=False).count()
    except Exception:
        unread = 0

    return {'unread_notifications_count': unread}
