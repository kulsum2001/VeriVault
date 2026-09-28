import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from vault.audit import client_ip, record

from . import qr, throttle, totp
from .forms import (ApiTokenForm, LoginForm, PasswordConfirmForm, ProfileForm, RegisterForm,
                    StyledPasswordChangeForm, TotpCodeForm, UserForm)
from .models import ApiToken

User = get_user_model()
BACKEND = "accounts.backends.EmailOrUsernameBackend"
PRE_2FA_SECONDS = 5 * 60


def _safe_next(request, default=None):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return default or settings.LOGIN_REDIRECT_URL


def register(request):
    if request.user.is_authenticated:
        return redirect("vault:dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend=BACKEND)
        record(request, "register", user=user, details="Account created")
        messages.success(request, "Welcome to VeriVault! Your vault is ready - upload your first document.")
        return redirect("vault:upload")
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))
    ip = client_ip(request)
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST":
        identifier = request.POST.get("username", "").strip()
        if throttle.is_locked(identifier, ip):
            messages.error(request, "Too many failed attempts. Please wait 15 minutes or reset your password.")
            record(request, "login_blocked", details=f"Throttled sign-in for '{identifier[:60]}'")
        elif form.is_valid():
            user = form.get_user()
            throttle.reset(identifier, ip)
            if user.profile.totp_enabled:
                request.session["pre2fa_user"] = user.pk
                request.session["pre2fa_ts"] = time.time()
                request.session["pre2fa_next"] = _safe_next(request)
                return redirect("accounts:twofa")
            login(request, user, backend=BACKEND)
            record(request, "login", user=user, details="Signed in")
            return redirect(_safe_next(request))
        else:
            throttle.register_failure(identifier, ip)
            record(request, "login_failed", details=f"Failed sign-in for '{identifier[:60]}'")
    return render(request, "accounts/login.html", {"form": form, "next": request.GET.get("next", "")})


def twofa(request):
    user_id = request.session.get("pre2fa_user")
    started = request.session.get("pre2fa_ts", 0)
    if not user_id or time.time() - started > PRE_2FA_SECONDS:
        request.session.pop("pre2fa_user", None)
        messages.error(request, "Your sign-in session expired. Please start again.")
        return redirect("accounts:login")
    user = get_object_or_404(User, pk=user_id, is_active=True)
    ip = client_ip(request)
    lock_id = f"2fa-{user.pk}"
    form = TotpCodeForm(request.POST or None, secret=user.profile.totp_secret)
    if request.method == "POST":
        if throttle.is_locked(lock_id, ip):
            messages.error(request, "Too many incorrect codes. Please try again later.")
        elif form.is_valid():
            throttle.reset(lock_id, ip)
            next_url = request.session.pop("pre2fa_next", settings.LOGIN_REDIRECT_URL)
            request.session.pop("pre2fa_user", None)
            request.session.pop("pre2fa_ts", None)
            login(request, user, backend=BACKEND)
            record(request, "login", user=user, details="Signed in with two-factor code")
            return redirect(next_url)
        else:
            throttle.register_failure(lock_id, ip)
            record(request, "login_failed", user=user, details="Incorrect two-factor code")
    return render(request, "accounts/twofa.html", {"form": form, "account": user})


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        record(request, "logout", details="Signed out")
    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("core:home")


@login_required
def reauth(request):
    """Re-enter the password to unlock sensitive documents for a short time."""
    form = PasswordConfirmForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        request.session["reauth_at"] = time.time()
        record(request, "reauth", details="Password re-entered to unlock sensitive documents")
        return redirect(_safe_next(request, default=reverse("vault:dashboard")))
    return render(request, "accounts/reauth.html", {"form": form, "next": request.GET.get("next", "")})


