"""Rule-based intelligence layer (no external AI service).

* ``suggest_metadata``   - guess category, tags and expiry from a file name
* ``vault_health``       - 0-100 score with prioritised recommendations
* ``essentials_checklist`` - which everyday documents are still missing
* ``related_documents``  - similarity ranking between documents
* ``find_duplicates``    - identical content grouped by SHA-256
* ``expiry_report``      - expired / expiring documents
"""
import re
from collections import Counter, defaultdict
from datetime import date

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from .models import Category, Document, ShareLink

# keyword -> weight, per category. Multi-word phrases match on normalised text.
CATEGORY_RULES = {
    Category.IDENTITY: {
        "passport": 4, "aadhaar": 4, "aadhar": 4, "driving licence": 4, "driving license": 4, "licence": 2,
        "license": 2, "voter": 3, "pan card": 4, "pan": 1, "national id": 4, "identity": 3, "id card": 3,
        "visa": 3, "ssn": 3, "birth certificate": 4, "residence permit": 3, "photo id": 3,
    },
    Category.FINANCIAL: {
        "bank": 3, "statement": 2, "invoice": 3, "receipt": 2, "tax": 3, "itr": 4, "form 16": 4, "form16": 4,
        "salary": 3, "payslip": 4, "investment": 3, "loan": 3, "credit": 2, "mutual fund": 3, "demat": 3,
        "gst": 3, "account": 1, "budget": 2, "pf": 2, "epf": 3,
    },
    Category.LEGAL: {
        "contract": 3, "agreement": 3, "will": 2, "deed": 3, "affidavit": 4, "nda": 4, "power of attorney": 4,
        "court": 3, "legal": 3, "notary": 3, "notarized": 3, "notarised": 3, "settlement": 2,
    },
    Category.MEDICAL: {
        "medical": 4, "prescription": 4, "lab": 2, "blood": 2, "vaccination": 4, "vaccine": 3, "health": 2,
        "hospital": 3, "discharge": 3, "diagnosis": 3, "scan": 2, "xray": 3, "x-ray": 3, "doctor": 2,
    },
    Category.EDUCATION: {
        "degree": 4, "transcript": 4, "marksheet": 4, "mark sheet": 4, "diploma": 4, "school": 2, "college": 2,
        "university": 3, "course": 2, "semester": 3, "thesis": 3, "graduation": 3,
    },
    Category.EMPLOYMENT: {
        "offer letter": 4, "resume": 3, "cv": 2, "employment": 3, "appointment": 2, "relieving": 4,
        "experience letter": 4, "payroll": 3, "job": 2, "internship": 3, "promotion": 2,
    },
    Category.PROPERTY: {
        "lease": 4, "rent": 3, "rental": 3, "property": 3, "sale deed": 4, "mortgage": 4, "housing": 3,
        "flat": 2, "apartment": 2, "utility": 2, "electricity": 2, "maintenance": 1, "registry": 3,
    },
    Category.INSURANCE: {
        "insurance": 4, "policy": 3, "claim": 3, "premium": 3, "coverage": 3, "insured": 3,
    },
    Category.TRAVEL: {
        "ticket": 3, "boarding": 4, "itinerary": 4, "flight": 3, "hotel": 3, "booking": 2, "travel": 3,
        "reservation": 2, "visa": 1,
    },
}

EXPIRY_HINTS = {
    "passport": "Passports usually last 10 years - add the expiry date so you are reminded in time.",
    "licence": "Driving licences need renewing - add the expiry date.",
    "license": "Driving licences need renewing - add the expiry date.",
    "visa": "Visas have hard deadlines - add the expiry date.",
    "insurance": "Insurance policies renew every year - add the renewal date as the expiry date.",
    "policy": "Policies renew on a fixed date - add it as the expiry date.",
    "lease": "Rental agreements end on a date - add it so you can renew or move on time.",
    "agreement": "Agreements often have an end date - add it if this one does.",
    "vaccination": "Some vaccination certificates expire - add the date if yours does.",
}

