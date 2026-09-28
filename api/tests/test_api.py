import json

from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import ApiToken
from core.testing import TempStorageTestCase
from vault.models import Document

User = get_user_model()


class ApiTests(TempStorageTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("kate", "kate@example.com", "pw12345!")
        self.token_obj, self.token = ApiToken.issue(self.user, "test")
        self.auth = {"HTTP_AUTHORIZATION": f"Token {self.token}"}

    def test_token_endpoint_issues_token(self):
        User.objects.create_user("liam", "liam@example.com", "pw12345!")
        resp = self.client.post(reverse("api:token"), data=json.dumps({"username": "liam", "password": "pw12345!"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 201)
        self.assertIn("token", resp.json())

    def test_documents_requires_auth(self):
        resp = self.client.get(reverse("api:documents"))
        self.assertEqual(resp.status_code, 401)

    def test_upload_and_list_via_api(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        resp = self.client.post(reverse("api:documents"), {
            "file": SimpleUploadedFile("offer-letter.pdf", b"%PDF-1.4 x", content_type="application/pdf"),
            "title": "Offer", "sensitivity": "standard",
        }, **self.auth)
        self.assertEqual(resp.status_code, 201, resp.content)
        doc_id = resp.json()["id"]
        listing = self.client.get(reverse("api:documents"), **self.auth)
        self.assertEqual(listing.json()["count"], 1)
        detail = self.client.get(reverse("api:document_detail", args=[doc_id]), **self.auth)
        self.assertEqual(detail.json()["category"], "employment")

    def test_patch_document(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        resp = self.client.post(reverse("api:documents"), {
            "file": SimpleUploadedFile("note.txt", b"hello", content_type="text/plain"), "title": "Note",
        }, **self.auth)
        doc_id = resp.json()["id"]
        patch = self.client.patch(reverse("api:document_detail", args=[doc_id]), data=json.dumps({"is_favorite": True}),
                                  content_type="application/json", **self.auth)
        self.assertEqual(patch.status_code, 200)
        self.assertTrue(patch.json()["is_favorite"])

    def test_delete_moves_to_trash_then_permanent(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        resp = self.client.post(reverse("api:documents"), {
            "file": SimpleUploadedFile("note2.txt", b"hello2", content_type="text/plain"), "title": "Note2",
        }, **self.auth)
        doc_id = resp.json()["id"]
        d1 = self.client.delete(reverse("api:document_detail", args=[doc_id]), **self.auth)
        self.assertEqual(d1.json()["permanent"], False)
        d2 = self.client.delete(reverse("api:document_detail", args=[doc_id]) + "?permanent=1", **self.auth)
        self.assertEqual(d2.json()["permanent"], True)
        self.assertFalse(Document.objects.filter(pk=doc_id).exists())

    def test_public_verify_endpoint(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        resp = self.client.post(reverse("api:documents"), {
            "file": SimpleUploadedFile("cert.pdf", b"%PDF-1.4 cert", content_type="application/pdf"), "title": "Cert",
        }, **self.auth)
        doc_id = resp.json()["id"]
        self.client.post(reverse("api:document_verify", args=[doc_id]), **self.auth)
        self.client.login(username="kate", password="pw12345!")
        self.client.post(reverse("vault:certify", args=[doc_id]))
        self.client.logout()
        doc = Document.objects.get(pk=doc_id)
        v = self.client.post(reverse("api:verify"), data=json.dumps({"code": doc.verification_code}), content_type="application/json")
        self.assertEqual(v.status_code, 200)
        self.assertTrue(v.json()["found"])

    def test_invalid_token_rejected(self):
        resp = self.client.get(reverse("api:documents"), HTTP_AUTHORIZATION="Token bogus")
        self.assertEqual(resp.status_code, 401)
