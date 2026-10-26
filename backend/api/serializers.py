import re

from django.conf import settings
from django.contrib.auth import authenticate
from rest_framework import serializers

from .models import Board, Card, Column, File, User
from .file_validation import validate_upload

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
PASSWORD_RE = re.compile(r"^(?=.*[A-Za-zА-Яа-я])(?=.*\d).{8,64}$")


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    username = serializers.CharField(max_length=30)
    password = serializers.CharField(
        write_only=True, min_length=8, max_length=64,
        error_messages={"required": "Укажите пароль", "blank": "Укажите пароль"},
    )
    # фронтенд отправляет поле как password2 — принимаем оба варианта
    password_confirm = serializers.CharField(
        write_only=True, min_length=8, max_length=64, required=False, allow_blank=True,
    )
    password2 = serializers.CharField(
        write_only=True, min_length=8, max_length=64, required=False, allow_blank=True,
    )

    def validate_email(self, value):
        value = value.strip().lower()
        if "@" not in value or "." not in value.split("@")[-1]:
            raise serializers.ValidationError("Введите корректный email")
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Этот email уже занят")
        return value

    def validate_username(self, value):
        value = value.strip()
        if not USERNAME_RE.match(value):
            raise serializers.ValidationError(
                "Только латиница, цифры и _, от 3 до 30 символов"
            )
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Этот логин уже занят")
        return value

    def validate_password(self, value):
        if not PASSWORD_RE.match(value):
            raise serializers.ValidationError(
                "Пароль: от 8 символов, буквы и цифры"
            )
        return value

    def validate(self, attrs):
        confirm = attrs.get("password_confirm") or attrs.get("password2")
        # если фронтенд (или браузерное автозаполнение) не передал поле
        # подтверждения — не блокируем регистрацию; совпадение проверяем
        # только когда значение прислано непустым
        if confirm and attrs["password"] != confirm:
            raise serializers.ValidationError({"password2": "Пароли не совпадают"})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data["email"],
            username=validated_data["username"],
            password=validated_data["password"],
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            email=attrs.get("email", "").strip().lower(),
            password=attrs.get("password", ""),
        )
        if user is None:
            # одинаковая ошибка для неверного email и неверного пароля
            raise serializers.ValidationError(
                {"detail": "Неверный email или пароль"}, code="invalid_login"
            )
        attrs["user"] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "username", "role", "created_at"]
        read_only_fields = fields


class TitleFieldsMixin:
    def validate_title(self, value):
        value = (value or "").strip()
        if not value or len(value) > 120:
            raise serializers.ValidationError(
                ["Введите название (до 120 символов)"]
            )
        return value

    def validate_description(self, value):
        if value and len(value) > 2000:
            raise serializers.ValidationError("Не более 2000 символов")
        return value


class FileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = File
        fields = [
            "id",
            "card_id",
            "original_name",
            "mime",
            "size_bytes",
            "is_public",
            "url",
            "created_at",
        ]
        read_only_fields = fields

    def get_url(self, obj):
        if obj.is_public:
            return obj.url_path
        # приватные файлы отдаёт эндпоинт Django после проверки владельца
        return f"/api/files/{obj.id}/download/"


class UploadFileSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):
        validate_upload(value)
        return value


class CardSerializer(TitleFieldsMixin, serializers.ModelSerializer):
    files = FileSerializer(many=True, read_only=True)

    class Meta:
        model = Card
        fields = [
            "id",
            "column_id",
            "title",
            "description",
            "position",
            "due_date",
            "priority",
            "files",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "files"]
        extra_kwargs = {"column_id": {"required": False}}

    def validate_priority(self, value):
        if value is None or value < 0 or value > 3:
            raise serializers.ValidationError("Приоритет: от 0 до 3")
        return value


class ColumnSerializer(TitleFieldsMixin, serializers.ModelSerializer):
    cards = CardSerializer(many=True, read_only=True)

    class Meta:
        model = Column
        fields = [
            "id",
            "board_id",
            "title",
            "position",
            "cards",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "cards"]


class ColumnListSerializer(TitleFieldsMixin, serializers.ModelSerializer):
    card_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Column
        fields = ["id", "board_id", "title", "position", "card_count"]
        read_only_fields = ["id", "board_id", "position", "card_count"]


class MoveCardSerializer(serializers.Serializer):
    column_id = serializers.IntegerField()
    position = serializers.IntegerField(min_value=0)


class BoardSerializer(TitleFieldsMixin, serializers.ModelSerializer):
    columns = ColumnSerializer(many=True, read_only=True)

    class Meta:
        model = Board
        fields = [
            "id",
            "title",
            "description",
            "columns",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "columns"]


class BoardListSerializer(TitleFieldsMixin, serializers.ModelSerializer):
    column_count = serializers.IntegerField(read_only=True)
    card_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Board
        fields = [
            "id",
            "title",
            "description",
            "column_count",
            "card_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
