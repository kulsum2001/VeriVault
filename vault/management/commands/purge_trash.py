from django.core.management.base import BaseCommand

from vault import services


class Command(BaseCommand):
    help = "Permanently delete documents that have been in the trash longer than --days (default 30)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **opts):
        count = services.purge_trash(opts["days"])
        self.stdout.write(self.style.SUCCESS(f"Purged {count} document(s) from the trash."))
