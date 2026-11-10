from django.db.models.functions import Lower
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from .permissions import ADMIN, ANALYST, REVIEWER

User = get_user_model()
ROLES = [ADMIN, ANALYST, REVIEWER]


def role_of(user):
    if user.is_superuser:
        return "Superuser"
    return next((g.name for g in user.groups.all() if g.name in ROLES), None)


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "role", "is_active", "date_joined", "last_login"]

    def get_role(self, obj):
        return role_of(obj)


class UserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, validators=[UnicodeUsernameValidator()])
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    role = serializers.ChoiceField(choices=ROLES)

    def validate_username(self, value):
        value = value.strip()

        if User.objects.annotate(
            normalized_username=Lower("username")
        ).filter(normalized_username=value.lower()).exists():
            raise serializers.ValidationError(
                "That username is already taken."
            )

        return value

    def validate(self, attrs):
        try:
            validate_password(attrs["password"], user=User(username=attrs["username"]))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        with transaction.atomic():
            user = User.objects.create_user(
                username=validated_data["username"], password=validated_data["password"]
            )
            user.groups.set([Group.objects.get(name=validated_data["role"])])
        return user


class UserUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=ROLES, required=False)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Send a role or is_active to change.")
        return attrs