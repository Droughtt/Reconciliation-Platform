from django.urls import path

from .views import index, ping

urlpatterns = [
    path("", index, name="index"),
    path("ping/", ping, name="ping"),
]