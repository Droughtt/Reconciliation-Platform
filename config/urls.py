from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def ping(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/imports/", include("imports.urls")),
    path("api/reconciliation/", include("reconciliation.urls")),
    path("api/reports/", include("reports.urls")),
    path("api/ping/", ping),
    path("", include("frontend.urls")),
]