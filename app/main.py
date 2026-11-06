"""Точка входа веб-приложения Energy Lab."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.deps import LoginRequired, render
from app.routers import admin, api_bot, auth, cabinet, expertise, public


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # В продакшене схему создаёт Alembic (alembic upgrade head); create_all — страховка для разработки.
    Base.metadata.create_all(engine)
    from app.seed import seed_reference
    with SessionLocal() as db:
        seed_reference(db)
    yield


app = FastAPI(title="Energy Lab", lifespan=lifespan, description="ИС экспертно-оценочных тренингов Energy Lab",
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="lab_session",
                   max_age=14 * 24 * 3600, same_site="lax", https_only=settings.secure_cookies)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
os.makedirs(settings.media_dir, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")

for r in (public.router, auth.router, cabinet.router, expertise.router, admin.router, api_bot.router):
    app.include_router(r)


@app.exception_handler(LoginRequired)
async def _login_required(request: Request, exc: LoginRequired):
    return RedirectResponse(f"/login?next={request.url.path}", 303)


@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    titles = {403: "Доступ закрыт", 404: "Страница не найдена", 400: "Запрос не выполнен"}
    return render(request, "public/message.html", {"title": titles.get(exc.status_code, "Ошибка"),
                                                   "text": exc.detail}, exc.status_code)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}
