# PostgreSQL Runtime Design

## Goal

Run the shared HelpFlow environment on PostgreSQL without removing the fast SQLite path used by unit tests and zero-setup local development.

## Decisions

- Docker Compose uses `postgres:16-alpine` as the primary database.
- The API waits for PostgreSQL health before starting and runs `alembic upgrade head` before Uvicorn.
- `DATABASE_URL` remains the only database selector; SQLite stays the application default outside Compose.
- SQLAlchemy remains database-agnostic. PostgreSQL connectivity is provided by `psycopg[binary]`.
- Database state lives in a named Docker volume and credentials have development-only defaults that can be overridden from `.env`.
- CI/unit tests continue to use isolated SQLite databases. A Compose smoke check proves the PostgreSQL path.

## Acceptance Criteria

1. `docker compose config` resolves an API and a healthy PostgreSQL service.
2. The API receives a `postgresql+psycopg://` URL in Compose.
3. Alembic migrations run before the API process.
4. Existing SQLite tests remain green.
5. README and `.env.example` explain both modes for macOS and Windows.

