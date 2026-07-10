.PHONY: help db-up db-down install migrate createdb api agent bot bot-login fmt test frontend-install frontend-dev create-user prod-build prod-up prod-down prod-logs prod-migrate prod-create-user

COMPOSE_PROD := docker compose -f docker-compose.prod.yml --env-file .env.production

help:
	@echo "MeetingMind targets:"
	@echo "  db-up            start Postgres+pgvector (docker compose)"
	@echo "  db-down          stop Postgres"
	@echo "  install          install backend deps + playwright chromium"
	@echo "  migrate          alembic upgrade head"
	@echo "  createdb         dev: create extension+tables without alembic"
	@echo "  api              run FastAPI (uvicorn) on :8000"
	@echo "  agent            run the LiveKit transcription worker"
	@echo "  bot CALL=<uuid>  run the Meet bot for a call"
	@echo "  bot-login        sign the bot profile into the .env Google account"
	@echo "  create-user      create a MeetingMind login (password + 2FA on first sign-in)"
	@echo "  frontend-dev     run the Next.js dashboard"
	@echo ""
	@echo "Production (needs .env.production — see .env.production.example):"
	@echo "  prod-build       build the API + web images"
	@echo "  prod-up          build and start the whole stack"
	@echo "  prod-down        stop the stack (volumes survive)"
	@echo "  prod-logs        tail all service logs"
	@echo "  prod-create-user create the first login inside the running API container"

db-up:
	docker compose up -d

db-down:
	docker compose down

install:
	cd backend && pip install -r requirements.txt && playwright install chromium

migrate:
	cd backend && alembic upgrade head

createdb:
	cd backend && python -m scripts.create_db

api:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

agent:
	cd backend && python -m app.agent.transcription_agent dev

bot:
	@if [ -z "$(CALL)" ]; then \
		echo "Usage: make bot CALL=<call-uuid>"; \
		echo "  Get a call id from the dashboard or: curl -s localhost:8000/calls | jq -r '.[0].id'"; \
		exit 1; \
	fi
	cd backend && python -m scripts.run_bot $(CALL)

bot-login:
	cd backend && python -m scripts.bot_login $(ARGS)

fmt:
	cd backend && ruff check --fix . && ruff format .

test:
	cd backend && pytest -q

create-user:
	cd backend && python -m scripts.create_user $(ARGS)

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

# --- production ---------------------------------------------------------------

prod-build:
	$(COMPOSE_PROD) build

prod-up:
	$(COMPOSE_PROD) up -d --build

prod-down:
	$(COMPOSE_PROD) down

prod-logs:
	$(COMPOSE_PROD) logs -f

# Migrations run automatically on api start; this is for running them by hand.
prod-migrate:
	$(COMPOSE_PROD) exec api alembic upgrade head

prod-create-user:
	$(COMPOSE_PROD) exec -it api python -m scripts.create_user $(ARGS)
