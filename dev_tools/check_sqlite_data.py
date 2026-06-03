from sqlalchemy import create_engine, text

e = create_engine('sqlite:///stoku.db')
with e.connect() as conn:
    tables = [r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))]
    print('sqlite tables:', tables)
    targets = ['user','client','purchase_item','department','material','audit_log','completed_client','completed_purchase_item']
    for t in targets:
        try:
            cnt = conn.execute(text(f'SELECT count(*) FROM {t}')).scalar()
            print(f'{t}: {cnt}')
        except Exception as e:
            print(f'{t}: error -', e)
