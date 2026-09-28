"""Shared helpers for the automated tests."""
import shutil
import tempfile

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings


class TempStorageTestCase(TestCase):
    """Runs each test class against throw-away media/vault directories."""

    _tmp = None

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="verivault-tests-")
        cls._override = override_settings(
            VAULT_STORAGE_ROOT=cls._tmp + "/vault",
            MEDIA_ROOT=cls._tmp + "/media",
            PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
        )
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def setUp(self):
        cache.clear()

    @staticmethod
    def make_file(name="passport-scan.pdf", content=b"%PDF-1.4 sample content", content_type="application/pdf"):
        return SimpleUploadedFile(name, content, content_type=content_type)
