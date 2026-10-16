"""Small SQLite read-only capability. Never expose a generator connection."""
from pathlib import Path
import sqlite3


class QueryError(ValueError):
    pass


def query(path, sql, *, max_rows=100, max_steps=100000):
    if not isinstance(sql, str) or len(sql) > 10000 or max_rows < 1 or max_steps < 1:
        raise QueryError('invalid_query')
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
               sqlite3.SQLITE_RECURSIVE}
    def authorize(action, arg1, arg2, database, trigger):
        if action == sqlite3.SQLITE_READ and arg1 != 'orders':
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or '').lower() not in {
            'count', 'sum', 'min', 'max', 'avg', 'coalesce', 'abs', 'round'}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
    try:
        db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
        try:
            db.execute('PRAGMA query_only=ON')
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 100000)
            db.set_authorizer(authorize)
            remaining = max_steps
            def progress():
                nonlocal remaining
                remaining -= 100
                return int(remaining <= 0)
            db.set_progress_handler(progress, 100)
            cursor = db.execute(sql)
            rows = cursor.fetchmany(max_rows + 1)
            if len(rows) > max_rows:
                raise QueryError('row_limit')
            return {'columns': [c[0] for c in cursor.description], 'rows': [list(r) for r in rows]}
        finally:
            db.close()
    except sqlite3.Error:
        raise QueryError('query_rejected_or_budget_exceeded') from None
