import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import text

from app import tickets
from app.models import TicketEvent
from app.seed import seed_id
from test_phase_one import BASE, OTHER, PAYLOAD, TICKET, WID

PATH = BASE + '/tickets/' + TICKET


def editable(client, path=PATH, **changes):
    current = client.get(path).json()
    return {**{key: current[key] for key in ('title', 'body', 'priority', 'assignee_id', 'version')}, **changes}


def test_full_filters_sort_and_summary(login):
    client = login()
    for i in range(24):
        assert client.post(BASE + '/tickets', json={**PAYLOAD, 'title': f'needle {i:02}', 'priority': 'high', 'assignee_id': str(seed_id('agent'))}).status_code == 201
    result = client.get(BASE + '/tickets?q=needle&priority=high&status=new&page_size=3&page=8').json()
    assert result['total'] == 24 and len(result['items']) == 3
    assert client.get(BASE + '/tickets?q=needle%2000').json()['total'] == 1
    assert client.get(BASE + '/tickets?q=%25').json()['total'] == 0
    assert client.get(BASE + '/tickets?unassigned=true&q=needle').json()['total'] == 0
    assert client.get(BASE + '/tickets?assignee_id=' + str(seed_id('agent'))).json()['total'] >= 24
    assert client.get(BASE + '/tickets?created_from=2099-01-01T00:00:00Z').json()['total'] == 0
    assert client.get(BASE + '/tickets?created_to=2000-01-01T00:00:00Z').json()['total'] == 0
    assert client.get(BASE + '/tickets?created_from=2099-01-01T00:00:00Z&created_to=2000-01-01T00:00:00Z').status_code == 422
    assert client.get(BASE + '/tickets?status=invalid').status_code == 422
    newest = client.get(BASE + '/tickets?q=needle&sort=newest').json()['items'][0]
    oldest = client.get(BASE + '/tickets?q=needle&sort=oldest').json()['items'][0]
    assert newest['title'] == 'needle 23' and oldest['title'] == 'needle 00'
    stats = client.get(BASE + '/tickets/summary').json()
    assert stats['total'] == 26 and stats['priorities']['high'] >= 24
    client = login('alice')
    assert client.get(BASE + '/tickets/summary').json()['total'] == 1


def test_workflow_roles_reasons_and_audit(login):
    client = login('agent')
    current = client.get(PATH).json()
    assert client.post(PATH + '/transitions', json={'version': current['version'], 'status': 'closed'}).status_code == 403
    result = client.put(PATH, json=editable(client, assignee_id=str(seed_id('agent'))))
    assert result.status_code == 200, result.text
    version = result.json()['version']
    for status in ['accepted', 'in_progress', 'review']:
        result = client.post(PATH + '/transitions', json={'version': version, 'status': status})
        assert result.status_code == 200, result.text
        version += 1
        assert result.json()['version'] == version
    assert client.post(PATH + '/transitions', json={'version': version, 'status': 'closed'}).status_code == 403
    client = login('alice')
    assert client.get(PATH + '/actions').json()['transitions'] == ['closed', 'in_progress']
    assert client.post(PATH + '/transitions', json={'version': version, 'status': 'in_progress'}).status_code == 422
    assert client.post(PATH + '/transitions', json={'version': version, 'status': 'closed'}).status_code == 200
    assert client.post(PATH + '/transitions', json={'version': version + 1, 'status': 'in_progress', 'reason': '仍可复现'}).status_code == 200
    events = client.get(PATH + '/activity').json()['items']
    assert len(events) == 6
    assert events[0]['detail']['reason'] == '仍可复现'
    assert events[0]['detail']['before']['status'] == 'closed'
    assert events[0]['detail']['after']['version'] == version + 2


def test_requester_edit_cancel_and_assignment_rules(login):
    client = login('alice')
    assert client.put(PATH, json=editable(client, title='修改自己的请求')).status_code == 200
    assert client.put(PATH, json=editable(client, priority='urgent')).status_code == 403
    assert client.put(PATH, json=editable(client, assignee_id=str(seed_id('agent')))).status_code == 403
    version = client.get(PATH).json()['version']
    assert client.post(PATH + '/transitions', json={'version': version, 'status': 'cancelled', 'reason': '不再需要'}).status_code == 200
    assert client.put(PATH, json=editable(client, title='不应保存')).status_code == 403
    assert client.get(PATH + '/actions').json() == {'transitions': [], 'can_edit': False}
    client = login()
    created = client.post(BASE + '/tickets', json=PAYLOAD).json()
    assert client.post(BASE + '/tickets/' + created['id'] + '/transitions', json={'version': 1, 'status': 'accepted'}).status_code == 422


