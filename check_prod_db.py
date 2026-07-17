"""Check Production database state using sync engine."""
import sys
sys.path.insert(0, 'backend')

from urllib.parse import parse_qsl, urlsplit, urlunsplit
from sqlalchemy import create_engine, text
from backend.app.config import settings

# Convert async URL to sync URL
db_url = settings.database_url
if '+asyncpg' in db_url:
    db_url = db_url.replace('+asyncpg', '+psycopg2')

# Remove sslmode and channel_binding from query, pass as connect_args
parsed = urlsplit(db_url)
query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
connect_args = {}
filtered = []
for k, v in query_pairs:
    if k == 'sslmode':
        if v.lower() != 'disable':
            connect_args['sslmode'] = v
    elif k == 'channel_binding':
        pass
    else:
        filtered.append((k, v))

from urllib.parse import urlencode
db_url = urlunsplit((
    parsed.scheme, parsed.netloc, parsed.path,
    urlencode(filtered, doseq=True),
    parsed.fragment
))

print(f'Connecting to: {db_url[:80]}...')
print(f'SSL args: {connect_args}')

engine = create_engine(db_url, connect_args=connect_args)

with engine.connect() as conn:
    # Check alembic_version
    try:
        result = conn.execute(text('SELECT * FROM alembic_version'))
        rows = result.fetchall()
        print('\n=== alembic_version ===')
        for row in rows:
            print(f'  {row}')
    except Exception as e:
        print(f'alembic_version error: {e}')
    
    # Check broker_tokens table columns
    result = conn.execute(text("""
        SELECT column_name, data_type, is_nullable, character_maximum_length
        FROM information_schema.columns
        WHERE table_name = 'broker_tokens'
        ORDER BY ordinal_position
    """))
    rows = result.fetchall()
    print('\n=== broker_tokens columns ===')
    for row in rows:
        print(f'  {row[0]:30s} {str(row[1]):20s} nullable={row[2]}')
    
    # Check broker_tokens count
    result = conn.execute(text('SELECT COUNT(*) FROM broker_tokens'))
    print('\nbroker_tokens count:', result.scalar())
    
    # Check users
    result = conn.execute(text('SELECT COUNT(*) FROM users'))
    print('users count:', result.scalar())
    
    # Check broker_tokens data
    result = conn.execute(text('SELECT id, user_id, broker, status, is_active, created_at FROM broker_tokens LIMIT 10'))
    rows = result.fetchall()
    if rows:
        print('\n=== broker_tokens sample data ===')
        for row in rows:
            print(f'  id={row[0]} user_id={row[1]} broker={row[2]} status={row[3]} is_active={row[4]} created_at={row[5]}')
    else:
        print('\nNo broker_tokens rows found')
    
    # Current revision(s)
    result = conn.execute(text('SELECT version_num FROM alembic_version'))
    current = set(r[0] for r in result.fetchall())
    print('\nCurrent revision(s):', current)

engine.dispose()
print('\nDone.')
