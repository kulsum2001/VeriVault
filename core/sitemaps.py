from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    changefreq = "monthly"
    protocol = "http"

    def items(self):
        return ["core:home", "core:features", "core:security", "core:faq",
                "core:privacy", "core:terms", "vault:verify", "api:docs",
                "accounts:login", "accounts:register"]

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return 1.0 if item == "core:home" else 0.6


SITEMAPS = {"static": StaticViewSitemap}
