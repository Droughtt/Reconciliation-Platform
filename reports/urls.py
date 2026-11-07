from django.urls import path

from .views import RunExportView, RunSummaryView

urlpatterns = [
    path("runs/<int:pk>/summary/", RunSummaryView.as_view(), name="run-summary"),
    path("runs/<int:pk>/export/", RunExportView.as_view(), name="run-export"),
]