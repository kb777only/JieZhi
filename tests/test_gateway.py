import json
import threading

import pytest
import requests

from jiezhi.devices import DeviceRegistry
from jiezhi.gateway import Gateway, conversation, slug


class FakeClient:
    """Stands in for the phone: a library, a loaded model and a token stream."""

    def __init__(self):
        self.serial = ""; self.port = 0
        self.phone = "Xiaomi 15 Ultra"
        self.library = [{"id": "a" * 64, "name": "Qwen3-1.7B-Q4_0.gguf", "size": 1 << 30}]
        self.loaded = ""
        self.loads = []
        self.reply = ["Hel", "lo"]
        self.failure = None
        self.cancelled = 0

    def connect(self, serial):
        self.serial = serial; self.port = 41000
        return {"state": "idle"}

    def disconnect(self):
        self.port = 0

    def status(self):
        return {"phone": self.phone, "models": self.library, "loaded_id": self.loaded}

    def load(self, model_id, backend="npu", context=2048):
        self.loads.append((model_id, backend, context)); self.loaded = model_id
        return self.status()

    def chat(self, messages, emit, max_tokens=512):
        self.last = (messages, max_tokens)
        if self.failure:
            raise RuntimeError(self.failure)
        emit({"type": "start"})
        for piece in self.reply:
            emit({"type": "token", "text": piece})
        emit({"type": "done", "profile": {"tokens": len(self.reply)}, "cancelled": False})

    def cancel(self):
        self.cancelled += 1


def build(phones=(("A", "Xiaomi 15 Ultra"),), api_key=""):
    clients = {}
    def factory():
        client = FakeClient(); clients[len(clients)] = client; return client
    props = {}
    attached = []
    for serial, name in phones:
        props[(serial, "ro.soc.model")] = "SM8750"
        props[(serial, "ro.product.model")] = name
        attached.append({"serial": serial, "state": "device", "description": f"{serial} usb:1"})
    registry = DeviceRegistry(factory=factory,
                              probe=lambda *a, serial="", timeout=30: props.get((serial, a[-1]), ""),
                              enumerate_devices=lambda: attached)
    registry.scan()
    for serial, name in phones:
        registry.client(serial).phone = name
        registry.connect(serial)
    gateway = Gateway(registry, port=0, api_key=api_key)
    gateway.start()
    return gateway, registry


@pytest.fixture
def gateway():
    made, _ = build()
    yield made
    made.stop()


def post(gateway, path, payload, **kwargs):
    return requests.post(f"http://127.0.0.1:{gateway.port}{path}", json=payload, timeout=10, **kwargs)


def test_models_are_listed_with_readable_ids(gateway):
    data = requests.get(f"http://127.0.0.1:{gateway.port}/v1/models", timeout=10).json()
    ids = {entry["id"] for entry in data["data"]}
    assert ids == {"qwen3-1.7b-q4_0", "qwen3-1.7b-q4_0@xiaomi-15-ultra"}
    assert data["object"] == "list"
    assert all(entry["owned_by"] == "jiezhi" for entry in data["data"])


def test_chat_completion_returns_the_openai_shape(gateway):
    body = post(gateway, "/v1/chat/completions",
                {"model": "qwen3-1.7b-q4_0", "messages": [{"role": "user", "content": "hi"}]}).json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"] == {"role": "assistant", "content": "Hello"}
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"]["completion_tokens"] == 2
    assert body["model"] == "qwen3-1.7b-q4_0"


def test_streaming_emits_sse_frames_and_a_done_sentinel(gateway):
    response = post(gateway, "/v1/chat/completions",
                    {"model": "qwen3-1.7b-q4_0", "stream": True,
                     "messages": [{"role": "user", "content": "hi"}]}, stream=True)
    frames = [line[6:] for line in response.iter_lines(decode_unicode=True) if line.startswith("data: ")]
    assert frames[-1] == "[DONE]"
    chunks = [json.loads(frame) for frame in frames[:-1]]
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant"}
    assert "".join(c["choices"][0]["delta"].get("content", "") for c in chunks) == "Hello"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert all(chunk["object"] == "chat.completion.chunk" for chunk in chunks)


