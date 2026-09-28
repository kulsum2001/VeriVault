"""Private file storage for vault documents.

Files are kept in ``settings.VAULT_STORAGE_ROOT`` which is *not* exposed by any
URL. The only way to read a document is through the permission-checked views.
The location is looked up lazily so tests can point it at a temporary folder.
"""
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateStorage(FileSystemStorage):
    @property
    def base_location(self):
        return str(settings.VAULT_STORAGE_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise ValueError("Vault files have no public URL; use the download view.")


def private_storage():
    return PrivateStorage()
