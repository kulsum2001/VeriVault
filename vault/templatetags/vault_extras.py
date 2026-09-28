from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

_ICONS = {
    "shield": '<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/>',
    "home": '<path d="M4 11l8-7 8 7"/><path d="M6 10v10h12V10"/>',
    "file": '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4"/>',
    "upload": '<path d="M12 16V5"/><path d="M7 9l5-5 5 5"/><path d="M5 19h14"/>',
    "download": '<path d="M12 4v11"/><path d="M7 11l5 5 5-5"/><path d="M5 20h14"/>',
    "folder": '<path d="M3 7h7l2 2h9v10H3z"/>',
    "tag": '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1.2"/>',
    "share": '<circle cx="6" cy="12" r="2.5"/><circle cx="17" cy="6" r="2.5"/><circle cx="17" cy="18" r="2.5"/><path d="M8.2 10.8l6.6-3.6M8.2 13.2l6.6 3.6"/>',
    "trash": '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
    "bell": '<path d="M6 16V11a6 6 0 0112 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 004 0"/>',
    "activity": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.5-7 8-7s8 3 8 7"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.5 3-6 6.5-6s6.5 2.5 6.5 6"/><path d="M16 4.7a3.5 3.5 0 010 6.6M18 14.3c2.2.7 3.5 2.6 3.5 5.7"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9"/><path d="M17 6l3 3"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l5 5"/>',
    "star": '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    "archive": '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v11h14V9"/><path d="M10 13h4"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "alert": '<path d="M12 3l10 18H2z"/><path d="M12 10v5"/><path d="M12 18v.5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "link": '<path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 00-1-1H5a1 1 0 00-1 1v10a1 1 0 001 1h3"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
    "moon": '<path d="M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1"/>',
    "logout": '<path d="M9 4H5v16h4"/><path d="M15 8l4 4-4 4"/><path d="M19 12H9"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "edit": '<path d="M4 20l1-4L16 5l3 3L8 19z"/><path d="M14 7l3 3"/>',
    "eye": '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "grid": '<rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/><rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/>',
    "list": '<path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
    "history": '<path d="M4 12a8 8 0 108-8 8 8 0 00-6 2.7"/><path d="M4 4v4h4"/><path d="M12 8v4l3 2"/>',
    "pulse": '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
    "id": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2"/><path d="M6 16c.5-1.5 1.7-2 3-2s2.5.5 3 2M14 10h4M14 14h3"/>',
    "coins": '<circle cx="9" cy="9" r="5"/><path d="M14 14.5A5 5 0 1019 10"/>',
    "scale": '<path d="M12 4v16M6 20h12M5 8h14"/><path d="M5 8l-2.5 6a3 3 0 005 0zM19 8l-2.5 6a3 3 0 005 0z"/>',
    "heart": '<path d="M12 20s-8-5-8-10.5A4.5 4.5 0 0112 7a4.5 4.5 0 018 2.5C20 15 12 20 12 20z"/>',
    "cap": '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11.5V16c0 1.5 3 3 6 3s6-1.5 6-3v-4.5"/>',
    "briefcase": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V4h6v3M3 13h18"/>',
    "building": '<rect x="5" y="3" width="14" height="18"/><path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2M10 21v-3h4v3"/>',
    "umbrella": '<path d="M3 12a9 9 0 0118 0z"/><path d="M12 12v6a2 2 0 004 0"/>',
    "plane": '<path d="M21 4L3 11l6 2.5L11.5 20 14 14l7-10z"/>',
    "box": '<path d="M3 8l9-5 9 5v8l-9 5-9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    "fingerprint": '<path d="M6 10a6 6 0 0112 0v3M9 20c0-3 0-7 3-7s3 4 3 7M4 14c0-1 .2-2 .5-3M20 13v3c0 2-.5 3-1 4M12 9c-2 0-3 1.5-3 4s-.5 4-1.5 5.5"/>',
    "seal": '<circle cx="12" cy="10" r="6"/><path d="M8.5 15L7 21l5-2.5L17 21l-1.5-6"/><path d="M9.5 10l2 2 3.5-3.5"/>',
    "refresh": '<path d="M20 11a8 8 0 00-14.5-4M4 13a8 8 0 0014.5 4"/><path d="M20 4v7h-7M4 20v-7h7"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
}

CATEGORY_ICONS = {
    "identity": "id", "financial": "coins", "legal": "scale", "medical": "heart", "education": "cap",
    "employment": "briefcase", "property": "building", "insurance": "umbrella", "travel": "plane", "other": "box",
}


@register.simple_tag
def icon(name, size=18, css=""):
    body = _ICONS.get(name, _ICONS["file"])
    return mark_safe(
        f'<svg class="icon {css}" width="{int(size)}" height="{int(size)}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{body}</svg>'
    )


@register.simple_tag
def category_icon(category, size=18, css=""):
    return icon(CATEGORY_ICONS.get(category, "box"), size, css)


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """Return the current query string with some parameters replaced."""
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key, "")
    except AttributeError:
        return ""


@register.filter
def initials_of(user):
    try:
        return user.profile.initials
    except Exception:
        return "?"


@register.filter
def name_of(user):
    try:
        return user.profile.name
    except Exception:
        return getattr(user, "username", "")


@register.filter
def pluralize_word(count, word):
    return word if count == 1 else word + "s"


@register.filter
def mask_hash(value, keep=8):
    value = value or ""
    return f"{value[:keep]}…{value[-keep:]}" if len(value) > keep * 2 else value


@register.simple_tag
def expiry_badge(doc):
    state, days = doc.expiry_state, doc.days_to_expiry
    if state == "none":
        return ""
    if state == "expired":
        return format_html('<span class="badge badge-danger">Expired {}d ago</span>', abs(days))
    if state == "soon":
        return format_html('<span class="badge badge-warn">Expires in {}d</span>', days)
    return format_html('<span class="badge badge-ok">Valid to {}</span>', doc.expiry_date.strftime("%d %b %Y"))
