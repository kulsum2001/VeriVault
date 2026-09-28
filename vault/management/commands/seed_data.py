"""Populate VeriVault with realistic, fictional sample data.

    python manage.py seed_data            # add demo users + documents (idempotent)
    python manage.py seed_data --reset    # wipe the demo accounts first
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from vault import sampledata as sd
from vault import services
from vault.models import (AuditLog, Document, DocumentShare, Folder, Notification, ShareLink, Tag)

User = get_user_model()
PASSWORD = "Demo@12345"

USERS = [
    ("demo", "Ananya Rao", "ananya.rao@example.com", "Product designer"),
    ("priya", "Priya Menon", "priya.menon@example.com", "Chartered accountant"),
    ("arjun", "Arjun Nair", "arjun.nair@example.com", "Software engineer"),
]

FOLDERS = [
    ("Identity & Travel", "navy", None), ("Money", "teal", None), ("Home", "brass", None),
    ("Health", "rose", None), ("Career & Study", "violet", None), ("Tax returns", "teal", "Money"),
]

# title, filename, kind, category, folder, tags, issuer, reference, issued(days ago), expiry(days from now), sensitivity, favourite, description
DOCS = [
    ("Passport - Ananya Rao", "passport-ananya-rao.pdf", "pdf", "identity", "Identity & Travel", ["passport", "travel"], "Passport Office, Bengaluru", "P1234567", 2400, 1250, "critical", True, "Primary travel document. Renewal needs 6 months' validity."),
    ("Aadhaar card (masked)", "aadhaar-masked.pdf", "pdf", "identity", "Identity & Travel", ["aadhaar", "id"], "UIDAI", "XXXX XXXX 4821", 1800, None, "sensitive", False, "Masked copy for routine KYC."),
    ("Aadhaar card copy", "aadhaar-copy.pdf", "pdf", "identity", "Identity & Travel", ["aadhaar"], "UIDAI", "XXXX XXXX 4821", 1800, None, "sensitive", False, ""),
    ("Driving licence", "driving-licence.png", "png", "identity", "Identity & Travel", ["licence", "id"], "RTO Bengaluru East", "KA05 2019 0043", 1500, 18, "sensitive", False, "Two-wheeler and LMV. Renewal due."),
    ("PAN card", "pan-card.pdf", "pdf", "identity", "Identity & Travel", ["pan", "tax"], "Income Tax Department", "ABCPR1234K", 2900, None, "sensitive", False, ""),
    ("Schengen visa 2025", "schengen-visa-2025.pdf", "pdf", "travel", "Identity & Travel", ["visa", "travel", "2025"], "VFS Global", "SCH-88214", 420, -30, "standard", False, "Expired after the Lisbon trip."),
    ("HDFC savings statement - Aug 2026", "bank-statement-aug-2026.pdf", "pdf", "financial", "Money", ["bank", "statement", "2026"], "HDFC Bank", "", 25, None, "standard", False, "Monthly statement."),
    ("Salary slip - July 2026", "salary-slip-july-2026.pdf", "pdf", "financial", "Money", ["payslip", "salary", "2026"], "Northwind Labs", "", 55, None, "standard", False, ""),
    ("Form 16 FY 2025-26", "form16-fy2025-26.pdf", "pdf", "financial", "Tax returns", ["form16", "tax", "2026"], "Northwind Labs", "F16-25-26-0192", 120, None, "standard", True, "Needed for the annual ITR filing."),
    ("ITR acknowledgement AY 2025-26", "itr-ack-ay2025-26.pdf", "pdf", "financial", "Tax returns", ["itr", "tax"], "Income Tax Department", "ACK-9931827", 400, None, "standard", False, ""),
    ("Mutual fund holdings", "mutual-fund-holdings.csv", "csv", "financial", "Money", ["investment", "csv"], "Kuvera", "", 40, None, "standard", False, "Export of current holdings."),
    ("Home loan sanction letter", "home-loan-sanction.pdf", "pdf", "financial", "Home", ["loan", "home"], "SBI Home Finance", "HL-2024-55810", 700, None, "sensitive", False, ""),
    ("Rent agreement - Indiranagar flat", "rent-agreement-indiranagar.pdf", "pdf", "property", "Home", ["rent", "lease", "address"], "Sharma Realty", "RA-2026-118", 200, 165, "standard", True, "11-month agreement. Renew before it lapses."),
    ("Electricity bill - July 2026", "electricity-bill-july-2026.pdf", "pdf", "property", "Home", ["utility", "bill", "address"], "BESCOM", "", 45, None, "standard", False, "Proof of address."),
    ("Health insurance policy", "health-insurance-policy.pdf", "pdf", "insurance", "Health", ["insurance", "policy", "health"], "Star Health", "SH-P-7720145", 300, 65, "standard", True, "Family floater, 10 lakh cover."),
    ("Vehicle insurance - Honda Activa", "vehicle-insurance-activa.pdf", "pdf", "insurance", "Home", ["insurance", "vehicle"], "ICICI Lombard", "VI-3320-91", 350, 6, "standard", False, "Renews very soon."),
    ("COVID-19 vaccination certificate", "vaccination-certificate.pdf", "pdf", "medical", "Health", ["vaccination", "medical"], "CoWIN", "", 1500, None, "standard", False, ""),
    ("Blood test report - March 2026", "blood-test-march-2026.pdf", "pdf", "medical", "Health", ["lab", "medical", "2026"], "Apollo Diagnostics", "AD-556021", 170, None, "sensitive", False, "Annual health check."),
    ("B.Des degree certificate", "degree-certificate.pdf", "pdf", "education", "Career & Study", ["degree", "education"], "NID Ahmedabad", "DEG-2019-0417", 2600, None, "standard", False, ""),
    ("Semester transcripts", "semester-transcripts.pdf", "pdf", "education", "Career & Study", ["transcript", "education"], "NID Ahmedabad", "", 2590, None, "standard", False, ""),
    ("Offer letter - Northwind Labs", "offer-letter-northwind.pdf", "pdf", "employment", "Career & Study", ["offer-letter", "employment"], "Northwind Labs", "NL-OFR-2023-77", 1000, None, "sensitive", False, ""),
    ("Resume", "resume-ananya-rao.pdf", "pdf", "employment", "Career & Study", ["resume", "cv"], "", "", 90, None, "standard", False, "Latest CV."),
    ("Flight itinerary - Lisbon", "flight-itinerary-lisbon.pdf", "pdf", "travel", "Identity & Travel", ["flight", "itinerary", "travel"], "TAP Air Portugal", "TP-1G9QXA", 380, None, "standard", False, ""),
    ("Old broadband invoice", "broadband-invoice-2022.pdf", "pdf", "financial", "Home", ["invoice"], "ACT Fibernet", "", 1400, None, "standard", False, "Superseded."),
    ("Scan 0042", "scan-0042.png", "png", "other", None, [], "", "", 15, None, "standard", False, ""),
    ("Meeting notes", "meeting-notes.txt", "txt", "other", None, [], "", "", 10, None, "standard", False, ""),
]


def build_file(kind, title, reference, seed_text=""):
    lines = [
        f"Document: {title}", f"Reference: {reference or 'n/a'}", "",
        "This is a fictional sample generated by the VeriVault seed command.",
        "It contains no real personal data.", "", seed_text,
    ]
    if kind == "pdf":
        return sd.make_pdf(title, lines)
    if kind == "png":
        rnd = random.Random(title)
        return sd.make_png(color=(rnd.randint(20, 60), rnd.randint(90, 140), rnd.randint(80, 130)))
    if kind == "csv":
        return sd.make_csv([["fund", "units", "nav", "value_inr"], ["Nifty 50 Index", 812.4, 231.5, 188071], ["Flexi Cap", 401.2, 68.2, 27362], ["Liquid Fund", 55.0, 1310.0, 72050]])
    return sd.make_text(title, ["Ship v2 review notes", "- share the certificate flow with design", "- schedule the security audit"])


class Command(BaseCommand):
    help = "Create realistic sample users and documents (demo accounts use the password 'Demo@12345')."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete the demo accounts (and their documents) first.")
        parser.add_argument("--with-admin", action="store_true", help="Also create an 'admin' superuser (password admin12345).")

    def handle(self, *args, **opts):
        random.seed(42)
        if opts["reset"]:
            User.objects.filter(username__in=[u[0] for u in USERS]).delete()
            self.stdout.write("Removed existing demo accounts.")
        if User.objects.filter(username="demo").exists() and Document.objects.filter(owner__username="demo").exists():
            self.stdout.write(self.style.WARNING("Sample data already present. Use --reset to rebuild."))
            return
        users = {}
        for username, name, email, org in USERS:
            user, _ = User.objects.get_or_create(username=username, defaults={"email": email, "first_name": name.split()[0], "last_name": name.split()[1]})
            user.set_password(PASSWORD)
            user.save()
            profile = user.profile
            profile.display_name, profile.organization = name, org
            profile.save()
            users[username] = user
        if opts["with_admin"]:
            admin, created = User.objects.get_or_create(username="admin", defaults={"email": "admin@example.com", "is_staff": True, "is_superuser": True})
            admin.is_staff = admin.is_superuser = True
            admin.set_password("admin12345")
            admin.save()
            self.stdout.write("Superuser 'admin' ready (password: admin12345).")

        demo = users["demo"]
        now = timezone.now()
        today = timezone.localdate()

        folders = {}
        for name, color, parent in FOLDERS:
            folders[name] = Folder.objects.create(owner=demo, name=name, color=color, parent=folders.get(parent))

        docs, contents = {}, {}
        for (title, fname, kind, cat, folder, tags, issuer, ref, issued, expiry, sens, fav, desc) in DOCS:
            content = build_file(kind, title, ref, desc)
            doc = Document(title=title, description=desc, category=cat, folder=folders.get(folder), issuer=issuer,
                           reference_number=ref, issue_date=today - timedelta(days=issued),
                           expiry_date=today + timedelta(days=expiry) if expiry is not None else None,
                           sensitivity=sens, is_favorite=fav)
            if fname == "aadhaar-copy.pdf":
                content = contents["Aadhaar card (masked)"]  # identical bytes -> duplicate fingerprint
            contents[title] = content
            uploaded = ContentFile(content, name=fname)
            uploaded.size = len(content)
            services.create_document(demo, uploaded, doc, tags)
            created_at = now - timedelta(days=max(2, min(issued, 240)) + random.randint(0, 5), hours=random.randint(0, 20))
            Document.objects.filter(pk=doc.pk).update(created_at=created_at, updated_at=created_at + timedelta(days=random.randint(0, 3)))
            docs[title] = doc

        # Extra versions to show history
        rent = docs["Rent agreement - Indiranagar flat"]
        for n, note in ((2, "Landlord added the parking clause"), (3, "Signed copy with stamp paper")):
            data = sd.make_pdf(rent.title, [f"Version {n}", note, "Fictional sample - not a real agreement."])
            f = ContentFile(data, name="rent-agreement-indiranagar.pdf")
            f.size = len(data)
            services.add_version(rent, f, demo, note)
        resume = docs["Resume"]
        data = sd.make_pdf("Resume", ["Ananya Rao - Product Designer", "Updated: portfolio link and 2026 role."])
        f = ContentFile(data, name="resume-ananya-rao.pdf")
        f.size = len(data)
        services.add_version(resume, f, demo, "Updated portfolio link")

        # Lifecycle states
        Document.objects.filter(pk=docs["Old broadband invoice"].pk).update(status=Document.ARCHIVED)
        Document.objects.filter(pk=docs["Meeting notes"].pk).update(status=Document.TRASHED, deleted_at=now - timedelta(days=4))
        # Public certificates
        for title in ("B.Des degree certificate", "Offer letter - Northwind Labs", "Form 16 FY 2025-26"):
            Document.objects.filter(pk=docs[title].pk).update(public_verification=True, certified_at=now - timedelta(days=20))
        # One integrity check performed recently, most left "ok" from upload; make a few stale
        stale = now - timedelta(days=45)
        Document.objects.filter(title__in=["Scan 0042", "Old broadband invoice", "Electricity bill - July 2026"]).update(last_verified_at=stale)

        # Share links
        def link(doc, label, expires, max_dl=None, password="", downloads=0, active=True):
            sl = ShareLink(document=doc, created_by=demo, label=label, expires_at=expires, max_downloads=max_dl,
                           download_count=downloads, view_count=downloads * 2 + 1, is_active=active)
            sl.set_password(password)
            sl.save()
            return sl

        link(docs["Rent agreement - Indiranagar flat"], "For the bank", now + timedelta(days=6), 5, "bank2026", 1)
        link(docs["B.Des degree certificate"], "Recruiter - Orbit Studio", now + timedelta(days=20), None, "", 2)
        link(docs["Resume"], "Portfolio site", None, None, "", 14)
        link(docs["Salary slip - July 2026"], "Landlord (old)", now - timedelta(days=3), 3, "", 3)

        # User-to-user shares
        DocumentShare.objects.create(document=docs["Health insurance policy"], shared_with=users["priya"], shared_by=demo, can_download=True, note="For the claim paperwork")
        DocumentShare.objects.create(document=docs["Rent agreement - Indiranagar flat"], shared_with=users["arjun"], shared_by=demo, can_download=False, note="Co-tenant copy")
        services.notify(users["priya"], Notification.SHARE, "Ananya Rao shared 'Health insurance policy' with you", "You can view and download it", docs["Health insurance policy"])
        # Priya has a couple of docs of her own so 'shared with me' is realistic
        for title, fname, cat in (("Client invoice register", "invoice-register.csv", "financial"), ("Practice certificate", "practice-certificate.pdf", "employment")):
            kind = "csv" if fname.endswith("csv") else "pdf"
            content = build_file(kind, title, "", "")
            up = ContentFile(content, name=fname)
            up.size = len(content)
            services.create_document(users["priya"], up, Document(title=title, category=cat), ["sample"])

        # Audit history spread over the last two weeks
        rnd = random.Random(7)
        actions = [("upload", "Uploaded"), ("view", "Viewed"), ("download", "Downloaded"), ("verify", "Intact"), ("edit", "Details updated")]
        titles = list(docs)
        entries = []
        for _ in range(60):
            action, details = rnd.choice(actions)
            title = rnd.choice(titles)
            entries.append(AuditLog(user=demo, action=action, document=docs[title], document_title=title, details=details,
                                    ip_address=rnd.choice(["49.37.12.8", "106.51.94.20", "157.45.6.102"]), user_agent="Seeded"))
        for e in AuditLog.objects.bulk_create(entries):
            pass
        for e in AuditLog.objects.filter(user_agent="Seeded"):
            AuditLog.objects.filter(pk=e.pk).update(created_at=now - timedelta(days=rnd.random() * 14, hours=rnd.randint(0, 23)), user_agent="Seeded demo")
        AuditLog.objects.create(user=demo, action="login", details="Signed in", ip_address="49.37.12.8", user_agent="Seeded demo")
        AuditLog.objects.create(action="public_view", document=docs["B.Des degree certificate"], document_title="B.Des degree certificate",
                                details="Link 'Recruiter - Orbit Studio'", ip_address="203.0.113.14", user_agent="Seeded demo")
        AuditLog.objects.create(action="login_failed", details="Failed sign-in for 'demo'", ip_address="198.51.100.23", user_agent="Seeded demo")

        # Notifications for expiring / expired documents
        services.sync_expiry_notifications(demo)
        Tag.objects.filter(owner=demo, documents__isnull=True).delete()

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {Document.objects.filter(owner=demo).count()} documents for 'demo' "
            f"and {len(users) - 1} more users. Sign in with demo / {PASSWORD}."))
