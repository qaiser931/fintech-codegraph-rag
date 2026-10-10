"""Database session management and connection pool simulation."""

from contextlib import contextmanager
from typing import Generator
from data.sample_codebase.config.settings import app_settings
from data.sample_codebase.utils.logging import get_logger

logger = get_logger("db.session")


class DatabaseSession:
    """Simulated SQLAlchemy / relational database session with transactional semantics."""

    def __init__(self) -> None:
        self.is_active: bool = True
        self.in_transaction: bool = False
        self.held_locks: list[str] = []

    def begin(self) -> None:
        """Begin transaction block."""
        self.in_transaction = True
        logger.info("Database transaction started.")

    def commit(self) -> None:
        """Commit pending modifications and release row locks."""
        self.in_transaction = False
        self.held_locks.clear()
        logger.info("Database transaction committed. Row locks released.")

    def rollback(self) -> None:
        """Rollback transaction and release row locks."""
        self.in_transaction = False
        self.held_locks.clear()
        logger.info("Database transaction rolled back. Row locks released.")

    def close(self) -> None:
        """Close connection and return to pool."""
        self.is_active = False


@contextmanager
def get_db_session() -> Generator[DatabaseSession, None, None]:
    """Context manager supplying database sessions from the pool."""
    session = DatabaseSession()
    session.begin()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error(f"Transaction failed, rolling back: {exc}")
        raise
    finally:
        session.close()
