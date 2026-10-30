"""Регистрация моделей в стандартной админ-панели Django (django.contrib.admin).

Модели: User, Board, Column, Card, File.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import Board, Card, Column, File, User


# ── Кастомный заголовок панели ────────────────────────────────────────────
admin.site.site_header = "Админ-панель Kanban"
admin.site.site_title = "Kanban Admin"
admin.site.index_title = "Управление проектом"


# ── Пользователи ──────────────────────────────────────────────────────────
class BoardInline(admin.TabularInline):
    model = Board
    extra = 0
    fields = ("title", "category", "created_at")
    readonly_fields = ("created_at",)
    show_change_link = True


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-created_at",)
    list_display = (
        "username", "email", "role_badge", "is_staff",
        "is_active", "boards_count", "created_at",
    )
    list_filter = ("role", "is_staff", "is_active", "created_at")
    search_fields = ("username", "email")
    inlines = [BoardInline]

    # Пользователь аутентифицируется по email, поэтому переопределяем fieldsets
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Профиль", {"fields": ("username", "role", "created_at")}),
        (
            "Права доступа",
            {
                "fields": (
                    "is_active", "is_staff", "is_superuser",
                    "groups", "user_permissions",
                ),
            },
        ),
        ("Последний вход", {"fields": ("last_login",)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "username", "role", "password1", "password2"),
            },
        ),
    )
    readonly_fields = ("created_at", "last_login")

    @admin.display(description="Роль", ordering="role")
    def role_badge(self, obj):
        color = "#7c3aed" if obj.role == "admin" else "#64748b"
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;'
            'border-radius:12px;font-size:12px;">{}</span>',
            color, obj.get_role_display(),
        )

    @admin.display(description="Досок")
    def boards_count(self, obj):
        return obj.boards.count()


# ── Доски ─────────────────────────────────────────────────────────────────
class ColumnInline(admin.TabularInline):
    model = Column
    extra = 0
    fields = ("title", "position", "cards_count")
    readonly_fields = ("cards_count",)
    show_change_link = True

    @admin.display(description="Карточек")
    def cards_count(self, obj):
        return obj.cards.count()


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = (
        "title", "owner", "category", "columns_count",
        "cards_count", "created_at", "updated_at",
    )
    list_filter = ("category", "created_at", "owner")
    search_fields = ("title", "description", "category", "owner__username")
    autocomplete_fields = ("owner",)
    ordering = ("-created_at",)
    inlines = [ColumnInline]
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 50

    @admin.display(description="Колонок")
    def columns_count(self, obj):
        return obj.columns.count()

    @admin.display(description="Карточек")
    def cards_count(self, obj):
        return Card.objects.filter(column__board=obj).count()


# ── Колонки ───────────────────────────────────────────────────────────────
class CardInline(admin.TabularInline):
    model = Card
    extra = 0
    fields = ("title", "position", "priority", "due_date", "files_count")
    readonly_fields = ("files_count",)
    show_change_link = True

    @admin.display(description="Файлов")
    def files_count(self, obj):
        return obj.files.count()


@admin.register(Column)
class ColumnAdmin(admin.ModelAdmin):
    list_display = ("title", "board", "position", "cards_count", "created_at")
    list_filter = ("board", "created_at")
    search_fields = ("title", "board__title")
    autocomplete_fields = ("board",)
    ordering = ("board", "position")
    inlines = [CardInline]
    list_select_related = ("board",)

    @admin.display(description="Карточек")
    def cards_count(self, obj):
        return obj.cards.count()


# ── Карточки ──────────────────────────────────────────────────────────────
@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = (
        "title", "column", "column__board", "priority_badge",
        "due_date", "position", "files_count", "created_at",
    )
    list_filter = ("priority", "column__board", "due_date")
    search_fields = ("title", "description", "column__title", "column__board__title")
    autocomplete_fields = ("column",)
    ordering = ("-created_at",)
    list_select_related = ("column", "column__board")
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 50

    @admin.display(description="Приоритет", ordering="priority")
    def priority_badge(self, obj):
        colors = {0: "#94a3b8", 1: "#3b82f6", 2: "#f59e0b", 3: "#ef4444"}
        labels = {0: "нет", 1: "низкий", 2: "средний", 3: "высокий"}
        c = colors.get(obj.priority, "#94a3b8")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;'
            'border-radius:12px;font-size:12px;">{}</span>',
            c, labels.get(obj.priority, obj.priority),
        )

    @admin.display(description="Файлов")
    def files_count(self, obj):
        return obj.files.count()


# ── Файлы ─────────────────────────────────────────────────────────────────
@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = (
        "original_name", "card", "file_type", "size_human",
        "is_public", "link", "created_at",
    )
    list_filter = ("is_public", "mime", "created_at")
    search_fields = ("original_name", "stored_name", "card__title")
    autocomplete_fields = ("card",)
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "stored_name", "size_bytes")
    list_select_related = ("card",)
    list_per_page = 50

    @admin.display(description="Тип")
    def file_type(self, obj):
        return obj.mime.split("/")[-1].upper()

    @admin.display(description="Размер")
    def size_human(self, obj):
        size = obj.size_bytes or 0
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.0f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @admin.display(description="Ссылка")
    def link(self, obj):
        if obj.is_public and obj.url_path:
            return format_html('<a href="{}" target="_blank">открыть ↗</a>', obj.url_path)
        return "— (приватный)"
