import hashlib
import json
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from jiezhi.client import Client, save_json


@pytest.fixture
def bridge():
    state = {"data": bytearray(), "committed": False, "requests": []}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def reply(self, data, code=200):
            payload = json.dumps(data).encode()
            self.send_response(code); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append((self.path, body))
            if self.headers.get("Authorization") != "Bearer test":
                return self.reply({"error": "Unauthorized"}, 401)
            if self.path == "/v1/uploads":
                state["meta"] = body; self.reply({"offset": len(state["data"]), "complete": state["committed"]})
            elif self.path == "/v1/commit":
                assert hashlib.sha256(state["data"]).hexdigest() == body["id"]
                state["committed"] = True; self.reply({"ok": True})
            elif self.path == "/v1/load":
                self.reply({"error": "Unsupported quantization"}, 400)
            elif self.path == "/v1/chat":
                self.send_response(200); self.end_headers()
                self.wfile.write(b'{"type":"token","text":"partial"}\n')
        def do_PUT(self):
            assert int(self.headers["X-Offset"]) == len(state["data"])
            state["data"].extend(self.rfile.read(int(self.headers["Content-Length"])))
            self.reply({"offset": len(state["data"])})
        def do_GET(self):
            self.reply({"models": [state.get("meta")] if state["committed"] else []})
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    client = Client(); client.port = server.server_port; client.token = "test"
    yield client, state
    server.shutdown(); server.server_close(); thread.join()


def model_file(tmp_path, size=128):
    data = b"GGUF" + struct.pack("<IQQ", 3, 0, 0) + b"a" * size
    path = tmp_path / "example.gguf"; path.write_bytes(data)
    return path, data


def test_import_resumes_and_checks_integrity(bridge, tmp_path):
    client, state = bridge; path, data = model_file(tmp_path)
    state["data"].extend(data[:53])
    result = client.import_model(path)
    assert state["data"] == data
    assert state["committed"]
    assert result["models"][0]["id"] == hashlib.sha256(data).hexdigest()


def test_rejects_non_gguf_without_network(bridge, tmp_path):
    client, state = bridge; path = tmp_path / "fake.gguf"; path.write_text("not a model")
    with pytest.raises(RuntimeError, match="GGUF"):
        client.import_model(path)
    assert state["requests"] == []


def test_cancelled_import_does_not_commit(bridge, tmp_path):
    client, state = bridge; path, _ = model_file(tmp_path)
    cancelled = threading.Event(); cancelled.set()
    with pytest.raises(RuntimeError, match="paused"):
        client.import_model(path, cancelled=cancelled)
    assert not state["committed"]


def test_runtime_error_is_actionable(bridge):
    client, _ = bridge
    with pytest.raises(RuntimeError, match="Unsupported quantization"):
        client.load("a" * 64)


def test_truncated_stream_is_not_success(bridge):
    client, _ = bridge; events = []
    with pytest.raises(RuntimeError, match="before generation completed"):
        client.chat([{"role": "user", "content": "test"}], events.append)
    assert events == [{"type": "token", "text": "partial"}]


def test_credentials_saved_privately(tmp_path):
    path = tmp_path / "state/pairing.json"; save_json(path, {"test": "secret"})
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text()) == {"test": "secret"}


def test_installer_preserves_bundle_and_supports_update(tmp_path):
    from jiezhi.installer import install_bundle
    source = tmp_path / "source"; source.mkdir()
    (source / "JieZhi").write_text("v1")
    destination = tmp_path / "install"; desktop = tmp_path / "apps/jiezhi.desktop"
    install_bundle(source, destination, desktop)
    assert (destination / "JieZhi").read_text() == "v1"
    (source / "JieZhi").write_text("v2")
    install_bundle(source, destination, desktop)
    assert (destination / "JieZhi").read_text() == "v2"
    assert not destination.with_name("install.previous").exists()
    assert str(destination) in desktop.read_text()
