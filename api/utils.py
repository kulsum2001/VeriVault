"""Tiny JSON-API toolkit built on plain Django (no third-party packages)."""
import functools
import json

from django.core.paginator import EmptyPage, Paginator
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from accounts.models import ApiToken

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


class ApiError(Exception):
    def __init__(self, status, message, errors=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.errors = errors


def error_response(status, message, errors=None):
    body = {"error": {"status": status, "message": message}}
    if errors:
        body["error"]["fields"] = errors
    return JsonResponse(body, status=status)


def form_errors(form):
    return {field: [e["message"] for e in errs] for field, errs in form.errors.get_json_data().items()}


def authenticate(request):
    """Token auth for every method; session auth only for safe (read-only) methods."""
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if header:
        scheme, _, value = header.partition(" ")
        if scheme.lower() in ("token", "bearer") and value.strip():
            token = ApiToken.authenticate(value.strip())
            if token:
                return token.user
        raise ApiError(401, "Invalid or revoked API token.")
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and request.method in SAFE_METHODS:
        return user
    if user is not None and user.is_authenticated:
        raise ApiError(403, "Write requests must use token authentication (Authorization: Token <key>).")
    raise ApiError(401, "Authentication required. Send 'Authorization: Token <key>'.")


def api(methods, auth=True):
    """Decorator: CSRF-exempt, method-checked, authenticated JSON endpoint."""
    allowed = tuple(m.upper() for m in methods)

    def decorator(view):
        @csrf_exempt
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in allowed:
                response = error_response(405, f"Method {request.method} not allowed.")
                response["Allow"] = ", ".join(allowed)
                return response
            try:
                request.api_user = authenticate(request) if auth else None
                response = view(request, *args, **kwargs)
            except ApiError as exc:
                return error_response(exc.status, exc.message, exc.errors)
            response["Cache-Control"] = "no-store"
            return response

        return wrapper

    return decorator


def body(request):
    """Parse the request payload (JSON or form-encoded) into a plain dict."""
    content_type = request.META.get("CONTENT_TYPE", "")
    if content_type.startswith("application/json"):
        try:
            data = json.loads(request.body or b"{}")
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "Request body is not valid JSON.")
        if not isinstance(data, dict):
            raise ApiError(400, "JSON body must be an object.")
        return data
    if request.method != "POST" and content_type.startswith("application/x-www-form-urlencoded"):
        from django.http import QueryDict

        return QueryDict(request.body).dict()
    return {k: v for k, v in request.POST.items()}


def paginate(request, queryset, serialize, default_size=20, max_size=100):
    try:
        size = min(max(int(request.GET.get("page_size", default_size)), 1), max_size)
        number = max(int(request.GET.get("page", 1)), 1)
    except ValueError:
        raise ApiError(400, "page and page_size must be integers.")
    paginator = Paginator(queryset, size)
    if paginator.count == 0:
        return {"count": 0, "page": 1, "page_size": size, "num_pages": 1, "next": None, "previous": None, "results": []}
    try:
        page = paginator.page(number)
    except EmptyPage:
        raise ApiError(404, "That page does not exist.")

    def link(n):
        params = request.GET.copy()
        params["page"] = n
        return request.build_absolute_uri(request.path + "?" + params.urlencode())

    return {
        "count": paginator.count, "page": page.number, "page_size": size, "num_pages": paginator.num_pages,
        "next": link(page.number + 1) if page.has_next() else None,
        "previous": link(page.number - 1) if page.has_previous() else None,
        "results": [serialize(obj) for obj in page.object_list],
    }
