import os
from dotenv import load_dotenv
import psycopg2

load_dotenv(override=True)
PGDB = os.getenv('PGDATABASE')
PGUSER = os.getenv('PGUSER')
PGPASSWORD = os.getenv('PGPASSWORD')
PGHOST = os.getenv('PGHOST')
PGPORT = os.getenv('PGPORT')
print('Attempting connect with:', PGUSER, '@', PGHOST, PGPORT, 'db:', PGDB)
try:
    conn = psycopg2.connect(dbname=PGDB, user=PGUSER, password=PGPASSWORD, host=PGHOST, port=PGPORT)
    print('Connected OK')
    conn.close()
except Exception as e:
    print('Connection failed:', type(e).__name__, e)
