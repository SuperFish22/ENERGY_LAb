"""Документы проектов, файлы в задачах, ссылки на Яндекс/Google Диск, полный фотоальбом (spec 004)."""
import io
import os

from sqlalchemy import select

from app import attachments as at
from app import models as m
from app.config import settings
from tests.conftest import Client, app

HEAD = ("head@test.local", "head-password")
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
DOCX = b"PK\x03\x04" + b"\x00" * 60


def _user(db, email):
    return db.scalar(select(m.User).where(m.User.email == email))


def test_detect_by_content_not_extension():
    assert at.detect(PDF, "смета.pdf") == "pdf"
    assert at.detect(PDF, "смета.exe") == "pdf"                       # имя не решает — решает содержимое
    assert at.detect(DOCX, "договор.docx") == "docx"
    assert at.detect(DOCX, "virus.exe") is None                       # ZIP только под разрешённым расширением
    assert at.detect(b"MZ\x90\x00binary", "setup.exe") is None
    assert at.detect(b"MZ\x90\x00binary", "fake.pdf") is None
    assert at.detect("тайминг;мин\nсбор;15".encode(), "тайминг.csv") == "csv"
    assert at.detect(b"\x00\x01\x02", "x.txt") is None
    assert at.safe_name("../../etc/passwd") == "passwd" and at.safe_name('a<b>:"c".pdf') == "a_b_c_.pdf"


def test_parse_drive_links():
    assert at.parse_link("https://disk.yandex.ru/d/AbC123") == ("https://disk.yandex.ru/d/AbC123", "yandex")
    assert at.parse_link("yadi.sk/d/xyz")[1] == "yandex"
    assert at.parse_link("http://drive.google.com/drive/folders/1a")[0].startswith("https://drive.google.com/")
    assert at.parse_link("https://docs.google.com/spreadsheets/d/1/edit")[1] == "gsheets"
    assert at.parse_link("https://docs.google.com/document/d/1/edit")[1] == "gdocs"
    for bad in ("https://evil.example/disk.yandex.ru", "https://disk.yandex.ru.evil.com/d/1",
                "https://user:pass@drive.google.com/x", "javascript:alert(1)", ""):
        assert isinstance(at.parse_link(bad), str), bad


def test_project_documents_access(db):
    head = Client(app).__enter__().login(*HEAD)
    ev = db.scalar(select(m.Event).where(m.Event.code == "LAB-2026-07"))
    page = f"/cabinet/projects/{ev.id}?tab=docs"
    assert "Документы проекта" in head.get(page).text
    tok = head.csrf(page)
    r = head.post(f"/cabinet/projects/{ev.id}/docs", data={"csrf_token": tok, "mode": "file", "title": "Смета v2",
                                                          "category": "estimate"},
                  files={"file": ("смета.pdf", io.BytesIO(PDF), "application/pdf")}, follow_redirects=False)
    assert r.status_code == 303
    doc = db.scalar(select(m.Attachment).where(m.Attachment.title == "Смета v2"))
    assert doc.kind == "file" and doc.category == "estimate" and doc.size == len(PDF)
    assert os.path.isfile(os.path.join(settings.files_dir, doc.file))                # не в открытом MEDIA_DIR
    assert not os.path.exists(os.path.join(settings.media_dir, doc.file))
    got = head.get(f"/cabinet/files/{doc.id}")
    assert got.status_code == 200 and got.content == PDF and "attachment" in got.headers["content-disposition"]
    # исполняемый файл не пройдёт
    r = head.post(f"/cabinet/projects/{ev.id}/docs", data={"csrf_token": tok, "mode": "file"},
                  files={"file": ("setup.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")})
    assert "Такой файл загрузить нельзя" in r.text
    # ссылка на Яндекс Диск
    head.form(f"/cabinet/projects/{ev.id}/docs", {"mode": "link", "url": "https://disk.yandex.ru/d/Folder1",
                                                  "category": "other"}, page)
    link = db.scalar(select(m.Attachment).where(m.Attachment.url == "https://disk.yandex.ru/d/Folder1"))
    assert link.provider == "yandex" and link.title.startswith("Яндекс Диск")
    html = head.get(page).text
    assert "Смета" in html and 'href="https://disk.yandex.ru/d/Folder1"' in html
    # обычный участник, не участвующий в проекте, документы не видит и не скачает
    member = Client(app).__enter__().login("member@energy.local")
    assert "Документы проекта" not in member.get(page).text
    assert member.get(f"/cabinet/files/{doc.id}").status_code == 404
    # участник проекта (ответственный за станцию) видит, но удалить чужое не может
    tech = Client(app).__enter__().login("tech@energy.local")
    assert tech.get(f"/cabinet/files/{doc.id}").status_code == 200
    assert tech.form(f"/cabinet/projects/{ev.id}/docs/{doc.id}/delete", {}, page).status_code == 403
    doc_id, doc_path = doc.id, os.path.join(settings.files_dir, doc.file)
    head.form(f"/cabinet/projects/{ev.id}/docs/{doc_id}/delete", {}, page)
    db.expire_all()
    assert not db.get(m.Attachment, doc_id) and not os.path.exists(doc_path)