@pytest.mark.parametrize('person', ['bob', 'other'])
def test_all_new_endpoints_respect_visibility(login, person):
    client = login('alice')
    uploaded = client.post(PATH + '/attachments?filename=notes.txt', content=b'private').json()['id']
    client = login(person)
    for suffix in ['/actions', '/activity', '/attachments', '/attachments/' + uploaded]:
        assert client.get(PATH + suffix).status_code == 404
    assert client.put(PATH, json={**PAYLOAD, 'version': 1}).status_code == 404
    assert client.post(PATH + '/transitions', json={'version': 1, 'status': 'accepted'}).status_code == 404
    assert client.post(PATH + '/comments', json={'body': 'forged'}).status_code == 404
    assert client.post(PATH + '/attachments?filename=notes.txt', content=b'forged').status_code == 404
    if person == 'other':
        assert client.get(BASE + '/tickets/summary').status_code == 404
    assert client.get(f'/api/v1/workspaces/{OTHER}/tickets/{TICKET}/attachments/{uploaded}').status_code == 404


def test_comment_pagination_and_attachment_roundtrip(login):
    client = login('alice')
    for i in range(32):
        assert client.post(PATH + '/comments', json={'body': f'进展 {i}'}).status_code == 201
    assert client.post(PATH + '/comments', json={'body': '  '}).status_code == 422
    first = client.get(PATH + '/activity').json()
    second = client.get(PATH + '/activity?page=2').json()
    assert first['total'] == 32 and len(first['items']) == 30 and len(second['items']) == 2
    assert not {e['id'] for e in first['items']} & {e['id'] for e in second['items']}
    body = '验收说明'.encode()
    result = client.post(PATH + '/attachments', params={'filename': '说明.txt'}, content=body)
    assert result.status_code == 201, result.text
    download = client.get(PATH + '/attachments/' + result.json()['id'])
    assert download.content == body and 'attachment;' in download.headers['content-disposition']
    assert download.headers['x-content-type-options'] == 'nosniff'
    assert download.headers['content-type'] == 'application/octet-stream'
    assert client.get(PATH + '/attachments').json()[0]['filename'] == '说明.txt'


@pytest.mark.parametrize('filename,body,code', [('../secret.txt', b'x', 422), ('evil.html', b'<script>', 422), ('fake.png', b'not image', 422), ('empty.txt', b'', 422), ('invalid.txt', b'\xff', 422), ('null.txt', b'x\x00', 422), ('huge.txt', b'x' * 5242881, 413)], ids=['path', 'html', 'signature', 'empty', 'encoding', 'null-byte', 'size'])
def test_attachment_validation(login, filename, body, code):
    client = login()
    response = client.post(PATH + '/attachments', params={'filename': filename}, content=body)
    assert response.status_code == code, response.text
    assert client.get(PATH + '/attachments').json() == []


def test_attachment_quota(login):
    client = login()
    for i in range(10):
        assert client.post(PATH + '/attachments?filename=a.txt', content=b'x').status_code == 201
    assert client.post(PATH + '/attachments?filename=a.txt', content=b'x').status_code == 422


def test_concurrent_update_only_one_wins_in_distinct_transactions(login, monkeypatch, sql):
    client = login()
    payload = editable(client)
    original = tickets.save_change
    pids = []
    gate = None
    async def synchronized(db, *args, **kwargs):
        nonlocal gate
        if gate is None:
            gate = asyncio.Event()
        pids.append(await db.scalar(text('SELECT pg_backend_pid()')))
        if len(pids) == 2:
            gate.set()
        await asyncio.wait_for(gate.wait(), 5)
        return await original(db, *args, **kwargs)
    monkeypatch.setattr(tickets, 'save_change', synchronized)
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda title: client.put(PATH, json={**payload, 'title': title}), ['parallel A', 'parallel B']))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert len(set(pids)) == 2
    stored = sql.execute('SELECT version,title FROM tickets WHERE id=%s', (TICKET,)).fetchone()
    winner = next(r.json() for r in responses if r.status_code == 200)
    assert stored == (payload['version'] + 1, winner['title'])
    assert sql.execute('SELECT count(*) FROM ticket_events WHERE ticket_id=%s', (TICKET,)).fetchone()[0] == 1


