import csv
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_GET, require_POST

from . import intelligence, services
from .audit import record
from .forms import (DocumentForm, DocumentUploadForm, FolderForm, NewVersionForm, PublicPasswordForm,
                    ShareLinkForm, ShareUserForm, VerifyForm)
from .models import (AuditLog, Category, Document, DocumentShare, DocumentVersion, Folder, Notification,
                     ShareLink, Tag)

PAGE_SIZE = 12


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _owned_or_404(request, pk):
    return get_object_or_404(Document.objects.select_related("owner__profile", "folder"), pk=pk, owner=request.user)


def _accessible_or_404(request, pk):
    doc, role = services.get_document_for_user(request.user, pk)
    if doc is None:
        raise Http404("Document not found")
    return doc, role


def _reauth_redirect(request):
    return redirect(f"{reverse('accounts:reauth')}?{urlencode({'next': request.get_full_path()})}")


def _back(request, fallback):
    target = request.POST.get("next") or ""
    if target.startswith("/") and not target.startswith("//"):
        return redirect(target)
    return redirect(fallback)


def _file_response(stored, name, content_type, inline):
    """Stream a stored file with safe headers."""
    try:
        handle = stored.storage.open(stored.name, "rb")
    except (FileNotFoundError, OSError):
        raise Http404("The stored file is missing.")
    safe_inline = inline and content_type in Document.INLINE_TYPES
    response = FileResponse(handle, as_attachment=not safe_inline, filename=name,
                            content_type=content_type if safe_inline else "application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    if safe_inline and content_type != "application/pdf":
        response["Content-Security-Policy"] = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"
    return response


def ordered_folders(user):
    folders = list(Folder.objects.filter(owner=user).annotate(
        doc_count=Count("documents", filter=~Q(documents__status=Document.TRASHED))).select_related("parent"))
    children = {}
    for f in folders:
        children.setdefault(f.parent_id, []).append(f)
    ordered = []

    def walk(parent_id, depth):
        for f in sorted(children.get(parent_id, []), key=lambda x: x.name.lower()):
            f.tree_depth = depth
            ordered.append(f)
            if depth < 20:
                walk(f.pk, depth + 1)

    walk(None, 0)
    return ordered


def _querystring(request, drop=("page",)):
    params = request.GET.copy()
    for key in drop:
        params.pop(key, None)
    return params.urlencode()


# ---------------------------------------------------------------------------
# dashboard & insights
# ---------------------------------------------------------------------------
@login_required
def dashboard(request):
    user = request.user
    services.sync_expiry_notifications(user)
    library = Document.objects.filter(owner=user).library().select_related("owner__profile", "folder")
    health = intelligence.vault_health(user)
    expiry = intelligence.expiry_report(user)
    context = {
        "stats": {
            "total": library.count(),
            "favorites": library.filter(is_favorite=True).count(),
            "archived": Document.objects.filter(owner=user, status=Document.ARCHIVED).count(),
            "shared": ShareLink.objects.filter(created_by=user, is_active=True).count()
                      + DocumentShare.objects.filter(shared_by=user).count(),
            "trash": Document.objects.filter(owner=user).trashed().count(),
            "received": DocumentShare.objects.filter(shared_with=user).count(),
        },
        "recent": library.order_by("-updated_at")[:6],
        "favorites": library.filter(is_favorite=True)[:4],
        "expiry": expiry,
        "expiry_items": (expiry["expired"] + expiry["soon"])[:5],
        "health": health,
        "top_recs": health["recommendations"][:3],
        "categories": intelligence.category_breakdown(user),
        "activity": AuditLog.objects.filter(user=user).exclude(action__in=["view"])[:6],
        "profile": user.profile,
    }
    return render(request, "vault/dashboard.html", context)


@login_required
def insights(request):
    user = request.user
    health = intelligence.vault_health(user)
    context = {
        "health": health,
        "duplicates": intelligence.find_duplicates(user),
        "expiry": intelligence.expiry_report(user),
        "profile": user.profile,
        "categories": intelligence.category_breakdown(user),
        "checked": Document.objects.filter(owner=user).library().exclude(last_verified_at=None).count(),
        "failed": Document.objects.filter(owner=user).library().filter(integrity_status="failed"),
        "links": ShareLink.objects.filter(created_by=user, is_active=True).select_related("document"),
    }
    return render(request, "vault/insights.html", context)


@login_required
@require_POST
def verify_all(request):
    checked = failed = 0
    for doc in Document.objects.filter(owner=request.user).library():
        checked += 1
        if not doc.verify_integrity():
            failed += 1
    record(request, "verify", details=f"Checked {checked} documents, {failed} failed")
    if failed:
        messages.error(request, f"Integrity check finished: {failed} of {checked} documents failed verification.")
    else:
        messages.success(request, f"All {checked} documents match their recorded fingerprints.")
    return redirect("vault:insights")


# ---------------------------------------------------------------------------
# documents: list, upload, detail
# ---------------------------------------------------------------------------
@login_required
def document_list(request):
    user = request.user
    qs = Document.objects.filter(owner=user).select_related("owner__profile", "folder").prefetch_related("tags")
    qs = services.search_documents(qs, request.GET, alert_days=user.profile.expiry_alert_days)
    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    active_filters = {k: v for k, v in request.GET.items() if k not in ("page", "sort", "view") and v}
    context = {
        "page": page,
        "total": paginator.count,
        "folders": ordered_folders(user),
        "tags": Tag.objects.filter(owner=user).annotate(n=Count("documents")).filter(n__gt=0),
        "categories": Category.CHOICES,
        "f": request.GET,
        "view_mode": "grid" if request.GET.get("view") == "grid" else "list",
        "active_filters": active_filters,
        "qs": _querystring(request),
        "qs_nopage_noview": _querystring(request, drop=("page", "view")),
        "current_folder": Folder.objects.filter(owner=user, pk=request.GET["folder"]).first() if request.GET.get("folder", "").isdigit() else None,
    }
    return render(request, "vault/document_list.html", context)


@login_required
def document_upload(request):
    initial = {}
    if request.GET.get("folder", "").isdigit():
        initial["folder"] = request.GET["folder"]
    form = DocumentUploadForm(request.POST or None, request.FILES or None, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        doc = services.create_document(request.user, form.cleaned_data["file"], form.save(commit=False), form.tag_names)
        record(request, "upload", document=doc, details=f"{doc.original_name} ({doc.size} bytes), SHA-256 {doc.short_hash}")
        messages.success(request, f"'{doc.title}' is sealed in your vault.")
        return redirect(doc.get_absolute_url())
    return render(request, "vault/document_form.html", {"form": form, "mode": "upload", "profile": request.user.profile})


@login_required
def document_detail(request, pk):
    doc, role = _accessible_or_404(request, pk)
    is_owner = role == "owner"
    doc.last_accessed_at = timezone.now()
    Document.objects.filter(pk=doc.pk).update(last_accessed_at=doc.last_accessed_at)
    record(request, "view", document=doc, details="Viewed" + ("" if is_owner else f" (shared by {doc.owner.get_username()})"))
    context = {
        "doc": doc,
        "role": role,
        "is_owner": is_owner,
        "can_download": role in ("owner", "download"),
        "locked": services.needs_reauth(request, doc),
        "versions": doc.versions.select_related("uploaded_by"),
        "tags": doc.tags.all(),
    }
    if is_owner:
        context.update({
            "links": doc.share_links.all(),
            "user_shares": doc.user_shares.select_related("shared_with__profile"),
            "link_form": ShareLinkForm(),
            "user_form": ShareUserForm(owner=request.user),
            "related": intelligence.related_documents(doc),
            "history": AuditLog.objects.filter(document=doc)[:8],
        })
    return render(request, "vault/document_detail.html", context)


@login_required
def document_edit(request, pk):
    doc = _owned_or_404(request, pk)
    form = DocumentForm(request.POST or None, instance=doc, user=request.user)
    if request.method == "POST" and form.is_valid():
        doc = form.save()
        services.set_tags(doc, form.tag_names)
        record(request, "edit", document=doc, details="Details updated")
        messages.success(request, "Document details saved.")
        return redirect(doc.get_absolute_url())
    return render(request, "vault/document_form.html", {"form": form, "mode": "edit", "doc": doc, "profile": request.user.profile})


@login_required
def document_download(request, pk):
    doc, role = _accessible_or_404(request, pk)
    if role == "view":
        raise PermissionDenied("You have view-only access to this document.")
    if services.needs_reauth(request, doc):
        return _reauth_redirect(request)
    record(request, "download", document=doc, details=f"v{doc.version}, SHA-256 {doc.short_hash}")
    Document.objects.filter(pk=doc.pk).update(last_accessed_at=timezone.now())
    return _file_response(doc.file, doc.original_name, doc.content_type, inline=False)


@login_required
def document_preview(request, pk):
    doc, role = _accessible_or_404(request, pk)
    if not doc.can_preview:
        raise Http404("This file type cannot be previewed.")
    if services.needs_reauth(request, doc):
        return _reauth_redirect(request)
    return _file_response(doc.file, doc.original_name, doc.content_type, inline=True)


# ---------------------------------------------------------------------------
# document actions (owner only, POST)
# ---------------------------------------------------------------------------
@login_required
@require_POST
def document_favorite(request, pk):
    doc = _owned_or_404(request, pk)
    doc.is_favorite = not doc.is_favorite
    doc.save(update_fields=["is_favorite"])
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"favorite": doc.is_favorite})
    return _back(request, doc.get_absolute_url())


