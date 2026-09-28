from django import forms
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import UploadedFile
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm

from . import totp
from .models import UserProfile

User = get_user_model()


class StyledFormMixin:
    """Adds CSS classes to every widget so templates stay clean."""

    def _style(self):
        for field in self.fields.values():
            widget = field.widget
            css = widget.attrs.get("class", "")
            if isinstance(widget, (forms.CheckboxInput,)):
                widget.attrs["class"] = (css + " checkbox").strip()
            elif isinstance(widget, forms.FileInput):
                widget.attrs["class"] = (css + " file-input").strip()
            else:
                widget.attrs["class"] = (css + " input").strip()


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.CharField(label="Username or e-mail", widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}))
    password = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class RegisterForm(StyledFormMixin, UserCreationForm):
    full_name = forms.CharField(max_length=80, required=True)
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "full_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "Letters, digits and @/./+/-/_ only."
        self.fields["password1"].help_text = "At least 8 characters, not too common."
        for name in ("username", "email", "full_name"):
            self.fields[name].widget.attrs.setdefault("autocomplete", "off")
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password1"].widget.attrs["data-strength"] = "1"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        self._style()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this e-mail already exists.")
        return email

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with that username already exists.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        full = self.cleaned_data["full_name"].strip()
        parts = full.split(" ", 1)
        user.first_name = parts[0][:150]
        user.last_name = parts[1][:150] if len(parts) > 1 else ""
        if commit:
            user.save()
            profile = user.profile
            profile.display_name = full
            profile.save(update_fields=["display_name"])
        return user


class UserForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self._style()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account already uses this e-mail.")
        return email


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("display_name", "phone", "organization", "bio", "avatar", "timezone", "expiry_alert_days")
        widgets = {"bio": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["avatar"].widget = forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/gif,image/webp"})
        self.fields["expiry_alert_days"].widget.attrs.update({"min": 1, "max": 365})
        self._style()

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar and isinstance(avatar, UploadedFile):
            name = avatar.name.lower()
            if not name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                raise forms.ValidationError("Use a PNG, JPG, GIF or WebP image.")
            if avatar.size > 2 * 1024 * 1024:
                raise forms.ValidationError("Profile pictures must be 2 MB or smaller.")
        return avatar

    def clean_expiry_alert_days(self):
        days = self.cleaned_data["expiry_alert_days"]
        if not 1 <= days <= 365:
            raise forms.ValidationError("Choose between 1 and 365 days.")
        return days


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class PasswordConfirmForm(StyledFormMixin, forms.Form):
    password = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "autofocus": True}))

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self._style()

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("That password is not correct.")
        return password


class TotpCodeForm(StyledFormMixin, forms.Form):
    code = forms.CharField(
        label="6-digit code", max_length=7, min_length=6,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "autofocus": True, "placeholder": "123456"}),
    )

    def __init__(self, *args, secret=None, **kwargs):
        self.secret = secret
        super().__init__(*args, **kwargs)
        self._style()

    def clean_code(self):
        code = self.cleaned_data["code"]
        if not self.secret or not totp.verify(self.secret, code):
            raise forms.ValidationError("That code is not valid. Check your authenticator app and try again.")
        return code


class ApiTokenForm(StyledFormMixin, forms.Form):
    name = forms.CharField(max_length=80, help_text="For example: backup script, mobile shortcut")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()
