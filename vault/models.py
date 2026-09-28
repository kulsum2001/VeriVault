import hashlib
import mimetypes
import os
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .storage import private_storage

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_verification_code():
    """A short, human-friendly code such as VV-7K3M-Q9XA-2PDR."""
    while True:
        code = "VV-" + "-".join("".join(secrets.choice(CODE_ALPHABET) for _ in range(4)) for _ in range(3))
        if not Document.objects.filter(verification_code=code).exists():
            return code


def generate_share_token():
    return secrets.token_urlsafe(24)


def document_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()[:12]
    return f"u{instance.owner_id}/{uuid.uuid4().hex}{ext}"


def version_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()[:12]
    return f"u{instance.document.owner_id}/{uuid.uuid4().hex}{ext}"


# --------------------------------------------------------------------------
class Category:
    IDENTITY = "identity"
    FINANCIAL = "financial"
    LEGAL = "legal"
    MEDICAL = "medical"
    EDUCATION = "education"
    EMPLOYMENT = "employment"
    PROPERTY = "property"
    INSURANCE = "insurance"
    TRAVEL = "travel"
    OTHER = "other"
    CHOICES = [
        (IDENTITY, "Identity"),
        (FINANCIAL, "Financial & tax"),
        (LEGAL, "Legal"),
        (MEDICAL, "Medical"),
        (EDUCATION, "Education"),
        (EMPLOYMENT, "Employment"),
        (PROPERTY, "Property & housing"),
        (INSURANCE, "Insurance"),
        (TRAVEL, "Travel"),
        (OTHER, "Other"),
    ]


class Folder(models.Model):
    COLORS = [("teal", "Verdigris"), ("navy", "Ink"), ("brass", "Brass"), ("rose", "Rose"), ("violet", "Violet"), ("slate", "Slate")]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="folders")
    name = models.CharField(max_length=80)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    color = models.CharField(max_length=10, choices=COLORS, default="teal")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["owner", "parent", "name"], name="unique_folder_per_parent")]

    def __str__(self):
        return self.path

    @property
    def path(self):
        names, node, guard = [], self, 0
        while node is not None and guard < 20:
            names.append(node.name)
            node = node.parent
            guard += 1
        return " / ".join(reversed(names))

    @property
    def depth(self):
        depth, node = 0, self.parent
        while node is not None and depth < 20:
            depth += 1
            node = node.parent
        return depth

    def descendant_ids(self):
        ids, frontier = set(), [self.pk]
        while frontier:
            children = list(Folder.objects.filter(parent_id__in=frontier).values_list("pk", flat=True))
            frontier = [c for c in children if c not in ids]
            ids.update(children)
        return ids

    def get_absolute_url(self):
        return f"{reverse('vault:documents')}?folder={self.pk}"


class Tag(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="unique_tag_per_owner")]

    def __str__(self):
        return self.name


class DocumentQuerySet(models.QuerySet):
    def library(self):
        return self.exclude(status=Document.TRASHED)

    def active(self):
        return self.filter(status=Document.ACTIVE)

    def trashed(self):
        return self.filter(status=Document.TRASHED)

    def expired(self, today=None):
        today = today or timezone.localdate()
        return self.filter(expiry_date__lt=today)

    def expiring(self, days, today=None):
        today = today or timezone.localdate()
        return self.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=days))


