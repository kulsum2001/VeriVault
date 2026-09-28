"""Audit-trail helpers. Every meaningful action goes through ``record``."""


def client_ip(request):
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR") or None


def record(request, action, user=None, document=None, details="", title=""):
    from .models import AuditLog

    actor = user
    if actor is None and request is not None:
        candidate = getattr(request, "user", None)
        if candidate is not None and candidate.is_authenticated:
            actor = candidate
    agent = ""
    if request is not None:
        agent = request.META.get("HTTP_USER_AGENT", "")[:200]
    return AuditLog.objects.create(
        user=actor,
        action=action,
        document=document,
        document_title=(document.title if document is not None else title)[:160],
        details=details[:300],
        ip_address=client_ip(request),
        user_agent=agent,
    )
