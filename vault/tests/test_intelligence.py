from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

from core.testing import TempStorageTestCase
from vault import intelligence, services
from vault.models import Category, Document

User = get_user_model()


class IntelligenceTests(TempStorageTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("bob", "bob@example.com", "pw12345!")

    def test_suggest_metadata_detects_category(self):
        s = intelligence.suggest_metadata("passport-scan-2026.pdf")
        self.assertEqual(s["category"], Category.IDENTITY)
        self.assertGreater(s["confidence"], 0)

    def test_suggest_metadata_unknown_defaults_other(self):
        s = intelligence.suggest_metadata("random-file-xyz.pdf")
        self.assertEqual(s["category"], Category.OTHER)

    def test_pretty_title(self):
        self.assertEqual(intelligence.pretty_title("my_passport-scan.pdf"), "My passport scan")

    def _upload(self, name, content, category=Category.OTHER):
        f = ContentFile(content, name=name)
        f.size = len(content)
        return services.create_document(self.user, f, Document(title=name, category=category))

    def test_find_duplicates(self):
        self._upload("a.pdf", b"same bytes")
        self._upload("b.pdf", b"same bytes")
        self._upload("c.pdf", b"different")
        groups = intelligence.find_duplicates(self.user)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 2)

    def test_vault_health_empty_vault(self):
        health = intelligence.vault_health(self.user)
        self.assertEqual(health["score"], 50)
        self.assertEqual(health["document_count"], 0)

    def test_vault_health_penalizes_expired(self):
        from datetime import timedelta
        from django.utils import timezone
        doc = self._upload("passport.pdf", b"data", Category.IDENTITY)
        doc.expiry_date = timezone.localdate() - timedelta(days=5)
        doc.save()
        health = intelligence.vault_health(self.user)
        self.assertLess(health["score"], 100)
        self.assertTrue(any(r["level"] == "critical" for r in health["recommendations"]))

    def test_related_documents_by_shared_tag(self):
        d1 = self._upload("insurance-policy.pdf", b"1", Category.INSURANCE)
        d2 = self._upload("insurance-renewal.pdf", b"2", Category.INSURANCE)
        services.set_tags(d1, ["health"])
        services.set_tags(d2, ["health"])
        related = intelligence.related_documents(d1)
        self.assertTrue(any(r["document"].pk == d2.pk for r in related))
