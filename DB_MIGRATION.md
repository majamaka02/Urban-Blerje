Migration to PostgreSQL
=========================

This project now includes Flask-Migrate and a helper script to copy data from the
existing SQLite DB (`stoku.db`) into a PostgreSQL database.

High-level steps
-----------------
1. Install new dependencies in your virtualenv:

```bash
pip install -r requirements.txt
```

2. Create a PostgreSQL database and user (on your Postgres server).
   Example (Postgres shell):

```sql
CREATE DATABASE stoku;
CREATE USER stoku_user WITH PASSWORD 'strongpassword';
GRANT ALL PRIVILEGES ON DATABASE stoku TO stoku_user;
```

3. Point the app to Postgres by setting `DATABASE_URL`.

- Linux/macOS:

```bash
export DATABASE_URL="postgresql://stoku_user:strongpassword@localhost:5432/stoku"
export FLASK_APP=app.py
```

- Windows PowerShell:

```powershell
$env:DATABASE_URL = "postgresql://stoku_user:strongpassword@localhost:5432/stoku"
$env:FLASK_APP = "app.py"
```

4. Initialize migrations and create the schema in Postgres (this creates the
   `migrations/` folder and applies the initial schema):

```bash
flask db init
flask db migrate -m "Initial models"
flask db upgrade
```

5. Copy existing data from SQLite into Postgres:

```bash
python tools/migrate_sqlite_to_postgres.py
```

6. Verify data in Postgres. If everything looks good, update deployment to set
   `DATABASE_URL` to the Postgres DSN and restart the app.

Notes & Tips
------------
- If you prefer a one-off data move utility, consider `pgloader` which can
  directly migrate from SQLite to Postgres.
- After migration, consider adding indexes on `AuditLog.user` and
  `AuditLog.timestamp` to improve filter performance.
- Do NOT commit your `DATABASE_URL` or `.env` with credentials into version
  control. Use env vars or a secure secret manager.

If you want, I can:
- run `pip install -r requirements.txt` now and create the `migrations/` folder (I will not run migrations until you provide `DATABASE_URL`),
- or wait until you provide Postgres credentials and then run the full migration (create schema + copy data + set sequences).

Tell me which option you prefer.