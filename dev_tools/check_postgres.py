import os
from sqlalchemy import create_engine, inspect, text

url = os.environ.get('DATABASE_URL')
print('DATABASE_URL=' + (url or 'NOT SET'))
if not url:
    raise SystemExit('DATABASE_URL not set in this terminal')

try:
    engine = create_engine(url)
    with engine.connect() as conn:
        insp = inspect(conn)
        tables = insp.get_table_names()
        print('Tables:', tables)
        check_tables = ['audit_log','login_attempt','user','client','purchase_item','completed_client','completed_purchase_item']
        for t in check_tables:
            if t in tables:
                try:
                    c = conn.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar()
                except Exception as e:
                    c = f'error: {e}'
                print(f'{t}:', c)
        print('Done')
except Exception as e:
    print('Error connecting or inspecting DB:', e)
    raise
