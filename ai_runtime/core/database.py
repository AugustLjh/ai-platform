"""
Database Connection Pool Manager
"""
import asyncpg
import logging
from typing import Optional
from contextlib import asynccontextmanager

from .config import DatabaseConfig

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database connection pool manager"""

    def __init__(self, config: DatabaseConfig):
        """
        Initialize database manager

        Args:
            config: Database configuration
        """
        self.config = config
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create database connection pool"""
        if self._pool is not None:
            logger.warning("Database pool already exists")
            return

        try:
            self._pool = await asyncpg.create_pool(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                min_size=self.config.min_pool_size,
                max_size=self.config.max_pool_size,
                command_timeout=60,
            )
            logger.info(
                f"✅ Database pool created: {self.config.host}:{self.config.port}/{self.config.database}"
            )
            logger.info(
                f"   Pool size: {self.config.min_pool_size}-{self.config.max_pool_size}"
            )
        except Exception as e:
            logger.error(f"❌ Failed to create database pool: {e}")
            raise

    async def disconnect(self):
        """Close database connection pool"""
        if self._pool is None:
            return

        try:
            await self._pool.close()
            self._pool = None
            logger.info("✅ Database pool closed")
        except Exception as e:
            logger.error(f"❌ Failed to close database pool: {e}")
            raise

    @property
    def pool(self) -> asyncpg.Pool:
        """Get connection pool"""
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self._pool

    async def health_check(self) -> bool:
        """
        Check database connection health

        Returns:
            True if healthy, False otherwise
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    @asynccontextmanager
    async def transaction(self):
        """
        Context manager for database transactions

        Example:
            async with db_manager.transaction() as conn:
                await conn.execute("INSERT ...")
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield conn


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get global database manager instance"""
    global _db_manager
    if _db_manager is None:
        raise RuntimeError("Database manager not initialized")
    return _db_manager


def init_db_manager(config: DatabaseConfig) -> DatabaseManager:
    """
    Initialize global database manager

    Args:
        config: Database configuration

    Returns:
        Database manager instance
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(config)
    return _db_manager
