from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BoardViewSet,
    CardViewSet,
    ColumnViewSet,
    FileViewSet,
    login_view,
    logout_view,
    me,
    register,
)

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")
router.register("columns", ColumnViewSet, basename="column")
router.register("cards", CardViewSet, basename="card")
router.register("files", FileViewSet, basename="file")

urlpatterns = [
    path("auth/register/", register),
    path("auth/login/", login_view),
    path("auth/logout/", logout_view),
    path("auth/me/", me),
    path("", include(router.urls)),
]
