import re
import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")


class UserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        if not username:
            raise ValueError("Username is required")
        user = self.model(
            email=self.normalize_email(email).lower(), username=username, **extra
        )
        user.set_password(password)  # Django stores a PBKDF2 hash, never plaintext
        user.full_clean(exclude=["password", "last_login"])
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra):
        extra.setdefault("role", "admin")
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, username, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """users: id, email (unique), username (unique, 3-30), password_hash, role, created_at."""

    ROLE_CHOICES = [("user", "user"), ("admin", "admin")]

    email = models.EmailField(unique=True, max_length=254)
    username = models.CharField(
        unique=True,
        max_length=30,
        validators=[
            RegexValidator(
                regex=r"^[A-Za-z0-9_]{3,30}$",
                message="Только латиница, цифры и _, от 3 до 30 символов",
            )
        ],
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="user")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.username


def stored_upload_name(instance, filename):
    """Files are stored under UUID + extension; the original name lives in the DB."""
    safe_ext = re.sub(r"[^a-zA-Z0-9]", "", (filename.rsplit(".", 1)[-1] if "." in filename else ""))[:10]
    folder = "public" if instance.is_public else "private"
    ext = f".{safe_ext}" if safe_ext else ""
    return f"{folder}/{uuid.uuid4().hex}{ext}"


class Board(models.Model):
    """Main entity of the theme: Kanban board (replaces the `items` template table)."""

    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="boards"
    )
    title = models.CharField(max_length=120, validators=[])
    description = models.TextField(blank=True, default="", max_length=2000)
    category = models.CharField(
        max_length=50, blank=True, default="",
        help_text="Метка доски: Работа, Учёба и т.п.",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "boards"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Column(models.Model):
    """Column belongs to a board, ordered by position."""

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="columns")
    title = models.CharField(max_length=120)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "columns"
        ordering = ["position", "id"]


class Card(models.Model):
    """Card belongs to a column; moving changes column_id and position."""

    column = models.ForeignKey(Column, on_delete=models.CASCADE, related_name="cards")
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="", max_length=2000)
    position = models.PositiveIntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    priority = models.IntegerField(default=0, help_text="0..3")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cards"
        ordering = ["position", "id"]


class File(models.Model):
    """files: attached to a card, deleted together with it (ON DELETE CASCADE)."""

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="files")
    original_name = models.CharField(max_length=255)
    file = models.FileField(upload_to=stored_upload_name, max_length=255)
    stored_name = models.CharField(max_length=255, blank=True, default="")
    mime = models.CharField(max_length=100)
    size_bytes = models.BigIntegerField(default=0)
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "files"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.stored_name and self.file:
            self.stored_name = str(self.file.name).rsplit("/", 1)[-1]
            super().save(update_fields=["stored_name"])

    @property
    def url_path(self):
        """Path served by nginx (/media/...) for public files only."""
        if self.is_public:
            return f"/media/{self.file.name}"
        return None
