from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.testing import TempStorageTestCase
from vault.models import Document, ShareLink

User = get_user_model()


class DocumentFlowTests(TempStorageTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("carol", "carol@example.com", "pw12345!")
        self.client.login(username="carol", password="pw12345!")

    def upload(self, name="passport.pdf", content=b"%PDF-1.4 sample", **extra):
        data = {"title": "My Passport", "category": "identity", "sensitivity": "standard",
               "tags_text": "id, travel", "file": SimpleUploadedFile(name, content, content_type="application/pdf")}
        data.update(extra)
        return self.client.post(reverse("vault:upload"), data, follow=True)

    def test_upload_creates_document(self):
        resp = self.upload()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Document.objects.filter(owner=self.user).count(), 1)
        doc = Document.objects.get(owner=self.user)
        self.assertEqual(doc.category, "identity")
        self.assertEqual(set(doc.tag_names), {"id", "travel"})

    def test_upload_rejects_blocked_extension(self):
        resp = self.upload(name="virus.exe", content=b"MZ")
        self.assertEqual(Document.objects.count(), 0)
        self.assertContains(resp, "not allowed")

    def test_dashboard_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("vault:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_document_detail_and_download(self):
        self.upload()
        doc = Document.objects.get(owner=self.user)
        detail = self.client.get(doc.get_absolute_url())
        self.assertEqual(detail.status_code, 200)
        download = self.client.get(reverse("vault:download", args=[doc.pk]))
        self.assertEqual(download.status_code, 200)

    def test_other_user_cannot_access_document(self):
        self.upload()
        doc = Document.objects.get(owner=self.user)
        User.objects.create_user("dave", "dave@example.com", "pw12345!")
        self.client.logout()
        self.client.login(username="dave", password="pw12345!")
        resp = self.client.get(doc.get_absolute_url())
        self.assertEqual(resp.status_code, 404)

    def test_trash_and_restore_flow(self):
        self.upload()
        doc = Document.objects.get(owner=self.user)
        self.client.post(reverse("vault:trash_doc", args=[doc.pk]))
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.TRASHED)
        self.client.post(reverse("vault:restore", args=[doc.pk]))
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.ACTIVE)

    def test_favorite_toggle_json(self):
        self.upload()
        doc = Document.objects.get(owner=self.user)
        resp = self.client.post(reverse("vault:favorite", args=[doc.pk]), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.json(), {"favorite": True})

    def test_share_link_create_and_public_download(self):
        self.upload()
        doc = Document.objects.get(owner=self.user)
        resp = self.client.post(reverse("vault:share_link_create", args=[doc.pk]),
                                {"label": "test", "expires": "7d", "allow_download": "on"}, follow=True)
        link = ShareLink.objects.get(document=doc)
        self.client.logout()
        page = self.client.get(link.get_absolute_url())
        self.assertEqual(page.status_code, 200)
        dl = self.client.post(reverse("vault:share_public_download", args=[link.token]))
        self.assertEqual(dl.status_code, 200)
        link.refresh_from_db()
        self.assertEqual(link.download_count, 1)

    def test_critical_document_cannot_get_public_link(self):
        self.upload(sensitivity="critical")
        doc = Document.objects.get(owner=self.user)
        self.client.post(reverse("vault:share_link_create", args=[doc.pk]), {"expires": "7d"})
        self.assertEqual(ShareLink.objects.filter(document=doc).count(), 0)

    def test_public_certificate_verification(self):
        self.upload()
        doc = Document.objects.get(owner=self.user)
        self.client.post(reverse("vault:certify", args=[doc.pk]))
        doc.refresh_from_db()
        self.assertTrue(doc.public_verification)
        self.client.logout()
        resp = self.client.post(reverse("vault:verify"), {"code": doc.verification_code})
        self.assertContains(resp, "Certificate found")

    def test_bulk_favorite_action(self):
        self.upload()
        doc = Document.objects.get(owner=self.user)
        self.client.post(reverse("vault:bulk"), {"ids": [doc.pk], "action": "favorite"})
        doc.refresh_from_db()
        self.assertTrue(doc.is_favorite)