@login_required
@require_POST
def document_archive(request, pk):
    doc = _owned_or_404(request, pk)
    if doc.status == Document.ARCHIVED:
        doc.status = Document.ACTIVE
        record(request, "unarchive", document=doc)
        messages.success(request, "Document moved back to your active library.")
    else:
        doc.status = Document.ARCHIVED
        record(request, "archive", document=doc)
        messages.success(request, "Document archived.")
    doc.save(update_fields=["status", "updated_at"])
    return _back(request, doc.get_absolute_url())


@login_required
@require_POST
def document_trash(request, pk):
    doc = _owned_or_404(request, pk)
    services.trash_documents(Document.objects.filter(pk=doc.pk))
    doc.share_links.filter(is_active=True).update(is_active=False)
    record(request, "trash", document=doc, details="Moved to trash; share links revoked")
    messages.success(request, f"'{doc.title}' moved to trash. It will be purged after 30 days.")
    return redirect("vault:documents")


@login_required
@require_POST
def document_restore(request, pk):
    doc = _owned_or_404(request, pk)
    services.restore_documents(Document.objects.filter(pk=doc.pk))
    record(request, "restore", document=doc)
    messages.success(request, f"'{doc.title}' restored.")
    return redirect(doc.get_absolute_url())


@login_required
@require_POST
def document_delete(request, pk):
    doc = _owned_or_404(request, pk)
    title = doc.title
    record(request, "delete", title=title, details=f"Permanently deleted '{title}'", document=None)
    services.delete_permanently(doc)
    messages.success(request, f"'{title}' was permanently deleted.")
    return redirect("vault:trash")


