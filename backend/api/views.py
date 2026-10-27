import os

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .authentication import ACCESS_COOKIE, CookieJWTAuthentication  # noqa: F401

from .excel import ExcelExportMixin
from .file_validation import validate_upload
from .models import Board, Card, Column, File, User
from .serializers import (
    BoardListSerializer,
    BoardSerializer,
    CardSerializer,
    ColumnListSerializer,
    ColumnSerializer,
    FileSerializer,
    LoginSerializer,
    MoveCardSerializer,
    RegisterSerializer,
    UploadFileSerializer,
    UserSerializer,
)


# ---------------------- Access token in httpOnly cookie --------------------

COOKIE_AGE = 24 * 3600  # совпадает с ACCESS_TOKEN_LIFETIME (24 ч)


def _set_access_cookie(response, access_token):
    """Access-токен — только в httpOnly cookie, в теле ответа его нет."""
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=COOKIE_AGE,
        path="/",
        httponly=True,
        samesite="Lax",
        secure=getattr(settings, "SESSION_COOKIE_SECURE", False),
    )
    return response


def _delete_access_cookie(response):
    response.delete_cookie(ACCESS_COOKIE, path="/")
    return response


def _issue_tokens(request, user, response):
    """Выдать JWT и установить access-токен в httpOnly cookie.

    Refresh-токен храним подписанным в cacheDB ( inaccessible for JS),
    по нему работает /auth/refresh/. В теле ответа токенов нет.
    """
    from django.core.cache import cache as django_cache

    refresh = RefreshToken.for_user(user)
    try:
        django_cache.set(f"refresh:{user.id}", str(refresh), COOKIE_AGE)
    except Exception:  # кэш недоступен — просто теряем возможность refresh
        pass
    # Django-сессия как резервный способ авторизации (для admin и т.п.)
    login(request, user)
    return _set_access_cookie(response, str(refresh.access_token))


class EmailPasswordBackend:
    """Свой бэкенд аутентификации вместо ModelBackend.

    ModelBackend при неизвестном email возвращает None и пишет в лог
    «Failed login for …», а некоторые версии Django/DRF отдают
    «User not found». Здесь: явное сообщение на русском и тихий лог.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        login = (username or kwargs.get("email") or kwargs.get("username") or "").strip().lower()
        if not login or password is None:
            return None
        user = None
        if "@" in login:
            user = User.objects.filter(email__iexact=login).first()
        else:
            user = User.objects.filter(username__iexact=login).first()
        if user is None:
            # проверяем хеш несуществующего пользователя — защита от timing-атаки
            from django.contrib.auth.hashers import check_password, make_password
            check_password(password, make_password("dummy"))
            return None
        if not user.is_active:
            return None
        from django.contrib.auth.hashers import check_password

        if check_password(password, user.password):
            user.set_password(password)  # обновить хеш, если алгоритм изменился
            user.save(update_fields=["password"])
            return user
        return None

    def get_user(self, user_id):
        try:
            return get_user_model().objects.get(pk=user_id)
        except get_user_model().DoesNotExist:
            return None


def _friendly_auth_error(errors_dict):
    """Заменяем технические/английские сообщения DRF на человеческие."""
    out = {}
    for field, msgs in errors_dict.items():
        if isinstance(msgs, list):
            texts = [str(m) for m in msgs]
        elif isinstance(msgs, dict):
            texts = [str(v) for v in msgs.values()]
        else:
            texts = [str(msgs)]
        fixed = []
        for t in texts:
            tl = t.lower()
            if "user not found" in tl or "not_found" in tl or "unauthenticated user" in tl:
                fixed.append("Неверный email или пароль")
            elif "this password" in tl and "similiar" in tl:
                fixed.append("Пароль слишком простой")
            elif "entirely numeric" in tl:
                fixed.append("Пароль не может состоять только из цифр")
            elif "is too similar" in tl:
                fixed.append("Пароль слишком похож на email или логин")
            elif "this password cannot be similar to your" in tl:
                fixed.append("Пароль не должен совпадать с логином или email")
            else:
                fixed.append(t)
        out[field] = fixed
    return {"errors": out}


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Проверка живости для Docker и мониторинга."""
    from django.http import JsonResponse

    return JsonResponse({"status": "ok"})


from rest_framework.views import exception_handler as drf_exception_handler


def api_exception_handler(exc, context):
    """Единый формат ошибок: {"errors": {"поле": "сообщение"}}."""
    from rest_framework.exceptions import ValidationError as DRFValidationError

    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    data = response.data
    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        detail = data["detail"]
        msg = str(detail[0]) if isinstance(detail, list) else str(detail)
        response.data = {"errors": {"detail": msg}}
    elif isinstance(data, dict):
        response.data = _errors(data)
    elif isinstance(data, list):
        response.data = _errors({"detail": data})
    return response


