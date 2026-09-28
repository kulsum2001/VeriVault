from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from vault import services


class Command(BaseCommand):
    help = "Create notifications for documents that are expiring or expired, and deactivate lapsed share links."

    def handle(self, *args, **opts):
        total = 0
        for user in get_user_model().objects.filter(is_active=True):
            total += services.sync_expiry_notifications(user)
        lapsed = services.deactivate_lapsed_links()
        self.stdout.write(self.style.SUCCESS(f"{total} new notification(s); {lapsed} lapsed link(s) deactivated."))
