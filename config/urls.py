from django.contrib import admin
from django.urls import include, path
from frontend.views import ping

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/imports/", include("imports.urls")),
    path("api/reconciliation/", include("reconciliation.urls")),
    path("api/reports/", include("reports.urls")),
    path("api/ping/", ping, name="ping"),
    path("", include("frontend.urls")),
]