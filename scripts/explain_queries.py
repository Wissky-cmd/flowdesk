"""Read-only query plans on real development data; not a throughput benchmark."""
import json
from pathlib import Path
import uuid

from dotenv import dotenv_values
import psycopg

root = Path(__file__).resolve().parents[1]
dsn = dotenv_values(root / '.env')['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://', 1)
wid = uuid.uuid5(uuid.NAMESPACE_URL, 'https://flowdesk.example/seed/product')
with psycopg.connect(dsn) as db:
    db.execute('SET TRANSACTION READ ONLY')
    count = db.execute('SELECT count(*) FROM tickets WHERE workspace_id=%s', (wid,)).fetchone()[0]
    plans = {}
    for name, query in {
        'workspace_updated_page': 'SELECT id,title,status,priority FROM tickets WHERE workspace_id=%s ORDER BY updated_at DESC,id DESC LIMIT 20',
        'status_filter': "SELECT id,title FROM tickets WHERE workspace_id=%s AND status='new' ORDER BY updated_at DESC,id DESC LIMIT 20",
        'status_priority_summary': 'SELECT status,priority,count(*) FROM tickets WHERE workspace_id=%s GROUP BY status,priority',
    }.items():
        plans[name] = db.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + query, (wid,)).fetchone()[0]
report = {'workspace_ticket_count':count, 'limitation':'Small real development dataset, plans only; no throughput or capacity claim.', 'plans':plans}
(root / 'docs/evidence/query-plans.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(f'Saved 3 real PostgreSQL plans; {count} visible workspace tickets. Not a performance benchmark.')
