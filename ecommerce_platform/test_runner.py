"""Use only the pre-created local test DB; never create/drop databases or call providers."""
from contextlib import ExitStack
import socket
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import connections
from django.test.runner import DiscoverRunner


class IsolatedPostgresRunner(DiscoverRunner):
    def __init__(self, *args, **kwargs):
        kwargs['keepdb'] = True
        super().__init__(*args, **kwargs)
        if self.parallel not in (0, 1):
            raise ImproperlyConfigured('Use one test process; dedicated concurrency tests create independent connections.')

    def setup_databases(self, **kwargs):
        old_config = super().setup_databases(**kwargs)
        # The advisory lock and identity checks already protect this dedicated DB.
        # Remove leftovers from an interrupted previous run before fixtures load.
        call_command('flush', verbosity=0, interactive=False, database='default')
        return old_config

    def run_tests(self, test_labels, **kwargs):
        db = settings.DATABASES['default']
        # Validate the parsed settings again so alternative settings cannot redirect tests.
        if (db['ENGINE'] != 'django.db.backends.postgresql' or db['NAME'] != 'eazyshop_test'
                or db['USER'] != 'eazyshop_test' or db['HOST'] not in ('127.0.0.1', '::1')
                or db.get('TEST', {}).get('NAME') != 'eazyshop_test'):
            raise ImproperlyConfigured('Test execution requires the isolated local eazyshop_test database and login.')
        guard = connections['default'].copy(alias='test_guard')
        try:
            with guard.cursor() as cursor:
                cursor.execute('SELECT pg_try_advisory_lock(47004)')
                if not cursor.fetchone()[0]:
                    raise RuntimeError('Another EazyShop test run holds this database. Wait for it to finish.')
                cursor.execute('SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user')
                if any(cursor.fetchone()):
                    raise RuntimeError('Test login has excessive privileges.')
            original_connect = socket.socket.connect
            original_dns = socket.getaddrinfo
            original_connect_ex = socket.socket.connect_ex

            def connect(sock, address):
                if not (isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1') and int(address[1]) == int(db['PORT'])):
                    raise RuntimeError('External network disabled during tests. Mock provider calls.')
                return original_connect(sock, address)

            def connect_ex(sock, address):
                if not (isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1') and int(address[1]) == int(db['PORT'])):
                    raise RuntimeError('External network disabled during tests. Mock provider calls.')
                return original_connect_ex(sock, address)

            def resolve(host, *args, **kwargs):
                if host not in ('localhost', '127.0.0.1', '::1'):
                    raise RuntimeError('External DNS disabled during tests. Mock provider calls.')
                return original_dns(host, *args, **kwargs)

            with ExitStack() as stack:
                stack.enter_context(patch.object(socket.socket, 'connect', connect))
                stack.enter_context(patch.object(socket.socket, 'connect_ex', connect_ex))
                stack.enter_context(patch.object(socket, 'getaddrinfo', resolve))
                return super().run_tests(test_labels, **kwargs)
        finally:
            guard.close()  # releases the run-wide advisory lock
