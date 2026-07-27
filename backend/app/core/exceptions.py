"""Custom Exception classes for Scanner Cache and application core services."""

import logging

logger = logging.getLogger("app.exceptions")


class ScannerCacheException(Exception):
    """Base exception for scanner cache operations."""
    pass


class RedisCacheTimeoutException(ScannerCacheException):
    """Raised when a Redis cache operation exceeds configured timeout bounds."""
    pass


class RedisCacheConnectionException(ScannerCacheException):
    """Raised when Redis server connection fails or is unreachable."""
    pass
