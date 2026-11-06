"""
Connection-Managed Async Task Pool (ARCH-09)
Replaces raw unmanaged `threading.Thread` dispatches with a managed ThreadPoolExecutor
that strictly wraps task execution with Django's `close_old_connections()`.

This guarantees:
1. PostgreSQL connection hygiene (prevents orphaned/leaked DB connections).
2. Clean resource cleanup before and after task execution.
3. Configurable concurrency limits (max_workers) preventing thread exhaustion attacks.
4. Deterministic synchronous fallback during test execution ('test' in sys.argv).
"""
import sys
import logging
from concurrent.futures import ThreadPoolExecutor
from django.db import close_old_connections
from django.conf import settings

logger = logging.getLogger(__name__)

# Enterprise connection-managed thread pool
_MAX_WORKERS = getattr(settings, 'ASYNC_TASK_MAX_WORKERS', 10)
_EXECUTOR = ThreadPoolExecutor(
    max_workers=_MAX_WORKERS,
    thread_name_prefix='eazyshop_async'
)


def run_async(func, *args, **kwargs):
    """
    Submits a callable to the managed thread pool with strict connection cleanup.
    If running inside Django test runner ('test' in sys.argv), executes synchronously
    to ensure test determinism and prevent SQLite database lock collisions.
    """
    force_sync = kwargs.pop('force_sync', False)
    force_async = kwargs.pop('force_async', False)

    def _connection_managed_wrapper():
        close_old_connections()
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            func_name = getattr(func, '__name__', str(func))
            logger.error(f"[ASYNC TASK ERROR] ❌ Task '{func_name}' failed: {exc}")
        finally:
            close_old_connections()

    # In unit tests or when explicitly requested, execute synchronously for deterministic state
    if not force_async and (force_sync or 'test' in sys.argv or getattr(settings, 'IS_TESTING', False)):
        return _connection_managed_wrapper()

    return _EXECUTOR.submit(_connection_managed_wrapper)