@login_required
def profile(request):
    user_form = UserForm(request.POST or None, instance=request.user, prefix="u")
    profile_form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user.profile, prefix="p")
    if request.method == "POST" and user_form.is_valid() and profile_form.is_valid():
        user_form.save()
        profile_form.save()
        record(request, "profile_update", details="Profile updated")
        messages.success(request, "Profile saved.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"user_form": user_form, "profile_form": profile_form})


@login_required
def security(request):
    password_form = StyledPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST":
        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            record(request, "password_change", details="Password changed")
            messages.success(request, "Password updated.")
            return redirect("accounts:security")
    context = {
        "password_form": password_form,
        "token_form": ApiTokenForm(),
        "tokens": request.user.api_tokens.all(),
        "new_token": request.session.pop("new_api_token", None),
        "disable_form": PasswordConfirmForm(request.user),
    }
    return render(request, "accounts/security.html", context)


@login_required
def twofa_setup(request):
    profile = request.user.profile
    if profile.totp_enabled:
        messages.info(request, "Two-factor authentication is already enabled.")
        return redirect("accounts:security")
    secret = request.session.get("totp_setup_secret")
    if not secret:
        secret = totp.generate_secret()
        request.session["totp_setup_secret"] = secret
    form = TotpCodeForm(request.POST or None, secret=secret)
    if request.method == "POST" and form.is_valid():
        profile.totp_secret = secret
        profile.totp_enabled = True
        profile.save(update_fields=["totp_secret", "totp_enabled"])
        request.session.pop("totp_setup_secret", None)
        record(request, "twofa_enable", details="Two-factor authentication enabled")
        messages.success(request, "Two-factor authentication is now on.")
        return redirect("accounts:security")
    context = {
        "form": form,
        "secret": totp.pretty(secret),
        "uri": totp.provisioning_uri(secret, request.user.email or request.user.get_username()),
    }
    return render(request, "accounts/twofa_setup.html", context)


@login_required
@require_GET
def twofa_qr(request):
    """A scannable QR code for the secret currently being set up.

    Only ever encodes the in-progress setup secret held in this user's own
    session - never a secret already confirmed and stored on the account.
    """
    if request.user.profile.totp_enabled:
        raise Http404
    secret = request.session.get("totp_setup_secret")
    if not secret:
        raise Http404
    uri = totp.provisioning_uri(secret, request.user.email or request.user.get_username())
    svg = qr.make_qr_svg(uri, box_size=8, border=3)
    response = HttpResponse(svg, content_type="image/svg+xml")
    response["Cache-Control"] = "no-store, private"
    return response


@login_required
@require_POST
def twofa_disable(request):
    form = PasswordConfirmForm(request.user, request.POST)
    if form.is_valid():
        profile = request.user.profile
        profile.totp_enabled = False
        profile.totp_secret = ""
        profile.save(update_fields=["totp_enabled", "totp_secret"])
        record(request, "twofa_disable", details="Two-factor authentication disabled")
        messages.success(request, "Two-factor authentication turned off.")
    else:
        messages.error(request, "Password incorrect - two-factor authentication is still on.")
    return redirect("accounts:security")


@login_required
@require_POST
def token_create(request):
    form = ApiTokenForm(request.POST)
    if form.is_valid():
        token, raw = ApiToken.issue(request.user, form.cleaned_data["name"])
        request.session["new_api_token"] = {"name": token.name, "value": raw}
        record(request, "token_create", details=f"API token '{token.name}' created")
        messages.success(request, "Token created. Copy it now - it will not be shown again.")
    else:
        messages.error(request, "Give the token a name.")
    return redirect("accounts:security")


@login_required
@require_POST
def token_revoke(request, pk):
    token = get_object_or_404(ApiToken, pk=pk, user=request.user)
    name = token.name
    token.delete()
    record(request, "token_revoke", details=f"API token '{name}' revoked")
    messages.success(request, f"Token '{name}' revoked.")
    return redirect("accounts:security")


@login_required
def delete_account(request):
    form = PasswordConfirmForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid() and request.POST.get("confirm") == "DELETE":
        user = request.user
        profile = user.profile
        if profile.avatar:
            profile.avatar.delete(save=False)
        logout(request)
        user.delete()
        messages.info(request, "Your account and all of its documents have been permanently deleted.")
        return redirect("core:home")
    if request.method == "POST" and form.is_valid():
        form.add_error(None, "Type DELETE to confirm.")
    return render(request, "accounts/delete_account.html", {"form": form})
