"""
Simple migration helper: copies all rows from the existing SQLite `stoku.db` into
an already-created PostgreSQL schema. Assumes the target schema/tables already
exist (e.g. after running `flask db upgrade`).

Usage:
  - Set environment variable `DATABASE_URL` to your Postgres DSN, for example
      export DATABASE_URL="postgresql://user:pass@localhost:5432/stoku"
    or on Windows PowerShell:
      $env:DATABASE_URL = "postgresql://user:pass@localhost:5432/stoku"

  - Run this script from the project root:
      python tools/migrate_sqlite_to_postgres.py

Notes:
  - This script preserves numeric primary keys (inserts explicit `id` values).
  - After running it will attempt to update Postgres sequences for `id` columns.
  - Run this only once; inspect the target DB before re-running.
"""

import os
import sys
from sqlalchemy import create_engine, MetaData, select, text, func
from sqlalchemy.exc import SQLAlchemyError

SQLITE_URL = os.getenv('SQLITE_URL', 'sqlite:///stoku.db')
POSTGRES_URL = os.getenv('DATABASE_URL')

if not POSTGRES_URL:
    print('ERROR: Please set the environment variable DATABASE_URL to your Postgres connection string.')
    print('Example (Linux/macOS): export DATABASE_URL="postgresql://user:pass@localhost:5432/stoku"')
    print('Windows (PowerShell): $env:DATABASE_URL = "postgresql://user:pass@localhost:5432/stoku"')
    sys.exit(1)

print('Source SQLite:', SQLITE_URL)
print('Destination Postgres:', POSTGRES_URL)

src_engine = create_engine(SQLITE_URL)
dst_engine = create_engine(POSTGRES_URL)

src_meta = MetaData()
dst_meta = MetaData()

print('Reflecting source (sqlite) metadata...')
src_meta.reflect(bind=src_engine)
print('Reflecting destination (postgres) metadata...')
dst_meta.reflect(bind=dst_engine)

# Try to create destination tables from the application's metadata if missing
try:
    print('Attempting to create destination tables from app metadata (if missing)...')
    # Import app's db metadata (this will import models defined in app.py)
    from app import db as app_db
    app_db.metadata.create_all(bind=dst_engine)
    # refresh reflection
    dst_meta = MetaData()
    dst_meta.reflect(bind=dst_engine)
    print('Destination tables creation attempt finished.')
except Exception as e:
    print('  Unable to auto-create destination tables from app metadata:', e)

# Copy tables in dependency order
for table in src_meta.sorted_tables:
    tname = table.name
    print(f'Processing table: {tname}')
    if tname not in dst_meta.tables:
        print(f'  WARNING: destination does not have table {tname}; skipping.')
        continue

    dst_table = dst_meta.tables[tname]

    src_conn = src_engine.connect()
    dst_conn = dst_engine.connect()
    trans = dst_conn.begin()
    try:
        rows = src_conn.execute(select(table)).mappings().all()
        if not rows:
            print('  No rows to copy.')
            trans.commit()
            continue

        # Bulk insert
        batch = [dict(r) for r in rows]
        print(f'  Inserting {len(batch)} rows...')
        dst_conn.execute(dst_table.insert(), batch)
        trans.commit()
        print('  Insert complete.')
    except SQLAlchemyError as e:
        print('  ERROR while copying:', e)
        try:
            trans.rollback()
        except Exception:
            pass
    finally:
        src_conn.close()
        dst_conn.close()

# Update sequences for Postgres (set to max(id))
print('Updating Postgres sequences for integer primary keys (if any)...')
dst_conn = dst_engine.connect()
for t in dst_meta.sorted_tables:
    # attempt to update sequence for 'id' column
    if 'id' in t.c:
        try:
            max_id = dst_conn.execute(select(func.max(t.c.id))).scalar() or 0
            seq_sql = text(f"SELECT setval(pg_get_serial_sequence('{t.name}','id'), :v, true);")
            dst_conn.execute(seq_sql, {'v': int(max_id)})
            print(f'  Sequence for {t.name} set to {max_id}')
        except Exception as e:
            # Not all tables have serial sequences or permission to set them
            print(f'  Skipping sequence update for {t.name}: {e}')

print('Migration complete. Please verify data in Postgres before removing or switching back.')
