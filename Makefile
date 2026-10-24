.PHONY: up up-gpu down test test-db lint-frontend

up:            ; docker compose up -d --build
up-gpu:        ; docker compose --profile gpu up -d --build
down:          ; docker compose --profile gpu down
test:          ; python -m pytest deepstream/tests backend/tests -q && cd frontend && npm test
# Needs a reachable PostgreSQL: TEST_DATABASE_URL=postgresql://user:pw@localhost:5432/vehicles_test make test-db
test-db:       ; python -m pytest deepstream/tests backend/tests -q