def test_a_model_that_is_not_loaded_is_swapped_in(gateway):
    client = gateway.registry.client("A")
    client.loaded = "b" * 64
    post(gateway, "/v1/chat/completions",
         {"model": "qwen3-1.7b-q4_0", "messages": [{"role": "user", "content": "hi"}]})
    assert client.loads == [("a" * 64, "npu", 4096)]


def test_the_loaded_model_is_not_reloaded(gateway):
    client = gateway.registry.client("A")
    client.loaded = "a" * 64
    post(gateway, "/v1/chat/completions",
         {"model": "qwen3-1.7b-q4_0", "messages": [{"role": "user", "content": "hi"}]})
    assert client.loads == []


def test_max_tokens_reached_reports_length(gateway):
    body = post(gateway, "/v1/chat/completions",
                {"model": "qwen3-1.7b-q4_0", "max_tokens": 2,
                 "messages": [{"role": "user", "content": "hi"}]}).json()
    assert body["choices"][0]["finish_reason"] == "length"


def test_unknown_model_names_what_is_available(gateway):
    response = post(gateway, "/v1/chat/completions",
                    {"model": "llama-70b", "messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 404
    assert "qwen3-1.7b-q4_0" in response.json()["error"]["message"]


def test_content_parts_are_flattened_and_tools_refused(gateway):
    post(gateway, "/v1/chat/completions",
         {"model": "qwen3-1.7b-q4_0",
          "messages": [{"role": "user", "content": [{"type": "text", "text": "split"}, {"type": "text", "text": "me"}]}]})
    assert gateway.registry.client("A").last[0] == [{"role": "user", "content": "splitme"}]
    refused = post(gateway, "/v1/chat/completions",
                   {"model": "qwen3-1.7b-q4_0", "messages": [{"role": "tool", "content": "x"}]})
    assert refused.status_code == 400 and "Tool calling" in refused.json()["error"]["message"]


def test_legacy_completions_endpoint(gateway):
    body = post(gateway, "/v1/completions", {"model": "qwen3-1.7b-q4_0", "prompt": "hi"}).json()
    assert body["object"] == "text_completion"
    assert body["choices"][0]["text"] == "Hello"
    assert gateway.registry.client("A").last[0] == [{"role": "user", "content": "hi"}]


def test_embeddings_say_so_rather_than_failing_obscurely(gateway):
    response = post(gateway, "/v1/embeddings", {"model": "qwen3-1.7b-q4_0", "input": "hi"})
    assert response.status_code == 501
    assert "text only" in response.json()["error"]["message"]


def test_a_phone_error_becomes_a_gateway_error(gateway):
    gateway.registry.client("A").failure = "Unsupported quantization"
    response = post(gateway, "/v1/chat/completions",
                    {"model": "qwen3-1.7b-q4_0", "messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 502
    assert response.json()["error"]["message"] == "Unsupported quantization"


def test_a_busy_phone_asks_the_caller_to_retry(gateway):
    gateway.router.queue_timeout = 0.1
    held = gateway.router._lock("A")
    held.acquire()
    try:
        response = post(gateway, "/v1/chat/completions",
                        {"model": "qwen3-1.7b-q4_0", "messages": [{"role": "user", "content": "hi"}]})
    finally:
        held.release()
    assert response.status_code == 503


def test_requests_queue_rather_than_collide(gateway):
    seen = []
    original = gateway.registry.client("A").chat
    def slow(messages, emit, max_tokens=512):
        seen.append("in"); threading.Event().wait(0.05); seen.append("out"); original(messages, emit, max_tokens)
    gateway.registry.client("A").chat = slow
    threads = [threading.Thread(target=post, args=(gateway, "/v1/chat/completions",
               {"model": "qwen3-1.7b-q4_0", "messages": [{"role": "user", "content": "hi"}]})) for _ in range(3)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert seen == ["in", "out"] * 3


def test_api_key_is_enforced_when_set():
    made, _ = build(api_key="secret")
    try:
        assert requests.get(f"http://127.0.0.1:{made.port}/v1/models", timeout=10).status_code == 401
        ok = requests.get(f"http://127.0.0.1:{made.port}/v1/models", timeout=10,
                          headers={"Authorization": "Bearer secret"})
        assert ok.status_code == 200
    finally:
        made.stop()


def test_a_foreign_host_header_is_refused(gateway):
    response = requests.get(f"http://127.0.0.1:{gateway.port}/v1/models", timeout=10,
                            headers={"Host": "evil.example.com"})
    assert response.status_code == 403


def test_a_non_json_content_type_is_refused(gateway):
    response = requests.post(f"http://127.0.0.1:{gateway.port}/v1/chat/completions", timeout=10,
                             data="model=x", headers={"Content-Type": "text/plain"})
    assert response.status_code == 400


def test_two_phones_holding_the_same_file_get_qualified_ids():
    made, registry = build(phones=(("A", "Xiaomi 15 Ultra"), ("D", "Xiaomi 14")))
    try:
        ids = {entry["id"] for entry in
               requests.get(f"http://127.0.0.1:{made.port}/v1/models", timeout=10).json()["data"]}
        assert ids == {"qwen3-1.7b-q4_0@xiaomi-15-ultra", "qwen3-1.7b-q4_0@xiaomi-14"}
    finally:
        made.stop()


def test_health_reports_connected_phones(gateway):
    body = requests.get(f"http://127.0.0.1:{gateway.port}/health", timeout=10).json()
    assert [d["serial"] for d in body["devices"]] == ["A"]


def test_slug_is_stable_and_filename_free():
    assert slug("Qwen3-1.7B-Q4_0.gguf") == "qwen3-1.7b-q4_0"
    assert slug("weird  name!!.GGUF") == "weird-name"
    assert slug("") == "model"


def test_conversation_rejects_an_empty_list():
    with pytest.raises(ValueError):
        conversation([])


def test_max_tokens_is_clamped_to_what_the_phone_accepts(gateway):
    post(gateway, "/v1/chat/completions",
         {"model": "qwen3-1.7b-q4_0", "max_tokens": 100000,
          "messages": [{"role": "user", "content": "hi"}]})
    assert gateway.registry.client("A").last[1] == 2048


def test_a_nonsense_max_tokens_is_refused(gateway):
    response = post(gateway, "/v1/chat/completions",
                    {"model": "qwen3-1.7b-q4_0", "max_tokens": -1,
                     "messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 400


def test_too_many_messages_are_refused_here_not_on_the_phone(gateway):
    response = post(gateway, "/v1/chat/completions",
                    {"model": "qwen3-1.7b-q4_0",
                     "messages": [{"role": "user", "content": "hi"}] * 101})
    assert response.status_code == 400 and "100 messages" in response.json()["error"]["message"]
    assert not hasattr(gateway.registry.client("A"), "last")


def test_a_developer_role_is_accepted_as_system(gateway):
    post(gateway, "/v1/chat/completions",
         {"model": "qwen3-1.7b-q4_0", "messages": [{"role": "developer", "content": "be brief"},
                                                   {"role": "user", "content": "hi"}]})
    assert gateway.registry.client("A").last[0][0] == {"role": "system", "content": "be brief"}


def test_the_endpoint_answers_before_any_phone_is_attached():
    """Open WebUI verifies a connection on save; a dead port reads as a network error."""
    registry = DeviceRegistry(factory=FakeClient, probe=lambda *a, serial="", timeout=30: "",
                              enumerate_devices=lambda: [])
    made = Gateway(registry, port=0)
    made.start()
    try:
        response = requests.get(f"http://127.0.0.1:{made.port}/v1/models", timeout=10)
        assert response.status_code == 200 and response.json()["data"] == []
        health = requests.get(f"http://127.0.0.1:{made.port}/health", timeout=10).json()
        assert health["ready"] is False
    finally:
        made.stop()


def test_a_phone_plugged_in_after_startup_is_picked_up(monkeypatch):
    attached = []
    props = {("A", "ro.soc.model"): "SM8750", ("A", "ro.product.model"): "Xiaomi 15 Ultra"}
    registry = DeviceRegistry(factory=FakeClient,
                              probe=lambda *a, serial="", timeout=30: props.get((serial, a[-1]), ""),
                              enumerate_devices=lambda: attached)
    monkeypatch.setattr("jiezhi.gateway.read_json", lambda *_: {"A": "stored-token"})
    made = Gateway(registry, port=0)
    made.router.rescan_interval = 0
    made.start()
    try:
        assert requests.get(f"http://127.0.0.1:{made.port}/v1/models", timeout=10).json()["data"] == []
        attached.append({"serial": "A", "state": "device", "description": "A usb:1"})
        ids = {m["id"] for m in
               requests.get(f"http://127.0.0.1:{made.port}/v1/models", timeout=10).json()["data"]}
        assert "qwen3-1.7b-q4_0" in ids
    finally:
        made.stop()


def test_an_unpaired_phone_is_reported_rather_than_connected(monkeypatch):
    props = {("A", "ro.soc.model"): "SM8750", ("A", "ro.product.model"): "Xiaomi 15 Ultra"}
    registry = DeviceRegistry(factory=FakeClient,
                              probe=lambda *a, serial="", timeout=30: props.get((serial, a[-1]), ""),
                              enumerate_devices=lambda: [{"serial": "A", "state": "device", "description": "A usb:1"}])
    monkeypatch.setattr("jiezhi.gateway.read_json", lambda *_: {})
    made = Gateway(registry, port=0)
    made.router.rescan_interval = 0
    made.start()
    try:
        health = requests.get(f"http://127.0.0.1:{made.port}/health", timeout=10).json()
        assert health["ready"] is False and "not paired" in health["trouble"]
    finally:
        made.stop()


def test_adb_trouble_is_reported_not_raised(monkeypatch):
    def broken():
        raise RuntimeError("ADB is missing. Reinstall the JieZhi desktop package.")
    registry = DeviceRegistry(factory=FakeClient, probe=lambda *a, serial="", timeout=30: "",
                              enumerate_devices=broken)
    made = Gateway(registry, port=0)
    made.router.rescan_interval = 0
    made.start()
    try:
        health = requests.get(f"http://127.0.0.1:{made.port}/health", timeout=10).json()
        assert "ADB is missing" in health["trouble"]
        assert requests.get(f"http://127.0.0.1:{made.port}/v1/models", timeout=10).status_code == 200
    finally:
        made.stop()


def test_binding_beyond_loopback_accepts_its_own_host_header():
    """Open WebUI in a container reaches the host by a name that is not 127.0.0.1."""
    made, _ = build()
    made.stop()
    registry = made.registry
    wide = Gateway(registry, host="0.0.0.0", port=0, api_key="secret")
    wide.start()
    try:
        response = requests.get(f"http://127.0.0.1:{wide.port}/v1/models", timeout=10,
                                headers={"Host": "host.docker.internal:11435",
                                         "Authorization": "Bearer secret"})
        assert response.status_code == 200
    finally:
        wide.stop()


def test_binding_beyond_loopback_without_a_key_is_refused():
    from jiezhi.gateway import main
    with pytest.raises(SystemExit) as error:
        main(["--host", "0.0.0.0"])
    assert error.value.code == 2