class Document(models.Model):
    ACTIVE, ARCHIVED, TRASHED = "active", "archived", "trashed"
    STATUSES = [(ACTIVE, "Active"), (ARCHIVED, "Archived"), (TRASHED, "In trash")]
    STANDARD, SENSITIVE, CRITICAL = "standard", "sensitive", "critical"
    SENSITIVITY = [
        (STANDARD, "Standard"),
        (SENSITIVE, "Sensitive - ask for my password before download"),
        (CRITICAL, "Critical - password required, no public links"),
    ]
    INTEGRITY = [("unknown", "Not yet checked"), ("ok", "Intact"), ("failed", "Mismatch")]
    INLINE_TYPES = {
        "application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp",
        "text/plain", "text/csv", "application/json", "text/markdown",
    }

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")
    folder = models.ForeignKey(Folder, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, max_length=2000)
    category = models.CharField(max_length=20, choices=Category.CHOICES, default=Category.OTHER, db_index=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="documents")
    reference_number = models.CharField("Reference / document number", max_length=64, blank=True)
    issuer = models.CharField("Issued by", max_length=120, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    sensitivity = models.CharField(max_length=10, choices=SENSITIVITY, default=STANDARD)
    status = models.CharField(max_length=10, choices=STATUSES, default=ACTIVE, db_index=True)
    is_favorite = models.BooleanField(default=False)

    file = models.FileField(upload_to=document_upload_path, storage=private_storage, max_length=255)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, db_index=True)
    version = models.PositiveIntegerField(default=1)

    verification_code = models.CharField(max_length=20, unique=True, default=generate_verification_code, editable=False)
    public_verification = models.BooleanField("Public verification page", default=False)
    certified_at = models.DateTimeField(null=True, blank=True)
    integrity_status = models.CharField(max_length=10, choices=INTEGRITY, default="unknown")
    last_verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)

    objects = DocumentQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["owner", "expiry_date"]),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("vault:detail", args=[self.pk])

    # ---- derived values --------------------------------------------------
    @property
    def extension(self):
        return os.path.splitext(self.original_name)[1].lower().lstrip(".")

    @property
    def can_preview(self):
        return (self.content_type or mimetypes.guess_type(self.original_name)[0] or "") in self.INLINE_TYPES

    @property
    def is_image(self):
        return (self.content_type or "").startswith("image/")

    @property
    def is_pdf(self):
        return self.content_type == "application/pdf"

    @property
    def is_text(self):
        return (self.content_type or "") in {"text/plain", "text/csv", "application/json", "text/markdown"}

    @property
    def alert_days(self):
        try:
            return self.owner.profile.expiry_alert_days
        except Exception:  # profile missing
            return 30

    @property
    def days_to_expiry(self):
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.localdate()).days

    @property
    def expiry_state(self):
        days = self.days_to_expiry
        if days is None:
            return "none"
        if days < 0:
            return "expired"
        if days <= self.alert_days:
            return "soon"
        return "valid"

    @property
    def days_in_trash_left(self):
        if not self.deleted_at:
            return None
        return max(0, 30 - (timezone.now() - self.deleted_at).days)

    @property
    def short_hash(self):
        return f"{self.sha256[:8]}…{self.sha256[-6:]}" if self.sha256 else ""

    @property
    def tag_names(self):
        return [t.name for t in self.tags.all()]

    # ---- behaviour -------------------------------------------------------
    def compute_stored_hash(self):
        """SHA-256 of the file currently on disk, or None if it is missing."""
        try:
            digest = hashlib.sha256()
            with self.file.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except (FileNotFoundError, OSError, ValueError):
            return None

    def verify_integrity(self, save=True):
        actual = self.compute_stored_hash()
        ok = actual is not None and actual == self.sha256
        self.integrity_status = "ok" if ok else "failed"
        self.last_verified_at = timezone.now()
        if save:
            Document.objects.filter(pk=self.pk).update(
                integrity_status=self.integrity_status, last_verified_at=self.last_verified_at
            )
        return ok

    def delete_stored_files(self):
        names = {self.file.name} | set(self.versions.values_list("file", flat=True))
        storage = self.file.storage
        for name in names:
            if name:
                try:
                    storage.delete(name)
                except OSError:
                    pass


