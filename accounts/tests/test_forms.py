from django.contrib.auth import get_user_model

from django.test import TestCase

from accounts.forms import RegisterForm

User = get_user_model()


class RegisterFormTests(TestCase):
    def test_duplicate_email_rejected(self):
        User.objects.create_user("existing", "taken@example.com", "pw12345!")
        form = RegisterForm({"username": "someoneelse", "full_name": "A B", "email": "taken@example.com",
                             "password1": "S0meLongPass!", "password2": "S0meLongPass!"})
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_valid_registration(self):
        form = RegisterForm({"username": "someoneelse", "full_name": "A B", "email": "new2@example.com",
                             "password1": "S0meLongPass!", "password2": "S0meLongPass!"})
        self.assertTrue(form.is_valid(), form.errors)