STOPWORDS = {"the", "and", "of", "for", "a", "an", "to", "in", "on", "my", "copy", "scan", "final", "new", "pdf", "doc", "docx", "file"}


def normalise(text):
    text = re.sub(r"[_\-.]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def tokens(text):
    return [t for t in re.findall(r"[a-z0-9]{3,}", normalise(text)) if t not in STOPWORDS]


def suggest_metadata(filename="", title="", description=""):
    """Return {category, confidence, tags, expiry_date, expiry_hint, reasons}."""
    text = normalise(" ".join([filename.rsplit(".", 1)[0] if filename else "", title, description]))
    padded = f" {text} "
    scores, hits = Counter(), defaultdict(list)
    for category, rules in CATEGORY_RULES.items():
        for keyword, weight in rules.items():
            if f" {keyword} " in padded or (len(keyword) > 4 and keyword in text):
                scores[category] += weight
                hits[category].append(keyword)
    category, confidence, tags, reasons = Category.OTHER, 0.0, [], []
    if scores:
        category, best = scores.most_common(1)[0]
        total = sum(scores.values())
        confidence = round(min(0.99, 0.35 + 0.1 * best + 0.3 * best / total), 2)
        tags = [k.replace(" ", "-") for k in hits[category]][:4]
        reasons = [f"'{k}' suggests {dict(Category.CHOICES)[category]}" for k in hits[category][:3]]
    year = re.search(r"\b(20\d{2})\b", text)
    if year:
        tags.append(year.group(1))
    expiry, hint = None, ""
    match = re.search(r"exp(?:ir(?:y|es|ation))?[ ]?(\d{4})[ ]?(\d{2})[ ]?(\d{2})", text)
    if match:
        try:
            expiry = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            expiry = None
    for keyword, message in EXPIRY_HINTS.items():
        if f" {keyword} " in padded:
            hint = message
            break
    seen, unique_tags = set(), []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)
    return {
        "category": category,
        "category_label": dict(Category.CHOICES)[category],
        "confidence": confidence,
        "tags": unique_tags,
        "expiry_date": expiry.isoformat() if expiry else None,
        "expiry_hint": hint,
        "reasons": reasons,
    }


def pretty_title(filename):
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    stem = re.sub(r"[_\-]+", " ", stem).strip()
    return (stem[:1].upper() + stem[1:]) if stem else "Untitled document"


# ---------------------------------------------------------------------------
ESSENTIALS = [
    # (label, category, keywords) - keywords None means any document in the category counts
    ("Government photo ID", Category.IDENTITY, None),
    ("Proof of address", Category.PROPERTY, ["utility", "electricity", "address", "lease", "rent", "bill"]),
    ("Tax records", Category.FINANCIAL, ["tax", "itr", "form16", "form-16"]),
    ("Bank or income statement", Category.FINANCIAL, ["bank", "statement", "salary", "payslip"]),
    ("Insurance policy", Category.INSURANCE, None),
    ("Medical records", Category.MEDICAL, None),
    ("Education certificate", Category.EDUCATION, None),
    ("Employment record", Category.EMPLOYMENT, None),
]


def essentials_checklist(user):
    docs = list(Document.objects.filter(owner=user).library().prefetch_related("tags"))
    labels = dict(Category.CHOICES)
    result = []
    for label, category, keywords in ESSENTIALS:
        found = None
        for doc in docs:
            haystack = normalise(" ".join([doc.title, doc.original_name] + [t.name for t in doc.tags.all()]))
            keyword_hit = bool(keywords) and any(k.replace("-", " ") in haystack for k in keywords)
            if (doc.category == category and (keywords is None or keyword_hit)) or keyword_hit:
                found = doc
                break
        result.append({"label": label, "category": category, "category_label": labels[category],
                       "present": found is not None, "document": found})
    return result


def find_duplicates(user):
    dupes = (Document.objects.filter(owner=user).library().values("sha256").annotate(n=Count("id")).filter(n__gt=1))
    hashes = [d["sha256"] for d in dupes]
    groups = []
    for sha in hashes:
        groups.append(list(Document.objects.filter(owner=user, sha256=sha).library().order_by("created_at")))
    return groups


