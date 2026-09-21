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
