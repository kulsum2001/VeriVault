"""Root URL configuration for VeriVault."""
import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from core.sitemaps import SITEMAPS

admin.site.site_header = "VeriVault Administration"
admin.site.site_title = "VeriVault Admin"
admin.site.index_title = "Vault operations"

handler400 = "core.views.bad_request"
handler403 = "core.views.permission_denied"
handler404 = "core.views.page_not_found"
handler500 = "core.views.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path("api/", include("api.urls")),
    path("accounts/", include("accounts.urls")),
    path("", include("vault.urls")),
    path("", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif os.environ.get("VERIVAULT_SERVE_MEDIA", "true").strip().lower() in ("1", "true", "yes", "on"):
    # Django's static() helper is a no-op outside DEBUG, so a small personal
    # deployment (no separate media host) wires the serve view directly.
    # Fine for one process serving one vault; move to S3/R2 and set
    # VERIVAULT_SERVE_MEDIA=false if this ever needs to scale out.
    from django.urls import re_path
    from django.views.static import serve as serve_static

    media_prefix = settings.MEDIA_URL.lstrip("/")
    urlpatterns += [
        re_path(rf"^{media_prefix}(?P<path>.*)$", serve_static, {"document_root": settings.MEDIA_ROOT}),
    ]
