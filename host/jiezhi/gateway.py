"""An OpenAI-compatible endpoint so third-party apps can use the phone's NPU.

Any workspace that accepts a custom base URL — Open WebUI, Jan, AnythingLLM,
Continue, Cline — can point at this server and the phone answers. The shape is
deliberately coarse: a prompt goes down the USB link and tokens stream back,
because the link is USB 2.0 and anything finer grained than a whole request
would spend its time on the cable rather than on the Hexagon NPU.

Routing goes through `DeviceRegistry`, so the day there is more than one phone
the catalogue simply grows and a "JieZhi - Max" entry can front all of them.

The server binds to loopback. It also checks the Host header and insists on a
JSON content type, which together keep a web page the user happens to be
visiting from driving the phone through their browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
import time
import uuid

from .client import DATA, read_json
from .devices import READY, DeviceRegistry

DEFAULT_PORT = 11435  # 11434 belongs to Ollama; sitting beside it is friendlier.
DEFAULT_CONTEXT = 4096
DEFAULT_BACKEND = "npu"
# The phone enforces these; rejecting or clamping here beats an opaque failure
# from the Android bridge. See BridgeServer.generate and BridgeServer /v1/load.
MAX_GENERATION = 2048
MAX_MESSAGES = 100
CONTEXT_RANGE = (512, 8192)
MAX_BODY = 8 * 1024 * 1024  # Prompts, not uploads; models still go through /v1/uploads.
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}


def slug(text: str) -> str:
    """A model id an app can store in its config and type by hand."""
    stem = re.sub(r"\.(gguf|bin|safetensors)$", "", (text or "").strip(), flags=re.I)
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9._]+", "-", stem.lower())).strip("-.") or "model"


@dataclass(frozen=True)
class ModelEntry:
    """One phone-resident model, as third-party apps see it."""

    id: str
    serial: str
    model_id: str      # SHA-256 the phone knows the file by
    name: str          # original filename
    size: int
    device: str        # phone's product name

    def summary(self, created: int) -> dict:
        return {"id": self.id, "object": "model", "created": created, "owned_by": "jiezhi",
                "jiezhi": {"device": self.device, "serial": self.serial,
                           "file": self.name, "size": self.size}}


class Busy(RuntimeError):
    """Another request holds the phone; the caller should retry."""


class Router:
    """Turns a requested model id into a generation on a specific phone.

    One phone runs one model and one generation at a time, so each serial has
    its own lock and requests for it queue. When the model an app asked for is
    not the one loaded, the router loads it first.
    """

    def __init__(self, registry: DeviceRegistry, context: int = DEFAULT_CONTEXT,
                 backend: str = DEFAULT_BACKEND, queue_timeout: float = 120.0,
                 serial: str = "", rescan_interval: float = 5.0):
        self.registry = registry
        self.context = context
        self.backend = backend
        self.queue_timeout = queue_timeout
        self.serial = serial
        self.rescan_interval = rescan_interval
        self.trouble = ""  # last reason the phones could not be read, for /health
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._entries: dict[str, ModelEntry] = {}
        self._scanned = 0.0
        self._scanning = threading.Lock()

    def refresh(self, force: bool = False) -> None:
        """Pick up a phone that was plugged in after the gateway started.

        An app is usually configured before the phone is attached, so the
        server has to keep looking rather than settle for what it found at
        startup. Only a phone already paired with this host is connected,
        because pairing needs the code shown on its screen.
        """
        now = time.monotonic()
        if not force and now - self._scanned < self.rescan_interval:
            return
        # Several handler threads can arrive at once; one scan is enough, and
        # connecting a phone twice in parallel would fight over the ADB forward.
        if not self._scanning.acquire(blocking=False):
            return
        try:
            self._refresh()
        finally:
            self._scanning.release()

    def _refresh(self) -> None:
        self._scanned = time.monotonic()
        try:
            self.registry.scan()
        except Exception as error:  # ADB missing, or no permission to reach it.
            self.trouble = str(error)
            return
        self.trouble = ""
        paired = read_json(DATA / "pairing.json", {})
        for device in self.registry.usable():
            if device.state == READY or (self.serial and device.serial != self.serial):
                continue
            if not paired.get(device.serial):
                self.trouble = f"{device.title} is attached but not paired with this host."
                continue
            try:
                result = self.registry.connect(device.serial)
            except Exception as error:
                self.trouble = f"{device.title}: {error}"
                continue
            if isinstance(result, dict) and result.get("needs_pairing"):
                self.registry.disconnect(device.serial)
                self.trouble = f"{device.title} needs pairing again in the desktop app."

    def _lock(self, serial: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(serial, threading.Lock())

    def catalog(self) -> list[ModelEntry]:
        """Ask every connected phone what it holds and name each model.

        A model gets a qualified `stem@device` id always, and the bare `stem`
        as well while only one phone holds a file by that name. Apps that pin
        the qualified id keep working when a second phone arrives.
        """
        self.refresh()
        found: list[ModelEntry] = []
        for device in self.registry.connected():
            client = self.registry.client(device.serial)
            try:
                status = client.status()
            except Exception:
                continue  # A phone that dropped mid-scan is absent, not fatal.
            name = status.get("phone") or device.title
            for model in status.get("models", []):
                found.append(ModelEntry(id=slug(model["name"]), serial=device.serial,
                                        model_id=model["id"], name=model["name"],
                                        size=int(model.get("size") or 0), device=name))
        counts: dict[str, int] = {}
        for entry in found:
            counts[entry.id] = counts.get(entry.id, 0) + 1
        entries: dict[str, ModelEntry] = {}
        for entry in found:
            qualified = f"{entry.id}@{slug(entry.device)}"
            entries[qualified] = ModelEntry(**{**entry.__dict__, "id": qualified})
            if counts[entry.id] == 1:
                entries[entry.id] = entry
        with self._guard:
            self._entries = entries
        return sorted(entries.values(), key=lambda e: e.id)

    def resolve(self, model_id: str) -> ModelEntry | None:
        with self._guard:
            entry = self._entries.get(model_id)
        if entry is not None:
            return entry
        self.catalog()  # An app may know a model we have not listed since it appeared.
        with self._guard:
            return self._entries.get(model_id)

    def generate(self, entry: ModelEntry, messages: list[dict], max_tokens: int, emit):
        """Run one generation, loading the model first if another one is in.

        `emit` receives the phone's own stream events. Exceptions from the
        phone propagate; the lock is always released.
        """
        lock = self._lock(entry.serial)
        if not lock.acquire(timeout=self.queue_timeout):
            raise Busy(f"{entry.device} is still answering another request.")
        try:
            client = self.registry.client(entry.serial)
            status = client.status()
            if status.get("loaded_id") != entry.model_id:
                client.load(entry.model_id, self.backend, self.context)
            client.chat(messages, emit, max_tokens=max_tokens)
        finally:
            lock.release()

    def cancel(self, serial: str) -> None:
        self.registry.client(serial).cancel()


def flatten(content) -> str:
    """OpenAI allows content parts; the phone runtime wants one string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content
                       if isinstance(part, dict) and part.get("type") in (None, "text"))
    return ""


