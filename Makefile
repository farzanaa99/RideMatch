.PHONY: up down logs ps test

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api worker db

ps:
	docker compose ps

test:
	.venv\Scripts\python.exe -m pytest
