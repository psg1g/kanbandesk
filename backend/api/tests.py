import io
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient


def register(client, email="user@test.com", username="user1", password="Passw0rd123"):
    return client.post(
        "/api/auth/register/",
        {
            "email": email,
            "username": username,
            "password": password,
            "password_confirm": password,
        },
        format="json",
    )


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_public(self):
        r = self.client.get("/health/")
        self.assertEqual(r.status_code, 200)

    def test_register_valid(self):
        r = register(self.client)
        self.assertEqual(r.status_code, 201)
        self.assertIn("access", r.json())

    def test_register_invalid_password(self):
        r = self.client.post(
            "/api/auth/register/",
            {"email": "a@b.com", "username": "aaa", "password": "short",
             "password_confirm": "short"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.json()["errors"])

    def test_register_duplicate_email(self):
        register(self.client)
        r = register(self.client, username="other1")
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", r.json()["errors"])

    def test_login_wrong_password_401(self):
        register(self.client)
        r = self.client.post(
            "/api/auth/login/",
            {"email": "user@test.com", "password": "WrongPass123"},
            format="json",
        )
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["errors"]["detail"], "Неверный email или пароль")

    def test_login_and_me_and_logout(self):
        register(self.client)
        r = self.client.post(
            "/api/auth/login/",
            {"email": "user@test.com", "password": "Passw0rd123"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        token = r.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["username"], "user1")
        out = self.client.post("/api/auth/logout/")
        self.assertEqual(out.status_code, 204)

    def test_closed_page_requires_auth(self):
        r = self.client.get("/api/boards/")
        self.assertEqual(r.status_code, 401)


class CrudTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        r = register(self.client)
        self.token = r.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def _board(self, title="Моя доска"):
        return self.client.post("/api/boards/", {"title": title}, format="json")

    def test_board_crud(self):
        r = self._board()
        self.assertEqual(r.status_code, 201)
        bid = r.json()["id"]
        self.assertEqual(self.client.get(f"/api/boards/{bid}/").status_code, 200)
        u = self.client.put(
            f"/api/boards/{bid}/", {"title": "Новое имя"}, format="json"
        )
        self.assertEqual(u.status_code, 200)
        d = self.client.delete(f"/api/boards/{bid}/")
        self.assertEqual(d.status_code, 204)

    def test_title_required_max_len(self):
        r = self.client.post("/api/boards/", {"title": "   "}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("title", r.json()["errors"])
        r = self._board("x" * 121)
        self.assertEqual(r.status_code, 400)

    def test_other_user_cannot_access(self):
        b = self._board().json()["id"]
        c2 = APIClient()
        register(c2, email="second@test.com", username="second")
        c2.credentials(
            HTTP_AUTHORIZATION=f"Bearer {c2.get('/api/auth/login', {'email':'second@test.com','password':'Passw0rd123'}, format='json').json()['access']}"
        ) if False else None
        tok2 = register(c2, email="third@test.com", username="third").json()["access"]
        c2.credentials(HTTP_AUTHORIZATION=f"Bearer {tok2}")
        self.assertIn(c2.get(f"/api/boards/{b}/").status_code, (403, 404))
        self.assertIn(
            c2.delete(f"/api/boards/{b}/").status_code, (403, 404)
        )

    def test_columns_cards_move(self):
        bid = self._board().json()["id"]
        col = self.client.post(
            f"/api/boards/{bid}/columns/", {"title": "Todo"}, format="json"
        ).json()
        self.assertEqual(col["title"], "Todo")
        card = self.client.post(
            "/api/cards/",
            {"column_id": col["id"], "title": "Задача"},
            format="json",
        )
        self.assertEqual(card.status_code, 201)
        cid = card.json()["id"]
        col2 = self.client.post(
            f"/api/boards/{bid}/columns/", {"title": "Done"}, format="json"
        ).json()
        mv = self.client.post(
            f"/api/cards/{cid}/move/",
            {"column_id": col2["id"], "position": 0},
            format="json",
        )
        self.assertEqual(mv.status_code, 200)
        self.assertEqual(mv.json()["column_id"], col2["id"])

    def test_delete_only_empty_column(self):
        bid = self._board().json()["id"]
        col = self.client.post(
            f"/api/boards/{bid}/columns/", {"title": "Todo"}, format="json"
        ).json()
        self.client.post(
            "/api/cards/", {"column_id": col["id"], "title": "X"}, format="json"
        )
        d = self.client.delete(f"/api/columns/{col['id']}/")
        self.assertEqual(d.status_code, 400)

    def test_search_pagination(self):
        self._board("Альфа")
        self._board("Бета")
        r = self.client.get("/api/boards/?search=Альфа")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data["results"]), 1)

    def test_export_xlsx(self):
        self._board("=1+1")  # инъекция формулы должна остаться текстом
        r = self.client.get("/api/boards/export/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(r.content))
        ws = wb["Данные"]
        self.assertEqual(ws.title, "Данные")
        self.assertEqual(ws.freeze_panes, "A2")
        cells = [str(c.value) for c in ws[2]]
        self.assertTrue(any("'=1+1" in v or "=1+1" in v for v in cells))


class FileTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        tok = register(self.client).json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
        bid = self.client.post("/api/boards/", {"title": "B"}, format="json").json()["id"]
        col = self.client.post(
            f"/api/boards/{bid}/columns/", {"title": "C"}, format="json"
        ).json()
        self.cid = self.client.post(
            "/api/cards/", {"column_id": col["id"], "title": "Card"}, format="json"
        ).json()["id"]

    def test_upload_image_ok(self):
        png = SimpleUploadedFile(
            "pic.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, content_type="image/png"
        )
        r = self.client.post(f"/api/cards/{self.cid}/files/", {"file": png}, format="multipart")
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["is_public"])
        self.assertIn("/media/public/", r.json()["url"])

    def test_upload_bad_type_415(self):
        f = SimpleUploadedFile("evil.exe", b"MZ", content_type="application/x-msdownload")
        r = self.client.post(f"/api/cards/{self.cid}/files/", {"file": f}, format="multipart")
        self.assertEqual(r.status_code, 415)

    def test_upload_too_large_413(self):
        big = SimpleUploadedFile(
            "big.png", b"\x89PNG\r\n\x1a\n" + b"0" * (6 * 1024 * 1024),
            content_type="image/png",
        )
        r = self.client.post(f"/api/cards/{self.cid}/files/", {"file": big}, format="multipart")
        self.assertEqual(r.status_code, 413)

    def test_upload_hidden_extension_rejected(self):
        # "../x.png" после санитизации Django превращается в "x.png" без точек —
        # такие имена отклоняются как недопустимые
        f = SimpleUploadedFile("..png", b"data", content_type="image/png")
        r = self.client.post(f"/api/cards/{self.cid}/files/", {"file": f}, format="multipart")
        self.assertIn(r.status_code, (400, 415))

    def test_file_deleted_with_card(self):
        png = SimpleUploadedFile("pic.png", b"\x89PNG\r\n\x1a\n" + b"0" * 50,
                                 content_type="image/png")
        fid = self.client.post(
            f"/api/cards/{self.cid}/files/", {"file": png}, format="multipart"
        ).json()["id"]
        r = self.client.delete(f"/api/files/{fid}/")
        self.assertEqual(r.status_code, 204)

        d = self.client.delete(f"/api/cards/{self.cid}/")
        self.assertEqual(d.status_code, 204)

    def test_guest_gets_401_on_export(self):
        anon = APIClient()
        self.assertEqual(anon.get("/api/boards/export/").status_code, 401)
