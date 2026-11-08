import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

User = get_user_model()
GOOD = {"username": "newperson", "password": "Correct-Horse-9", "role": "Reviewer"}


def patch(client, user, body):
    return client.patch(reverse("user-detail", args=[user.id]), body, format="json")


@pytest.mark.parametrize("role,expected", [("administrator", 200), ("analyst", 403), ("reviewer", 403), (None, 401)])
def test_only_administrators_can_list_users(request, db, client_for, role, expected):
    user = request.getfixturevalue(role) if role else None
    assert client_for(user).get(reverse("user-list")).status_code == expected


def test_admin_creates_a_user_with_a_role(client_for, administrator):
    r = client_for(administrator).post(reverse("user-list"), GOOD, format="json")
    assert r.status_code == 201 and r.data["role"] == "Reviewer"
    assert "password" not in r.data
    assert User.objects.get(username="newperson").check_password("Correct-Horse-9")


@pytest.mark.parametrize("change", [
    {"password": "123"},
    {"username": "bad name!"},
    {"role": "Boss"},
], ids=["weak-password", "bad-username", "unknown-role"])
def test_bad_new_users_are_rejected(client_for, administrator, change):
    r = client_for(administrator).post(reverse("user-list"), {**GOOD, **change}, format="json")
    assert r.status_code == 400
    assert User.objects.count() == 1  # only the administrator fixture


def test_duplicate_username_is_rejected_ignoring_case(client_for, administrator, analyst):
    r = client_for(administrator).post(reverse("user-list"), {**GOOD, "username": "ANALYST_T"}, format="json")
    assert r.status_code == 400


def test_admin_can_change_a_role(client_for, administrator, analyst):
    r = patch(client_for(administrator), analyst, {"role": "Reviewer"})
    assert r.status_code == 200 and r.data["role"] == "Reviewer"
    assert list(analyst.groups.values_list("name", flat=True)) == ["Reviewer"]


def test_empty_update_is_rejected(client_for, administrator, analyst):
    assert patch(client_for(administrator), analyst, {}).status_code == 400


def test_admin_cannot_change_own_access(client_for, administrator):
    client = client_for(administrator)
    assert patch(client, administrator, {"role": "Analyst"}).status_code == 400
    assert patch(client, administrator, {"is_active": False}).status_code == 400


def test_superusers_are_not_editable_here(client_for, administrator):
    root = User.objects.create_superuser("root_t", password="Correct-Horse-9")
    assert patch(client_for(administrator), root, {"role": "Analyst"}).status_code == 400


def test_deactivated_user_loses_access(client_for, administrator, analyst):
    token = Token.objects.create(user=analyst)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    assert client.get(reverse("me")).status_code == 200
    patch(client_for(administrator), analyst, {"is_active": False})
    assert client.get(reverse("me")).status_code == 401


def test_non_admins_cannot_change_users(client_for, analyst, reviewer):
    assert patch(client_for(analyst), reviewer, {"role": "Administrator"}).status_code == 403


def test_missing_user_is_404(client_for, administrator):
    r = client_for(administrator).patch(reverse("user-detail", args=[99999]), {"role": "Analyst"}, format="json")
    assert r.status_code == 404