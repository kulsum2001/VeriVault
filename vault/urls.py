from django.urls import path

from . import views

app_name = "vault"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("insights/", views.insights, name="insights"),
    path("insights/verify-all/", views.verify_all, name="verify_all"),

    path("documents/", views.document_list, name="documents"),
    path("documents/upload/", views.document_upload, name="upload"),
    path("documents/bulk/", views.bulk_action, name="bulk"),
    path("documents/suggest/", views.suggest, name="suggest"),
    path("documents/suggest-metadata/", views.suggest_metadata, name="suggest_metadata"),
    path("documents/<int:pk>/", views.document_detail, name="detail"),
    path("documents/<int:pk>/edit/", views.document_edit, name="edit"),
    path("documents/<int:pk>/download/", views.document_download, name="download"),
    path("documents/<int:pk>/preview/", views.document_preview, name="preview"),
    path("documents/<int:pk>/favorite/", views.document_favorite, name="favorite"),
    path("documents/<int:pk>/archive/", views.document_archive, name="archive"),
    path("documents/<int:pk>/trash/", views.document_trash, name="trash_doc"),
    path("documents/<int:pk>/restore/", views.document_restore, name="restore"),
    path("documents/<int:pk>/delete/", views.document_delete, name="delete"),
    path("documents/<int:pk>/verify/", views.document_verify, name="verify_doc"),
    path("documents/<int:pk>/certificate/", views.document_certify, name="certify"),
    path("documents/<int:pk>/versions/new/", views.version_new, name="version_new"),
    path("documents/<int:pk>/versions/<int:number>/download/", views.version_download, name="version_download"),
    path("documents/<int:pk>/versions/<int:number>/restore/", views.version_restore, name="version_restore"),
    path("documents/<int:pk>/share/link/", views.share_link_create, name="share_link_create"),
    path("documents/<int:pk>/share/link/<int:link_id>/revoke/", views.share_link_revoke, name="share_link_revoke"),
    path("documents/<int:pk>/share/user/", views.share_user_create, name="share_user_create"),
    path("documents/<int:pk>/share/user/<int:share_id>/revoke/", views.share_user_revoke, name="share_user_revoke"),

    path("shared/", views.shared_with_me, name="shared_with_me"),
    path("trash/", views.trash, name="trash"),
    path("trash/empty/", views.trash_empty, name="trash_empty"),
    path("folders/", views.folders, name="folders"),
    path("folders/<int:pk>/edit/", views.folder_edit, name="folder_edit"),
    path("folders/<int:pk>/delete/", views.folder_delete, name="folder_delete"),
    path("tags/", views.tags, name="tags"),
    path("activity/", views.activity, name="activity"),
    path("activity/export/", views.activity_export, name="activity_export"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/<int:pk>/read/", views.notification_read, name="notification_read"),
    path("export/", views.export_vault, name="export"),

    # Public (no login)
    path("s/<str:token>/", views.share_public, name="share_public"),
    path("s/<str:token>/download/", views.share_public_download, name="share_public_download"),
    path("verify/", views.verify_public, name="verify"),
    path("verify/<str:code>/", views.verify_public, name="verify_code"),
]