def conversation(messages) -> list[dict]:
    """Validate an incoming message list and reduce it to role/content pairs."""
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty array.")
    if len(messages) > MAX_MESSAGES:
        raise ValueError(f"The phone accepts at most {MAX_MESSAGES} messages per request.")
    result = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("Each message must be an object with a role and content.")
        role = message.get("role")
        if role in ("tool", "function"):
            raise ValueError("Tool calling is not supported; the phone runtime generates text only.")
        if role not in ("system", "user", "assistant", "developer"):
            raise ValueError(f"Unsupported message role {role!r}.")
        result.append({"role": "system" if role == "developer" else role,
                       "content": flatten(message.get("content"))})
    return result


def finish_reason(profile, max_tokens: int) -> str:
    generated = (profile or {}).get("tokens")
    return "length" if isinstance(generated, int) and generated >= max_tokens else "stop"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "JieZhi"
    sys_version = ""

    # --- plumbing -------------------------------------------------------

    def log_message(self, *args):
        pass  # The GUI and docs are where a user looks; stderr noise helps nobody.

    @property
    def gateway(self):
        return self.server.gateway

    def send_json(self, payload, code=200):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message, code=400, kind="invalid_request_error"):
        # A rejected request may still have an unread body, which would desync a
        # kept-alive connection, so every error ends its connection.
        self.close_connection = True
        self.send_json({"error": {"message": message, "type": kind, "code": None}}, code)

    def guard(self) -> bool:
        """Reject anything that is not a local client speaking JSON to us.

        Checking Host defeats DNS rebinding, and requiring a JSON content type
        means a browser has to preflight, which a cross-origin page cannot pass
        because no CORS headers are ever sent.
        """
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if self.gateway.local_only and host and host not in {h.strip("[]") for h in LOCAL_HOSTS}:
            self.send_error_json("JieZhi only serves local clients.", 403, "permission_error")
            return False
        key = self.gateway.api_key
        if key:
            offered = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
            if offered != key:
                self.send_error_json("Incorrect API key provided.", 401, "authentication_error")
                return False
        return True

    def body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("Request body is too large.")
        if "json" not in (self.headers.get("Content-Type") or ""):
            raise ValueError("Content-Type must be application/json.")
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            raise ValueError("Request body is not valid JSON.")
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    # --- routes ---------------------------------------------------------

    def do_GET(self):
        if not self.guard():
            return
        path = self.path.split("?")[0].rstrip("/")
        if path in ("", "/health", "/v1"):
            self.gateway.router.refresh()
            connected = [d.summary() for d in self.gateway.registry.connected()]
            return self.send_json({"service": "jiezhi", "object": "health", "devices": connected,
                                   "ready": bool(connected),
                                   "trouble": self.gateway.router.trouble})
        if path == "/v1/models":
            created = int(time.time())
            return self.send_json({"object": "list",
                                   "data": [e.summary(created) for e in self.gateway.router.catalog()]})
        if path.startswith("/v1/models/"):
            entry = self.gateway.router.resolve(path[len("/v1/models/"):])
            if entry is None:
                return self.send_error_json("The model does not exist on any connected phone.", 404, "not_found_error")
            return self.send_json(entry.summary(int(time.time())))
        self.send_error_json(f"Unknown path {path}.", 404, "not_found_error")

    def do_POST(self):
        if not self.guard():
            return
        path = self.path.split("?")[0].rstrip("/")
        try:
            payload = self.body()
        except ValueError as error:
            return self.send_error_json(str(error))
        if path == "/v1/chat/completions":
            return self.completions(payload, chat=True)
        if path == "/v1/completions":
            return self.completions(payload, chat=False)
        if path == "/v1/embeddings":
            return self.send_error_json(
                "Embeddings are not available; the phone runtime generates text only.", 501, "not_supported_error")
        self.send_error_json(f"Unknown path {path}.", 404, "not_found_error")

    # --- completions ----------------------------------------------------

    def completions(self, payload, chat: bool):
        model_id = payload.get("model")
        if not isinstance(model_id, str) or not model_id:
            return self.send_error_json("A model is required.")
        entry = self.gateway.router.resolve(model_id)
        if entry is None:
            known = ", ".join(e.id for e in self.gateway.router.catalog()) or "none"
            return self.send_error_json(
                f"Model {model_id!r} is not on any connected phone. Available: {known}.", 404, "not_found_error")
        try:
            if chat:
                messages = conversation(payload.get("messages"))
            else:
                prompt = payload.get("prompt")
                if not isinstance(prompt, str) or not prompt:
                    raise ValueError("prompt must be a non-empty string.")
                messages = [{"role": "user", "content": prompt}]
            max_tokens = payload.get("max_tokens") or payload.get("max_completion_tokens") or 512
            if not isinstance(max_tokens, int) or max_tokens < 1:
                raise ValueError("max_tokens must be a positive integer.")
            # Apps commonly default to more than the phone will take; clamping keeps
            # them working rather than failing every request. Documented in gateway.md.
            max_tokens = min(max_tokens, MAX_GENERATION)
        except ValueError as error:
            return self.send_error_json(str(error))
        if payload.get("stream"):
            return self.stream(entry, messages, max_tokens, chat)
        return self.collect(entry, messages, max_tokens, chat)

    def envelope(self, chat: bool) -> tuple[str, int]:
        kind = "chatcmpl" if chat else "cmpl"
        return f"{kind}-{uuid.uuid4().hex}", int(time.time())

    def collect(self, entry, messages, max_tokens, chat):
        text, profile = [], {}
        def emit(event):
            if event["type"] == "token":
                text.append(event.get("text", ""))
            elif event["type"] == "done":
                profile.update(event.get("profile") or {})
        try:
            self.gateway.router.generate(entry, messages, max_tokens, emit)
        except Busy as error:
            return self.send_error_json(str(error), 503, "rate_limit_error")
        except Exception as error:
            return self.send_error_json(str(error) or "The phone could not complete the request.",
                                        502, "api_error")
        identifier, created = self.envelope(chat)
        reason = finish_reason(profile, max_tokens)
        answer = "".join(text)
        choice = ({"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": reason}
                  if chat else {"index": 0, "text": answer, "finish_reason": reason})
        generated = profile.get("tokens") if isinstance(profile.get("tokens"), int) else 0
        self.send_json({"id": identifier, "object": "chat.completion" if chat else "text_completion",
                        "created": created, "model": entry.id, "choices": [choice],
                        # The phone runtime reports generated tokens only; prompt tokens are not counted.
                        "usage": {"prompt_tokens": 0, "completion_tokens": generated,
                                  "total_tokens": generated}})

    def stream(self, entry, messages, max_tokens, chat):
        identifier, created = self.envelope(chat)
        object_name = "chat.completion.chunk" if chat else "text_completion"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        broken = threading.Event()
        profile: dict = {}

        def write(chunk: dict):
            try:
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                broken.set()
                raise

        def frame(delta, reason=None):
            choice = ({"index": 0, "delta": delta, "finish_reason": reason} if chat
                      else {"index": 0, "text": delta.get("content", ""), "finish_reason": reason})
            return {"id": identifier, "object": object_name, "created": created,
                    "model": entry.id, "choices": [choice]}

        def emit(event):
            if event["type"] == "start" and chat:
                write(frame({"role": "assistant"}))
            elif event["type"] == "token":
                write(frame({"content": event.get("text", "")}))
            elif event["type"] == "done":
                profile.update(event.get("profile") or {})

        try:
            self.gateway.router.generate(entry, messages, max_tokens, emit)
        except Busy as error:
            if not broken.is_set():
                write({"error": {"message": str(error), "type": "rate_limit_error"}})
            return
        except Exception as error:
            if broken.is_set():
                # The app hung up mid-answer; stop the phone rather than let it run on.
                try:
                    self.gateway.router.cancel(entry.serial)
                except Exception:
                    pass
                return
            write({"error": {"message": str(error) or "The phone could not complete the request.",
                             "type": "api_error"}})
            return
        write(frame({}, finish_reason(profile, max_tokens)))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Gateway:
    """The endpoint an app points at, and the phones behind it."""

    def __init__(self, registry: DeviceRegistry, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
                 api_key: str = "", context: int = DEFAULT_CONTEXT, backend: str = DEFAULT_BACKEND,
                 serial: str = ""):
        self.registry = registry
        self.host = host
        self.port = port
        self.api_key = api_key
        # Bound to loopback, a foreign Host header can only be an attempt to
        # reach us from a browser; bound deliberately wider, it is the point.
        self.local_only = host in LOCAL_HOSTS
        self.router = Router(registry, context=context, backend=backend, serial=serial)
        self._server: Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/v1"

    def start(self) -> str:
        if self._server is not None:
            return self.url
        self._server = Server((self.host, self.port), Handler)
        self._server.gateway = self
        self.port = self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True,
                                        name="jiezhi-gateway")
        self._thread.start()
        return self.url

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None


