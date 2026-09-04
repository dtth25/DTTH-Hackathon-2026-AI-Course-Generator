"""Guarded, id-preserving migration from HackaGen SQLite to PostgreSQL."""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from collections.abc import Mapping
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool


TABLES_IN_FK_ORDER = ("users", "courses", "email_otp_codes", "processing_jobs")
INSERT_BATCH_SIZE = 500
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class MigrationError(RuntimeError):
    """A safe-to-display migration validation or execution failure."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate HackaGen persistence from SQLite to PostgreSQL."
    )
    parser.add_argument("--source-sqlite", required=True, type=Path)
    parser.add_argument("--target-postgres", required=True)
    parser.add_argument("--confirm", required=True)
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if args.confirm != "MIGRATE":
        raise MigrationError("Refusing migration: pass --confirm MIGRATE")
    if not args.source_sqlite.is_file():
        raise MigrationError("Source SQLite file does not exist")
    try:
        dialect = make_url(args.target_postgres).get_backend_name()
    except Exception as exc:
        raise MigrationError("Target PostgreSQL URL is invalid") from exc
    if dialect != "postgresql":
        raise MigrationError("Target must be a PostgreSQL URL")


def _sqlite_read_only_engine(source: Path) -> Engine:
    resolved = source.resolve()

    def connect_read_only():
        return sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)

    return create_engine("sqlite+pysqlite://", creator=connect_read_only, poolclass=NullPool)


def _normalized_database_value(value):
    """Normalize equivalent values returned differently by SQLite and PostgreSQL."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value
    if isinstance(value, (date, time, Decimal, str, int, float, bool, type(None))):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _normalized_database_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return tuple(_normalized_database_value(item) for item in value)
    if isinstance(value, memoryview):
        return bytes(value)
    return value


def _row_values_are_equivalent(source_row: dict, target_row: Mapping) -> bool:
    return all(
        _normalized_database_value(source_row[column_name])
        == _normalized_database_value(target_row[column_name])
        for column_name in source_row
    )


def _verify_skipped_primary_keys(
    target_connection,
    target_table,
    source_rows: list[dict],
    inserted_primary_keys: set[tuple],
) -> None:
    primary_key_columns = list(target_table.primary_key.columns)
    skipped_rows = [
        row
        for row in source_rows
        if tuple(row[column.name] for column in primary_key_columns)
        not in inserted_primary_keys
    ]
    if not skipped_rows:
        return

    skipped_keys = [
        tuple(row[column.name] for column in primary_key_columns)
        for row in skipped_rows
    ]
    if len(primary_key_columns) == 1:
        predicate = primary_key_columns[0].in_(key[0] for key in skipped_keys)
    else:
        predicate = tuple_(*primary_key_columns).in_(skipped_keys)
    existing_rows = target_connection.execute(
        select(target_table).where(predicate)
    ).mappings()
    existing_by_key = {
        tuple(row[column.name] for column in primary_key_columns): row
        for row in existing_rows
    }

    for source_row, primary_key in zip(skipped_rows, skipped_keys, strict=True):
        existing_row = existing_by_key.get(primary_key)
        if existing_row is None or not _row_values_are_equivalent(
            source_row, existing_row
        ):
            raise MigrationError(
                "Migration aborted because an existing row differs from the source"
            )


def upgrade_target_schema(target_url: str) -> None:
    """Upgrade only the explicit target, without reading or changing the source."""
    migration_environment = {
        "DATABASE_URL": target_url,
        "JWT_SECRET": "migration-command-placeholder",
        "OPENROUTER_API_KEY": "migration-command-placeholder",
        "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
        "ENVIRONMENT": "test",
        "JOB_QUEUE_PROVIDER": "inline",
        "CREATE_DEFAULT_ADMIN": "false",
    }
    previous_environment = {
        name: os.environ.get(name) for name in migration_environment
    }
    os.environ.update(migration_environment)
    previous_logging_threshold = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        config = Config()
        config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(config, "head")
    finally:
        logging.disable(previous_logging_threshold)
        for name, previous_value in previous_environment.items():
            if previous_value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous_value


def migrate(source: Path, target_url: str) -> dict[str, tuple[int, int, int]]:
    source_engine = _sqlite_read_only_engine(source)
    target_engine = create_engine(target_url, pool_pre_ping=True)
    source_metadata = MetaData()
    target_metadata = MetaData()
    results: dict[str, tuple[int, int, int]] = {}
    try:
        source_metadata.reflect(bind=source_engine, only=TABLES_IN_FK_ORDER)
        target_metadata.reflect(bind=target_engine, only=TABLES_IN_FK_ORDER)
        missing = [
            name
            for name in TABLES_IN_FK_ORDER
            if name not in source_metadata.tables or name not in target_metadata.tables
        ]
        if missing:
            raise MigrationError("Required migration tables are missing")

        with source_engine.connect() as source_connection, target_engine.begin() as target_connection:
            for table_name in TABLES_IN_FK_ORDER:
                source_table = source_metadata.tables[table_name]
                target_table = target_metadata.tables[table_name]
                target_columns = {column.name for column in target_table.columns}
                source_columns = {column.name for column in source_table.columns}
                if not target_columns.issubset(source_columns):
                    raise MigrationError("Source schema is older than the target schema")

                column_names = [column.name for column in target_table.columns]
                rows = [
                    {name: row[name] for name in column_names}
                    for row in source_connection.execute(select(source_table)).mappings()
                ]
                before = target_connection.scalar(select(func.count()).select_from(target_table)) or 0
                for start in range(0, len(rows), INSERT_BATCH_SIZE):
                    batch = rows[start : start + INSERT_BATCH_SIZE]
                    primary_key_columns = list(target_table.primary_key.columns)
                    inserted = target_connection.execute(
                        postgresql_insert(target_table)
                        .values(batch)
                        .on_conflict_do_nothing(index_elements=primary_key_columns)
                        .returning(*primary_key_columns)
                    )
                    inserted_primary_keys = {tuple(row) for row in inserted}
                    _verify_skipped_primary_keys(
                        target_connection,
                        target_table,
                        batch,
                        inserted_primary_keys,
                    )
                after = target_connection.scalar(select(func.count()).select_from(target_table)) or 0
                results[table_name] = (len(rows), after - before, after)
    finally:
        source_engine.dispose()
        target_engine.dispose()
    return results


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        validate_args(args)
        upgrade_target_schema(args.target_postgres)
        results = migrate(args.source_sqlite, args.target_postgres)
    except MigrationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("Migration failed; no rows were committed", file=sys.stderr)
        return 1

    for table_name in TABLES_IN_FK_ORDER:
        source_count, inserted_count, target_count = results[table_name]
        print(
            f"{table_name}: source={source_count} inserted={inserted_count} target={target_count}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
