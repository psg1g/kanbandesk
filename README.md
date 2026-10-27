# Канбан-доска 📎

Полностэковое приложение: **backend** — Django 5 + DRF (Python 3.12, PostgreSQL 16), **frontend** — React 18 + Vite, деплой через Docker Compose + nginx.

## Структура
```
backend/          # Django + DRF API (JWT-авторизация, CRUD досок, файлы, экспорт Excel)
frontend/         # React SPA (регистрация/вход, доски, drag-and-drop карточки, вложения)
docker-compose.yml# db (postgres) + app (gunicorn) + web (nginx :80)
.env.example      # шаблон переменных окружения
```

## Возможности
- Регистрация/вход/выход (JWT, токен 24 ч, rate-limit входа 10/мин)
- Доски → колонки → карточки, только свой контент (чужой доступ — 403/404)
- Drag-and-drop перенос карточек между колонками (PATCH `/api/cards/{id}/move/`)
- Вложения: jpg/png/webp/pdf/docx/mp3, лимит из `MAX_UPLOAD_MB`, изображения — публичные, остальное — приватные (отдача после проверки владельца)
- Поиск досок `?search=`, пагинация, экспорт доски в Excel (`/api/boards/export/`)
- Проверка здоровья: `GET /health`

## Локальный запуск
Backend:
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
USE_SQLITE=1 python manage.py migrate   # для разработки без PostgreSQL
USE_SQLITE=1 python manage.py runserver
python manage.py test api               # 20 тестов
```
Frontend:
```bash
cd frontend
npm install
npm run dev        # http://localhost:3000, прокси /api -> :8000
```

## Деплой (Ubuntu + Docker)
```bash
cp .env.example .env      # заполнить SECRET_KEY, пароли, домен
docker compose up -d --build
docker compose exec app python manage.py createsuperuser
```
Открыт только порт 80 (nginx раздаёт SPA, проксирует /api на gunicorn, /media/public с тома uploads). Порт 5432 наружу не публикуется. Firewall: `ufw allow 80,443`. Для HTTPS поставьте Caddy/certbot перед nginx или замените web-сервис.

Проверка: `curl http://<host>/health` → `{"status":"ok"}`.
