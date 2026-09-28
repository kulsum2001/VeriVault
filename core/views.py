from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

FEATURES = [
    ("Tamper-evident fingerprints", "Every file gets a SHA-256 fingerprint at upload. Re-check integrity any time and prove a document has not changed."),
    ("Version history", "Upload revisions without losing the original. Compare hashes, download or restore any earlier version."),
    ("Secure sharing", "Expiring links with optional passwords and download limits, or share directly with another VeriVault user."),
    ("Public verification certificates", "Issue a verification code so anyone can confirm a document's fingerprint without seeing the file."),
    ("Expiry reminders", "Passports, policies and licences expire. VeriVault tells you before they do."),
    ("Vault health score", "A rule-based advisor scores your vault, spots duplicates and lists the essential documents you are missing."),
    ("Full audit trail", "Every view, download, share and verification is logged with time and IP address, and exportable as CSV."),
    ("Smart organisation", "Folders, tags and automatic category suggestions based on file names keep everything findable."),
    ("Developer API", "A token-authenticated JSON API covers documents, folders, tags, sharing, insights and verification."),
]

FAQ = [
    ("Are my files encrypted?", "Files are stored on the server's disk outside the public web root and are only served through permission-checked views. VeriVault does not add its own encryption layer, so use full-disk encryption on the host for encryption at rest, and HTTPS in transit."),
    ("What does 'verified' actually mean?", "It means the file's current SHA-256 fingerprint matches the fingerprint recorded when it was uploaded. Anyone holding a certificate code can check a file against that fingerprint on the public verification page."),
    ("Can I share a document without an account?", "Yes. Create a share link with an expiry date, a download limit and an optional password. Critical documents cannot be shared by public link."),
    ("What happens when I delete a document?", "It moves to the trash, where you can restore it. Items are permanently purged after 30 days or when you empty the trash."),
    ("How are duplicates detected?", "By SHA-256 fingerprint. Two files with identical content share a fingerprint, regardless of file name."),
    ("Is there an API?", "Yes. Create a token under Security and see the API reference for every endpoint."),
]


def home(request):
    return render(request, "core/home.html", {"features": FEATURES[:6]})


def features(request):
    return render(request, "core/features.html", {"features": FEATURES})


def security(request):
    return render(request, "core/security.html")


def faq(request):
    return render(request, "core/faq.html", {"faq": FAQ})


def privacy(request):
    return render(request, "core/privacy.html")


def terms(request):
    return render(request, "core/terms.html")


@require_GET
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /api/",
        "Disallow: /dashboard/",
        "Disallow: /documents/",
        "Disallow: /accounts/",
        "Disallow: /s/",
        "Allow: /",
        f"Sitemap: {settings.SITE_URL.rstrip('/')}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def bad_request(request, exception=None):
    return render(request, "400.html", status=400)


def permission_denied(request, exception=None):
    return render(request, "403.html", {"exception": str(exception) if exception else ""}, status=403)


def page_not_found(request, exception=None):
    return render(request, "404.html", status=404)


def server_error(request):
    return render(request, "500.html", status=500)
