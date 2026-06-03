from sqlalchemy import create_engine, text
eng = create_engine('postgresql://postgres:123@localhost:5432/stoku')
with eng.connect() as conn:
    try:
        conn.execute(text('ALTER TABLE public."user" ALTER COLUMN password_hash TYPE text USING password_hash::text;'))
        print('altered2')
    except Exception as e:
        print('alter2 error', e)