@login_required
@require_POST
def document_verify(request, pk):
    doc = _owned_or_404(request, pk)
    ok = doc.verify_integrity()
    record(request, "verify", document=doc, details="Intact" if ok else "MISMATCH - stored file differs from fingerprint")
    if ok:
        messages.success(request, "Integrity confirmed: the stored file matches its SHA-256 fingerprint.")
    else:
        messages.error(request, "Integrity check FAILED: the stored file does not match its fingerprint.")
    return redirect(doc.get_absolute_url())


@login_required
@require_POST
def document_certify(request, pk):
    doc = _owned_or_404(request, pk)
    if doc.public_verification:
        doc.public_verification = False
        doc.save(update_fields=["public_verification"])
        record(request, "uncertify", document=doc)
        messages.success(request, "Public verification page turned off.")
    else:
        if not doc.verify_integrity():
            messages.error(request, "Cannot publish a certificate: the file failed its integrity check.")
            return redirect(doc.get_absolute_url())
        doc.public_verification = True
        doc.certified_at = timezone.now()
        doc.save(update_fields=["public_verification", "certified_at"])
        record(request, "certify", document=doc, details=f"Code {doc.verification_code}")
        messages.success(request, "Verification certificate is now public. Anyone with the code can confirm the fingerprint.")
    return redirect(doc.get_absolute_url() + "#certificate")


