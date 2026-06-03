from sqlalchemy import create_engine, text
eng = create_engine('postgresql://postgres:123@localhost:5432/stoku')
with eng.begin() as conn:
    try:
        conn.execute(text('ALTER TABLE public."user" ALTER COLUMN password_hash TYPE text USING password_hash::text;'))
        print('altered with begin commit')
    except Exception as e:
        print('alter error', e)
