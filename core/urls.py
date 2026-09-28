from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("features/", views.features, name="features"),
    path("security/", views.security, name="security"),
    path("faq/", views.faq, name="faq"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("robots.txt", views.robots_txt, name="robots"),
]
