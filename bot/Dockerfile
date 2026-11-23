# Бот Energy Lab — без зависимостей, только стандартная библиотека Python.
# Сборка из папки bot/: docker compose up -d --build (контекст — родительская папка, см. docker-compose.yml)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
RUN useradd --system --uid 10001 bot
COPY bot /srv/bot
USER bot
CMD ["python", "-m", "bot.main"]
