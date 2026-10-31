"""Заполнение БД демо-данными: 10 досок с колонками, карточками и пользователями.

Запуск (из папки backend):
    USE_SQLITE=1 python manage.py seed        # локально на SQLite
    python manage.py seed                     # если настроен PostgreSQL (.env)

Опции:
    --username demo   --password DemoPass123   пароль для всех созданных юзеров
    --flush           сначала удалить все доски/пользователей (кроме суперюзеров)
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.models import Board, Card, Column, User

CATEGORIES = ["Работа", "Учёба", "Личное", "Проекты", "Дом"]

BOARD_TEMPLATES = [
    ("Спринт разработки", "Задачи текущей итерации команды бэкенда", "Работа"),
    ("Релиз v2.0", "Подготовка к релизу: тесты, документация, деплой", "Работа"),
    ("Маркетинговый план", "Контент-план и промо-кампании на квартал", "Работа"),
    ("Диплом", "Главы, источники, правки от научного руководителя", "Учёба"),
    ("Курс по алгоритмам", "Лекции, задачи LeetCode, подготовка к собеседованию", "Учёба"),
    ("Английский язык", "Слова, грамматика, разговорная практика", "Учёба"),
    ("Поездка в Сочи", "Билеты, отель, маршрут, что взять с собой", "Личное"),
    ("Ремонт в квартире", "Материалы, подрядчики, бюджет", "Дом"),
    (" pet-проект: трекер привычек", "Идея, MVP, дизайн, публикация", "Проекты"),
    ("Книги на осень", "Что читаю, что дочитал, отзывы", "Личное"),
]

COLUMN_TITLES = ["Backlog", "В работе", "На проверке", "Готово"]

CARD_TITLES = {
    "Backlog": [
        "Собрать требования", "Написать ТЗ", "Прикинуть сроки", "Выбрать стек",
        "Найти референсы", "Согласовать бюджет", "Записаться на курс",
    ],
    "В работе": [
        "Реализовать API", "Нарисовать макет", "Написать тесты", "Настроить CI",
        "Читать главу 3", "Решить 5 задач", "Купить материалы",
    ],
    "На проверке": [
        "Code review модуля auth", "Тест-план релиза", "Проверить орфографию",
        "Прогон на staging", "Финальная вычитка",
    ],
    "Готово": [
        "Бэклог очищен", "Прототип утверждён", "Глава 1 сдана", "Отель забронирован",
        "Список книг составлен",
    ],
}

DESCRIPTIONS = [
    "", "Подробное описание задачи: критерии приёмки и ссылки на макеты.",
    "Срочно, но не блокирует релиз.", "Обсудить с командой на дейли.",
    "Сделать до конца недели.", "",
]

USERS = [
    ("alice", "alice@example.com"),
    ("bob", "bob@example.com"),
    ("carol", "carol@example.com"),
    ("dave", "dave@example.com"),
]


class Command(BaseCommand):
    help = "Заполнить БД 10 демо-досками с колонками и карточками"

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo", help="Логин демо-пользователя")
        parser.add_argument("--password", default="DemoPass123", help="Пароль всех демо-юзеров")
        parser.add_argument("--flush", action="store_true", help="Удалить старые данные перед сидом")

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(42)
        password = opts["password"]

        if opts["flush"]:
            Board.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write("Старые данные удалены.")

        # пользователи
        users = []
        for username, email in USERS:
            user, created = User.objects.get_or_create(
                email=email, defaults={"username": username, "role": "user"}
            )
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(f"Создан пользователь: {username} ({email})")
            users.append(user)

        demo, created_demo = User.objects.get_or_create(
            email=f"{opts['username']}@example.com",
            defaults={"username": opts["username"], "role": "user"},
        )
        if created_demo or not demo.password:
            demo.set_password(password)
            demo.save()

        owners = list({u.id: u for u in users + [demo]}.values())

        created_boards = 0
        now = timezone.now()
        for i, (title, desc, category) in enumerate(BOARD_TEMPLATES):
            owner = owners[i % len(owners)]
            board = Board.objects.create(
                owner=owner,
                title=title.strip(),
                description=desc,
                category=category,
                created_at=now - timedelta(days=len(BOARD_TEMPLATES) - i),
            )
            columns = []
            for pos, col_title in enumerate(COLUMN_TITLES):
                columns.append(
                    Column.objects.create(board=board, title=col_title, position=pos)
                )
            card_count = 0
            for col in columns:
                n = random.randint(1, 3)
                titles = random.sample(CARD_TITLES[col.title], k=n)
                for cpos, t in enumerate(titles):
                    Card.objects.create(
                        column=col,
                        title=t,
                        description=random.choice(DESCRIPTIONS),
                        position=cpos,
                        priority=random.choice([0, 1, 2, 3]),
                        due_date=(now + timedelta(days=random.randint(-3, 21))).date()
                        if random.random() < 0.5
                        else None,
                    )
                    card_count += 1
            created_boards += 1
            self.stdout.write(
                f"  Доска {created_boards:>2}: «{board.title}» — {len(columns)} колонки, "
                f"{card_count} карточек (владелец: {owner.username}, метка: {board.category})"
            )

        total_cards = Card.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nГотово: досок — {Board.objects.count()}, колонок — {Column.objects.count()}, "
                f"карточек — {total_cards}, пользователей — {User.objects.count()}.\n"
                f"Вход: любой email из списка выше или «{opts['username']}», пароль: {password}"
            )
        )