def _errors(detail):
    """Приводит ошибки DRF к виду {"errors": {"поле": "сообщение"}}."""
    # сначала отбрасываем вложенные списки сообщений до первой строки
    if isinstance(detail, dict):
        detail = {
            k: (v[0] if isinstance(v, list) and v else v) for k, v in detail.items()
        }
    if isinstance(detail, dict):
        out = {}
        for field, msgs in detail.items():
            if isinstance(msgs, list):
                out[field] = msgs[0] if msgs else ""
            elif isinstance(msgs, dict):
                out[str(field)] = str(list(msgs.values())[0])
            else:
                out[field] = str(msgs)
        return {"errors": out}
    if isinstance(detail, list):
        return {"errors": {"detail": str(detail[0])}}
    return {"errors": {"detail": str(detail)}}


# ----------------------------- Auth ---------------------------------------

class LogoutRateThrottle(UserRateThrottle):
    """Отдельный лимит на выход: не считаем logout общими 100/min."""

    scope = "logout"


def _xff_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


class XForwardedAnonThrottle(AnonRateThrottle):
    """Анонимный троттлинг по реальному IP клиента за прокси (X-Forwarded-For)."""

    def get_ident(self, request):
        return _xff_ip(request)


class RegisterRateThrottle(XForwardedAnonThrottle):
    """Не более 10 запросов в минуту на IP к /api/auth/register/.

    Важно: при запуске за nginx без учёта X-Forwarded-For DRF берёт
    REMOTE_ADDR — адрес контейнера web, общий для всех пользователей.
    Тогда лимит срабатывал глобально и ломал работу сайта целиком.
    """

    scope = "register"


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RegisterRateThrottle])
def register(request):
    ser = RegisterSerializer(data=request.data)
    if not ser.is_valid():
        return Response(_friendly_auth_error(ser.errors), status=status.HTTP_400_BAD_REQUEST)
    # дополнительные проверки Django (простые пароли и т.п.)
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError
    try:
        validate_password(ser.validated_data["password"])
    except DjangoValidationError as e:
        return Response(
            _friendly_auth_error({"password": list(e.messages)}),
            status=status.HTTP_400_BAD_REQUEST,
        )
    user = ser.save()
    response = Response(
        {"user": UserSerializer(user).data},
        status=status.HTTP_201_CREATED,
    )
    return _issue_tokens(request, user, response)


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    # Ограничение попыток входа: не более LOGIN_RATE_LIMIT в минуту с одного IP
    cache_key = f"login:{_client_ip(request)}"
    from django.core.cache import cache

    window = cache.get(cache_key) or []
    now = time_now()
    window = [t for t in window if now - t < 60]
    if len(window) >= settings.LOGIN_RATE_LIMIT:
        return Response(
            {"errors": {"detail": "Слишком много попыток. Повторите через минуту"}},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    ser = LoginSerializer(data=request.data, context={"request": request})
    if not ser.is_valid():
        window.append(now)
        cache.set(cache_key, window, 120)
        code = (
            status.HTTP_401_UNAUTHORIZED
            if "detail" in ser.errors
            else status.HTTP_400_BAD_REQUEST
        )
        errors = _friendly_auth_error(ser.errors)
        if "detail" in ser.errors:
            errors = {"errors": {"detail": "Неверный email или пароль"}}
        return Response(errors, status=code)

    user = ser.validated_data["user"]
    cache.delete(cache_key)
    response = Response({"user": UserSerializer(user).data})
    return _issue_tokens(request, user, response)


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_view(request):
    """Обновить access-токен в httpOnly cookie по серверному refresh-токену.

    Токены не возвращаются в теле и никогда не попадают в JS/localStorage.
    """
    from django.core.cache import cache as django_cache

    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        # кука access истекла — пробуем восстановить по сессии Django
        uid = request.session.get("_auth_user_id")
        if not uid:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            user = get_user_model().objects.get(pk=uid)
        except get_user_model().DoesNotExist:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
    stored = django_cache.get(f"refresh:{user.id}")
    if not stored:
        return Response(status=status.HTTP_401_UNAUTHORIZED)
    try:
        refresh = RefreshToken(stored)
        # продлеем хранение refresh-токена
        django_cache.set(f"refresh:{user.id}", str(refresh), COOKIE_AGE)
    except Exception:
        return Response(status=status.HTTP_401_UNAUTHORIZED)
    response = Response({"status": "ok"})
    return _set_access_cookie(response, str(refresh.access_token))


def _client_ip(request):
    return _xff_ip(request)


def time_now():
    import time

    return time.time()


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LogoutRateThrottle])
def logout_view(request):
    """Выход. Разрешён и неаутентифицированному клиенту (просто очищает
    сессию), чтобы фронтенд никогда не получал здесь 401/429."""
    uid = request.session.get("_auth_user_id")
    user = getattr(request, "user", None)
    if uid is None and user and user.is_authenticated:
        uid = user.pk
    if uid is not None:
        from django.core.cache import cache as django_cache

        django_cache.delete(f"refresh:{uid}")
    logout(request)
    return _delete_access_cookie(Response(status=status.HTTP_204_NO_CONTENT))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


