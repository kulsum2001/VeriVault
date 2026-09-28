from django.core.management.base import BaseCommand

from vault.models import Document


class Command(BaseCommand):
    help = "Recompute SHA-256 for every stored document and report mismatches."

    def handle(self, *args, **opts):
        checked = failed = 0
        for doc in Document.objects.exclude(status=Document.TRASHED).select_related("owner"):
            checked += 1
            if not doc.verify_integrity():
                failed += 1
                self.stderr.write(self.style.ERROR(f"MISMATCH: #{doc.pk} '{doc.title}' ({doc.owner.get_username()})"))
        style = self.style.ERROR if failed else self.style.SUCCESS
        self.stdout.write(style(f"Checked {checked} document(s); {failed} failed."))
