.PHONY: dev test lint demo migrate
dev:        ## локальный запуск без Docker (SQLite)
	python -m app.seed --demo && uvicorn app.main:app --reload
test:
	pytest -q --cov=app --cov-report=term-missing
lint:
	ruff check app tests
demo:
	python -m app.seed --demo
migrate:    ## новая миграция после изменения models.py
	alembic revision --autogenerate -m "$(m)"
