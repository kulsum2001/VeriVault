from django.contrib.auth import authenticate as django_authenticate
from django.db.models import Count, Q
from django.http import FileResponse, JsonResponse
from django.urls import reverse

from accounts import throttle
from accounts.models import ApiToken
from vault import intelligence, services
from vault.audit import client_ip, record
from vault.forms import DocumentForm, DocumentUploadForm, FolderForm, NewVersionForm, ShareLinkForm
from vault.models import AuditLog, Document, Folder, Notification, ShareLink, Tag

from .serializers import (AuditSerializer, DocumentSerializer, FolderSerializer, NotificationSerializer,
                          ProfileSerializer, ShareLinkSerializer, TagSerializer, VersionSerializer, serialize_health)
from .utils import ApiError, api, body, form_errors, paginate


def _doc_or_404(request, pk, owner_only=True):
    doc, role = services.get_document_for_user(request.api_user, pk)
    if doc is None or (owner_only and role != "owner"):
        raise ApiError(404, "Document not found.")
    return doc, role


def _base_queryset(user):
    return Document.objects.filter(owner=user).select_related("owner__profile", "folder").prefetch_related("tags")


# ---------------------------------------------------------------------------
@api(["GET"], auth=False)
def index(request):
    def u(name, *args):
        return request.build_absolute_uri(reverse(name, args=args))

    return JsonResponse({
        "name": "VeriVault API", "version": "v1", "documentation": u("api:docs"),
        "endpoints": {
            "token": u("api:token"), "me": u("api:me"), "documents": u("api:documents"),
            "folders": u("api:folders"), "tags": u("api:tags"), "insights": u("api:insights"),
            "stats": u("api:stats"), "activity": u("api:activity"), "notifications": u("api:notifications"),
            "verify": u("api:verify"),
        },
    })


@api(["POST"], auth=False)
def token(request):
    data = body(request)
    username, password = str(data.get("username", "")), str(data.get("password", ""))
    ip = client_ip(request)
    if throttle.is_locked(username, ip):
        raise ApiError(429, "Too many failed attempts. Try again later.")
    user = django_authenticate(request, username=username, password=password)
    if user is None:
        throttle.register_failure(username, ip)
        record(request, "login_failed", details=f"Failed API token request for '{username[:60]}'")
        raise ApiError(401, "Invalid credentials.")
    if user.profile.totp_enabled:
        raise ApiError(403, "This account uses two-factor authentication. Create a token in the web app under Security.")
    throttle.reset(username, ip)
    tok, raw = ApiToken.issue(user, str(data.get("name") or "api-login")[:80])
    record(request, "token_create", user=user, details=f"API token '{tok.name}' issued via API")
    return JsonResponse({"token": raw, "name": tok.name, "user": user.get_username()}, status=201)


@api(["GET"])
def me(request):
    return JsonResponse(ProfileSerializer.data(request.api_user))


@api(["GET"])
def stats(request):
    user = request.api_user
    lib = Document.objects.filter(owner=user).library()
    days = user.profile.expiry_alert_days
    return JsonResponse({
        "documents": lib.count(), "favorites": lib.filter(is_favorite=True).count(),
        "archived": Document.objects.filter(owner=user, status=Document.ARCHIVED).count(),
        "trashed": Document.objects.filter(owner=user).trashed().count(),
        "expired": lib.expired().count(), "expiring_soon": lib.expiring(days).count(),
        "active_share_links": ShareLink.objects.filter(created_by=user, is_active=True).count(),
        "storage": ProfileSerializer.data(user)["storage"],
        "by_category": intelligence.category_breakdown(user),
    })


@api(["GET"])
def insights(request):
    user = request.api_user
    data = serialize_health(intelligence.vault_health(user))
    data["duplicates"] = [[d.pk for d in group] for group in intelligence.find_duplicates(user)]
    return JsonResponse(data)


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------
@api(["GET", "POST"])
def documents(request):
    user = request.api_user
    serializer = DocumentSerializer(request)
    if request.method == "GET":
        params = request.GET.copy()
        qs = services.search_documents(_base_queryset(user), params, alert_days=user.profile.expiry_alert_days)
        return JsonResponse(paginate(request, qs, serializer))
    data = request.POST.copy()
    if "tags" in data and "tags_text" not in data:
        data["tags_text"] = data["tags"]
    data.setdefault("category", "auto")
    data.setdefault("sensitivity", Document.STANDARD)
    form = DocumentUploadForm(data, request.FILES, user=user)
    if not form.is_valid():
        raise ApiError(400, "Validation failed.", form_errors(form))
    doc = services.create_document(user, form.cleaned_data["file"], form.save(commit=False), form.tag_names)
    record(request, "upload", user=user, document=doc, details=f"{doc.original_name} via API")
    doc = _base_queryset(user).get(pk=doc.pk)
    return JsonResponse(serializer.data(doc), status=201)


