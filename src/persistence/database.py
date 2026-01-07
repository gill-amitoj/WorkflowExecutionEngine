"""
Database connection and session management.

Provides PostgreSQL connection handling with connection pooling
and proper session lifecycle management.
"""

import logging
from contextlib import contextmanager
from typing import Generator, Optional

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from src.config import get_config

logger = logging.getLogger(__name__)


class Database:
    """
    Database connection manager with connection pooling.
    
    Uses psycopg2's ThreadedConnectionPool for thread-safe connection management.
    """
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize database with connection URL."""
        config = get_config()
        self.database_url = database_url or config.DATABASE_URL
        self.pool_size = config.DATABASE_POOL_SIZE
        self.max_overflow = config.DATABASE_MAX_OVERFLOW
        self._pool: Optional[pool.ThreadedConnectionPool] = None
    
    def initialize(self) -> None:
        """Initialize the connection pool."""
        if self._pool is not None:
            return
        
        logger.info("Initializing database connection pool")
        try:
            self._pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=self.pool_size + self.max_overflow,
                dsn=self.database_url,
            )
            logger.info("Database connection pool initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    
    def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool is not None:
            logger.info("Closing database connection pool")
            self._pool.closeall()
            self._pool = None
    
    @contextmanager
    def get_connection(self) -> Generator:
        """
        Get a connection from the pool.
        
        Usage:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
        """
        if self._pool is None:
            self.initialize()
        
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)
    
    @contextmanager
    def get_cursor(self, commit: bool = True) -> Generator:
        """
        Get a cursor with automatic commit/rollback.
        
        Usage:
            with db.get_cursor() as cur:
                cur.execute("INSERT INTO ...")
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            try:
                yield cursor
                if commit:
                    conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()
    
    @contextmanager
    def transaction(self) -> Generator:
        """
        Create a transaction context for multiple operations.
        
        Usage:
            with db.transaction() as cur:
                cur.execute("INSERT INTO ...")
                cur.execute("UPDATE ...")
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            try:
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()
    
    def execute(self, query: str, params: tuple = None) -> list:
        """Execute a query and return results."""
        with self.get_cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchall()
            return []
    
    def execute_one(self, query: str, params: tuple = None) -> Optional[dict]:
        """Execute a query and return a single result."""
        with self.get_cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchone()
            return None
    
    def health_check(self) -> bool:
        """Check if database is accessible."""
        try:
            result = self.execute_one("SELECT 1 as healthy")
            return result is not None and result.get("healthy") == 1
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Global database instance
_database: Optional[Database] = None


def get_database() -> Database:
    """Get the global database instance."""
    global _database
    if _database is None:
        _database = Database()
        _database.initialize()
    return _database


def set_database(db: Database) -> None:
    """Set the global database instance (useful for testing)."""
    global _database
    _database = db
