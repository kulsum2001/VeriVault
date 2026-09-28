from django.test import TestCase
from django.urls import reverse


class PublicPageTests(TestCase):
    def test_home_ok(self):
        self.assertEqual(self.client.get(reverse("core:home")).status_code, 200)

    def test_features_ok(self):
        self.assertEqual(self.client.get(reverse("core:features")).status_code, 200)

    def test_faq_ok(self):
        self.assertEqual(self.client.get(reverse("core:faq")).status_code, 200)

    def test_robots_txt(self):
        resp = self.client.get(reverse("core:robots"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Sitemap:", resp.content)

    def test_sitemap(self):
        resp = self.client.get(reverse("sitemap"))
        self.assertEqual(resp.status_code, 200)

    def test_404_page(self):
        resp = self.client.get("/this-does-not-exist/")
        self.assertEqual(resp.status_code, 404)
