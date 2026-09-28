from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Document, DocumentVersion


@receiver(post_delete, sender=DocumentVersion)
def remove_version_file(sender, instance, **kwargs):
    """Delete the stored file once no other record points at it."""
    name = instance.file.name
    if not name:
        return
    still_used = (
        DocumentVersion.objects.filter(file=name).exists()
        or Document.objects.filter(file=name).exists()
    )
    if not still_used:
        try:
            instance.file.storage.delete(name)
        except OSError:
            pass


@receiver(post_delete, sender=Document)
def remove_document_file(sender, instance, **kwargs):
    name = instance.file.name
    if name and not DocumentVersion.objects.filter(file=name).exists():
        try:
            instance.file.storage.delete(name)
        except OSError:
            pass
