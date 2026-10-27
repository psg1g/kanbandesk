"""Аутентификация: access-токен берётся из httpOnly cookie `access`.

Вынесено в отдельный модуль, чтобы избежать циклического импорта
(api.views импортирует DRF, который при загрузке резолвит
DEFAULT_AUTHENTICATION_CLASSES из этого модуля).
"""

from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication

ACCESS_COOKIE = "access"


class CookieJWTAuthentication(JWTAuthentication):
    """Сначала смотрим заголовок Authorization (для совместимости с
    curl/admin-инструментами), затем — cookie `access`."""

    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            return super().authenticate(request)
        raw = request.COOKIES.get(ACCESS_COOKIE)
        if not raw:
            return None
        validated_token = self.get_validated_token(raw)
        return self.get_user(validated_token), validated_token