@api(["GET", "PATCH", "PUT", "DELETE"])
def document_detail(request, pk):
    user = request.api_user
    doc, role = _doc_or_404(request, pk, owner_only=request.method != "GET")
    serializer = DocumentSerializer(request)
    if request.method == "GET":
        return JsonResponse(serializer.data(doc))
    if request.method == "DELETE":
        if request.GET.get("permanent") in ("1", "true"):
            record(request, "delete", user=user, title=doc.title, details="Permanently deleted via API")
            services.delete_permanently(doc)
            return JsonResponse({"deleted": True, "permanent": True})
        services.trash_documents(Document.objects.filter(pk=doc.pk))
        doc.share_links.filter(is_active=True).update(is_active=False)
        record(request, "trash", user=user, document=doc, details="Moved to trash via API")
        return JsonResponse({"deleted": True, "permanent": False})
    payload = body(request)
    current = {
        "title": doc.title, "description": doc.description, "category": doc.category,
        "folder": doc.folder_id or "", "reference_number": doc.reference_number, "issuer": doc.issuer,
        "issue_date": doc.issue_date.isoformat() if doc.issue_date else "",
        "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else "",
        "sensitivity": doc.sensitivity, "tags_text": ", ".join(doc.tag_names),
    }
    if "tags" in payload and "tags_text" not in payload:
        payload["tags_text"] = ", ".join(payload["tags"]) if isinstance(payload["tags"], list) else payload["tags"]
    merged = {**current, **{k: ("" if v is None else v) for k, v in payload.items() if k in current}}
    form = DocumentForm(merged, instance=doc, user=user)
    if not form.is_valid():
        raise ApiError(400, "Validation failed.", form_errors(form))
    doc = form.save()
    services.set_tags(doc, form.tag_names)
    updated = []
    if "is_favorite" in payload:
        doc.is_favorite = str(payload["is_favorite"]).lower() in ("1", "true", "yes")
        updated.append("is_favorite")
    if payload.get("status") in (Document.ACTIVE, Document.ARCHIVED) and doc.status != Document.TRASHED:
        doc.status = payload["status"]
        updated.append("status")
    if updated:
        doc.save(update_fields=updated + ["updated_at"])
    record(request, "edit", user=user, document=doc, details="Updated via API")
    return JsonResponse(serializer.data(_base_queryset(user).get(pk=doc.pk)))


@api(["GET"])
def document_download(request, pk):
    doc, role = _doc_or_404(request, pk, owner_only=False)
    if role == "view":
        raise ApiError(403, "You have view-only access to this document.")
    if doc.sensitivity == Document.CRITICAL:
        raise ApiError(403, "Critical documents can only be downloaded from the web app after re-entering your password.")
    try:
        handle = doc.file.storage.open(doc.file.name, "rb")
    except (FileNotFoundError, OSError):
        raise ApiError(404, "The stored file is missing.")
    record(request, "download", user=request.api_user, document=doc, details=f"v{doc.version} via API")
    response = FileResponse(handle, as_attachment=True, filename=doc.original_name, content_type="application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Document-SHA256"] = doc.sha256
    return response


@api(["POST"])
def document_verify(request, pk):
    doc, _ = _doc_or_404(request, pk)
    ok = doc.verify_integrity()
    record(request, "verify", user=request.api_user, document=doc, details="Intact (API)" if ok else "MISMATCH (API)")
    return JsonResponse({"id": doc.pk, "intact": ok, "sha256": doc.sha256, "checked_at": doc.last_verified_at.isoformat()})


@api(["GET"])
def document_related(request, pk):
    doc, _ = _doc_or_404(request, pk)
    serializer = DocumentSerializer(request)
    return JsonResponse({"results": [
        {"score": r["score"], "reasons": r["reasons"], "document": serializer.data(r["document"])}
        for r in intelligence.related_documents(doc)]})


@api(["GET", "POST"])
def document_versions(request, pk):
    user = request.api_user
    doc, _ = _doc_or_404(request, pk)
    if request.method == "GET":
        return JsonResponse({"results": [VersionSerializer.data(v) for v in doc.versions.select_related("uploaded_by")]})
    form = NewVersionForm(request.POST, request.FILES, user=user)
    if not form.is_valid():
        raise ApiError(400, "Validation failed.", form_errors(form))
    uploaded = form.cleaned_data["file"]
    if services.file_digest(uploaded) == doc.sha256:
        raise ApiError(400, "Validation failed.", {"file": ["This file is identical to the current version."]})
    version = services.add_version(doc, uploaded, user, form.cleaned_data["note"])
    record(request, "version", user=user, document=doc, details=f"Version {version.number} via API")
    return JsonResponse(VersionSerializer.data(version), status=201)


