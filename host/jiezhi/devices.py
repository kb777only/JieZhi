"""Registry of attached phones: identity, capability and connection state.

The GUI drives a single `Client` whose serial, port and token are the only
record that a phone exists. Anything facing outward — a third-party endpoint,
and later the aggregated "JieZhi - Max" accelerator — has to speak about
several phones at once, so that record moves here and becomes explicit.

Nothing in this module starts the Android client or loads a model; it reads
hardware through ADB the way `recommendations.phone_profile` does, and hands
out a `Client` per serial for the work that does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import threading

from .client import Client, adb, devices as adb_devices

# Hexagon capability per SoC. The host cannot run a Qualcomm model on an
# unlisted chip, but "unlisted" is not the same as "refused forever" — the
# registry records the finding and lets the caller decide.
SOC_CAPABILITY = {
    "SM8750": {"label": "Snapdragon 8 Elite", "htp": "v79", "supported": True},
}

OFFLINE = "offline"          # adb sees the serial but not as a usable device
UNAUTHORIZED = "unauthorized"  # USB debugging not accepted on the phone
INCOMPATIBLE = "incompatible"  # attached, readable, but the NPU is not one we drive
AVAILABLE = "available"      # usable, no session open
READY = "ready"              # paired session open on this host


def capability(soc: str) -> dict:
    """Describe a SoC string from `ro.soc.model` without judging the phone."""
    key = (soc or "").strip().upper()
    known = SOC_CAPABILITY.get(key)
    if known:
        return {"soc": key, **known}
    return {"soc": key, "label": soc.strip() or "Unknown SoC", "htp": "", "supported": False}


@dataclass
class Device:
    """One attached phone as the host currently understands it."""

    serial: str
    state: str = OFFLINE
    soc: str = ""
    soc_label: str = ""
    htp: str = ""
    supported: bool = False
    name: str = ""
    description: str = ""
    error: str = ""
    status: dict = field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.name or self.serial

    def summary(self) -> dict:
        """Stable, JSON-safe view — what an outward-facing caller may see."""
        return {"serial": self.serial, "name": self.title, "soc": self.soc,
                "soc_label": self.soc_label, "htp": self.htp,
                "supported": self.supported, "state": self.state}


class DeviceRegistry:
    """Tracks every attached phone and owns one `Client` per serial.

    `probe` and `enumerate` are injected so the registry is testable without
    a phone; both default to the ADB helpers in `client`.
    """

    def __init__(self, factory=Client, probe=adb, enumerate_devices=adb_devices):
        self._factory = factory
        self._probe = probe
        self._enumerate = enumerate_devices
        self._lock = threading.RLock()
        self._clients: dict[str, Client] = {}
        self._devices: dict[str, Device] = {}
        self._hardware: dict[str, dict] = {}  # serial -> capability, read once per serial

    def adopt(self, serial: str, client: Client) -> None:
        """Register a `Client` the caller already owns, so state has one home."""
        with self._lock:
            self._clients[serial] = client

    def client(self, serial: str) -> Client:
        with self._lock:
            if serial not in self._clients:
                self._clients[serial] = self._factory()
            return self._clients[serial]

    def scan(self) -> list[Device]:
        """Refresh every attached serial. Hardware is read once per serial."""
        found = []
        for entry in self._enumerate():
            serial = entry["serial"]
            device = Device(serial=serial, description=entry.get("description", ""))
            if entry.get("state") != "device":
                device.state = UNAUTHORIZED if entry.get("state") == "unauthorized" else OFFLINE
            else:
                self._describe(device)
            with self._lock:
                opened = self._clients.get(serial)
            if device.state == AVAILABLE and opened is not None and opened.port:
                device.state = READY
            found.append(device)
        with self._lock:
            self._devices = {d.serial: d for d in found}
        return found

    def _describe(self, device: Device) -> None:
        serial = device.serial
        hardware = self._hardware.get(serial)
        if hardware is None:
            try:
                soc = self._probe("shell", "getprop", "ro.soc.model", serial=serial, timeout=10)
                name = self._probe("shell", "getprop", "ro.product.model", serial=serial, timeout=10)
            except Exception as error:
                device.state = OFFLINE
                device.error = str(error)
                return
            hardware = {**capability(soc), "name": name.strip()}
            self._hardware[serial] = hardware
        device.soc = hardware["soc"]
        device.soc_label = hardware["label"]
        device.htp = hardware["htp"]
        device.supported = hardware["supported"]
        device.name = hardware["name"]
        device.state = AVAILABLE if device.supported else INCOMPATIBLE

    def all(self) -> list[Device]:
        with self._lock:
            return list(self._devices.values())

    def get(self, serial: str) -> Device | None:
        with self._lock:
            return self._devices.get(serial)

    def usable(self) -> list[Device]:
        """Phones whose NPU this host can actually drive, connected or not."""
        return [d for d in self.all() if d.supported]

    def connected(self) -> list[Device]:
        with self._lock:
            return [d for d in self._devices.values()
                    if (client := self._clients.get(d.serial)) is not None and client.port]

    def connect(self, serial: str) -> dict:
        client = self.client(serial)
        result = client.connect(serial)
        device = self.get(serial)
        if device is not None:
            device.state = READY
            device.status = result if isinstance(result, dict) else {}
        return result

    def disconnect(self, serial: str) -> None:
        with self._lock:
            client = self._clients.get(serial)
        if client is not None:
            client.disconnect()
        device = self.get(serial)
        if device is not None and device.state == READY:
            device.state = AVAILABLE if device.supported else INCOMPATIBLE

    def disconnect_all(self) -> None:
        with self._lock:
            serials = list(self._clients)
        for serial in serials:
            self.disconnect(serial)

    def forget(self, serial: str) -> None:
        """Drop a phone entirely, including its cached hardware reading."""
        self.disconnect(serial)
        with self._lock:
            self._clients.pop(serial, None)
            self._devices.pop(serial, None)
            self._hardware.pop(serial, None)
