import os
import re
import tempfile

import pytest

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"
os.environ["BOT_API_TOKEN"] = "test-bot-token"
os.environ["ADMIN_EMAIL"] = "head@test.local"
os.environ["ADMIN_PASSWORD"] = "head-password"
os.environ["MEDIA_DIR"] = tempfile.mkdtemp(prefix="lab-media-")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_demo, seed_reference  # noqa: E402

BOT = {"Authorization": "Bearer test-bot-token"}


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_reference(db)
        seed_demo(db)
    yield


class Client(TestClient):
    def csrf(self, url="/login") -> str:
        r = self.get(url)
        return re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)

    def login(self, email, password="demo12345"):
        tok = self.csrf("/login")
        r = self.post("/login", data={"email": email, "password": password, "csrf_token": tok, "next": "/cabinet"},
                      follow_redirects=False)
        assert r.status_code == 303, r.text
        return self

    def form(self, url, data, page="/cabinet", files=None):
        data = dict(data)
        data["csrf_token"] = self.csrf(page)
        return self.post(url, data=data, files=files, follow_redirects=False)


@pytest.fixture
def client():
    with Client(app) as c:
        yield c


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s
