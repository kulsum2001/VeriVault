from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("login/verify/", views.twofa, name="twofa"),
    path("logout/", views.logout_view, name="logout"),
    path("reauth/", views.reauth, name="reauth"),
    path("profile/", views.profile, name="profile"),
    path("security/", views.security, name="security"),
    path("security/2fa/setup/", views.twofa_setup, name="twofa_setup"),
    path("security/2fa/setup/qr.svg", views.twofa_qr, name="twofa_qr"),
    path("security/2fa/disable/", views.twofa_disable, name="twofa_disable"),
    path("tokens/create/", views.token_create, name="token_create"),
    path("tokens/<int:pk>/revoke/", views.token_revoke, name="token_revoke"),
    path("delete/", views.delete_account, name="delete"),
    # Password reset (mails go to the console by default)
    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name="accounts/password_reset_form.html",
        email_template_name="accounts/password_reset_email.txt",
        subject_template_name="accounts/password_reset_subject.txt",
        success_url=reverse_lazy("accounts:password_reset_done"),
    ), name="password_reset"),
    path("password-reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="accounts/password_reset_done.html"), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="accounts/password_reset_confirm.html",
        success_url=reverse_lazy("accounts:password_reset_complete"),
    ), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="accounts/password_reset_complete.html"), name="password_reset_complete"),
]
