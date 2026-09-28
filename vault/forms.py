import os
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.forms import StyledFormMixin

from . import intelligence, services
from .models import Category, Document, Folder

User = get_user_model()


def validate_upload(uploaded, user, extra_bytes=0):
    """Shared upload checks: size, blocked extensions, quota."""
    name = os.path.basename(uploaded.name or "")
    ext = os.path.splitext(name)[1].lower()
    if ext in settings.VAULT_BLOCKED_EXTENSIONS:
        raise forms.ValidationError(f"Files of type '{ext}' are not allowed in the vault.")
    if uploaded.size == 0:
        raise forms.ValidationError("This file is empty.")
    limit = settings.VAULT_MAX_UPLOAD_MB * 1024 * 1024
    if uploaded.size > limit:
        raise forms.ValidationError(f"Files can be at most {settings.VAULT_MAX_UPLOAD_MB} MB.")
    if uploaded.size > user.profile.storage_left:
        raise forms.ValidationError("This upload would exceed your storage quota. Free some space first.")
    return uploaded


class DocumentForm(StyledFormMixin, forms.ModelForm):
    tags_text = forms.CharField(label="Tags", required=False, max_length=200,
                                help_text="Comma separated, e.g. travel, 2026",
                                widget=forms.TextInput(attrs={"placeholder": "travel, renewal, 2026"}))

    class Meta:
        model = Document
        fields = ["title", "description", "category", "folder", "reference_number", "issuer",
                  "issue_date", "expiry_date", "sensitivity"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "issue_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "expiry_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["folder"].queryset = Folder.objects.filter(owner=user)
        self.fields["folder"].empty_label = "No folder"
        self.fields["folder"].label_from_instance = lambda f: ("— " * f.depth) + f.name
        self.fields["title"].required = False
        if self.instance.pk:
            self.fields["title"].required = True
            self.fields["tags_text"].initial = ", ".join(self.instance.tag_names)
        self._style()

    def clean(self):
        cleaned = super().clean()
        issue, expiry = cleaned.get("issue_date"), cleaned.get("expiry_date")
        if issue and expiry and expiry < issue:
            self.add_error("expiry_date", "The expiry date cannot be before the issue date.")
        return cleaned

    def clean_tags_text(self):
        return services.parse_tags(self.cleaned_data.get("tags_text", ""))

    @property
    def tag_names(self):
        return self.cleaned_data.get("tags_text", [])


class DocumentUploadForm(DocumentForm):
    file = forms.FileField(help_text="Up to %d MB. Executables and scripts are blocked." % settings.VAULT_MAX_UPLOAD_MB)
    field_order = ["file", "title", "category", "folder", "description", "reference_number", "issuer",
                   "issue_date", "expiry_date", "sensitivity", "tags_text"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"] = forms.ChoiceField(
            choices=[("auto", "Detect automatically")] + Category.CHOICES, initial="auto",
            widget=forms.Select(attrs={"class": "input"}))
        self.fields["file"].widget = forms.ClearableFileInput(attrs={"class": "file-input"})
        self.order_fields(self.field_order)

    def clean_file(self):
        return validate_upload(self.cleaned_data["file"], self.user)

    def clean(self):
        cleaned = super().clean()
        uploaded = cleaned.get("file")
        if uploaded:
            suggestion = intelligence.suggest_metadata(uploaded.name, cleaned.get("title", ""), cleaned.get("description", ""))
            if not cleaned.get("title"):
                cleaned["title"] = intelligence.pretty_title(uploaded.name)[:160]
            if cleaned.get("category") in (None, "", "auto"):
                cleaned["category"] = suggestion["category"]
            if not self.tag_names and not self.data.get("tags_text"):
                cleaned["tags_text"] = suggestion["tags"]
            if not cleaned.get("expiry_date") and suggestion["expiry_date"]:
                from datetime import date
                cleaned["expiry_date"] = date.fromisoformat(suggestion["expiry_date"])
            self.suggestion = suggestion
        return cleaned


class NewVersionForm(StyledFormMixin, forms.Form):
    file = forms.FileField()
    note = forms.CharField(max_length=200, required=False, help_text="What changed in this version?")

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["file"].widget = forms.ClearableFileInput(attrs={"class": "file-input"})
        self.fields["note"].widget.attrs["class"] = "input"

    def clean_file(self):
        return validate_upload(self.cleaned_data["file"], self.user)


class FolderForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Folder
        fields = ["name", "parent", "color"]

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        qs = Folder.objects.filter(owner=user)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk).exclude(pk__in=self.instance.descendant_ids())
        self.fields["parent"].queryset = qs
        self.fields["parent"].required = False
        self.fields["parent"].empty_label = "Top level"
        self.fields["parent"].label_from_instance = lambda f: f.path
        self._style()

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def clean(self):
        cleaned = super().clean()
        name, parent = cleaned.get("name"), cleaned.get("parent")
        if name:
            dupes = Folder.objects.filter(owner=self.user, parent=parent, name__iexact=name)
            if self.instance.pk:
                dupes = dupes.exclude(pk=self.instance.pk)
            if dupes.exists():
                self.add_error("name", "A folder with this name already exists here.")
        if parent and self.instance.pk and (parent.pk == self.instance.pk or parent.pk in self.instance.descendant_ids()):
            self.add_error("parent", "A folder cannot be moved inside itself.")
        return cleaned


