import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from api.views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("django-admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("health/", health),
]

# Media files are served by nginx in production; locally (DEBUG or tests) we
# serve them from Django so that /media/public/... links work without nginx.
if settings.DEBUG or os.environ.get("USE_SQLITE") == "1":
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
