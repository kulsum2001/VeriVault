from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse

from core.testing import TempStorageTestCase
from vault import services
from vault.models import Document, Folder

User = get_user_model()


class DocumentModelTests(TempStorageTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("alice", "alice@example.com", "pw12345!")

    def _upload(self, name="file.pdf", content=b"hello world"):
        f = ContentFile(content, name=name)
        f.size = len(content)
        return services.create_document(self.user, f, Document(title="Doc"), ["a", "b"])

    def test_create_document_sets_hash_and_version(self):
        doc = self._upload()
        self.assertEqual(doc.version, 1)
        self.assertEqual(len(doc.sha256), 64)
        self.assertEqual(doc.versions.count(), 1)
        self.assertEqual(set(doc.tag_names), {"a", "b"})

    def test_verify_integrity_ok_then_detects_tamper(self):
        doc = self._upload()
        self.assertTrue(doc.verify_integrity())
        with doc.file.open("wb") as fh:
            fh.write(b"tampered content")
        self.assertFalse(doc.verify_integrity())
        doc.refresh_from_db()
        self.assertEqual(doc.integrity_status, "failed")

    def test_add_version_increments_and_updates_current(self):
        doc = self._upload()
        f2 = ContentFile(b"version two", name="file2.pdf")
        f2.size = len(f2.read()); f2.seek(0)
        v2 = services.add_version(doc, f2, self.user, "update")
        doc.refresh_from_db()
        self.assertEqual(doc.version, 2)
        self.assertEqual(v2.number, 2)
        self.assertEqual(doc.versions.count(), 2)

    def test_folder_path_and_descendants(self):
        top = Folder.objects.create(owner=self.user, name="Top")
        mid = Folder.objects.create(owner=self.user, name="Mid", parent=top)
        leaf = Folder.objects.create(owner=self.user, name="Leaf", parent=mid)
        self.assertEqual(leaf.path, "Top / Mid / Leaf")
        self.assertEqual(top.descendant_ids(), {mid.pk, leaf.pk})

    def test_expiry_state(self):
        from datetime import timedelta
        from django.utils import timezone
        doc = self._upload()
        doc.expiry_date = timezone.localdate() - timedelta(days=1)
        doc.save()
        self.assertEqual(doc.expiry_state, "expired")
        doc.expiry_date = timezone.localdate() + timedelta(days=5)
        doc.save()
        self.assertEqual(doc.expiry_state, "soon")
        doc.expiry_date = timezone.localdate() + timedelta(days=100)
        doc.save()
        self.assertEqual(doc.expiry_state, "valid")

    def test_trash_and_purge(self):
        doc = self._upload()
        services.trash_documents(Document.objects.filter(pk=doc.pk))
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.TRASHED)
        self.assertIsNotNone(doc.deleted_at)
        services.restore_documents(Document.objects.filter(pk=doc.pk))
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.ACTIVE)
