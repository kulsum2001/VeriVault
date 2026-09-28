from django.conf import settings
from django.utils import timezone


def site(request):
    unread = 0
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from vault.models import Notification

        unread = Notification.objects.filter(user=user, is_read=False).count()
    path = request.path
    return {
        "SITE_NAME": settings.SITE_NAME,
        "SITE_TAGLINE": settings.SITE_TAGLINE,
        "SITE_DESCRIPTION": settings.SITE_DESCRIPTION,
        "SITE_URL": settings.SITE_URL.rstrip("/"),
        "CANONICAL_URL": settings.SITE_URL.rstrip("/") + path,
        "CURRENT_YEAR": timezone.now().year,
        "UNREAD_NOTIFICATIONS": unread,
    }
