"""Business logic shared by the web views, the API and management commands."""
import hashlib
import mimetypes
import os
import re
import tempfile
import time
import zipfile
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import (Document, DocumentShare, DocumentVersion, Folder, Notification, ShareLink, Tag)


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
def file_digest(uploaded):
    digest = hashlib.sha256()
    uploaded.seek(0)
    for chunk in iter(lambda: uploaded.read(1024 * 1024), b""):
        digest.update(chunk)
    uploaded.seek(0)
    return digest.hexdigest()


def guess_content_type(name, fallback=""):
    guessed = mimetypes.guess_type(name)[0]
    if guessed:
        return guessed
    if name.lower().endswith(".md"):
        return "text/markdown"
    return fallback or "application/octet-stream"


def clean_filename(name):
    name = os.path.basename(name or "file").replace("\x00", "")
    name = re.sub(r"[\r\n\t]+", " ", name).strip()
    return name[:255] or "file"


def parse_tags(text):
    names, seen = [], set()
    for raw in re.split(r"[,;\n]+", text or ""):
        name = re.sub(r"\s+", "-", raw.strip().lower())[:32]
        name = name.strip("-")
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names[:12]


def set_tags(document, names):
    tags = []
    for name in names:
        tag, _ = Tag.objects.get_or_create(owner=document.owner, name=name)
        tags.append(tag)
    document.tags.set(tags)
    return tags


@transaction.atomic
def create_document(owner, uploaded, form_instance, tag_names=()):
    """Persist a new document (form_instance is an unsaved Document) and its v1."""
    name = clean_filename(uploaded.name)
    form_instance.owner = owner
    form_instance.original_name = name
    form_instance.content_type = guess_content_type(name, getattr(uploaded, "content_type", ""))
    form_instance.size = uploaded.size
    form_instance.sha256 = file_digest(uploaded)
    form_instance.version = 1
    form_instance.integrity_status = "ok"
    form_instance.last_verified_at = timezone.now()
    form_instance.file.save(name, uploaded, save=False)
    form_instance.save()
    DocumentVersion.objects.create(
        document=form_instance, number=1, file=form_instance.file.name, original_name=name,
        content_type=form_instance.content_type, size=form_instance.size, sha256=form_instance.sha256,
        note="Original upload", uploaded_by=owner,
    )
    set_tags(form_instance, tag_names)
    return form_instance


@transaction.atomic
def add_version(document, uploaded, user, note=""):
    name = clean_filename(uploaded.name)
    number = (document.versions.order_by("-number").values_list("number", flat=True).first() or 0) + 1
    digest = file_digest(uploaded)
    document.file.save(name, uploaded, save=False)
    document.original_name = name
    document.content_type = guess_content_type(name, getattr(uploaded, "content_type", ""))
    document.size = uploaded.size
    document.sha256 = digest
    document.version = number
    document.integrity_status = "ok"
    document.last_verified_at = timezone.now()
    document.save()
    return DocumentVersion.objects.create(
        document=document, number=number, file=document.file.name, original_name=name,
        content_type=document.content_type, size=document.size, sha256=digest,
        note=note[:200], uploaded_by=user,
    )


@transaction.atomic
def restore_version(document, version, user):
    """Make an old version current again by copying it into a brand-new version."""
    with version.file.open("rb") as handle:
        content = ContentFile(handle.read(), name=version.original_name)
    content.size = version.size
    return add_version(document, content, user, note=f"Restored from version {version.number}")


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def trash_documents(qs):
    return qs.exclude(status=Document.TRASHED).update(status=Document.TRASHED, deleted_at=timezone.now(), updated_at=timezone.now())


def restore_documents(qs):
    return qs.filter(status=Document.TRASHED).update(status=Document.ACTIVE, deleted_at=None, updated_at=timezone.now())


def delete_permanently(document):
    document.delete()


def purge_trash(older_than_days=30, owner=None):
    cutoff = timezone.now() - timedelta(days=older_than_days)
    qs = Document.objects.trashed().filter(deleted_at__lte=cutoff)
    if owner is not None:
        qs = qs.filter(owner=owner)
    count = 0
    for doc in qs:
        doc.delete()
        count += 1
    return count


# ---------------------------------------------------------------------------
# Search & filter (used by the web UI and the API)
# ---------------------------------------------------------------------------
SORTS = {
    "updated": "-updated_at", "oldest": "updated_at", "title": "title", "title_desc": "-title",
    "created": "-created_at", "size": "-size", "size_asc": "size",
}