def containers_present() -> bool:
    """Is something on this machine likely to run an app inside a container?

    It matters because a container cannot reach the desktop on 127.0.0.1 — that
    address is the container itself — and the app reports only a network error.
    """
    return any(Path(p).exists() for p in
               ("/var/run/docker.sock", "/sys/class/net/docker0", "/run/podman/podman.sock"))


def advice(host: str, port: int, key: str, containers: bool) -> list[str]:
    """What to paste into a third-party app, for the setups that are plausible."""
    reachable = "127.0.0.1" if host == "0.0.0.0" else host
    lines = [f"JieZhi is serving at http://{reachable}:{port}/v1 — point a third-party app there."]
    if host in LOCAL_HOSTS:
        if containers:
            lines += ["",
                      "Docker is running here, and an app inside a container cannot reach",
                      "127.0.0.1 on your desktop. If that is where your app lives, either",
                      "start its container with --network=host, or stop this and run:",
                      f"  jiezhi-gateway --host 0.0.0.0 --api-key jiezhi --port {port}",
                      f"then point the app at http://host.docker.internal:{port}/v1 with that key."]
    else:
        lines += [f"An app in a container should use http://host.docker.internal:{port}/v1",
                  f"Send the key {key!r} as a bearer token; it is required on this address."]
    return lines


