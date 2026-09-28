from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import ApiToken, UserProfile

User = get_user_model()


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    fk_name = "user"
    fields = ("display_name", "phone", "organization", "bio", "timezone", "storage_quota_mb", "expiry_alert_days", "totp_enabled")
    readonly_fields = ("totp_enabled",)


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "is_active", "document_count", "date_joined")
    list_filter = BaseUserAdmin.list_filter + ("profile__totp_enabled",)

    @admin.display(description="Documents")
    def document_count(self, obj):
        return obj.documents.count()

    def get_inline_instances(self, request, obj=None):
        return super().get_inline_instances(request, obj) if obj else []


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "organization", "storage_quota_mb", "totp_enabled", "created_at")
    list_filter = ("totp_enabled", "timezone")
    search_fields = ("user__username", "user__email", "display_name", "organization")
    readonly_fields = ("totp_secret", "created_at")
    raw_id_fields = ("user",)


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "prefix", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active",)
    search_fields = ("name", "user__username", "prefix")
    readonly_fields = ("prefix", "key_hash", "created_at", "last_used_at")
    raw_id_fields = ("user",)