def test_idempotent_concurrent_create_and_payload_conflict(login, sql):
    client = login()
    key = str(uuid4())
    gate = Barrier(2)
    def create(_):
        gate.wait(timeout=5)
        return client.post(BASE + '/tickets', json=PAYLOAD, headers={'Idempotency-Key': key})
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(create, range(2)))
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json() == responses[1].json()
    assert sql.execute('SELECT count(*) FROM tickets').fetchone()[0] == 4
    assert sql.execute('SELECT count(*) FROM ticket_events').fetchone()[0] == 1
    assert sql.execute('SELECT count(*) FROM idempotency_requests').fetchone()[0] == 1
    conflict = client.post(BASE + '/tickets', json={**PAYLOAD, 'title': 'different'}, headers={'Idempotency-Key': key})
    assert conflict.status_code == 409
    client = login('alice')
    assert client.post(BASE + '/tickets', json=PAYLOAD, headers={'Idempotency-Key': key}).json()['id'] != responses[0].json()['id']


@pytest.mark.parametrize('operation', ['edit', 'transition', 'create', 'comment', 'attachment'])
def test_database_audit_failure_rolls_back_whole_transaction(login, sql, monkeypatch, operation):
    client = login()
    before = client.get(PATH).json()
    original = tickets.audit
    def broken_audit(db, ticket, user, kind, detail):
        # Fail on a real PostgreSQL CHECK, after the business write was issued.
        db.add(TicketEvent(workspace_id=ticket.workspace_id, ticket_id=ticket.id, actor_id=user.id, kind='invalid', detail={}))
    monkeypatch.setattr(tickets, 'audit', broken_audit)
    key = str(uuid4())
    if operation == 'edit':
        response = client.put(PATH, json=editable(client, title='must roll back'))
    elif operation == 'transition':
        response = client.post(PATH + '/transitions', json={'version': before['version'], 'status': 'cancelled', 'reason': 'rollback'})
    elif operation == 'create':
        response = client.post(BASE + '/tickets', json=PAYLOAD, headers={'Idempotency-Key': key})
    elif operation == 'comment':
        response = client.post(PATH + '/comments', json={'body': 'must roll back'})
    else:
        response = client.post(PATH + '/attachments?filename=rollback.txt', content=b'rollback')
    assert response.status_code == 409, response.text
    assert client.get(PATH).json() == before
    for table in ['ticket_events', 'attachments', 'idempotency_requests']:
        assert sql.execute(psycopg.sql.SQL('SELECT count(*) FROM {}').format(psycopg.sql.Identifier(table))).fetchone()[0] == 0
    assert sql.execute('SELECT count(*) FROM tickets').fetchone()[0] == 3
    monkeypatch.setattr(tickets, 'audit', original)
    if operation == 'create':
        assert client.post(BASE + '/tickets', json=PAYLOAD, headers={'Idempotency-Key': key}).status_code == 201


@pytest.mark.parametrize('table', ['ticket_events', 'attachments'])
def test_postgresql_enforces_child_workspace_foreign_keys(sql, table):
    with pytest.raises(psycopg.IntegrityError):
        with sql.transaction():
            if table == 'ticket_events':
                sql.execute("INSERT INTO ticket_events(id,workspace_id,ticket_id,actor_id,kind,detail) VALUES (%s,%s,%s,%s,'comment','{}')", (uuid4(), OTHER, TICKET, seed_id('other')))
            else:
                sql.execute("INSERT INTO attachments(id,workspace_id,ticket_id,actor_id,filename,content_type,content,size) VALUES (%s,%s,%s,%s,'a.txt','text/plain',%s,1)", (uuid4(), OTHER, TICKET, seed_id('other'), b'x'))
