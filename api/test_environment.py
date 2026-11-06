"""Execute the actual settings module against synthetic files, without opening a DB."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from decouple import AutoConfig
from django.core.exceptions import ImproperlyConfigured


SETTINGS_SOURCE = (Path(__file__).resolve().parents[1] / 'ecommerce_platform/settings.py').read_text()
REMOTE = 'postgresql://fixture:synthetic@remote.example.invalid/shop?sslmode=require'
LOCAL = 'postgresql://eazyshop_dev:synthetic@127.0.0.1:5434/eazyshop_dev'
TEST = 'postgresql://eazyshop_test:synthetic@127.0.0.1:5434/eazyshop_test'
COMMON = {
    'SECRET_KEY': 'synthetic-configuration-only-key-not-used-for-authentication-123456789',
    'DEBUG': 'False', 'BREVO_API_KEY': 'synthetic',
    'DEFAULT_FROM_EMAIL': 'fixture@example.invalid',
    'CLOUDINARY_URL': 'cloudinary://synthetic:synthetic@invalid',
    'RAZORPAY_KEY_ID': 'synthetic', 'RAZORPAY_KEY_SECRET': 'synthetic',
    'RAZORPAY_WEBHOOK_SECRET': 'synthetic',
}


class EnvironmentSelectionTests(unittest.TestCase):
    def load(self, files=None, env=None, testing=False):
        with TemporaryDirectory(prefix='eazyshop-config-') as folder:
            root = Path(folder)
            for name, values in (files or {}).items():
                (root / name).write_text(''.join(f'{key}={value}\n' for key, value in values.items()))
            namespace = {'__file__': str(root / 'ecommerce_platform/settings.py'),
                         '__name__': 'ecommerce_platform.settings_fixture', '__package__': 'ecommerce_platform'}
            with patch.dict(os.environ, env or {}, clear=True), \
                 patch('sys.argv', ['manage.py', 'test' if testing else 'check']), \
                 patch('decouple.config', AutoConfig(search_path=str(root))), \
                 patch('psycopg2.connect', side_effect=AssertionError('Database connection forbidden')) as connect, \
                 patch('socket.socket.connect', side_effect=AssertionError('Network forbidden')):
                try:
                    exec(compile(SETTINGS_SOURCE, '<synthetic-settings>', 'exec'), namespace)
                finally:
                    connect.assert_not_called()
            return namespace

    def test_missing_local_file_never_reads_legacy_remote_env(self):
        with self.assertRaises(ImproperlyConfigured):
            self.load({'.env': {**COMMON, 'DATABASE_URL': REMOTE}})

    def test_missing_local_file_rejects_process_remote_url(self):
        with self.assertRaises(ImproperlyConfigured):
            self.load(env={**COMMON, 'DATABASE_URL': REMOTE})

    def test_valid_local_profile_isolated_and_legacy_file_ignored(self):
        result = self.load({'.env.local': {**COMMON, 'DATABASE_URL': LOCAL},
                            '.env': {**COMMON, 'DATABASE_URL': REMOTE}})
        self.assertTrue(result['LOCAL_DATABASE'])
        self.assertEqual(result['DATABASES']['default']['NAME'], 'eazyshop_dev')
        self.assertEqual(result['DATABASES']['default']['USER'], 'eazyshop_dev')
        self.assertEqual(result['DATABASES']['default']['HOST'], '127.0.0.1')

    def test_incomplete_local_file_cannot_be_hidden_by_process_configuration(self):
        for profile in ({}, {'SECRET_KEY': COMMON['SECRET_KEY']}, {'DATABASE_URL': LOCAL},
                        {'SECRET_KEY': '', 'DATABASE_URL': LOCAL}):
            with self.subTest(keys=list(profile)), self.assertRaises(ImproperlyConfigured):
                self.load({'.env.local': profile}, env={**COMMON, 'DATABASE_URL': LOCAL})

    def test_invalid_local_database_and_remote_process_override_rejected(self):
        for url in (REMOTE, TEST, 'sqlite:///db.sqlite3', '',
                    'postgresql://eazyshop_dev:synthetic@127.0.0.1:5434/unrelated'):
            with self.subTest(url=url), self.assertRaises(ImproperlyConfigured):
                self.load({'.env.local': {**COMMON, 'DATABASE_URL': url}})
        with self.assertRaises(ImproperlyConfigured):
            self.load({'.env.local': {**COMMON, 'DATABASE_URL': LOCAL}}, env={'DATABASE_URL': REMOTE})

    def test_file_selector_alone_is_not_a_production_opt_in(self):
        for files in ({'.env': {**COMMON, 'DATABASE_URL': REMOTE}},
                      {'.env.local': {**COMMON, 'DATABASE_URL': LOCAL}, '.env': {**COMMON, 'DATABASE_URL': REMOTE}}):
            with self.subTest(local_exists='.env.local' in files), self.assertRaises(ImproperlyConfigured):
                self.load(files, env={'EAZYSHOP_ENV_FILE': '.env'})

    def test_explicit_production_environment_preserves_neon_ssl(self):
        result = self.load({'.env.local': {**COMMON, 'DATABASE_URL': LOCAL}},
                          env={**COMMON, 'EAZYSHOP_RUNTIME': 'production', 'DATABASE_URL': REMOTE})
        db = result['DATABASES']['default']
        self.assertFalse(result['LOCAL_DATABASE'])
        self.assertEqual(db['HOST'], 'remote.example.invalid')
        self.assertEqual(db['OPTIONS']['sslmode'], 'require')
        self.assertEqual(db['ENGINE'], 'django.db.backends.postgresql')

    def test_explicit_production_file_and_environment_precedence(self):
        file_only = self.load({'.env': {**COMMON, 'DATABASE_URL': REMOTE}}, env={
            'EAZYSHOP_RUNTIME': 'production', 'EAZYSHOP_ENV_FILE': '.env',
        })
        self.assertEqual(file_only['DATABASES']['default']['OPTIONS']['sslmode'], 'require')
        result = self.load({'.env': {**COMMON, 'DATABASE_URL': LOCAL}}, env={
            'EAZYSHOP_RUNTIME': 'production', 'EAZYSHOP_ENV_FILE': '.env', 'DATABASE_URL': REMOTE,
        })
        self.assertEqual(result['DATABASES']['default']['HOST'], 'remote.example.invalid')
        with self.assertRaises(ImproperlyConfigured):
            self.load(env={'EAZYSHOP_RUNTIME': 'production', 'EAZYSHOP_ENV_FILE': 'missing.env'})

    def test_test_mode_ignores_production_selectors_and_database_url(self):
        result = self.load({'.env.test': {**COMMON, 'TEST_DATABASE_URL': TEST},
                            '.env': {**COMMON, 'DATABASE_URL': REMOTE}}, env={
            'EAZYSHOP_RUNTIME': 'production', 'EAZYSHOP_ENV_FILE': '.env', 'DATABASE_URL': REMOTE,
        }, testing=True)
        db = result['DATABASES']['default']
        self.assertEqual(db['USER'], 'eazyshop_test')
        self.assertEqual(db['NAME'], 'eazyshop_test')
        self.assertEqual(db['TEST']['NAME'], 'eazyshop_test')
        with self.assertRaises(ImproperlyConfigured):
            self.load({'.env.test': {**COMMON, 'TEST_DATABASE_URL': TEST}},
                      env={'TEST_DATABASE_URL': REMOTE}, testing=True)

    def test_test_mode_preserves_environment_only_ci_configuration(self):
        result = self.load(env={**COMMON, 'TEST_DATABASE_URL': TEST,
                               'EAZYSHOP_RUNTIME': 'production', 'DATABASE_URL': REMOTE}, testing=True)
        self.assertEqual(result['DATABASES']['default']['NAME'], 'eazyshop_test')

    def test_local_integration_values_preserved_with_explicit_process_overrides(self):
        profile = {**COMMON, 'DATABASE_URL': LOCAL, 'RAZORPAY_KEY_ID': 'rzp_test_synthetic',
                   'CORS_ALLOWED_ORIGINS': 'https://sandbox.example.invalid',
                   'CSRF_TRUSTED_ORIGINS': 'https://sandbox.example.invalid'}
        result = self.load({'.env.local': profile}, env={'RAZORPAY_KEY_SECRET': 'synthetic-process-override'})
        self.assertEqual(result['RAZORPAY_KEY_ID'], 'rzp_test_synthetic')
        self.assertEqual(result['RAZORPAY_KEY_SECRET'], 'synthetic-process-override')
        self.assertEqual(result['CORS_ALLOWED_ORIGINS'], ['https://sandbox.example.invalid'])
        self.assertEqual(result['CSRF_TRUSTED_ORIGINS'], ['https://sandbox.example.invalid'])

    def test_invalid_runtime_fails_closed(self):
        with self.assertRaises(ImproperlyConfigured):
            self.load({'.env.local': {**COMMON, 'DATABASE_URL': LOCAL}}, env={'EAZYSHOP_RUNTIME': 'prodution'})

    def test_production_environment_only_does_not_discover_legacy_file(self):
        with self.assertRaises(ImproperlyConfigured):
            self.load({'.env': {**COMMON, 'DATABASE_URL': REMOTE}},
                      env={**COMMON, 'EAZYSHOP_RUNTIME': 'production'})