def test_task_files_notify_and_clip(db):
    author = _user(db, "katya@energy.local")
    smi = _user(db, "smi@energy.local")
    t = m.Task(title="Пост в соцсети", author_id=author.id, assignee_id=smi.id, status="in_progress", position=1)
    db.add(t)
    db.commit()
    c = Client(app).__enter__().login("smi@energy.local")
    page = f"/cabinet/tasks/{t.id}"
    assert "Прикрепить файл или ссылку" in c.get(page).text
    tok = c.csrf(page)
    c.post(f"{page}/files", data={"csrf_token": tok, "mode": "file", "title": "Макет поста"},
           files={"file": ("post.docx", io.BytesIO(DOCX), "application/octet-stream")})
    c.form(f"{page}/files", {"mode": "link", "url": "https://drive.google.com/drive/folders/abc"}, page)
    db.expire_all()
    t = db.get(m.Task, t.id)
    assert [a.kind for a in t.attachments] == ["file", "link"]
    inbox = db.scalars(select(m.InboxItem).where(m.InboxItem.user_id == author.id).order_by(m.InboxItem.id.desc()))
    texts = [i.text for i in inbox][:2]
    assert any("прикрепил(а) файл к задаче «Пост в соцсети»: Макет поста" in x for x in texts)
    assert any("прикрепил(а) ссылку" in x for x in texts)
    board = Client(app).__enter__().login("katya@energy.local").get("/cabinet/tasks").text
    assert "tcard-clip" in board
    hist = db.scalars(select(m.TaskEvent).where(m.TaskEvent.task_id == t.id, m.TaskEvent.field == "file")).all()
    assert len(hist) == 2
    # посторонний не скачает
    member = Client(app).__enter__().login("member@energy.local")
    assert member.get(f"/cabinet/files/{t.attachments[0].id}").status_code == 404
    assert member.get(page).status_code == 404


def test_album_link_on_public_page(client, db):
    head = Client(app).__enter__().login(*HEAD)
    ev = db.scalar(select(m.Event).where(m.Event.code == "LAB-2026-01"))
    page = f"/cabinet/projects/{ev.id}?tab=photos"
    head.form(f"/cabinet/projects/{ev.id}/album", {"album_url": "https://example.com/photos"}, page)
    db.expire_all()
    assert db.get(m.Event, ev.id).album_url is None
    head.form(f"/cabinet/projects/{ev.id}/album", {"album_url": "https://disk.yandex.ru/d/AllPhotos"}, page)
    pub = client.get("/e/LAB-2026-01").text
    assert 'href="https://disk.yandex.ru/d/AllPhotos"' in pub and "Все фото на Яндекс Диске" in pub
