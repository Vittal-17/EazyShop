"""Intentional runtime selection; never discover a legacy environment file."""
import os
from pathlib import Path

from decouple import Config, RepositoryEmpty, RepositoryEnv
from django.core.exceptions import ImproperlyConfigured

from .database import database_config


def load_environment(base_dir, *, testing=False):
    base_dir = Path(base_dir)
    if testing:
        # Ignore production selectors and DATABASE_URL, preserving isolated CI use.
        path = base_dir / '.env.test'
        return Config(RepositoryEnv(str(path)) if path.is_file() else RepositoryEmpty()), False

    runtime = os.environ.get('EAZYSHOP_RUNTIME', 'local')
    if runtime not in ('local', 'production'):
        raise ImproperlyConfigured('EAZYSHOP_RUNTIME must be local or production.')

    selected_file = os.environ.get('EAZYSHOP_ENV_FILE')
    if runtime == 'production':
        # Environment-only deployment is the default for explicit production mode.
        if selected_file is None:
            return Config(RepositoryEmpty()), False
        if not selected_file:
            raise ImproperlyConfigured('EAZYSHOP_ENV_FILE must name an existing production configuration file.')
        path = Path(selected_file)
        if not path.is_absolute():
            path = base_dir / path
        if not path.is_file():
            raise ImproperlyConfigured('Explicit production configuration file is missing.')
        return Config(RepositoryEnv(str(path))), False

    if selected_file is not None:
        raise ImproperlyConfigured('EAZYSHOP_ENV_FILE requires explicit EAZYSHOP_RUNTIME=production. Local mode uses .env.local only.')
    path = base_dir / '.env.local'
    if not path.is_file():
        raise ImproperlyConfigured('Local configuration .env.local is required. See docs/local-postgresql.md; no legacy .env fallback is allowed.')
    repository = RepositoryEnv(str(path))
    # A process environment must not conceal an absent/incomplete local DB profile.
    try:
        complete = all(repository[key].strip() for key in ('SECRET_KEY', 'DATABASE_URL'))
    except KeyError:
        complete = False
    if not complete:
        raise ImproperlyConfigured('.env.local must contain non-empty SECRET_KEY and DATABASE_URL values.')
    database_config(repository['DATABASE_URL'], local=True)
    return Config(repository), True
