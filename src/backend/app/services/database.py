"""SQLAlchemy database setup and session management.

Production connection budget for the planned single-replica deployment:

* API: ``1 * (20 pool + 20 overflow) = 40``
* default and video workers: ``(4 + 3) * 40 = 280``
* conservative scheduler allowance: ``1 * 40 = 40``
* migrations/operations headroom: ``10``

The conservative ceiling is therefore 370 connections, below the deployment's
required PostgreSQL ``max_connections=400``. Any replica, concurrency, or pool
increase must recalculate this budget and rerun the load gate.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from app.core.config import Settings, logger, settings


def create_database_engine(database_url: str, app_settings: Settings = settings):
    """Create an engine with SQLite-safe or production PostgreSQL pooling."""
    is_sqlite = database_url.startswith("sqlite")
    is_sqlite_memory = database_url in ("sqlite://", "sqlite:///:memory:")

    if is_sqlite and not is_sqlite_memory:
        # File-based SQLite doesn't create its parent directory (only the file
        # itself), so a fresh checkout crashes with "unable to open database
        # file" if data/ was never created — it's gitignored as a runtime dir.
        db_path = database_url.replace("sqlite:///", "", 1)
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    if is_sqlite_memory:
        # In-memory SQLite only exists for the lifetime of a single connection,
        # so every session must share that one connection to see the same data.
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    if is_sqlite:
        # File-based SQLite: each thread gets its own connection to the file.
        # PostgreSQL pool settings intentionally do not apply to dev/test SQLite.
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )

    return create_engine(
        database_url,
        poolclass=QueuePool,
        pool_size=app_settings.DATABASE_POOL_SIZE,
        max_overflow=app_settings.DATABASE_MAX_OVERFLOW,
        pool_timeout=app_settings.DATABASE_POOL_TIMEOUT_SECONDS,
        pool_recycle=1800,
        pool_pre_ping=True,
    )


engine = create_database_engine(settings.DATABASE_URL)

# NOTE: no PRAGMA foreign_keys=ON is set here, so SQLite never enforces the
# ondelete="CASCADE" declared on FK columns in app/models/*.py — those cascades only
# happen because application code (e.g. auth.py::delete_account) deletes child rows
# by hand before deleting the parent. Keep that in mind before adding a new FK.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that provides a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error("Database session exception: %s", e)
        db.rollback()
        raise
    finally:
        db.close()
