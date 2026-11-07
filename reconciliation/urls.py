from django.urls import path

from .flag_views import FlagDetailView, FlagListView
from .views import RunDetailView, RunListCreateView

urlpatterns = [
    path("runs/", RunListCreateView.as_view(), name="run-list"),
    path("runs/<int:pk>/", RunDetailView.as_view(), name="run-detail"),
    path("flags/", FlagListView.as_view(), name="flag-list"),
    path("flags/<int:pk>/", FlagDetailView.as_view(), name="flag-detail"),
]