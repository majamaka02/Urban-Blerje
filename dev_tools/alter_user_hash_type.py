from sqlalchemy import create_engine, text
eng = create_engine('postgresql://postgres:123@localhost:5432/stoku')
with eng.connect() as conn:
    try:
        conn.execute(text('ALTER TABLE "user" ALTER COLUMN password_hash TYPE TEXT;'))
        print('altered')
    except Exception as e:
        print('alter error', e)
