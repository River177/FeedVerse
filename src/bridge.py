"""Loopback OAuth Responses gateway; persistent per-attempt request accounting."""
import argparse
import hashlib
import json
import sqlite3
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests
from azure.identity import AzureCliCredential, ChainedTokenCredential, ManagedIdentityCredential


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS keys (hash TEXT PRIMARY KEY, attempt TEXT, cap INTEGER)')
    db.execute('''CREATE TABLE IF NOT EXISTS requests (
        id TEXT PRIMARY KEY, attempt TEXT, started REAL, ended REAL,
        status TEXT, http_status INTEGER, response_id TEXT, usage TEXT, error TEXT)''')
    return db


def register(path, key, attempt, cap):
    with connect(path) as db:
        db.execute('INSERT INTO keys VALUES (?,?,?)', (hashlib.sha256(key.encode()).hexdigest(), attempt, cap))


def reserve(path, key):
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT attempt,cap FROM keys WHERE hash=?',
                         (hashlib.sha256(key.encode()).hexdigest(),)).fetchone()
        if not row:
            raise PermissionError('Unknown attempt credential')
        attempt, cap = row
        used = db.execute('SELECT COUNT(*) FROM requests WHERE attempt=?', (attempt,)).fetchone()[0]
        if used >= cap:
            raise OverflowError('Attempt model request limit reached')
        request_id = str(uuid.uuid4())
        db.execute('INSERT INTO requests(id,attempt,started,status) VALUES (?,?,?,?)',
                   (request_id, attempt, time.time(), 'in_flight'))
        return request_id


def finish(path, request_id, status, http_status=None, response_id=None, usage=None, error=None):
    with connect(path) as db:
        db.execute('UPDATE requests SET ended=?,status=?,http_status=?,response_id=?,usage=?,error=? WHERE id=?',
                   (time.time(), status, http_status, response_id, json.dumps(usage) if usage else None,
                    error, request_id))


def inspect_event(event):
    kind = event.get('type')
    response = event.get('response', {})
    if kind == 'response.completed':
        return 'completed', response.get('id'), response.get('usage')
    if kind in ('response.failed', 'response.incomplete', 'error'):
        return kind, response.get('id'), response.get('usage')
    return None, None, None


def serve(config):
    database = Path(config['root']) / 'control' / 'usage.sqlite'
    database.parent.mkdir(parents=True, exist_ok=True)
    connect(database).close()
    credential = ChainedTokenCredential(AzureCliCredential(), ManagedIdentityCredential())
    upstream = f"https://trapi.research.microsoft.com/{config['instance']}/openai/responses"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def key(self):
            header = self.headers.get('Authorization', '')
            return header[7:] if header.startswith('Bearer ') else ''

        def valid(self):
            with connect(database) as db:
                return db.execute('SELECT 1 FROM keys WHERE hash=?',
                    (hashlib.sha256(self.key().encode()).hexdigest(),)).fetchone() is not None

        def reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/health':
                return self.reply(200, {'service': 'agh-rsi', 'deployment': config['deployment']})
            if not self.valid():
                return self.reply(401, {'error': {'message': 'Attempt credential required'}})
            if self.path == '/v1/models':
                return self.reply(200, {'object': 'list', 'data': [
                    {'id': config['model'], 'object': 'model', 'owned_by': 'trapi'}]})
            self.reply(404, {'error': {'message': 'Unknown route'}})

        def do_POST(self):
            if self.path != '/v1/responses':
                return self.reply(404, {'error': {'message': 'Only Responses supported'}})
            request_id = None
            headers_sent = False
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 8 * 1024 * 1024:
                    return self.reply(413, {'error': {'message': 'Invalid request size'}})
                body = json.loads(self.rfile.read(length))
                if body.get('model') != config['model']:
                    return self.reply(400, {'error': {'message': 'Frozen model mismatch'}})
                request_id = reserve(database, self.key())
                body['model'] = config['deployment']
                body['max_output_tokens'] = config['max_output_tokens']
                token = credential.get_token('api://trapi/.default').token
                with requests.post(upstream, params={'api-version': config['api_version']},
                    headers={'Authorization': 'Bearer ' + token, 'x-ms-client-request-id': request_id},
                    json=body, stream=True, timeout=(20, 300)) as response:
                    self.send_response(response.status_code)
                    self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                    self.send_header('Connection', 'close')
                    self.send_header('X-AGH-RSI-Request-ID', request_id)
                    self.end_headers()
                    headers_sent = True
                    state, rid, usage = 'missing_completion', None, None
                    if response.status_code != 200:
                        state = 'auth_error' if response.status_code in (401, 403) else 'http_error'
                        for chunk in response.iter_content(4096):
                            self.wfile.write(chunk)
                    elif body.get('stream'):
                        for line in response.iter_lines(chunk_size=1):
                            self.wfile.write(line + b'\n')
                            self.wfile.flush()
                            if line.startswith(b'data: '):
                                try:
                                    event = json.loads(line[6:])
                                    found, event_id, event_usage = inspect_event(event)
                                    if found:
                                        state, rid, usage = found, event_id, event_usage
                                except (ValueError, TypeError):
                                    pass
                    else:
                        data = response.json()
                        state, rid, usage = data.get('status', 'missing_completion'), data.get('id'), data.get('usage')
                        self.wfile.write(json.dumps(data).encode())
                    finish(database, request_id, state, response.status_code, rid, usage)
                    self.close_connection = True
            except PermissionError:
                self.reply(401, {'error': {'message': 'Attempt credential required'}})
            except OverflowError:
                self.reply(429, {'error': {'type': 'budget_exhausted', 'message': 'Attempt model request limit reached'}})
            except (ValueError, TypeError):
                if not headers_sent:
                    self.reply(400, {'error': {'message': 'Invalid request JSON'}})
                if request_id:
                    finish(database, request_id, 'invalid_response')
            except Exception as error:
                kind = type(error).__name__
                if request_id:
                    finish(database, request_id, 'bridge_error', error=kind)
                if not headers_sent:
                    self.reply(502, {'error': {'message': 'Gateway failed: ' + kind}})
                self.close_connection = True

    ThreadingHTTPServer(('127.0.0.1', config['port']), Handler).serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    serve(json.loads(Path(parser.parse_args().config).read_text()))