def expiry_report(user):
    qs = Document.objects.filter(owner=user).library().select_related("owner__profile")
    days = user.profile.expiry_alert_days
    return {
        "expired": list(qs.expired().order_by("expiry_date")),
        "soon": list(qs.expiring(days).order_by("expiry_date")),
        "days": days,
    }


def related_documents(doc, limit=5):
    """Rank the owner's other documents by how much they resemble ``doc``."""
    my_tags = {t.pk for t in doc.tags.all()}
    my_tokens = set(tokens(doc.title))
    candidates = (Document.objects.filter(owner=doc.owner).library().exclude(pk=doc.pk)
                  .select_related("folder").prefetch_related("tags"))
    scored = []
    for other in candidates:
        score = 0.0
        reasons = []
        if other.category == doc.category:
            score += 2
            reasons.append("same category")
        shared = my_tags & {t.pk for t in other.tags.all()}
        if shared:
            score += 3 * len(shared)
            reasons.append(f"{len(shared)} shared tag{'s' if len(shared) > 1 else ''}")
        if doc.folder_id and other.folder_id == doc.folder_id:
            score += 1
            reasons.append("same folder")
        their = set(tokens(other.title))
        if my_tokens and their:
            jaccard = len(my_tokens & their) / len(my_tokens | their)
            if jaccard:
                score += 3 * jaccard
                reasons.append("similar title")
        if doc.issuer and other.issuer and doc.issuer.lower() == other.issuer.lower():
            score += 2
            reasons.append("same issuer")
        if score >= 2:
            scored.append((score, other, reasons))
    scored.sort(key=lambda item: (-item[0], item[1].title))
    return [{"document": d, "score": round(s, 1), "reasons": r} for s, d, r in scored[:limit]]


# ---------------------------------------------------------------------------
def _grade(score):
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 55:
        return "Fair"
    return "Needs attention"


