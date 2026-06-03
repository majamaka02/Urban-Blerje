from sqlalchemy import create_engine, text
import os

POSTGRES_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:123@localhost:5432/stoku')
eng = create_engine(POSTGRES_URL)

tables = ['user','client','purchase_item','department','material','audit_log','completed_client','completed_purchase_item','login_attempt']
with eng.begin() as conn:
    for t in tables:
        qname = f'"{t}"' if t == 'user' else t
        try:
            res = conn.execute(text(f"SELECT max(id) FROM {qname}"))
            m = res.scalar() or 0
            if m > 0:
                conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{qname.replace('"','')}', 'id'), :v, true)"), {'v': m})
                print(f"Sequence for {t} set to {m}")
            else:
                print(f"Sequence for {t} skipped (max=0)")
        except Exception as e:
            print(f"Skipping sequence update for {t}: {e}")
