from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts import totp
from core.testing import TempStorageTestCase

User = get_user_model()


class RegistrationLoginTests(TempStorageTestCase):
    def test_register_creates_user_and_profile(self):
        resp = self.client.post(reverse("accounts:register"), {
            "username": "newuser", "full_name": "New User", "email": "new@example.com",
            "password1": "S0meLongPass!", "password2": "S0meLongPass!",
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(username="newuser")
        self.assertTrue(hasattr(user, "profile"))
        self.assertEqual(user.profile.display_name, "New User")

    def test_login_with_email(self):
        User.objects.create_user("frank", "frank@example.com", "pw12345!")
        resp = self.client.post(reverse("accounts:login"), {"username": "frank@example.com", "password": "pw12345!"}, follow=True)
        self.assertTrue(resp.context["user"].is_authenticated)

    def test_login_wrong_password_shows_error(self):
        User.objects.create_user("gina", "gina@example.com", "pw12345!")
        resp = self.client.post(reverse("accounts:login"), {"username": "gina", "password": "wrong"})
        self.assertFalse(resp.context["user"].is_authenticated)

    def test_throttling_locks_after_max_attempts(self):
        from django.conf import settings
        User.objects.create_user("hank", "hank@example.com", "pw12345!")
        for _ in range(settings.LOGIN_MAX_ATTEMPTS):
            self.client.post(reverse("accounts:login"), {"username": "hank", "password": "wrong"})
        resp = self.client.post(reverse("accounts:login"), {"username": "hank", "password": "pw12345!"})
        self.assertFalse(resp.context["user"].is_authenticated)
        self.assertContains(resp, "Too many failed attempts")

    def test_2fa_flow(self):
        user = User.objects.create_user("ivy", "ivy@example.com", "pw12345!")
        self.client.login(username="ivy", password="pw12345!")
        secret = totp.generate_secret()
        self.client.session["totp_setup_secret"] = secret
        session = self.client.session
        session["totp_setup_secret"] = secret
        session.save()
        code = totp.totp(secret)
        resp = self.client.post(reverse("accounts:twofa_setup"), {"code": code}, follow=True)
        user.refresh_from_db()
        self.assertTrue(user.profile.totp_enabled)
        self.client.logout()
        resp = self.client.post(reverse("accounts:login"), {"username": "ivy", "password": "pw12345!"}, follow=False)
        self.assertRedirects(resp, reverse("accounts:twofa"))
        code2 = totp.totp(user.profile.totp_secret)
        final = self.client.post(reverse("accounts:twofa"), {"code": code2}, follow=True)
        self.assertTrue(final.context["user"].is_authenticated)

    def test_twofa_qr_code_is_scannable(self):
        """The QR image served during setup must actually decode back to the otpauth URI.

        This check uses optional, dev-only libraries (cairosvg, opencv) to prove the
        SVG is a genuinely scannable QR code - not just well-formed markup. It's not
        part of the shipped requirements, so it skips itself if they aren't installed.
        """
        try:
            import cairosvg  # noqa: F401
            import cv2  # noqa: F401
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("cairosvg/opencv not installed - optional QR decode check skipped")
        user = User.objects.create_user("qrena", "qrena@example.com", "pw12345!")
        self.client.login(username="qrena", password="pw12345!")
        self.client.get(reverse("accounts:twofa_setup"))  # generates + stores the setup secret
        resp = self.client.get(reverse("accounts:twofa_qr"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/svg+xml")
        svg = resp.content.decode("utf-8")
        self.assertIn("<svg", svg)
        self.assertIn('fill="#ffffff"', svg)  # background rect present for dark-mode/scanability

        secret = self.client.session["totp_setup_secret"]
        expected_uri = totp.provisioning_uri(secret, user.email)
        decoded = _decode_qr_svg(svg)
        self.assertEqual(decoded, expected_uri)

    def test_twofa_qr_requires_login_and_pending_setup(self):
        self.assertEqual(self.client.get(reverse("accounts:twofa_qr")).status_code, 302)  # not logged in
        User.objects.create_user("qbert", "qbert@example.com", "pw12345!")
        self.client.login(username="qbert", password="pw12345!")
        self.assertEqual(self.client.get(reverse("accounts:twofa_qr")).status_code, 404)  # no setup in progress


def _decode_qr_svg(svg_text):
    """Render an SVG QR code to a raster image and decode it, to prove it's genuinely scannable."""
    import cairosvg
    import cv2
    import numpy as np

    png_bytes = cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), output_width=300, output_height=300)
    array = np.frombuffer(png_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    data, _points, _ = cv2.QRCodeDetector().detectAndDecode(image)
    return data


class ApiTokenModelTests(TempStorageTestCase):
    def test_issue_and_authenticate(self):
        from accounts.models import ApiToken
        user = User.objects.create_user("jack", "jack@example.com", "pw12345!")
        token, raw = ApiToken.issue(user, "test token")
        found = ApiToken.authenticate(raw)
        self.assertEqual(found.pk, token.pk)
        self.assertIsNone(ApiToken.authenticate("bogus"))
