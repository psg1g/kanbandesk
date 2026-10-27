"""Аутентификация: access-токен берётся из httpOnly cookie `access`.

Вынесено в отдельный модуль, чтобы избежать циклического импорта
(api.views импортирует DRF, который при загрузке резолвит
DEFAULT_AUTHENTICATION_CLASSES из этого модуля).
"""

from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

ACCESS_COOKIE = "access"


class CookieJWTAuthentication(JWTAuthentication):
    """Сначала смотрим заголовок Authorization (для совместимости с
    curl/admin-инструментами), затем — cookie `access`.

    Важно: если пользователя из токена найти нельзя (например, аккаунт был
    удалён, а кука с access-токеном всё ещё живёт в браузере до 24 часов),
    стандартный simplejwt бросает «User not found; user_not_found» и фронт
    показывает эту техническую ошибку прямо на странице. Здесь такая
    ситуация трактуется как «нет авторизации»: возвращаем None — DRF отдаст
    чистый 401, а фронт по 401 сам обновит токен или уйдёт на /login.
    """

    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            return super().authenticate(request)
        raw = request.COOKIES.get(ACCESS_COOKIE)
        if not raw:
            return None
        try:
            validated_token = self.get_validated_token(raw)
            return self.get_user(validated_token), validated_token
        except AuthenticationFailed as e:
            codes = {
                getattr(e.detail, "code", None),
                getattr(e.default_detail, "code", None),
            }
            texts = str(getattr(e, "detail", "")).lower()
            if "user_not_found" in codes or "user not found" in texts:
                # устаревшая/поддельная кука — считаем гостем, не ошибкой
                return None
            raise
