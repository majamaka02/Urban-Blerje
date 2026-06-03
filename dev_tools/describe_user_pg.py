from sqlalchemy import create_engine, text
eng = create_engine('postgresql://postgres:123@localhost:5432/stoku')
with eng.connect() as conn:
    res = conn.execute(text("SELECT column_name, data_type, character_maximum_length FROM information_schema.columns WHERE table_name='user'"))
    for r in res:
        print(r)
