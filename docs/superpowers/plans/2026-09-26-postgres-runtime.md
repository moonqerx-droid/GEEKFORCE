# PostgreSQL Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PostgreSQL the Docker Compose database while retaining SQLite for tests and zero-setup development.

**Architecture:** Compose owns PostgreSQL lifecycle and passes an explicit SQLAlchemy URL to the API. Application code remains selected by `DATABASE_URL`; migrations run before Uvicorn.

**Tech Stack:** Docker Compose, PostgreSQL 16, SQLAlchemy 2, psycopg 3, Alembic, pytest

**Spec:** `docs/superpowers/specs/2026-09-26-postgres-runtime-design.md`

## Global Constraints

- Keep SQLite as the default outside Docker Compose.
- Do not change the HTTP API contract.
- PostgreSQL credentials must be overridable by environment variables.
- Preserve macOS and Windows compatibility through Docker Desktop.

## Review Focus

- PostgreSQL is not ready when the API starts: healthcheck and `depends_on.condition` prevent a startup race.
- A password contains URL-sensitive characters: Compose builds the URL from documented development defaults; custom deployments should provide `DATABASE_URL` directly.
- Existing volume from the SQLite Compose version exists: new PostgreSQL volume has a distinct name.
- Migrations fail: the API command must stop instead of starting against an old schema.
- Unit tests run without Docker: SQLite remains the default and all tests pass.

---

### Task 1: PostgreSQL Compose Runtime

**Files:**
- Modify: `apps/api/tests/test_config.py`
- Modify: `apps/api/requirements.txt`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: `Settings.database_url: str` and Alembic runtime URL override.
- Produces: Compose service `db`, API `DATABASE_URL`, and dependency `psycopg[binary]`.

- [ ] **Step 1: Write failing configuration tests**

Add tests that read `docker-compose.yml` and assert `postgres:16-alpine`, a healthcheck, `depends_on.db.condition == "service_healthy"`, a `postgresql+psycopg://` API URL, and an API command beginning with `alembic upgrade head`.

- [ ] **Step 2: Verify RED**

Run: `cd apps/api && pytest tests/test_config.py -q`
Expected: FAIL because Compose has no `db` service.

- [ ] **Step 3: Implement the runtime**

Add `psycopg[binary]==3.2.10`; add the PostgreSQL service, healthcheck and named volume; make API depend on health; run migrations before Uvicorn; document environment overrides and the SQLite fallback.

- [ ] **Step 4: Verify GREEN**

Run: `cd apps/api && pytest tests/test_config.py -q && pytest -q`
Expected: all configuration and API tests pass.

- [ ] **Step 5: Validate Compose**

Run: `docker compose config --quiet`
Expected: exit code 0.

- [ ] **Step 6: Commit**

Run: `git add .env.example README.md docker-compose.yml apps/api/requirements.txt apps/api/tests/test_config.py docs/superpowers && git commit -m "feat: add PostgreSQL compose runtime"`

