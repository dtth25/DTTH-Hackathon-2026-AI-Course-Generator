"""SQLAlchemy database setup and session management."""

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from app.core.config import Settings, logger, settings


def create_database_engine(settings_obj: Settings) -> Engine:
    """Build an engine with SQLite-safe behavior or a bounded server DB pool."""
    database_url = settings_obj.DATABASE_URL
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
        # StaticPool would force concurrent requests onto one shared connection,
        # causing spurious "not found" reads when transactions overlap.
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )

    return create_engine(
        database_url,
        poolclass=QueuePool,
        pool_size=settings_obj.DB_POOL_SIZE,
        max_overflow=settings_obj.DB_MAX_OVERFLOW,
        pool_timeout=settings_obj.DB_POOL_TIMEOUT_SECONDS,
        pool_recycle=settings_obj.DB_POOL_RECYCLE_SECONDS,
        pool_pre_ping=True,
    )


engine = create_database_engine(settings)

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
