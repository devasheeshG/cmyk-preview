.PHONY: sync run format lint docker-up

sync:
	uv sync

run:
	uv run uvicorn app.main:app --reload --port 8080

format:
	uv run ruff format app

lint:
	uv run ruff check app

docker-up:
	docker compose up --build
