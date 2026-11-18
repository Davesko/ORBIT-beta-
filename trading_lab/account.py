"""One active virtual account, shared between mutually exclusive trading modes."""
import json
import re
import sqlite3
from pathlib import Path

from continuous_data import atomic_json
from copy_trading import PaperCopyLedger


def database_path(root, name):
    if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+\.sqlite', name):
        raise ValueError('Hibás portfólió-adatbázis.')
    return root / 'data' / name


def active_account(root):
    path = root / 'portfolio-account.json'
    if path.exists():
        account = json.loads(path.read_text())
        if account.get('mode') not in ('copy', 'fast_ai'): raise ValueError('Hibás kereskedési mód.')
        database_path(root, account['database'])
        return account
    legacy = root / 'paper-copy-config.json'
    if legacy.exists():
        address = json.loads(legacy.read_text()).get('address', '')
        if not re.fullmatch(r'0x[0-9a-fA-F]{40}', address): raise ValueError('Hibás követett számla.')
        return {'mode':'copy', 'leader':address, 'database':'paper-copy-' + address.lower() + '.sqlite'}
    return None


def read_book(root, account):
    if not account: return None
    path = database_path(root, account['database'])
    if not path.exists(): return None
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        return json.loads(db.execute('SELECT payload FROM book WHERE id=1').fetchone()[0])


def prepare_account(root, mode, leader=None):
    """Call only while both workers are stopped. Never duplicate starting capital."""
    previous = active_account(root)
    name = previous['database'] if previous else 'paper-portfolio.sqlite'
    path = database_path(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = PaperCopyLedger(path)
    try:
        ledger.connection.execute('BEGIN IMMEDIATE')
        book = ledger.book()
        same = previous and previous['mode'] == mode and (mode == 'fast_ai' or previous.get('leader') == leader)
        if book['positions'] and not same:
            raise ValueError('Mód- vagy kereskedőváltás előtt zárd le a meglévő virtuális pozíciókat a Portfólió oldalon.')
        if not book['positions']:
            book.update(leader=None, scope=None, currency=None, last_source_at=None)
        ledger.connection.execute('UPDATE book SET payload=? WHERE id=1', (json.dumps(book),))
        ledger.connection.execute('COMMIT')
    finally:
        if ledger.connection.in_transaction: ledger.connection.execute('ROLLBACK')
        ledger.close()
    account = {'mode':mode, 'leader':leader if mode == 'copy' else None, 'database':name}
    atomic_json(root / 'portfolio-account.json', account)
    return account
