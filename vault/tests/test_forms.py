from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from core.testing import TempStorageTestCase
from vault.forms import DocumentUploadForm, FolderForm, ShareUserForm
from vault.models import Folder

User = get_user_model()


class FormTests(TempStorageTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("erin", "erin@example.com", "pw12345!")

    def test_upload_form_auto_category(self):
        f = SimpleUploadedFile("aadhaar-card.pdf", b"%PDF-1.4 x", content_type="application/pdf")
        form = DocumentUploadForm({"category": "auto", "sensitivity": "standard", "tags_text": ""}, {"file": f}, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["category"], "identity")

    def test_upload_form_rejects_empty_file(self):
        f = SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")
        form = DocumentUploadForm({"category": "auto", "sensitivity": "standard"}, {"file": f}, user=self.user)
        self.assertFalse(form.is_valid())

    def test_folder_form_prevents_duplicate_name(self):
        Folder.objects.create(owner=self.user, name="Money")
        form = FolderForm({"name": "Money", "color": "teal"}, user=self.user)
        self.assertFalse(form.is_valid())

    def test_folder_form_prevents_self_parenting(self):
        folder = Folder.objects.create(owner=self.user, name="Money")
        form = FolderForm({"name": "Money2", "parent": folder.pk, "color": "teal"}, instance=folder, user=self.user)
        self.assertFalse(form.is_valid())

    def test_share_user_form_unknown_recipient(self):
        form = ShareUserForm({"recipient": "nobody@example.com"}, owner=self.user)
        self.assertFalse(form.is_valid())

    def test_share_user_form_cannot_share_with_self(self):
        form = ShareUserForm({"recipient": "erin"}, owner=self.user)
        self.assertFalse(form.is_valid())
