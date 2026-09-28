"""Small, dependency-free security-header middleware."""

CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-src 'self'; "
    "object-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'self'"
)


class SecurityHeadersMiddleware:
    """Adds a strict Content-Security-Policy and a few hardening headers.

    The Django admin is excluded from the CSP because it ships its own markup.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/admin/") and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = CSP
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            response.setdefault("Cache-Control", "private, no-cache")
        return response
