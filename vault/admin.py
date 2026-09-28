from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from .models import (AuditLog, Document, DocumentShare, DocumentVersion, Folder, Notification, ShareLink, Tag)


class VersionInline(admin.TabularInline):
    model = DocumentVersion
    extra = 0
    can_delete = False
    fields = ("number", "original_name", "size", "sha256", "note", "uploaded_by", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class ShareLinkInline(admin.TabularInline):
    model = ShareLink
    extra = 0
    fields = ("label", "is_active", "expires_at", "max_downloads", "download_count", "view_count")
    readonly_fields = ("download_count", "view_count")
    show_change_link = True


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "category", "status", "sensitivity", "expiry_badge", "size_kb", "version",
                    "integrity_badge", "public_verification", "updated_at")
    list_filter = ("status", "category", "sensitivity", "integrity_status", "public_verification", "is_favorite", "created_at")
    search_fields = ("title", "original_name", "owner__username", "owner__email", "sha256", "verification_code", "reference_number")
    date_hierarchy = "created_at"
    raw_id_fields = ("owner", "folder")
    filter_horizontal = ("tags",)
    readonly_fields = ("sha256", "size", "content_type", "original_name", "version", "verification_code",
                       "certified_at", "last_verified_at", "created_at", "updated_at", "deleted_at", "last_accessed_at")
    inlines = [VersionInline, ShareLinkInline]
    actions = ["action_archive", "action_trash", "action_restore", "action_verify"]
    fieldsets = (
        ("Record", {"fields": ("owner", "title", "description", "category", "folder", "tags", "status", "is_favorite")}),
        ("Details", {"fields": ("reference_number", "issuer", "issue_date", "expiry_date", "sensitivity")}),
        ("File", {"fields": ("file", "original_name", "content_type", "size", "sha256", "version")}),
        ("Verification", {"fields": ("verification_code", "public_verification", "certified_at", "integrity_status", "last_verified_at")}),
        ("Timestamps", {"fields": ("created_at", "updated_at", "deleted_at", "last_accessed_at")}),
    )

    @admin.display(description="Size (KB)", ordering="size")
    def size_kb(self, obj):
        return f"{obj.size / 1024:.1f}"

    @admin.display(description="Expiry")
    def expiry_badge(self, obj):
        colors = {"expired": "#b42318", "soon": "#b54708", "valid": "#067647", "none": "#667085"}
        label = {"expired": "Expired", "soon": "Soon", "valid": "Valid", "none": "—"}[obj.expiry_state]
        return format_html('<b style="color:{}">{}</b>', colors[obj.expiry_state], label)

    @admin.display(description="Integrity")
    def integrity_badge(self, obj):
        colors = {"ok": "#067647", "failed": "#b42318", "unknown": "#667085"}
        return format_html('<b style="color:{}">{}</b>', colors[obj.integrity_status], obj.get_integrity_status_display())

    @admin.action(description="Archive selected documents")
    def action_archive(self, request, queryset):
        self.message_user(request, f"{queryset.update(status=Document.ARCHIVED)} archived.")

    @admin.action(description="Move selected documents to trash")
    def action_trash(self, request, queryset):
        n = queryset.exclude(status=Document.TRASHED).update(status=Document.TRASHED, deleted_at=timezone.now())
        self.message_user(request, f"{n} moved to trash.")

    @admin.action(description="Restore selected documents")
    def action_restore(self, request, queryset):
        n = queryset.update(status=Document.ACTIVE, deleted_at=None)
        self.message_user(request, f"{n} restored.")

    @admin.action(description="Run integrity check on selected documents")
    def action_verify(self, request, queryset):
        bad = sum(0 if d.verify_integrity() else 1 for d in queryset)
        level = messages.ERROR if bad else messages.SUCCESS
        self.message_user(request, f"Checked {queryset.count()} documents; {bad} failed.", level)


@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "parent", "color", "created_at")
    list_filter = ("color",)
    search_fields = ("name", "owner__username")
    raw_id_fields = ("owner", "parent")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "created_at")
    search_fields = ("name", "owner__username")
    raw_id_fields = ("owner",)


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ("document", "number", "original_name", "size", "uploaded_by", "created_at")
    search_fields = ("document__title", "original_name", "sha256")
    raw_id_fields = ("document", "uploaded_by")
    readonly_fields = ("sha256", "size", "created_at")


@admin.register(ShareLink)
class ShareLinkAdmin(admin.ModelAdmin):
    list_display = ("document", "label", "created_by", "state_badge", "expires_at", "download_count", "max_downloads", "view_count")
    list_filter = ("is_active", "allow_download")
    search_fields = ("document__title", "label", "created_by__username")
    raw_id_fields = ("document", "created_by")
    readonly_fields = ("token", "password_hash", "download_count", "view_count", "created_at", "last_accessed_at")
    actions = ["revoke"]

    @admin.display(description="State")
    def state_badge(self, obj):
        return obj.state

    @admin.action(description="Revoke selected links")
    def revoke(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=False)} links revoked.")


@admin.register(DocumentShare)
class DocumentShareAdmin(admin.ModelAdmin):
    list_display = ("document", "shared_with", "shared_by", "can_download", "expires_at", "created_at")
    list_filter = ("can_download",)
    search_fields = ("document__title", "shared_with__username", "shared_by__username")
    raw_id_fields = ("document", "shared_with", "shared_by")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "kind", "is_read", "created_at")
    list_filter = ("kind", "is_read")
    search_fields = ("title", "user__username")
    raw_id_fields = ("user", "document")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "user", "document_title", "details", "ip_address")
    list_filter = ("action", "created_at")
    search_fields = ("document_title", "details", "user__username", "ip_address")
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