# --------------------------- Boards (items) --------------------------------

class BoardPagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = "limit"
    max_page_size = 100

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data["page"] = self.page.number
        response.data["pages"] = self.page.paginator.num_pages
        response.data["page_size"] = self.get_page_size(self.request)
        return response


class BoardViewSet(ExcelExportMixin, viewsets.ModelViewSet):
    """Основная сущность темы — доски. Пользователь видит только свои."""

    permission_classes = [IsAuthenticated]
    pagination_class = BoardPagination
    export_columns = [
        ("ID", lambda b: b.id),
        ("Название", lambda b: b.title),
        ("Описание", lambda b: b.description),
        ("Колонок", lambda b: b.columns.count()),
        ("Карточек", lambda b: sum(c.cards.count() for c in b.columns.all())),
        ("Создана", lambda b: b.created_at.date()),
    ]

    def get_queryset(self):
        qs = (
            Board.objects.filter(owner=self.request.user)
            .prefetch_related("columns__cards")
        )
        search = self.request.query_params.get("search", "").strip()
        if search:
            from django.db.models import Q

            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))
        category = self.request.query_params.get("category", "").strip()
        if category:
            if category == "none":
                qs = qs.filter(category="")
            else:
                qs = qs.filter(category__iexact=category)
        return qs

    @action(detail=False, methods=["get"], url_path="categories")
    def categories(self, request):
        """Список меток досок текущего пользователя для фильтра."""
        names = (
            Board.objects.filter(owner=request.user)
            .exclude(category="")
            .values_list("category", flat=True)
            .distinct()
        )
        return Response(sorted({n for n in names if n}))

    def get_serializer_class(self):
        if self.action == "list":
            return BoardListSerializer
        return BoardSerializer

    def get_object(self):
        obj = super().get_object()
        if obj.owner_id != self.request.user.id and self.request.user.role != "admin":
            raise NotFound()  # чужая доска недоступна (404/403)
        return obj

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def destroy(self, request, *args, **kwargs):
        board = self.get_object()
        paths = [
            f.file.path
            for f in File.objects.filter(card__column__board=board)
        ]
        super().destroy(request, *args, **kwargs)
        _remove_files(paths)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ---- columns nested under a board ----
    @action(detail=True, methods=["get", "post"], url_path="columns")
    def columns(self, request, pk=None):
        board = self.get_object()
        if request.method == "GET":
            cols = board.columns.annotate(card_count=models_count_cards())
            return Response(ColumnListSerializer(cols, many=True).data)
        ser = ColumnListSerializer(data=request.data)
        if not ser.is_valid():
            return Response(_errors(ser.errors), status=400)
        last = board.columns.order_by("-position").first()
        col = Column.objects.create(
            board=board,
            title=ser.validated_data["title"].strip(),
            position=(last.position + 1) if last else 0,
        )
        return Response(
            ColumnListSerializer(col).data, status=status.HTTP_201_CREATED
        )

    # ---- create card directly on a column of this board ----
    @action(
        detail=True,
        methods=["post"],
        url_path=r"columns/(?P<col_pk>\d+)/cards",
    )
    def column_cards(self, request, pk=None, col_pk=None):
        board = self.get_object()
        try:
            column = board.columns.get(pk=col_pk)
        except Column.DoesNotExist:
            raise NotFound()
        ser = CardSerializer(data=request.data)
        if not ser.is_valid():
            return Response(_errors(ser.errors), status=400)
        last = column.cards.order_by("-position").first()
        card = ser.save(column=column, position=(last.position + 1) if last else 0)
        return Response(CardSerializer(card).data, status=status.HTTP_201_CREATED)


def models_count_cards():
    from django.db.models import Count

    return Count("cards")


def _remove_files(paths):
    for p in paths:
        try:
            if p and os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass


# ------------------------------ Columns ------------------------------------

class ColumnViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ColumnListSerializer

    def get_queryset(self):
        return Column.objects.filter(board__owner=self.request.user)

    def get_object(self):
        obj = super().get_object()
        if obj.board.owner_id != self.request.user.id and self.request.user.role != "admin":
            raise NotFound()
        return obj

    def create(self, request, *args, **kwargs):
        board_id = request.data.get("board_id")
        try:
            board = Board.objects.get(pk=board_id, owner=request.user)
        except Board.DoesNotExist:
            raise NotFound()
        ser = self.get_serializer(data=request.data)
        if not ser.is_valid():
            return Response(_errors(ser.errors), status=400)
        last = board.columns.order_by("-position").first()
        col = Column.objects.create(
            board=board,
            title=ser.validated_data["title"].strip(),
            position=(last.position + 1) if last else 0,
        )
        return Response(self.get_serializer(col).data, status=201)

    def destroy(self, request, *args, **kwargs):
        column = self.get_object()
        if column.cards.exists():
            return Response(
                {"errors": {"detail": "Удалить можно только пустую колонку"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        super().destroy(request, *args, **kwargs)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ------------------------------- Cards ---------------------------------------

class CardViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CardSerializer

    def get_queryset(self):
        return Card.objects.filter(column__board__owner=self.request.user)

    def get_object(self):
        obj = super().get_object()
        if obj.column.board.owner_id != self.request.user.id and self.request.user.role != "admin":
            raise NotFound()
        return obj

    def create(self, request, *args, **kwargs):
        column_id = request.data.get("column_id")
        try:
            column = Column.objects.get(pk=column_id, board__owner=request.user)
        except (Column.DoesNotExist, ValueError, TypeError):
            raise NotFound({"errors": {"detail": "Колонка не найдена"}})
        ser = self.get_serializer(data=request.data)
        if not ser.is_valid():
            return Response(_errors(ser.errors), status=400)
        last = column.cards.order_by("-position").first()
        card = ser.save(column=column, position=(last.position + 1) if last else 0)
        return Response(self.get_serializer(card).data, status=201)

    @action(detail=True, methods=["patch", "post"], url_path="move")
    def move(self, request, pk=None):
        """Перенос карточки: меняет колонку и позицию."""
        card = self.get_object()
        ser = MoveCardSerializer(data=request.data)
        if not ser.is_valid():
            return Response(_errors(ser.errors), status=400)
        try:
            target = Column.objects.get(
                pk=ser.validated_data["column_id"],
                board__owner=request.user,
            )
        except Column.DoesNotExist:
            raise NotFound({"errors": {"column_id": "Колонка не найдена"}})
        card.column = target
        card.position = ser.validated_data["position"]
        card.save()
        # нормализуем позиции в целевой колонке
        for i, c in enumerate(target.cards.order_by("position", "id")):
            if c.position != i:
                c.position = i
                c.save(update_fields=["position"])
        return Response(self.get_serializer(card).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="files",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload(self, request, pk=None):
        """Загрузка вложения к карточке (multipart/form-data)."""
        card = self.get_object()
        ser = UploadFileSerializer(data=request.data)
        if not ser.is_valid():
            return Response(_errors(ser.errors), status=400)
        upload = ser.validated_data["file"]
        kind = validate_upload(upload)  # raises 415/413 APIError with clear text
        is_public = kind == "image"
        f = File.objects.create(
            card=card,
            original_name=os.path.basename(upload.name),
            mime=upload.content_type,
            size_bytes=upload.size,
            is_public=is_public,
            file=upload,
        )
        return Response(FileSerializer(f).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        card = self.get_object()
        paths = [f.file.path for f in card.files.all()]
        super().destroy(request, *args, **kwargs)
        _remove_files(paths)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ------------------------------- Files ---------------------------------------

class FileViewSet(viewsets.GenericViewSet):
    """Удаление файла и отдача приватных файлов после проверки владельца."""

    permission_classes = [IsAuthenticated]
    queryset = File.objects.all()

    def _get_owned(self, pk):
        try:
            f = File.objects.get(pk=pk)
        except File.DoesNotExist:
            raise NotFound()
        if f.card.column.board.owner_id != self.request.user.id and self.request.user.role != "admin":
            raise PermissionDenied()
        return f

    def destroy(self, request, pk=None):
        f = self._get_owned(pk)
        path = f.file.path
        f.delete()
        _remove_files([path])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        from django.http import FileResponse

        f = self._get_owned(pk)
        full = os.path.join(settings.MEDIA_ROOT, f.file.name)
        if not os.path.isfile(full):
            raise NotFound()
        # inline=True -> preview in the browser tab; as_attachment via ?dl=1
        as_attachment = request.GET.get("dl") == "1"
        return FileResponse(
            open(full, "rb"),
            as_attachment=as_attachment,
            filename=f.original_name,
            content_type=f.mime or "application/octet-stream",
        )
