import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone


def avatar_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    return f"avatars/user{instance.user_id}-{secrets.token_hex(6)}.{ext}"


class UserProfile(models.Model):
    TIMEZONES = [
        ("Asia/Kolkata", "India (IST)"),
        ("UTC", "UTC"),
        ("Europe/London", "London"),
        ("Europe/Berlin", "Central Europe"),
        ("America/New_York", "US Eastern"),
        ("America/Los_Angeles", "US Pacific"),
        ("Asia/Singapore", "Singapore"),
        ("Australia/Sydney", "Sydney"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    organization = models.CharField(max_length=120, blank=True)
    bio = models.CharField(max_length=240, blank=True)
    avatar = models.FileField(upload_to=avatar_path, blank=True)
    timezone = models.CharField(max_length=40, choices=TIMEZONES, default="Asia/Kolkata")
    storage_quota_mb = models.PositiveIntegerField(default=500)
    expiry_alert_days = models.PositiveSmallIntegerField(default=30, help_text="Warn this many days before a document expires.")
    totp_secret = models.CharField(max_length=64, blank=True)
    totp_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"Profile of {self.user.get_username()}"

    @property
    def name(self):
        return self.display_name or self.user.get_full_name() or self.user.get_username()

    @property
    def initials(self):
        parts = [p for p in self.name.replace("_", " ").split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def quota_bytes(self):
        return self.storage_quota_mb * 1024 * 1024

    @property
    def storage_used(self):
        from vault.models import DocumentVersion

        total = DocumentVersion.objects.filter(document__owner=self.user).aggregate(t=Sum("size"))["t"]
        return total or 0

    @property
    def storage_left(self):
        return max(0, self.quota_bytes - self.storage_used)

    @property
    def storage_percent(self):
        if not self.quota_bytes:
            return 100
        return min(100, round(self.storage_used * 100 / self.quota_bytes, 1))


class ApiToken(models.Model):
    """API tokens are stored as SHA-256 digests; the raw value is shown once."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=80)
    prefix = models.CharField(max_length=8, editable=False)
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"

    @staticmethod
    def digest(raw):
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def issue(cls, user, name):
        raw = "vv_" + secrets.token_urlsafe(32)
        token = cls.objects.create(user=user, name=name, prefix=raw[:8], key_hash=cls.digest(raw))
        return token, raw

    @classmethod
    def authenticate(cls, raw):
        if not raw:
            return None
        token = cls.objects.select_related("user").filter(key_hash=cls.digest(raw), is_active=True).first()
        if token and token.user.is_active:
            cls.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
            return token
        return None