@login_required
def version_new(request, pk):
    doc = _owned_or_404(request, pk)
    form = NewVersionForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        uploaded = form.cleaned_data["file"]
        if services.file_digest(uploaded) == doc.sha256:
            form.add_error("file", "This file is identical to the current version.")
        else:
            version = services.add_version(doc, uploaded, request.user, form.cleaned_data["note"])
            record(request, "version", document=doc, details=f"Version {version.number}: {version.note or 'no note'}")
            messages.success(request, f"Version {version.number} saved.")
            return redirect(doc.get_absolute_url() + "#versions")
    return render(request, "vault/version_form.html", {"form": form, "doc": doc, "profile": request.user.profile})


@login_required
def version_download(request, pk, number):
    doc, role = _accessible_or_404(request, pk)
    if role != "owner":
        raise PermissionDenied("Only the owner can download earlier versions.")
    version = get_object_or_404(DocumentVersion, document=doc, number=number)
    if services.needs_reauth(request, doc):
        return _reauth_redirect(request)
    record(request, "download", document=doc, details=f"Version {version.number}")
    return _file_response(version.file, version.original_name, version.content_type, inline=False)


@login_required
@require_POST
def version_restore(request, pk, number):
    doc = _owned_or_404(request, pk)
    version = get_object_or_404(DocumentVersion, document=doc, number=number)
    if version.number == doc.version:
        messages.info(request, "That is already the current version.")
        return redirect(doc.get_absolute_url() + "#versions")
    new_version = services.restore_version(doc, version, request.user)
    record(request, "version_restore", document=doc, details=f"Version {version.number} restored as version {new_version.number}")
    messages.success(request, f"Version {version.number} restored as version {new_version.number}.")
    return redirect(doc.get_absolute_url() + "#versions")


# ---------------------------------------------------------------------------
# sharing
# ---------------------------------------------------------------------------
@login_required
@require_POST
def share_link_create(request, pk):
    doc = _owned_or_404(request, pk)
    if doc.status == Document.TRASHED:
        raise Http404
    if doc.sensitivity == Document.CRITICAL:
        messages.error(request, "Critical documents cannot be shared by public link. Share with a VeriVault user instead.")
        return redirect(doc.get_absolute_url() + "#sharing")
    if services.needs_reauth(request, doc):
        return _reauth_redirect(request)
    form = ShareLinkForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Could not create the link: " + "; ".join(e for errs in form.errors.values() for e in errs))
        return redirect(doc.get_absolute_url() + "#sharing")
    link = ShareLink(document=doc, created_by=request.user, label=form.cleaned_data["label"],
                     allow_download=form.cleaned_data["allow_download"], expires_at=form.expires_at(),
                     max_downloads=form.cleaned_data["max_downloads"])
    link.set_password(form.cleaned_data["password"])
    link.save()
    record(request, "share_link_create", document=doc,
           details=f"Link '{link.label or link.token[:6]}' expires {link.expires_at:%d %b %Y %H:%M}" if link.expires_at else f"Link '{link.label or link.token[:6]}' (no expiry)")
    messages.success(request, "Share link created. Copy it below.")
    return redirect(doc.get_absolute_url() + "#sharing")


@login_required
@require_POST
def share_link_revoke(request, pk, link_id):
    doc = _owned_or_404(request, pk)
    link = get_object_or_404(ShareLink, pk=link_id, document=doc)
    link.is_active = False
    link.save(update_fields=["is_active"])
    record(request, "share_link_revoke", document=doc, details=f"Link '{link.label or link.token[:6]}' revoked")
    messages.success(request, "Share link revoked.")
    return redirect(doc.get_absolute_url() + "#sharing")


