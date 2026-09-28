from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("docs/", views.docs_page, name="docs"),
    path("v1/", views.index, name="index"),
    path("v1/auth/token/", views.token, name="token"),
    path("v1/me/", views.me, name="me"),
    path("v1/stats/", views.stats, name="stats"),
    path("v1/insights/", views.insights, name="insights"),
    path("v1/documents/", views.documents, name="documents"),
    path("v1/documents/<int:pk>/", views.document_detail, name="document_detail"),
    path("v1/documents/<int:pk>/download/", views.document_download, name="document_download"),
    path("v1/documents/<int:pk>/verify/", views.document_verify, name="document_verify"),
    path("v1/documents/<int:pk>/related/", views.document_related, name="document_related"),
    path("v1/documents/<int:pk>/versions/", views.document_versions, name="document_versions"),
    path("v1/documents/<int:pk>/share-links/", views.document_share_links, name="document_share_links"),
    path("v1/share-links/<int:pk>/", views.share_link_detail, name="share_link_detail"),
    path("v1/folders/", views.folders, name="folders"),
    path("v1/folders/<int:pk>/", views.folder_detail, name="folder_detail"),
    path("v1/tags/", views.tags, name="tags"),
    path("v1/tags/<int:pk>/", views.tag_detail, name="tag_detail"),
    path("v1/activity/", views.activity, name="activity"),
    path("v1/notifications/", views.notifications, name="notifications"),
    path("v1/verify/", views.verify, name="verify"),
]
