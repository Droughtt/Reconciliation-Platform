from django.urls import path

from .views import ImportBatchDetailView, ImportBatchListCreateView

urlpatterns = [
    path("", ImportBatchListCreateView.as_view(), name="import-list"),
    path("<int:pk>/", ImportBatchDetailView.as_view(), name="import-detail"),
]