def search_documents(qs, params, alert_days=30):
    q = (params.get("q") or "").strip()
    for term in q.split()[:8]:
        qs = qs.filter(
            Q(title__icontains=term) | Q(description__icontains=term) | Q(original_name__icontains=term)
            | Q(tags__name__icontains=term) | Q(reference_number__icontains=term) | Q(issuer__icontains=term)
            | Q(verification_code__icontains=term)
        )
    category = params.get("category")
    if category:
        qs = qs.filter(category=category)
    folder = params.get("folder")
    if folder == "none":
        qs = qs.filter(folder__isnull=True)
    elif folder and str(folder).isdigit():
        try:
            root = Folder.objects.get(pk=int(folder))
            qs = qs.filter(folder_id__in=[root.pk, *root.descendant_ids()])
        except Folder.DoesNotExist:
            qs = qs.none()
    tag = params.get("tag")
    if tag:
        qs = qs.filter(tags__name=tag)
    status = params.get("status")
    if status in (Document.ACTIVE, Document.ARCHIVED):
        qs = qs.filter(status=status)
    elif status != Document.TRASHED:
        qs = qs.exclude(status=Document.TRASHED)
    if params.get("favorite") in ("1", "true", "yes"):
        qs = qs.filter(is_favorite=True)
    sensitivity = params.get("sensitivity")
    if sensitivity:
        qs = qs.filter(sensitivity=sensitivity)
    expiry = params.get("expiry")
    today = timezone.localdate()
    if expiry == "expired":
        qs = qs.filter(expiry_date__lt=today)
    elif expiry == "soon":
        qs = qs.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=alert_days))
    elif expiry == "valid":
        qs = qs.filter(expiry_date__gt=today + timedelta(days=alert_days))
    elif expiry == "none":
        qs = qs.filter(expiry_date__isnull=True)
    sort = params.get("sort", "updated")
    if sort == "expiry":
        qs = qs.order_by(F("expiry_date").asc(nulls_last=True), "title")
    else:
        qs = qs.order_by(SORTS.get(sort, "-updated_at"), "-id")
    return qs.distinct()


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------
def get_document_for_user(user, pk):
    """Return (document, role); role is 'owner', 'download' or 'view'. (None, None) if no access."""
    doc = Document.objects.select_related("owner__profile", "folder").filter(pk=pk).first()
    if doc is None:
        return None, None
    if doc.owner_id == user.pk:
        return doc, "owner"
    share = DocumentShare.objects.filter(document=doc, shared_with=user).first()
    if share and share.is_active and doc.status != Document.TRASHED:
        return doc, ("download" if share.can_download else "view")
    return None, None


def needs_reauth(request, document):
    if document.sensitivity == Document.STANDARD:
        return False
    return time.time() - request.session.get("reauth_at", 0) > settings.REAUTH_WINDOW_SECONDS


def is_unlocked(request):
    return time.time() - request.session.get("reauth_at", 0) <= settings.REAUTH_WINDOW_SECONDS


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
def notify(user, kind, title, message="", document=None, dedupe_key=None):
    if dedupe_key and Notification.objects.filter(user=user, dedupe_key=dedupe_key).exists():
        return None
    return Notification.objects.create(user=user, kind=kind, title=title[:160], message=message[:300],
                                       document=document, dedupe_key=dedupe_key)


def sync_expiry_notifications(user):
    """Create (once) a notification for each expiring / expired document."""
    created = 0
    profile = user.profile
    docs = Document.objects.filter(owner=user).library().exclude(expiry_date__isnull=True).select_related("owner__profile")
    for doc in docs:
        state = doc.expiry_state
        if state == "expired":
            n = notify(user, Notification.EXPIRED, f"{doc.title} has expired",
                       f"Expired on {doc.expiry_date:%d %b %Y}. Renew it or archive the old copy.", doc,
                       dedupe_key=f"expired:{doc.pk}:{doc.expiry_date}")
        elif state == "soon":
            n = notify(user, Notification.EXPIRING, f"{doc.title} expires in {doc.days_to_expiry} days",
                       f"Expires on {doc.expiry_date:%d %b %Y} (alert window: {profile.expiry_alert_days} days).", doc,
                       dedupe_key=f"expiring:{doc.pk}:{doc.expiry_date}")
        else:
            n = None
        created += 1 if n else 0
    return created


def deactivate_lapsed_links():
    return ShareLink.objects.filter(is_active=True, expires_at__lte=timezone.now()).update(is_active=False)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def build_export_zip(user):
    """Return an open temporary file positioned at 0 containing every active document."""
    import json

    tmp = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)
    manifest = []
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as archive:
        used = set()
        for doc in Document.objects.filter(owner=user).library().select_related("folder").prefetch_related("tags"):
            folder = re.sub(r"[^\w\- ./]", "_", doc.folder.path) if doc.folder else "Unfiled"
            arcname = f"documents/{folder}/{doc.original_name}"
            base, ext = os.path.splitext(arcname)
            counter = 1
            while arcname in used:
                counter += 1
                arcname = f"{base} ({counter}){ext}"
            used.add(arcname)
            try:
                with doc.file.open("rb") as handle:
                    archive.writestr(arcname, handle.read())
                present = True
            except (FileNotFoundError, OSError):
                present = False
            manifest.append({
                "title": doc.title, "path": arcname if present else None, "category": doc.category,
                "tags": doc.tag_names, "sha256": doc.sha256, "size": doc.size, "version": doc.version,
                "issuer": doc.issuer, "reference_number": doc.reference_number,
                "issue_date": doc.issue_date.isoformat() if doc.issue_date else None,
                "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
                "verification_code": doc.verification_code, "status": doc.status,
            })
        archive.writestr("manifest.json", json.dumps({
            "exported_at": timezone.now().isoformat(), "owner": user.get_username(),
            "document_count": len(manifest), "documents": manifest,
        }, indent=2))
    tmp.seek(0)
    return tmp, len(manifest)
