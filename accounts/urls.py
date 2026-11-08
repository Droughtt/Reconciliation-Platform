from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token

from .views import MeView, UserDetailView, UserListCreateView

urlpatterns = [
    path("token/", obtain_auth_token, name="token"),
    path("me/", MeView.as_view(), name="me"),
    path("users/", UserListCreateView.as_view(), name="user-list"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
]