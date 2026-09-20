import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from jiezhi.hub import Hub, Paused
import jiezhi.hub as hub_module


@pytest.fixture
def hub(tmp_path, monkeypatch):
    state = {'data': b'GGUF' + b'a' * (3 * 1024 * 1024), 'ranges': [], 'tokens': [], 'status': 200}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            state['tokens'].append(self.headers.get('Authorization'))
            if self.path == '/api/whoami-v2':
                body = b'{"name":"example-user"}'
                self.send_response(state['status']); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body); return
            offset = int(self.headers.get('Range', 'bytes=0-').split('=')[1].split('-')[0])
            state['ranges'].append(offset)
            body = state['data'][offset:]
            self.send_response(206 if offset else 200)
            if offset: self.send_header('Content-Range', f"bytes {offset}-{len(state['data'])-1}/{len(state['data'])}")
            self.send_header('Content-Length', str(len(body))); self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    hub = Hub(tmp_path / 'cache'); hub.base = f'http://127.0.0.1:{server.server_port}'
    monkeypatch.setattr(hub_module, 'DATA', tmp_path / 'data')
    file = {'repo': 'test/model', 'revision': 'a'*40, 'name': 'model.gguf', 'size': len(state['data']), 'sha256': hashlib.sha256(state['data']).hexdigest()}
    yield hub, file, state
    server.shutdown(); server.server_close(); thread.join()


def test_pause_resume_checksum_and_cache(hub):
    client, file, state = hub; cancel = threading.Event()
    def progress(percent, message):
        if percent > 0: cancel.set()
    with pytest.raises(Paused): client.download(file, progress, cancel)
    assert not client.destination(file).exists()
    cancel.clear(); path = client.download(file, cancelled=cancel)
    assert path.read_bytes() == state['data']
    assert state['ranges'][1] > 0
    before = len(state['ranges']); assert client.download(file) == path
    assert len(state['ranges']) == before


def test_checksum_failure_discards_partial(hub):
    client, file, state = hub; file['sha256'] = '0'*64
    with pytest.raises(RuntimeError, match='checksum'): client.download(file)
    assert not client.destination(file).exists()
    assert not client.destination(file).with_suffix('.gguf.partial').exists()


def test_unsafe_and_unsupported_files(hub):
    client, file, state = hub
    for name in ['../../secret.gguf', '/tmp/secret.gguf', 'a\\b.gguf']:
        with pytest.raises(ValueError, match='Unsafe'): client.destination({**file, 'name': name})
    with pytest.raises(ValueError, match='Split'): client.download({**file, 'split': True})
    with pytest.raises(ValueError, match='verifiable'): client.download({**file, 'sha256': ''})
    with pytest.raises(ValueError, match='pinned'): client.destination({**file, 'revision': 'main'})
    assert state['ranges'] == []


def test_account_session_and_failed_auth(hub):
    client, _, state = hub
    assert client.connect('hf_testToken', False)['username'] == 'example-user'
    account = hub_module.DATA / 'hub-account.json'
    assert 'hf_' not in account.read_text()
    assert account.stat().st_mode & 0o777 == 0o600
    state['status'] = 401
    with pytest.raises(RuntimeError, match='valid read token'): client.connect('hf_badToken', False)
    assert client.token == 'hf_testToken'
    client.disconnect(); assert not client.token and not account.exists()


def test_keyring_persistence_and_disconnect(hub, monkeypatch):
    client, _, state = hub; saved = {}
    from keyring.backends import SecretService
    class FakeKeyring:
        def set_password(self, service, name, token): saved[(service, name)] = token
        def get_password(self, service, name): return saved.get((service, name))
        def delete_password(self, service, name): del saved[(service, name)]
    monkeypatch.setattr(SecretService, 'Keyring', FakeKeyring)
    assert client.connect('hf_savedToken', True)['remember']
    client.token = ''; assert client.restore()['username'] == 'example-user'
    assert client.token == 'hf_savedToken'
    client.disconnect(); assert not saved


def test_keyring_unavailable_stays_in_memory(hub, monkeypatch):
    client, _, state = hub
    from keyring.backends import SecretService
    class Unavailable:
        def set_password(self, *args): raise RuntimeError('locked')
    monkeypatch.setattr(SecretService, 'Keyring', Unavailable)
    result = client.connect('hf_sessionToken', True)
    assert not result['remember'] and 'session only' in result['warning']
    assert 'hf_sessionToken' not in (hub_module.DATA / 'hub-account.json').read_text()