class DocumentVersion(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    file = models.FileField(upload_to=version_upload_path, storage=private_storage, max_length=255)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    note = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-number"]
        constraints = [models.UniqueConstraint(fields=["document", "number"], name="unique_version_number")]

    def __str__(self):
        return f"{self.document.title} v{self.number}"

    @property
    def is_current(self):
        return self.number == self.document.version


class ShareLink(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="share_links")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="share_links")
    token = models.CharField(max_length=64, unique=True, default=generate_share_token, editable=False)
    label = models.CharField(max_length=80, blank=True)
    password_hash = models.CharField(max_length=128, blank=True)
    allow_download = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    max_downloads = models.PositiveIntegerField(null=True, blank=True)
    download_count = models.PositiveIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Link for {self.document.title} ({self.token[:6]}…)"

    def set_password(self, raw):
        self.password_hash = make_password(raw) if raw else ""

    def check_password(self, raw):
        return bool(self.password_hash) and check_password(raw, self.password_hash)

    @property
    def requires_password(self):
        return bool(self.password_hash)

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def is_exhausted(self):
        return self.max_downloads is not None and self.download_count >= self.max_downloads

    @property
    def is_usable(self):
        return self.is_active and not self.is_expired and self.document.status != Document.TRASHED

    @property
    def state(self):
        if not self.is_active:
            return "revoked"
        if self.is_expired:
            return "expired"
        if self.is_exhausted:
            return "exhausted"
        return "live"

    @property
    def downloads_left(self):
        if self.max_downloads is None:
            return None
        return max(0, self.max_downloads - self.download_count)

    def get_absolute_url(self):
        return reverse("vault:share_public", args=[self.token])


class DocumentShare(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="user_shares")
    shared_with = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_shares")
    shared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    can_download = models.BooleanField(default=False)
    note = models.CharField(max_length=200, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["document", "shared_with"], name="unique_share_per_user")]

    def __str__(self):
        return f"{self.document.title} -> {self.shared_with}"

    @property
    def is_active(self):
        return not (self.expires_at and self.expires_at <= timezone.now())


class Notification(models.Model):
    EXPIRING, EXPIRED, SHARE, SECURITY, SYSTEM = "expiring", "expired", "share", "security", "system"
    KINDS = [(EXPIRING, "Expiring soon"), (EXPIRED, "Expired"), (SHARE, "Shared with you"), (SECURITY, "Security"), (SYSTEM, "System")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=10, choices=KINDS, default=SYSTEM)
    title = models.CharField(max_length=160)
    message = models.CharField(max_length=300, blank=True)
    document = models.ForeignKey(Document, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    dedupe_key = models.CharField(max_length=120, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["user", "dedupe_key"], name="unique_notification_key")]

    def __str__(self):
        return self.title


class AuditLog(models.Model):
    ACTIONS = [
        ("register", "Account created"), ("login", "Signed in"), ("logout", "Signed out"),
        ("login_failed", "Failed sign-in"), ("login_blocked", "Sign-in blocked"), ("reauth", "Password re-entered"),
        ("password_change", "Password changed"), ("profile_update", "Profile updated"),
        ("twofa_enable", "2FA enabled"), ("twofa_disable", "2FA disabled"),
        ("token_create", "API token created"), ("token_revoke", "API token revoked"),
        ("upload", "Uploaded"), ("version", "New version"), ("version_restore", "Version restored"),
        ("view", "Viewed"), ("download", "Downloaded"), ("edit", "Edited"),
        ("verify", "Integrity check"), ("certify", "Certificate enabled"), ("uncertify", "Certificate disabled"),
        ("favorite", "Favourite toggled"), ("archive", "Archived"), ("unarchive", "Unarchived"),
        ("trash", "Moved to trash"), ("restore", "Restored"), ("delete", "Deleted permanently"),
        ("share_link_create", "Share link created"), ("share_link_revoke", "Share link revoked"),
        ("share_user", "Shared with user"), ("unshare_user", "Access removed"),
        ("public_view", "Public link opened"), ("public_download", "Public download"),
        ("public_verify", "Public verification"),
        ("folder", "Folder changed"), ("tag", "Tag changed"), ("bulk", "Bulk action"), ("export", "Vault exported"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries")
    action = models.CharField(max_length=24, choices=ACTIONS, db_index=True)
    document = models.ForeignKey(Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries")
    document_title = models.CharField(max_length=160, blank=True)
    details = models.CharField(max_length=300, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.get_action_display()} - {self.document_title or self.details}"