@api(["GET", "POST"])
def document_share_links(request, pk):
    user = request.api_user
    doc, _ = _doc_or_404(request, pk)
    serializer = ShareLinkSerializer(request)
    if request.method == "GET":
        return JsonResponse({"results": [serializer.data(l) for l in doc.share_links.all()]})
    if doc.sensitivity == Document.CRITICAL:
        raise ApiError(403, "Critical documents cannot be shared by public link.")
    if doc.status == Document.TRASHED:
        raise ApiError(400, "Restore the document before sharing it.")
    payload = body(request)
    payload.setdefault("allow_download", True)
    payload.setdefault("expires", "7d")
    form = ShareLinkForm(payload)
    if not form.is_valid():
        raise ApiError(400, "Validation failed.", form_errors(form))
    link = ShareLink(document=doc, created_by=user, label=form.cleaned_data["label"],
                     allow_download=form.cleaned_data["allow_download"], expires_at=form.expires_at(),
                     max_downloads=form.cleaned_data["max_downloads"])
    link.set_password(form.cleaned_data["password"])
    link.save()
    record(request, "share_link_create", user=user, document=doc, details="Link created via API")
    return JsonResponse(serializer.data(link), status=201)


@api(["DELETE"])
def share_link_detail(request, pk):
    link = ShareLink.objects.filter(pk=pk, document__owner=request.api_user).first()
    if link is None:
        raise ApiError(404, "Share link not found.")
    link.is_active = False
    link.save(update_fields=["is_active"])
    record(request, "share_link_revoke", user=request.api_user, document=link.document, details="Revoked via API")
    return JsonResponse({"revoked": True})


# ---------------------------------------------------------------------------
# folders & tags
# ---------------------------------------------------------------------------
@api(["GET", "POST"])
def folders(request):
    user = request.api_user
    if request.method == "GET":
        return JsonResponse({"results": [FolderSerializer.data(f) for f in Folder.objects.filter(owner=user).select_related("parent")]})
    form = FolderForm(body(request), user=user)
    if not form.is_valid():
        raise ApiError(400, "Validation failed.", form_errors(form))
    folder = form.save(commit=False)
    folder.owner = user
    folder.save()
    record(request, "folder", user=user, details=f"Created folder '{folder.path}' via API")
    return JsonResponse(FolderSerializer.data(folder), status=201)


@api(["GET", "PATCH", "DELETE"])
def folder_detail(request, pk):
    user = request.api_user
    folder = Folder.objects.filter(pk=pk, owner=user).select_related("parent").first()
    if folder is None:
        raise ApiError(404, "Folder not found.")
    if request.method == "GET":
        return JsonResponse(FolderSerializer.data(folder))
    if request.method == "DELETE":
        Folder.objects.filter(parent=folder).update(parent=folder.parent)
        folder.delete()
        return JsonResponse({"deleted": True})
    payload = body(request)
    merged = {"name": folder.name, "parent": folder.parent_id or "", "color": folder.color}
    merged.update({k: ("" if v is None else v) for k, v in payload.items() if k in merged})
    form = FolderForm(merged, instance=folder, user=user)
    if not form.is_valid():
        raise ApiError(400, "Validation failed.", form_errors(form))
    return JsonResponse(FolderSerializer.data(form.save()))


@api(["GET", "POST"])
def tags(request):
    user = request.api_user
    if request.method == "GET":
        rows = Tag.objects.filter(owner=user).annotate(n=Count("documents", filter=~Q(documents__status=Document.TRASHED)))
        return JsonResponse({"results": [TagSerializer.data(t, t.n) for t in rows]})
    names = services.parse_tags(str(body(request).get("name", "")))
    if not names:
        raise ApiError(400, "Validation failed.", {"name": ["This field is required."]})
    tag, created = Tag.objects.get_or_create(owner=user, name=names[0])
    return JsonResponse(TagSerializer.data(tag), status=201 if created else 200)


@api(["DELETE"])
def tag_detail(request, pk):
    tag = Tag.objects.filter(pk=pk, owner=request.api_user).first()
    if tag is None:
        raise ApiError(404, "Tag not found.")
    tag.delete()
    return JsonResponse({"deleted": True})