class ShareLinkForm(StyledFormMixin, forms.Form):
    EXPIRY = [("1h", "1 hour"), ("1d", "1 day"), ("7d", "7 days"), ("30d", "30 days"), ("never", "Never")]
    label = forms.CharField(max_length=80, required=False, help_text="Who is this for?")
    expires = forms.ChoiceField(choices=EXPIRY, initial="7d")
    max_downloads = forms.IntegerField(min_value=1, max_value=1000, required=False, help_text="Leave blank for unlimited")
    password = forms.CharField(required=False, strip=False, min_length=4, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                               help_text="Optional. Share it separately from the link.")
    allow_download = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()

    def expires_at(self):
        unit = {"1h": timedelta(hours=1), "1d": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30)}
        delta = unit.get(self.cleaned_data["expires"])
        return timezone.now() + delta if delta else None


class ShareUserForm(StyledFormMixin, forms.Form):
    recipient = forms.CharField(label="Username or e-mail", max_length=150)
    can_download = forms.BooleanField(required=False, label="Allow download")
    days = forms.IntegerField(required=False, min_value=1, max_value=365, label="Access ends after (days)",
                              help_text="Leave blank for no end date")
    note = forms.CharField(required=False, max_length=200)

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)
        self._style()

    def clean_recipient(self):
        value = self.cleaned_data["recipient"].strip()
        user = (User.objects.filter(username__iexact=value, is_active=True).first()
                or User.objects.filter(email__iexact=value, is_active=True).first())
        if user is None:
            raise forms.ValidationError("No active VeriVault user matches that username or e-mail.")
        if user.pk == self.owner.pk:
            raise forms.ValidationError("You already own this document.")
        self.recipient_user = user
        return value


class PublicPasswordForm(StyledFormMixin, forms.Form):
    password = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"autofocus": True}))

    def __init__(self, *args, link=None, **kwargs):
        self.link = link
        super().__init__(*args, **kwargs)
        self._style()

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.link.check_password(password):
            raise forms.ValidationError("That password is not correct.")
        return password


class VerifyForm(StyledFormMixin, forms.Form):
    code = forms.CharField(label="Verification code", max_length=20, required=False,
                           widget=forms.TextInput(attrs={"placeholder": "VV-XXXX-XXXX-XXXX", "autocomplete": "off"}))
    sha256 = forms.CharField(label="SHA-256 fingerprint", max_length=64, required=False,
                             widget=forms.TextInput(attrs={"placeholder": "or paste a 64-character SHA-256", "autocomplete": "off"}))
    file = forms.FileField(required=False, label="File to check")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()
        self.fields["file"].widget.attrs["class"] = "file-input"

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()

    def clean_sha256(self):
        value = self.cleaned_data["sha256"].strip().lower()
        if value and (len(value) != 64 or any(c not in "0123456789abcdef" for c in value)):
            raise forms.ValidationError("A SHA-256 fingerprint is 64 hexadecimal characters.")
        return value

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("code") and not cleaned.get("sha256") and not cleaned.get("file"):
            raise forms.ValidationError("Enter a verification code, a fingerprint, or choose a file.")
        return cleaned
