from datetime import datetime, timedelta, timezone
import uuid

import psycopg
import pytest

from app.seed import seed_id
from app.security import COOKIE, digest
from conftest import PASSWORD

WID = str(seed_id('product'))
OTHER = str(seed_id('support'))
BASE = f'/api/v1/workspaces/{WID}'
TICKET = str(seed_id('ticket-1'))
PAYLOAD = {'title': '测试工单', 'body': '需要帮助解决的问题', 'priority': 'normal'}


def test_login_bad_password_and_cookie_attributes(client, login, sql):
    result = client.post('/api/v1/auth/login', json={'email': 'admin@flowdesk.example', 'password': 'wrong'})
    assert result.status_code == 401
    login()
    token = client.cookies[COOKIE]
    assert len(token) >= 40
    stored = sql.execute('SELECT token_hash FROM sessions').fetchone()[0]
    assert stored == digest(token) and stored != token
    result = client.post('/api/v1/auth/login', json={'email': 'admin@flowdesk.example', 'password': PASSWORD})
    cookie = result.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=lax' in cookie and 'path=/api' in cookie


@pytest.mark.parametrize('role', ['admin', 'agent', 'alice'])
def test_create_list_detail_for_each_role(login, role):
    client = login(role)
    result = client.post(BASE + '/tickets', json=PAYLOAD)
    assert result.status_code == 201, result.text
    ticket = result.json()
    assert ticket['creator_id'] == str(seed_id(role)) and ticket['version'] == 1
    assert client.get(BASE + '/tickets/' + ticket['id']).json()['title'] == PAYLOAD['title']
    assert ticket['id'] in [row['id'] for row in client.get(BASE + '/tickets').json()['items']]


def test_cross_workspace_and_same_workspace_requester_isolation(login):
    client = login('other')
    for path in [BASE + '/tickets', BASE + '/tickets/' + TICKET, BASE + '/members', BASE + '/assignees']:
        assert client.get(path).status_code == 404
    assert client.post(BASE + '/tickets', json=PAYLOAD).status_code == 404
    assert client.get(f'/api/v1/workspaces/{OTHER}/tickets/{TICKET}').status_code == 404
    client = login('bob')
    assert client.get(BASE + '/tickets/' + TICKET).status_code == 404
    assert TICKET not in [t['id'] for t in client.get(BASE + '/tickets').json()['items']]
    assert client.get('/api/v1/me').json()['workspaces'][0]['id'] == WID


@pytest.mark.parametrize('person', ['agent', 'alice'])
def test_members_require_admin(login, person):
    client = login(person)
    assert client.get(BASE + '/members').status_code == 403
    assert client.put(BASE + '/members', json={'email': 'bob@flowdesk.example', 'role': 'admin'}).status_code == 403


def test_member_changes_and_last_admin_protection(login, sql):
    client = login()
    assert client.put(BASE + '/members', json={'email': 'admin@flowdesk.example', 'role': 'requester'}).status_code == 409
    assert client.put(BASE + '/members', json={'email': 'bob@flowdesk.example', 'role': 'agent'}).status_code == 200
    assert sql.execute('SELECT role FROM memberships WHERE workspace_id=%s AND user_id=%s', (WID, seed_id('bob'))).fetchone()[0] == 'agent'


def test_assignee_must_be_active_member_and_requester_cannot_assign(login, sql):
    client = login()
    assert client.post(BASE + '/tickets', json={**PAYLOAD, 'assignee_id': str(seed_id('other'))}).status_code == 422
    assert client.post(BASE + '/tickets', json={**PAYLOAD, 'assignee_id': str(seed_id('bob'))}).status_code == 422
    assert client.post(BASE + '/tickets', json={**PAYLOAD, 'assignee_id': str(seed_id('agent'))}).status_code == 201
    sql.execute('UPDATE memberships SET is_active=false WHERE user_id=%s', (seed_id('agent'),))
    assert client.post(BASE + '/tickets', json={**PAYLOAD, 'assignee_id': str(seed_id('agent'))}).status_code == 422
    client = login('alice')
    assert client.post(BASE + '/tickets', json={**PAYLOAD, 'assignee_id': str(seed_id('admin'))}).status_code == 403


