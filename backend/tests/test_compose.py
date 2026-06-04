"""
test_compose.py — validate docker-compose.yml and env examples without Docker.

All checks read files as plain text and look for structural patterns.  No YAML
parser or Docker installation is required.  The goal is to catch regressions
(missing service, wrong image, public port binding, accidentally activated
DATABASE_URL) before any container is started.

Covered assertions
------------------
- docker-compose.yml exists at the repository root
- db service is defined and uses the official pgvector/pgvector:pg16 image
- the database port is bound to 127.0.0.1 (never exposed beyond localhost)
- a named db-data volume is declared for persistence
- the db service has a pg_isready healthcheck
- db/schema.sql is mounted read-only for automatic initialisation
- POSTGRES_PASSWORD references the DB_PASSWORD env var (not hardcoded)
- DATABASE_URL is commented out in the compose file (JSON is still default)
- DATABASE_URL placeholder appears in both .env.example files
"""
from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parent.parent.parent   # repository root
COMPOSE_FILE = _REPO / "docker-compose.yml"
ROOT_ENV_EXAMPLE = _REPO / ".env.example"
BACKEND_ENV_EXAMPLE = _REPO / "backend" / ".env.example"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def compose_text() -> str:
    assert COMPOSE_FILE.exists(), f"docker-compose.yml not found at {COMPOSE_FILE}"
    return COMPOSE_FILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# db service
# ---------------------------------------------------------------------------

class TestComposeDbService:
    def test_compose_file_exists(self):
        assert COMPOSE_FILE.exists(), "docker-compose.yml must exist at the repository root"

    def test_db_service_defined(self, compose_text: str):
        assert "db:" in compose_text, "docker-compose.yml must define a 'db' service"

    def test_db_uses_official_pgvector_image(self, compose_text: str):
        assert "pgvector/pgvector" in compose_text, (
            "The db service must use the official pgvector/pgvector image "
            "(https://hub.docker.com/r/pgvector/pgvector)"
        )

    def test_db_image_pinned_to_pg16(self, compose_text: str):
        assert "pgvector:pg16" in compose_text, (
            "Pin the db image to a specific PostgreSQL major version tag, e.g. pg16"
        )

    def test_db_port_bound_to_localhost_only(self, compose_text: str):
        """5432 must not be exposed on all interfaces (0.0.0.0)."""
        # A bare "5432:5432" (no host part) binds to all interfaces.
        assert '"5432:5432"' not in compose_text, (
            "Database port must not be bound to all interfaces. "
            'Use "127.0.0.1:5432:5432" instead of "5432:5432".'
        )
        assert "127.0.0.1:5432" in compose_text, (
            "Database port must be explicitly bound to 127.0.0.1"
        )

    def test_db_named_volume_declared(self, compose_text: str):
        assert "db-data:" in compose_text, (
            "A named volume 'db-data' must be declared for PostgreSQL persistence"
        )

    def test_db_healthcheck_uses_pg_isready(self, compose_text: str):
        assert "pg_isready" in compose_text, (
            "The db service healthcheck must use pg_isready"
        )

    def test_schema_sql_mounted_for_init(self, compose_text: str):
        assert "schema.sql" in compose_text, (
            "db/schema.sql must be mounted into the container for automatic initialisation"
        )

    def test_schema_sql_mounted_read_only(self, compose_text: str):
        assert "schema.sql:ro" in compose_text, (
            "The schema.sql init mount must be read-only (:ro)"
        )

    def test_postgres_password_references_env_var(self, compose_text: str):
        """POSTGRES_PASSWORD must come from DB_PASSWORD env var, not be bare text."""
        assert "DB_PASSWORD" in compose_text, (
            "POSTGRES_PASSWORD must reference the DB_PASSWORD env var "
            "so operators can override the dev default at runtime"
        )

    def test_database_url_commented_out_in_compose(self, compose_text: str):
        """DATABASE_URL must remain commented out — JSON persistence is the default."""
        for line in compose_text.splitlines():
            stripped = line.strip()
            # Accept commented-out DATABASE_URL lines; reject active ones.
            if "DATABASE_URL" in stripped and not stripped.startswith("#"):
                pytest.fail(
                    "DATABASE_URL must be commented out in docker-compose.yml. "
                    "The backend uses JSON persistence by default. "
                    "Activate PostgreSQL explicitly when store_pg.py is wired."
                )

    def test_backend_data_volume_still_declared(self, compose_text: str):
        assert "backend-data:" in compose_text, (
            "The backend-data named volume must still be declared "
            "(needed for JSON store and uploaded files)"
        )


# ---------------------------------------------------------------------------
# .env.example files contain DATABASE_URL placeholder
# ---------------------------------------------------------------------------

class TestEnvExamplesHaveDatabaseUrl:
    def test_root_env_example_has_database_url(self):
        assert ROOT_ENV_EXAMPLE.exists(), f".env.example not found at {ROOT_ENV_EXAMPLE}"
        content = ROOT_ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "DATABASE_URL" in content, (
            ".env.example must document the DATABASE_URL placeholder"
        )

    def test_backend_env_example_has_database_url(self):
        assert BACKEND_ENV_EXAMPLE.exists(), f".env.example not found at {BACKEND_ENV_EXAMPLE}"
        content = BACKEND_ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "DATABASE_URL" in content, (
            "backend/.env.example must document the DATABASE_URL placeholder"
        )

    def test_backend_env_example_documents_db_password(self):
        content = BACKEND_ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "DB_PASSWORD" in content, (
            "backend/.env.example must mention DB_PASSWORD so operators "
            "know how to override the dev default"
        )
