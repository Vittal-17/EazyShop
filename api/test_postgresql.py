from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
import uuid

from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from django.test import SimpleTestCase, TransactionTestCase
from rest_framework.test import APIClient

from ecommerce_platform.database import database_config
from .models import Order, Product, User


class DatabaseConfigurationTests(SimpleTestCase):
    def test_sqlite_missing_and_remote_test_configuration_rejected(self):
        for url in ('', 'sqlite:///db.sqlite3',
                    'postgresql://eazyshop_test:fixture@production.invalid:5434/eazyshop_test',
                    'postgresql://eazyshop_dev:fixture@127.0.0.1:5434/eazyshop_dev',
                    'postgresql://eazyshop_test:fixture@127.0.0.1:5434/eazyshop_test?host=production.invalid'):
            with self.subTest(url=url), self.assertRaises(ImproperlyConfigured):
                database_config(url, testing=True)

    def test_local_test_identity_and_production_ssl_options_preserved(self):
        local = database_config('postgresql://eazyshop_test:fixture@127.0.0.1:5434/eazyshop_test', testing=True)
        self.assertEqual(local['TEST']['NAME'], 'eazyshop_test')
        self.assertEqual(local['CONN_MAX_AGE'], 0)
        production = database_config('postgresql://example:fixture@db.example.invalid/shop?sslmode=require')
        self.assertEqual(production['OPTIONS']['sslmode'], 'require')
        self.assertEqual(production['ENGINE'], 'django.db.backends.postgresql')


class PostgresStockConcurrencyTests(TransactionTestCase):
    """Real commits and independent buyer connections; providers are always mocked."""
    def _run_concurrent_stock_test(self, stock, qty, count):
        self.assertEqual(connections['default'].vendor, 'postgresql')
        seller = User.objects.create_user('seller', 'seller@example.invalid', role='seller')
        product = Product.objects.create(name='Scarce fixture', price=100, stock=stock,
                                         approval_status='approved', is_active=True, vendor=seller)
        buyers = User.objects.bulk_create([
            User(username=f'buyer{i}', email=f'buyer{i}@example.invalid') for i in range(count)
        ])
        workers = min(count, 20)
        barrier = Barrier(workers, timeout=15)

        def place_order(buyer):
            connections.close_all()
            try:
                with connections['default'].cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    backend_pid = cursor.fetchone()[0]
                client = APIClient()
                client.force_authenticate(buyer)
                barrier.wait()
                response = client.post('/api/orders/create-razorpay-order/', {
                    'shipping_address': 'Fixture', 'contact_phone': '1234',
                    'order_items': [{'product': product.pk, 'quantity': qty}],
                }, format='json')
                return response.status_code, backend_pid
            finally:
                connections.close_all()

        with patch('api.views.razorpay.Client') as gateway, patch('api.views.async_notify_vendors'):
            gateway.return_value.order.create.side_effect = lambda data, **kwargs: {
                'id': 'order_' + uuid.uuid4().hex, 'amount': data['amount'], 'currency': 'INR',
            }
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(place_order, buyers))
        codes = [code for code, _ in results]
        self.assertEqual(codes.count(201), 1)
        self.assertEqual(codes.count(400), count - 1, codes)
        self.assertGreaterEqual(len({pid for _, pid in results}), workers)
        product.refresh_from_db()
        self.assertEqual(product.stock, 0)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.get().order_items.get().quantity, qty)
        self.assertEqual(gateway.return_value.order.create.call_count, 1)

    def test_fin09_concurrent_rollback(self):
        """Two independent buyers contend for two units; one qty=2 order succeeds."""
        self._run_concurrent_stock_test(stock=2, qty=2, count=2)

    def test_fin09_stock_starvation(self):
        """100 buyers in 20 concurrent workers contend for the last unit."""
        self._run_concurrent_stock_test(stock=1, qty=1, count=100)
