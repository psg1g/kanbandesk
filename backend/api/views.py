import os

from django.conf import settings
from django.contrib.auth import login, logout
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

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

@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    ser = RegisterSerializer(data=request.data)
    if not ser.is_valid():
        return Response(_errors(ser.errors), status=status.HTTP_400_BAD_REQUEST)
    user = ser.save()
    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "user": UserSerializer(user).data,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        },
        status=status.HTTP_201_CREATED,
    )


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
        errors = _errors(ser.errors)
        if "detail" in ser.errors:
            errors = {"errors": {"detail": "Неверный email или пароль"}}
        return Response(errors, status=code)

    user = ser.validated_data["user"]
    cache.delete(cache_key)
    login(request, user)  # cookie-сессия Django
    refresh = RefreshToken.for_user(user)  # JWT для Authorization: Bearer
    return Response(
        {
            "user": UserSerializer(user).data,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
    )


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


def time_now():
    import time

    return time.time()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


# --------------------------- Boards (items) --------------------------------

class BoardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "limit"
    max_page_size = 100


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
            qs = qs.filter(title__icontains=search)
        return qs

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
        return FileResponse(open(full, "rb"), as_attachment=True, filename=f.original_name)
