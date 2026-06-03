from sqlalchemy import create_engine, text
import os

POSTGRES_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:123@localhost:5432/stoku')
print('Using', POSTGRES_URL)

eng = create_engine(POSTGRES_URL)
with eng.connect() as conn:
    tables = [r[0] for r in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))]
    print('tables:', tables)
    targets = ['"user"', 'client', 'purchase_item', 'department', 'material', 'audit_log', 'completed_client', 'completed_purchase_item']
    for t in targets:
        try:
            cnt = conn.execute(text(f'SELECT count(*) FROM {t}')).scalar()
            print(f'{t}: {cnt}')
        except Exception as e:
            print(f'{t}: error -', e)