def main(argv=None) -> int:
    """Run the endpoint on its own, for apps that only need the phone.

    The server starts whether or not a phone is attached, so an app can be
    pointed at it and verified first; a paired phone is picked up as soon as
    it appears.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="jiezhi-gateway",
                                     description="Serve a connected phone's NPU over an OpenAI-compatible API.")
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind (default: loopback only)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default: {DEFAULT_PORT})")
    parser.add_argument("--api-key", default="", help="require this key; apps send it as a bearer token")
    parser.add_argument("--context", type=int, default=DEFAULT_CONTEXT,
                        help=f"context size used when loading a model ({CONTEXT_RANGE[0]}-{CONTEXT_RANGE[1]})")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, choices=["npu", "cpu"], help="phone backend to request")
    parser.add_argument("--serial", default="", help="serve only this phone")
    args = parser.parse_args(argv)
    if not CONTEXT_RANGE[0] <= args.context <= CONTEXT_RANGE[1]:
        parser.error(f"--context must be between {CONTEXT_RANGE[0]} and {CONTEXT_RANGE[1]}.")
    if args.host not in LOCAL_HOSTS and not args.api_key:
        parser.error("--host beyond loopback puts the phone on the network. Pass a key too, "
                     f"for example: --host {args.host} --api-key jiezhi")

    registry = DeviceRegistry()
    gateway = Gateway(registry, host=args.host, port=args.port, api_key=args.api_key,
                      context=args.context, backend=args.backend, serial=args.serial)
    try:
        gateway.start()
    except OSError as error:
        print(f"Could not listen on {args.host}:{args.port} — {error}")
        print("Something else may already hold that port; pick another with --port.")
        return 1

    for line in advice(args.host, gateway.port, args.api_key, containers_present()):
        print(line)
    gateway.router.refresh(force=True)
    models = gateway.router.catalog()
    connected = registry.connected()
    if connected:
        print(f"Connected: {', '.join(d.title for d in connected)}")
    for entry in models:
        print(f"  {entry.id}")
    if not models:
        print(gateway.router.trouble or
              "No phone connected yet. Attach a paired phone and it will appear; "
              "pair it in the desktop app first if you have not.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        gateway.stop()
        registry.disconnect_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
