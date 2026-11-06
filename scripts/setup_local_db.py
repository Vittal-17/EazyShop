"""Create ignored local credentials and a consistent SQLite backup; never overwrite."""
import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import secrets
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def private_write(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as handle:
        handle.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5433)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a non-privileged TCP port.')
    paths = [ROOT / name for name in ('.env.postgres', '.env.local', '.env.test')]
    if any(path.exists() for path in paths):
        parser.error('Local credential files already exist. Refusing to overwrite or rotate volume credentials.')

    sqlite = ROOT / 'db.sqlite3'
    if sqlite.exists():
        folder = ROOT / '.local/backups'
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = folder / ('sqlite-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
        backup.touch(mode=0o600, exist_ok=False)
        with sqlite3.connect(f'file:{sqlite}?mode=ro', uri=True) as source, sqlite3.connect(backup) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('SQLite backup integrity check failed.')
            counts = {name: target.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
                      for name in ('api_user', 'api_order', 'api_payment', 'api_giftcard')
                      if target.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()}
        print('SQLite backup:', backup)
        print('Backup SHA256:', hashlib.sha256(backup.read_bytes()).hexdigest())
        print('Preserved record counts:', counts)

    admin, dev, test = (secrets.token_urlsafe(36) for _ in range(3))
    private_write(paths[0], f'POSTGRES_USER=eazyshop_bootstrap\nPOSTGRES_PASSWORD={admin}\nPOSTGRES_DB=postgres\nEAZYSHOP_DEV_PASSWORD={dev}\nEAZYSHOP_TEST_PASSWORD={test}\nEAZYSHOP_POSTGRES_PORT={args.port}\n')
    common = ('BREVO_API_KEY=local-placeholder\nDEFAULT_FROM_EMAIL=local@example.invalid\n'
              'CLOUDINARY_URL=cloudinary://placeholder:placeholder@invalid\n'
              'RAZORPAY_KEY_ID=local-placeholder\nRAZORPAY_KEY_SECRET=local-placeholder\n'
              'RAZORPAY_WEBHOOK_SECRET=local-placeholder\nREDIS_URL=\n')
    private_write(paths[1], 'SECRET_KEY=' + secrets.token_urlsafe(64) + '\n' + common + f'DEBUG=True\nDATABASE_URL=postgresql://eazyshop_dev:{dev}@127.0.0.1:{args.port}/eazyshop_dev\n')
    private_write(paths[2], 'SECRET_KEY=' + secrets.token_urlsafe(64) + '\n' + common + f'DEBUG=False\nTEST_DATABASE_URL=postgresql://eazyshop_test:{test}@127.0.0.1:{args.port}/eazyshop_test\n')
    print(f'Created three mode-0600 ignored environment files for localhost port {args.port}. No credentials printed.')


if __name__ == '__main__':
    main()
