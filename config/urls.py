from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/imports/", include("imports.urls")),
    path("api/reconciliation/", include("reconciliation.urls")),
    path("api/reports/", include("reports.urls")),
    path("", include("frontend.urls")),
    path("ping/", include("frontend.urls")),
]