@login_required
@require_POST
def share_user_create(request, pk):
    doc = _owned_or_404(request, pk)
    if doc.status == Document.TRASHED:
        raise Http404
    form = ShareUserForm(request.POST, owner=request.user)
    if not form.is_valid():
        messages.error(request, "; ".join(e for errs in form.errors.values() for e in errs))
        return redirect(doc.get_absolute_url() + "#sharing")
    recipient = form.recipient_user
    days = form.cleaned_data["days"]
    share, created = DocumentShare.objects.update_or_create(
        document=doc, shared_with=recipient,
        defaults={"shared_by": request.user, "can_download": form.cleaned_data["can_download"],
                  "note": form.cleaned_data["note"], "expires_at": timezone.now() + timedelta(days=days) if days else None},
    )
    record(request, "share_user", document=doc, details=f"With {recipient.get_username()} ({'download' if share.can_download else 'view only'})")
    services.notify(recipient, Notification.SHARE, f"{request.user.profile.name} shared '{doc.title}' with you",
                    "View-only access" if not share.can_download else "You can view and download it", doc)
    messages.success(request, f"Shared with {recipient.profile.name}." if created else f"Access for {recipient.profile.name} updated.")
    return redirect(doc.get_absolute_url() + "#sharing")


@login_required
@require_POST
def share_user_revoke(request, pk, share_id):
    doc = _owned_or_404(request, pk)
    share = get_object_or_404(DocumentShare, pk=share_id, document=doc)
    who = share.shared_with.get_username()
    share.delete()
    record(request, "unshare_user", document=doc, details=f"Removed {who}")
    messages.success(request, f"Access removed for {who}.")
    return redirect(doc.get_absolute_url() + "#sharing")


@login_required
def shared_with_me(request):
    shares = [s for s in DocumentShare.objects.filter(shared_with=request.user)
              .select_related("document__owner__profile", "shared_by__profile").order_by("-created_at")
              if s.is_active and s.document.status != Document.TRASHED]
    return render(request, "vault/shared_with_me.html", {"shares": shares})


# ---------------------------------------------------------------------------
# public share links
# ---------------------------------------------------------------------------
def _get_link(token):
    return ShareLink.objects.select_related("document__owner__profile").filter(token=token).first()


def _invalid(request, reason, status=404):
    return render(request, "vault/share_invalid.html", {"reason": reason}, status=status)


def share_public(request, token):
    link = _get_link(token)
    if link is None:
        return _invalid(request, "This link does not exist.")
    if not link.is_usable:
        reason = {"revoked": "The owner has revoked this link.", "expired": "This link has expired."}.get(link.state, "This link is no longer available.")
        return _invalid(request, reason, 410)
    session_key = f"sharelink_ok_{link.pk}"
    if link.requires_password and not request.session.get(session_key):
        form = PublicPasswordForm(request.POST or None, link=link)
        if request.method == "POST" and form.is_valid():
            request.session[session_key] = True
            return redirect("vault:share_public", token=token)
        return render(request, "vault/share_password.html", {"form": form, "link": link})
    doc = link.document
    ShareLink.objects.filter(pk=link.pk).update(view_count=link.view_count + 1, last_accessed_at=timezone.now())
    record(request, "public_view", document=doc, details=f"Link '{link.label or link.token[:6]}'")
    return render(request, "vault/share_public.html", {"link": link, "doc": doc, "can_download": link.allow_download and not link.is_exhausted})


@require_POST
def share_public_download(request, token):
    link = _get_link(token)
    if link is None or not link.is_usable:
        return _invalid(request, "This link is no longer available.", 410)
    if link.requires_password and not request.session.get(f"sharelink_ok_{link.pk}"):
        return redirect("vault:share_public", token=token)
    if not link.allow_download:
        raise PermissionDenied("Downloads are disabled for this link.")
    # Atomically claim a download so limits cannot be exceeded by parallel requests.
    from django.db.models import F
    claim = ShareLink.objects.filter(pk=link.pk, is_active=True)
    if link.max_downloads is not None:
        claim = claim.filter(download_count__lt=link.max_downloads)
    if not claim.update(download_count=F("download_count") + 1, last_accessed_at=timezone.now()):
        return _invalid(request, "The download limit for this link has been reached.", 410)
    doc = link.document
    record(request, "public_download", document=doc, details=f"Link '{link.label or link.token[:6]}'")
    return _file_response(doc.file, doc.original_name, doc.content_type, inline=False)