# ---------------------------------------------------------------------------
# activity, notifications
# ---------------------------------------------------------------------------
@api(["GET"])
def activity(request):
    user = request.api_user
    qs = AuditLog.objects.filter(Q(user=user) | Q(document__owner=user))
    if request.GET.get("action"):
        qs = qs.filter(action=request.GET["action"])
    return JsonResponse(paginate(request, qs, AuditSerializer.data))


@api(["GET", "POST"])
def notifications(request):
    user = request.api_user
    if request.method == "POST":
        Notification.objects.filter(user=user, is_read=False).update(is_read=True)
        return JsonResponse({"marked_read": True})
    services.sync_expiry_notifications(user)
    qs = Notification.objects.filter(user=user)
    if request.GET.get("unread") in ("1", "true"):
        qs = qs.filter(is_read=False)
    return JsonResponse(paginate(request, qs, NotificationSerializer.data))


# ---------------------------------------------------------------------------
# public verification
# ---------------------------------------------------------------------------
@api(["POST"], auth=False)
def verify(request):
    from vault.views import _certificate_matches

    data = body(request)
    code = str(data.get("code", "")).strip().upper()
    digest = str(data.get("sha256", "")).strip().lower()
    if not code and not digest:
        raise ApiError(400, "Provide 'code' and/or 'sha256'.")
    if digest and (len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
        raise ApiError(400, "sha256 must be 64 hexadecimal characters.")
    public = Document.objects.select_related("owner__profile").filter(public_verification=True).exclude(status=Document.TRASHED)
    doc = public.filter(verification_code=code).first() if code else public.filter(Q(sha256=digest) | Q(versions__sha256=digest)).first()
    if doc is None:
        return JsonResponse({"found": False}, status=404)
    match = _certificate_matches(doc, digest) if digest else None
    record(request, "public_verify", document=doc, details="API certificate lookup")
    return JsonResponse({
        "found": True, "verification_code": doc.verification_code, "title": doc.title,
        "owner": doc.owner.profile.name, "sha256": doc.sha256, "version": doc.version, "size": doc.size,
        "certified_at": doc.certified_at.isoformat() if doc.certified_at else None,
        "integrity_status": doc.integrity_status,
        "match": match["kind"] if match else None,
        "matched_version": match.get("version") if match else None,
    })


def docs_page(request):
    from django.shortcuts import render

    endpoints = [
        ("POST", "/api/v1/auth/token/", "Exchange username + password for a token"),
        ("GET", "/api/v1/me/", "Current user and storage usage"),
        ("GET", "/api/v1/stats/", "Counts, expiry summary, category breakdown"),
        ("GET", "/api/v1/insights/", "Vault health score, recommendations, essentials, duplicates"),
        ("GET", "/api/v1/documents/", "List and search documents"),
        ("POST", "/api/v1/documents/", "Upload (multipart: file, title, category, folder, tags, dates…)"),
        ("GET", "/api/v1/documents/{id}/", "Retrieve a document"),
        ("PATCH", "/api/v1/documents/{id}/", "Update metadata, status, favourite"),
        ("DELETE", "/api/v1/documents/{id}/", "Move to trash (?permanent=1 to delete)"),
        ("GET", "/api/v1/documents/{id}/download/", "Download the file (X-Document-SHA256 header)"),
        ("POST", "/api/v1/documents/{id}/verify/", "Recompute and check the fingerprint"),
        ("GET", "/api/v1/documents/{id}/related/", "Related documents with reasons"),
        ("GET", "/api/v1/documents/{id}/versions/", "Version history"),
        ("POST", "/api/v1/documents/{id}/versions/", "Upload a new version (file, note)"),
        ("GET", "/api/v1/documents/{id}/share-links/", "List share links"),
        ("POST", "/api/v1/documents/{id}/share-links/", "Create link (expires, max_downloads, password, label)"),
        ("DELETE", "/api/v1/share-links/{id}/", "Revoke a link"),
        ("GET", "/api/v1/folders/", "List folders"),
        ("POST", "/api/v1/folders/", "Create folder (name, parent, color)"),
        ("PATCH", "/api/v1/folders/{id}/", "Rename or move"),
        ("DELETE", "/api/v1/folders/{id}/", "Delete folder"),
        ("GET", "/api/v1/tags/", "List tags with counts"),
        ("POST", "/api/v1/tags/", "Create tag (name)"),
        ("DELETE", "/api/v1/tags/{id}/", "Delete tag"),
        ("GET", "/api/v1/activity/", "Audit trail (?action=)"),
        ("GET", "/api/v1/notifications/", "Notifications (?unread=1)"),
        ("POST", "/api/v1/notifications/", "Mark all as read"),
        ("POST", "/api/v1/verify/", "Public certificate lookup by code and/or sha256"),
    ]
    return render(request, "api/docs.html", {"endpoints": endpoints})
