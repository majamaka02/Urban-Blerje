"""Safer migration helper: copies rows from SQLite to Postgres with per-table commits
and per-row fallback inserts to avoid aborting the whole migration on single errors.

Usage: set DATABASE_URL and run this script from project root.
"""
import os
import sys
from sqlalchemy import create_engine, MetaData, select, text, func
from sqlalchemy.exc import SQLAlchemyError

SQLITE_URL = os.getenv('SQLITE_URL', 'sqlite:///stoku.db')
POSTGRES_URL = os.getenv('DATABASE_URL')

if not POSTGRES_URL:
    print('ERROR: set DATABASE_URL to your Postgres DSN')
    sys.exit(1)

print('Source SQLite:', SQLITE_URL)
print('Destination Postgres:', POSTGRES_URL)

src_engine = create_engine(SQLITE_URL)
dst_engine = create_engine(POSTGRES_URL)

src_meta = MetaData(); src_meta.reflect(bind=src_engine)
dst_meta = MetaData(); dst_meta.reflect(bind=dst_engine)

print('Source tables:', [t.name for t in src_meta.sorted_tables])
print('Destination tables:', list(dst_meta.tables.keys()))

for table in src_meta.sorted_tables:
    tname = table.name
    print(f'Processing table: {tname}')
    if tname not in dst_meta.tables:
        print(f'  WARNING: destination does not have table {tname}; skipping.')
        continue

    dst_table = dst_meta.tables[tname]

    # Read source rows
    try:
        with src_engine.connect() as src_conn:
            rows = src_conn.execute(select(table)).mappings().all()
    except Exception as e:
        print('  ERROR reading source table:', e)
        continue

    if not rows:
        print('  No rows to copy.')
        continue

    batch = [dict(r) for r in rows]
    print(f'  Rows to insert: {len(batch)}')

    # Try bulk insert inside a fresh transaction
    try:
        with dst_engine.begin() as dst_conn:
            dst_conn.execute(dst_table.insert(), batch)
        print('  Bulk insert successful')
    except SQLAlchemyError as e:
        print('  Bulk insert failed:', e)
        print('  Falling back to per-row inserts...')
        # Per-row inserts with individual transactions
        inserted = 0
        for row in batch:
            try:
                with dst_engine.begin() as dst_conn:
                    dst_conn.execute(dst_table.insert(), row)
                inserted += 1
            except Exception as re:
                print('   Row insert failed, skipping row:', re)
        print(f'  Per-row inserts done, inserted {inserted}/{len(batch)}')

# Update sequences
print('Updating Postgres sequences...')
with dst_engine.connect() as conn:
    for t in dst_meta.sorted_tables:
        if 'id' in t.c:
            try:
                max_id = conn.execute(select(func.max(t.c.id))).scalar() or 0
                seq_sql = text(f"SELECT setval(pg_get_serial_sequence('{t.name}','id'), :v, true);")
                conn.execute(seq_sql, {'v': int(max_id)})
                print(f'  Sequence for {t.name} set to {max_id}')
            except Exception as e:
                print(f'  Skipping sequence update for {t.name}:', e)

print('Safe migration complete. Verify data in Postgres.')