# ---------------------------------------------------------------------------
# public verification
# ---------------------------------------------------------------------------
def _certificate_matches(doc, digest):
    if not digest:
        return None
    if digest == doc.sha256:
        return {"kind": "current", "version": doc.version}
    older = doc.versions.filter(sha256=digest).first()
    if older:
        return {"kind": "older", "version": older.number}
    return {"kind": "none"}


def verify_public(request, code=None):
    form = VerifyForm(request.POST or None, request.FILES or None, initial={"code": code or ""})
    result = None
    if code and request.method == "GET":
        doc = Document.objects.select_related("owner__profile").filter(
            verification_code=code.upper(), public_verification=True).exclude(status=Document.TRASHED).first()
        result = {"searched": True, "doc": doc, "match": None}
        if doc:
            record(request, "public_verify", document=doc, details="Certificate page opened")
    elif request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        digest = data["sha256"]
        if data["file"]:
            digest = services.file_digest(data["file"])
        doc = None
        public = Document.objects.select_related("owner__profile").filter(public_verification=True).exclude(status=Document.TRASHED)
        if data["code"]:
            doc = public.filter(verification_code=data["code"]).first()
        elif digest:
            doc = public.filter(Q(sha256=digest) | Q(versions__sha256=digest)).first()
        match = _certificate_matches(doc, digest) if doc else None
        result = {"searched": True, "doc": doc, "match": match, "digest": digest}
        if doc:
            record(request, "public_verify", document=doc,
                   details=f"Fingerprint check: {match['kind'] if match else 'code lookup'}")
    return render(request, "vault/verify.html", {"form": form, "result": result, "code": code})


# ---------------------------------------------------------------------------
# bulk actions
# ---------------------------------------------------------------------------
@login_required
@require_POST
def bulk_action(request):
    ids = [int(i) for i in request.POST.getlist("ids") if i.isdigit()]
    action = request.POST.get("action", "")
    qs = Document.objects.filter(owner=request.user, pk__in=ids)
    count = qs.count()
    if not count:
        messages.warning(request, "Select at least one document first.")
        return _back(request, reverse("vault:documents"))
    if action == "trash":
        services.trash_documents(qs)
        ShareLink.objects.filter(document__in=list(qs), is_active=True).update(is_active=False)
        note = "moved to trash"
    elif action == "archive":
        qs.update(status=Document.ARCHIVED, updated_at=timezone.now())
        note = "archived"
    elif action == "unarchive":
        qs.filter(status=Document.ARCHIVED).update(status=Document.ACTIVE, updated_at=timezone.now())
        note = "moved back to active"
    elif action == "favorite":
        qs.update(is_favorite=True)
        note = "added to favourites"
    elif action == "unfavorite":
        qs.update(is_favorite=False)
        note = "removed from favourites"
    elif action == "restore":
        services.restore_documents(qs)
        note = "restored"
    elif action == "move":
        folder_id = request.POST.get("folder", "")
        folder = Folder.objects.filter(owner=request.user, pk=folder_id).first() if folder_id.isdigit() else None
        qs.update(folder=folder, updated_at=timezone.now())
        note = f"moved to {folder.name if folder else 'no folder'}"
    elif action == "tag":
        names = services.parse_tags(request.POST.get("tag", ""))
        if not names:
            messages.warning(request, "Enter a tag name.")
            return _back(request, reverse("vault:documents"))
        for doc in qs:
            for tag_name in names:
                tag, _ = Tag.objects.get_or_create(owner=request.user, name=tag_name)
                doc.tags.add(tag)
        note = f"tagged '{', '.join(names)}'"
    else:
        messages.error(request, "Unknown action.")
        return _back(request, reverse("vault:documents"))
    record(request, "bulk", details=f"{count} document(s) {note}")
    messages.success(request, f"{count} document{'s' if count != 1 else ''} {note}.")
    return _back(request, reverse("vault:documents"))


