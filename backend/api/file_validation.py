"""File upload validation: allowed types by MIME + extension, size limits per kind."""
import os

from django.conf import settings
from rest_framework.exceptions import APIException, ValidationError

# kind -> (allowed extensions, allowed mimes, max bytes)
ALLOWED = {
    "image": (
        {".jpg", ".jpeg", ".png", ".webp"},
        {"image/jpeg", "image/png", "image/webp"},
        5 * 1024 * 1024,
    ),
    "document": (
        {".pdf", ".docx"},
        {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
        10 * 1024 * 1024,
    ),
    "audio": (
        {".mp3"},
        {"audio/mpeg", "audio/mp3"},
        15 * 1024 * 1024,
    ),
}


class WrongTypeError(APIException):
    status_code = 415
    default_detail = "Недопустимый тип файла. Разрешены: jpg, png, webp, pdf, docx, mp3"
    default_code = "unsupported_media_type"


class TooLargeError(APIException):
    status_code = 413
    default_detail = "Файл слишком большого размера"
    default_code = "payload_too_large"


def validate_upload(upload):
    """Raise 415/413 API errors with clear messages; return the detected kind."""
    raw_name = getattr(upload, "name", "") or ""
    # имена вида ../x отклоняются (Django срезает путь до basename,
    # поэтому недопустимое имя определяем по отсутствию расширения у basename
    # либо по точкам в начале имени)
    base = os.path.basename(raw_name)
    if ".." in raw_name or "/" in raw_name or "\\" in raw_name:
        raise WrongTypeError("Недопустимое имя файла")
    ext = os.path.splitext(base)[1].lower()
    mime = getattr(upload, "content_type", "") or ""

    kind = None
    for k, (exts, mimes, _max) in ALLOWED.items():
        if ext in exts and mime in mimes:
            kind = k
            break
    if kind is None:
        raise WrongTypeError()

    max_bytes = ALLOWED[kind][2]
    # общий лимит из .env не должен превышать лимит типа
    env_limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    max_bytes = min(max_bytes, max(env_limit, 5 * 1024 * 1024))
    if upload.size > max_bytes:
        raise TooLargeError(
            f"Размер файла превышает {max_bytes // (1024 * 1024)} МБ"
        )
    return kind