def vault_health(user):
    """Score the vault and return prioritised, actionable recommendations."""
    profile = user.profile
    docs = list(Document.objects.filter(owner=user).library().select_related("owner__profile").prefetch_related("tags"))
    now = timezone.now()
    recs, score = [], 100

    def add(level, title, detail, url="", penalty=0):
        nonlocal score
        score -= penalty
        recs.append({"level": level, "title": title, "detail": detail, "url": url, "penalty": penalty})

    docs_url = reverse("vault:documents")
    expired = [d for d in docs if d.expiry_state == "expired"]
    soon = [d for d in docs if d.expiry_state == "soon"]
    if expired:
        add("critical", f"{len(expired)} document{'s have' if len(expired) > 1 else ' has'} expired",
            "Renew them or archive the outdated copies: " + ", ".join(d.title for d in expired[:3]) + ("…" if len(expired) > 3 else ""),
            f"{docs_url}?expiry=expired", min(30, 8 * len(expired)))
    if soon:
        add("warning", f"{len(soon)} document{'s expire' if len(soon) > 1 else ' expires'} within {profile.expiry_alert_days} days",
            "Start renewal now: " + ", ".join(f"{d.title} ({d.days_to_expiry}d)" for d in soon[:3]) + ("…" if len(soon) > 3 else ""),
            f"{docs_url}?expiry=soon", min(20, 4 * len(soon)))

    if docs:
        unsorted = [d for d in docs if d.category == Category.OTHER and not d.tags.all()]
        if unsorted:
            add("info", f"{len(unsorted)} document{'s are' if len(unsorted) > 1 else ' is'} uncategorised and untagged",
                "Give them a category or a tag so you can find them quickly.", f"{docs_url}?category=other",
                min(10, 2 * len(unsorted)))
        undescribed = [d for d in docs if not d.description and not d.issuer and not d.reference_number]
        if len(undescribed) > len(docs) / 2 and len(docs) >= 4:
            add("info", "Most documents have no description or issuer",
                "A short description and issuer makes each record self-explanatory years later.", docs_url, 5)
        stale_check = [d for d in docs if not d.last_verified_at or (now - d.last_verified_at).days > 30]
        if stale_check:
            add("info", f"{len(stale_check)} document{'s were' if len(stale_check) > 1 else ' was'} not integrity-checked in 30 days",
                "Run an integrity check to confirm the files still match their fingerprints.", reverse("vault:insights"),
                min(10, len(stale_check)))
        failed = [d for d in docs if d.integrity_status == "failed"]
        if failed:
            add("critical", f"Integrity check failed for {len(failed)} document{'s' if len(failed) > 1 else ''}",
                "The stored file no longer matches its fingerprint: " + ", ".join(d.title for d in failed[:3]) + ". Restore from an earlier version.",
                docs_url, min(30, 15 * len(failed)))

    dupes = find_duplicates(user)
    if dupes:
        extra = sum(len(g) - 1 for g in dupes)
        add("info", f"{extra} duplicate file{'s' if extra > 1 else ''} found",
            "Identical files waste storage. Keep one and move the rest to trash.", reverse("vault:insights") + "#duplicates",
            min(15, 3 * extra))

    links = list(ShareLink.objects.filter(created_by=user, is_active=True, document__owner=user).exclude(document__status=Document.TRASHED))
    forever = [l for l in links if l.expires_at is None]
    lapsed = [l for l in links if l.is_expired]
    if forever:
        add("warning", f"{len(forever)} active share link{'s never expire' if len(forever) > 1 else ' never expires'}",
            "Set an expiry on links you no longer need open, or revoke them.", reverse("vault:documents"), min(15, 3 * len(forever)))
    if lapsed:
        add("info", f"{len(lapsed)} share link{'s have' if len(lapsed) > 1 else ' has'} lapsed but still {'appear' if len(lapsed) > 1 else 'appears'} active",
            "Revoke lapsed links to keep your sharing list tidy.", reverse("vault:documents"), 0)

    critical_shared = [l for l in links if l.document.sensitivity == Document.CRITICAL]
    if critical_shared:
        add("critical", "A critical document has a public link",
            "Critical documents should not be shared by link. Revoke it.", reverse("vault:documents"), 10)

    used = profile.storage_percent
    if used >= 90:
        add("warning", f"Storage is {used:.0f}% full", "Delete duplicates or old versions to free space.", reverse("vault:insights"), 10)
    elif used >= 75:
        add("info", f"Storage is {used:.0f}% full", "You are approaching your quota.", reverse("vault:insights"), 4)

    if not profile.totp_enabled:
        add("warning", "Two-factor authentication is off",
            "Add an authenticator app so a stolen password alone cannot open your vault.", reverse("accounts:security"), 10)

    checklist = essentials_checklist(user)
    missing = [c for c in checklist if not c["present"]]
    if missing and docs:
        add("info", f"{len(missing)} essential document type{'s are' if len(missing) > 1 else ' is'} missing",
            "Consider uploading: " + ", ".join(m["label"] for m in missing[:3]) + ("…" if len(missing) > 3 else ""),
            reverse("vault:insights") + "#essentials", min(15, 3 * len(missing)))
    if not docs:
        add("info", "Your vault is empty", "Upload your first document to get a meaningful health score.", reverse("vault:upload"), 0)
        score = 50

    score = max(0, min(100, score))
    order = {"critical": 0, "warning": 1, "info": 2}
    recs.sort(key=lambda r: (order[r["level"]], -r["penalty"]))
    return {
        "score": score,
        "grade": _grade(score),
        "recommendations": recs,
        "checklist": checklist,
        "document_count": len(docs),
    }


def category_breakdown(user):
    rows = (Document.objects.filter(owner=user).library().values("category").annotate(n=Count("id")).order_by("-n"))
    labels = dict(Category.CHOICES)
    return [{"category": r["category"], "label": labels.get(r["category"], r["category"]), "count": r["n"]} for r in rows]
