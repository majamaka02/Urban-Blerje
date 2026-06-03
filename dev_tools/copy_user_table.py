from sqlalchemy import create_engine, text, MetaData, Table, select
import os

SQLITE_URL = os.getenv('SQLITE_URL', 'sqlite:///instance/stoku.db')
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:123@localhost:5432/stoku')
print('Source', SQLITE_URL)
print('Dest', DATABASE_URL)

s_eng = create_engine(SQLITE_URL)
d_eng = create_engine(DATABASE_URL)

s_meta = MetaData()
s_meta.reflect(bind=s_eng)

if 'user' not in s_meta.tables:
    print('no user table in source')
    raise SystemExit(1)

users = Table('user', s_meta)
with s_eng.connect() as s_conn:
    rows = s_conn.execute(select(users)).mappings().all()
print('rows to insert:', len(rows))

with d_eng.connect() as conn:
    inserted = 0
    with conn.begin():
        for r in rows:
            data = dict(r)
            try:
                conn.execute(text('INSERT INTO "user" (id, username, password_hash, is_admin, is_super) VALUES (:id, :username, :password_hash, :is_admin, :is_super)'), data)
                inserted += 1
            except Exception as e:
                print('Row insert failed, skipping row:', e)
    print('Inserted', inserted, '/', len(rows))