def test_revocation_and_role_changes_take_effect_on_existing_session(login, sql):
    client = login('agent')
    assert client.get(BASE + '/tickets/' + TICKET).status_code == 200
    sql.execute("UPDATE memberships SET role='requester' WHERE user_id=%s", (seed_id('agent'),))
    assert client.get(BASE + '/tickets/' + TICKET).status_code == 404
    sql.execute('UPDATE memberships SET is_active=false WHERE user_id=%s', (seed_id('agent'),))
    assert client.get(BASE + '/tickets').status_code == 404
    assert client.get('/api/v1/me').json()['workspaces'] == []


@pytest.mark.parametrize('change', ['expire', 'disable'])
def test_invalidated_session(login, sql, change):
    client = login()
    if change == 'expire':
        sql.execute('UPDATE sessions SET expires_at=%s', (datetime.now(timezone.utc) - timedelta(seconds=1),))
    else:
        sql.execute('UPDATE users SET is_active=false WHERE id=%s', (seed_id('admin'),))
    assert client.get('/api/v1/me').status_code == 401


def test_logout_and_login_rotation_reject_replayed_cookie(login, client):
    login()
    old = client.cookies[COOKIE]
    response = client.post('/api/v1/auth/login', json={'email': 'admin@flowdesk.example', 'password': PASSWORD})
    current = client.cookies[COOKIE]
    client.headers['x-csrf-token'] = response.json()['csrf_token']
    assert client.post('/api/v1/auth/logout').status_code == 204
    for token in [old, current]:
        client.cookies.clear()
        client.cookies.set(COOKIE, token, path='/api')
        assert client.get('/api/v1/me').status_code == 401


@pytest.mark.parametrize('origin', [None, 'https://evil.example'])
def test_origin_required_even_for_login(client, origin):
    client.headers.pop('origin', None)
    if origin:
        client.headers['origin'] = origin
    assert client.post('/api/v1/auth/login', json={'email': 'admin@flowdesk.example', 'password': PASSWORD}).status_code == 403


@pytest.mark.parametrize('token', ['', 'invalid'])
def test_csrf_required_for_writes(login, token):
    client = login()
    client.headers['x-csrf-token'] = token
    assert client.post(BASE + '/tickets', json=PAYLOAD).status_code == 403
    assert client.post('/api/v1/auth/logout').status_code == 403


def test_anonymous_validation_pagination_and_errors(client, login):
    assert client.get(BASE + '/tickets').status_code == 401
    login()
    for payload in [{**PAYLOAD, 'title': '  '}, {**PAYLOAD, 'title': 'x' * 201}, {**PAYLOAD, 'priority': 'invalid'}, {**PAYLOAD, 'creator_id': str(seed_id('bob'))}]:
        assert client.post(BASE + '/tickets', json=payload).status_code == 422
    for query in ['page=0', 'page_size=101', 'page_size=-1']:
        response = client.get(BASE + '/tickets?' + query)
        assert response.status_code == 422
        assert response.json()['request_id'] == response.headers['x-request-id']
    first = client.get(BASE + '/tickets?page_size=1&page=1').json()
    second = client.get(BASE + '/tickets?page_size=1&page=2').json()
    assert first['total'] == 2 and first['items'][0]['id'] != second['items'][0]['id']


@pytest.mark.parametrize('violation', ['email', 'membership', 'role', 'priority', 'status', 'version', 'creator', 'assignee'])
def test_postgresql_rejects_constraint_violations(sql, violation):
    with pytest.raises(psycopg.IntegrityError):
        with sql.transaction():
            if violation == 'email':
                sql.execute("INSERT INTO users(id,email,name,password_hash) VALUES (%s,'admin@flowdesk.example','duplicate','x')", (uuid.uuid4(),))
            elif violation == 'membership':
                sql.execute("INSERT INTO memberships(workspace_id,user_id,role) VALUES (%s,%s,'admin')", (WID, seed_id('admin')))
            elif violation == 'role':
                sql.execute("UPDATE memberships SET role='root'")
            else:
                changes = {'priority': ('priority', 'invalid'), 'status': ('status', 'invalid'), 'version': ('version', 0), 'creator': ('creator_id', seed_id('other')), 'assignee': ('assignee_id', seed_id('other'))}
                field, value = changes[violation]
                sql.execute(psycopg.sql.SQL('UPDATE tickets SET {}=%s WHERE id=%s').format(psycopg.sql.Identifier(field)), (value, TICKET))
    assert sql.execute('SELECT count(*) FROM tickets').fetchone()[0] == 3