# ---------------------------------------------------------------------------
# trash
# ---------------------------------------------------------------------------
@login_required
def trash(request):
    docs = Document.objects.filter(owner=request.user).trashed().order_by("-deleted_at")
    return render(request, "vault/trash.html", {"docs": docs})


@login_required
@require_POST
def trash_empty(request):
    docs = list(Document.objects.filter(owner=request.user).trashed())
    for doc in docs:
        doc.delete()
    record(request, "delete", details=f"Emptied trash ({len(docs)} documents)")
    messages.success(request, f"Trash emptied - {len(docs)} document{'s' if len(docs) != 1 else ''} permanently deleted.")
    return redirect("vault:trash")


# ---------------------------------------------------------------------------
# folders & tags
# ---------------------------------------------------------------------------
@login_required
def folders(request):
    form = FolderForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        folder = form.save(commit=False)
        folder.owner = request.user
        folder.save()
        record(request, "folder", details=f"Created folder '{folder.path}'")
        messages.success(request, f"Folder '{folder.name}' created.")
        return redirect("vault:folders")
    unfiled = Document.objects.filter(owner=request.user, folder__isnull=True).library().count()
    return render(request, "vault/folders.html", {"form": form, "folders": ordered_folders(request.user), "unfiled": unfiled})


@login_required
def folder_edit(request, pk):
    folder = get_object_or_404(Folder, pk=pk, owner=request.user)
    form = FolderForm(request.POST or None, instance=folder, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        record(request, "folder", details=f"Updated folder '{folder.path}'")
        messages.success(request, "Folder updated.")
        return redirect("vault:folders")
    return render(request, "vault/folder_form.html", {"form": form, "folder": folder})


@login_required
@require_POST
def folder_delete(request, pk):
    folder = get_object_or_404(Folder, pk=pk, owner=request.user)
    path = folder.path
    # Sub-folders move up one level so nothing is lost; documents become unfiled.
    Folder.objects.filter(parent=folder).update(parent=folder.parent)
    folder.delete()
    record(request, "folder", details=f"Deleted folder '{path}'")
    messages.success(request, f"Folder '{path}' deleted. Its documents are now unfiled.")
    return redirect("vault:folders")


@login_required
def tags(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            names = services.parse_tags(request.POST.get("name", ""))
            for name in names:
                Tag.objects.get_or_create(owner=request.user, name=name)
            if names:
                record(request, "tag", details=f"Created {', '.join(names)}")
                messages.success(request, "Tag saved.")
            else:
                messages.error(request, "Enter a tag name.")
        elif action in ("rename", "delete"):
            tag = get_object_or_404(Tag, pk=request.POST.get("tag_id"), owner=request.user)
            if action == "delete":
                record(request, "tag", details=f"Deleted tag '{tag.name}'")
                tag.delete()
                messages.success(request, "Tag deleted.")
            else:
                names = services.parse_tags(request.POST.get("name", ""))
                if len(names) != 1:
                    messages.error(request, "Enter a single tag name.")
                elif Tag.objects.filter(owner=request.user, name=names[0]).exclude(pk=tag.pk).exists():
                    messages.error(request, f"A tag named '{names[0]}' already exists.")
                else:
                    record(request, "tag", details=f"Renamed '{tag.name}' to '{names[0]}'")
                    tag.name = names[0]
                    tag.save()
                    messages.success(request, "Tag renamed.")
        return redirect("vault:tags")
    tag_list = Tag.objects.filter(owner=request.user).annotate(n=Count("documents", filter=~Q(documents__status=Document.TRASHED)))
    return render(request, "vault/tags.html", {"tags": tag_list})


# ---------------------------------------------------------------------------
# activity, notifications
# ---------------------------------------------------------------------------
ACTIVITY_GROUPS = {
    "security": ["login", "logout", "login_failed", "login_blocked", "reauth", "password_change", "twofa_enable",
                 "twofa_disable", "token_create", "token_revoke", "register"],
    "documents": ["upload", "version", "version_restore", "edit", "view", "download", "verify", "certify", "uncertify",
                  "trash", "restore", "delete", "archive", "unarchive", "favorite", "bulk"],
    "sharing": ["share_link_create", "share_link_revoke", "share_user", "unshare_user", "public_view", "public_download", "public_verify"],
}


def _activity_queryset(request):
    qs = AuditLog.objects.filter(Q(user=request.user) | Q(document__owner=request.user)).select_related("document", "user")
    group = request.GET.get("type", "")
    if group in ACTIVITY_GROUPS:
        qs = qs.filter(action__in=ACTIVITY_GROUPS[group])
    action = request.GET.get("action", "")
    if action:
        qs = qs.filter(action=action)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(document_title__icontains=q) | Q(details__icontains=q) | Q(ip_address__icontains=q))
    if request.GET.get("hide_views") == "1":
        qs = qs.exclude(action="view")
    return qs


@login_required
def activity(request):
    paginator = Paginator(_activity_queryset(request), 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "vault/activity.html", {
        "page": page, "f": request.GET, "actions": AuditLog.ACTIONS, "qs": _querystring(request),
    })


def _csv_safe(value):
    value = "" if value is None else str(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


class _Echo:
    def write(self, value):
        return value


@login_required
def activity_export(request):
    writer = csv.writer(_Echo())
    rows = _activity_queryset(request)[:5000]

    def stream():
        yield writer.writerow(["time", "action", "document", "details", "ip_address", "user"])
        for e in rows:
            yield writer.writerow([e.created_at.isoformat(), e.get_action_display(), _csv_safe(e.document_title),
                                   _csv_safe(e.details), e.ip_address or "", e.user.get_username() if e.user else ""])

    record(request, "export", details="Activity log exported as CSV")
    response = StreamingHttpResponse(stream(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="verivault-activity.csv"'
    return response


@login_required
def notifications(request):
    if request.method == "POST":
        if request.POST.get("action") == "read_all":
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
            messages.success(request, "All notifications marked as read.")
        elif request.POST.get("action") == "clear":
            Notification.objects.filter(user=request.user, is_read=True).delete()
            messages.success(request, "Read notifications cleared.")
        return redirect("vault:notifications")
    services.sync_expiry_notifications(request.user)
    paginator = Paginator(Notification.objects.filter(user=request.user).select_related("document"), 20)
    return render(request, "vault/notifications.html", {"page": paginator.get_page(request.GET.get("page"))})


@login_required
@require_POST
def notification_read(request, pk):
    note = get_object_or_404(Notification, pk=pk, user=request.user)
    note.is_read = True
    note.save(update_fields=["is_read"])
    if note.document_id and Document.objects.filter(pk=note.document_id).exists():
        return redirect(note.document.get_absolute_url())
    return redirect("vault:notifications")


# ---------------------------------------------------------------------------
# JSON helpers & export
# ---------------------------------------------------------------------------
@login_required
@require_GET
def suggest(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    docs = (Document.objects.filter(owner=request.user).library()
            .filter(Q(title__icontains=q) | Q(original_name__icontains=q) | Q(tags__name__icontains=q)).distinct()[:6])
    return JsonResponse({"results": [
        {"title": d.title, "category": d.get_category_display(), "url": d.get_absolute_url()} for d in docs]})


@login_required
@require_GET
def suggest_metadata(request):
    data = intelligence.suggest_metadata(request.GET.get("filename", "")[:255], request.GET.get("title", "")[:160])
    data["title"] = intelligence.pretty_title(request.GET.get("filename", "")[:255]) if request.GET.get("filename") else ""
    return JsonResponse(data)


@login_required
def export_vault(request):
    archive, count = services.build_export_zip(request.user)
    record(request, "export", details=f"Vault exported ({count} documents)")
    response = FileResponse(archive, as_attachment=True, filename="verivault-export.zip", content_type="application/zip")
    response["Cache-Control"] = "private, no-store"
    return response
