"""PostgreSQL-only configuration with a fail-closed local/test boundary."""
from urllib.parse import urlsplit

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


def database_config(url, *, local=False, testing=False):
    message = 'Set TEST_DATABASE_URL in .env.test.' if testing else 'Set DATABASE_URL to PostgreSQL; see docs/local-postgresql.md.'
    if not url:
        raise ImproperlyConfigured(message)
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ('postgres', 'postgresql'):
            raise ValueError
        result = dj_database_url.parse(url, conn_max_age=0 if testing else 600, conn_health_checks=True)
        if local or testing:
            identity = 'eazyshop_test' if testing else 'eazyshop_dev'
            if (parsed.hostname not in ('127.0.0.1', '::1') or parsed.query or parsed.fragment
                    or result['NAME'] != identity or result['USER'] != identity
                    or not result['PASSWORD'] or not parsed.port or parsed.port < 1024):
                raise ValueError
        result.setdefault('OPTIONS', {}).setdefault('connect_timeout', 5)
        if testing:
            result['TEST'] = {'NAME': 'eazyshop_test'}
        return result
    except (ValueError, TypeError, KeyError):
        # Parsing exceptions may contain credentials. Do not echo the URL.
        raise ImproperlyConfigured('Invalid or unsafe PostgreSQL configuration. ' + message) from None
