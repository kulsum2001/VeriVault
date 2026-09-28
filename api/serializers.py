"""Plain-Python serializers that turn model instances into JSON-ready dicts."""
from django.urls import reverse


def _dt(value):
    return value.isoformat() if value else None


class TagSerializer:
    @staticmethod
    def data(tag, count=None):
        out = {"id": tag.pk, "name": tag.name}
        if count is not None:
            out["document_count"] = count
        return out


class FolderSerializer:
    @staticmethod
    def data(folder):
        return {"id": folder.pk, "name": folder.name, "path": folder.path, "parent": folder.parent_id,
                "color": folder.color, "created_at": _dt(folder.created_at)}


class ProfileSerializer:
    @staticmethod
    def data(user):
        p = user.profile
        return {
            "id": user.pk, "username": user.get_username(), "email": user.email, "name": p.name,
            "organization": p.organization, "timezone": p.timezone, "two_factor_enabled": p.totp_enabled,
            "expiry_alert_days": p.expiry_alert_days,
            "storage": {"used_bytes": p.storage_used, "quota_bytes": p.quota_bytes, "percent": p.storage_percent},
        }


class VersionSerializer:
    @staticmethod
    def data(version):
        return {"number": version.number, "original_name": version.original_name, "size": version.size,
                "sha256": version.sha256, "note": version.note, "is_current": version.is_current,
                "uploaded_by": version.uploaded_by.get_username() if version.uploaded_by else None,
                "created_at": _dt(version.created_at)}


class DocumentSerializer:
    def __init__(self, request):
        self.request = request

    def __call__(self, doc):
        return self.data(doc)

    def data(self, doc):
        return {
            "id": doc.pk, "title": doc.title, "description": doc.description,
            "category": doc.category, "category_label": doc.get_category_display(),
            "folder": {"id": doc.folder_id, "name": doc.folder.name} if doc.folder_id else None,
            "tags": [t.name for t in doc.tags.all()],
            "reference_number": doc.reference_number, "issuer": doc.issuer,
            "issue_date": _dt(doc.issue_date), "expiry_date": _dt(doc.expiry_date),
            "expiry_state": doc.expiry_state, "days_to_expiry": doc.days_to_expiry,
            "sensitivity": doc.sensitivity, "status": doc.status, "is_favorite": doc.is_favorite,
            "original_name": doc.original_name, "content_type": doc.content_type, "size": doc.size,
            "sha256": doc.sha256, "version": doc.version,
            "integrity_status": doc.integrity_status, "last_verified_at": _dt(doc.last_verified_at),
            "verification_code": doc.verification_code, "public_verification": doc.public_verification,
            "created_at": _dt(doc.created_at), "updated_at": _dt(doc.updated_at),
            "urls": {
                "self": self.request.build_absolute_uri(reverse("api:document_detail", args=[doc.pk])),
                "download": self.request.build_absolute_uri(reverse("api:document_download", args=[doc.pk])),
                "web": self.request.build_absolute_uri(doc.get_absolute_url()),
            },
        }


class ShareLinkSerializer:
    def __init__(self, request):
        self.request = request

    def __call__(self, link):
        return self.data(link)

    def data(self, link):
        return {
            "id": link.pk, "document": link.document_id, "label": link.label, "state": link.state,
            "url": self.request.build_absolute_uri(link.get_absolute_url()),
            "password_protected": link.requires_password, "allow_download": link.allow_download,
            "expires_at": _dt(link.expires_at), "max_downloads": link.max_downloads,
            "download_count": link.download_count, "view_count": link.view_count,
            "created_at": _dt(link.created_at),
        }


class AuditSerializer:
    @staticmethod
    def data(entry):
        return {"id": entry.pk, "action": entry.action, "action_label": entry.get_action_display(),
                "document": entry.document_id, "document_title": entry.document_title, "details": entry.details,
                "ip_address": entry.ip_address, "created_at": _dt(entry.created_at)}


class NotificationSerializer:
    @staticmethod
    def data(n):
        return {"id": n.pk, "kind": n.kind, "title": n.title, "message": n.message, "document": n.document_id,
                "is_read": n.is_read, "created_at": _dt(n.created_at)}


def serialize_health(health):
    return {
        "score": health["score"], "grade": health["grade"], "document_count": health["document_count"],
        "recommendations": [{k: r[k] for k in ("level", "title", "detail")} for r in health["recommendations"]],
        "essentials": [{"label": c["label"], "category": c["category"], "present": c["present"],
                        "document": c["document"].pk if c["document"] else None} for c in health["checklist"]],
    }
