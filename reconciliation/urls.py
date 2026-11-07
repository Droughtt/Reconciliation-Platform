from django.urls import path

from .views import RunDetailView, RunListCreateView

urlpatterns = [
    path("runs/", RunListCreateView.as_view(), name="run-list"),
    path("runs/<int:pk>/", RunDetailView.as_view(), name="run-detail"),
]