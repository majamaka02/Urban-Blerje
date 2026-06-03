import sqlite3
from pathlib import Path
p = Path('instance/stoku.db')
print('path', p.absolute())
if not p.exists():
    print('file missing')
else:
    conn = sqlite3.connect(str(p))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    rows = cur.fetchall()
    print('tables:', rows)
    for name, in rows:
        try:
            cur.execute(f"SELECT count(*) FROM {name}")
            print(name, cur.fetchone()[0])
        except Exception as e:
            print(name, 'error', e)
    conn.close()
