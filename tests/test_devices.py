import pytest

from jiezhi.devices import AVAILABLE, INCOMPATIBLE, READY, UNAUTHORIZED, DeviceRegistry, capability


class FakeClient:
    def __init__(self):
        self.serial = ""; self.port = 0; self.connected = []
    def connect(self, serial):
        self.serial = serial; self.port = 41000; self.connected.append(serial)
        return {"state": "idle"}
    def disconnect(self):
        self.port = 0


def registry(attached, props=None):
    props = props or {}
    calls = []
    def probe(*args, serial="", timeout=30):
        calls.append((args, serial))
        return props.get((serial, args[-1]), "")
    reg = DeviceRegistry(factory=FakeClient, probe=probe, enumerate_devices=lambda: attached)
    return reg, calls


ELITE = {("A", "ro.soc.model"): "SM8750", ("A", "ro.product.model"): "25010PN30G"}


def test_scan_reports_identity_and_capability():
    reg, _ = registry([{"serial": "A", "state": "device", "description": "A usb:1"}], ELITE)
    device, = reg.scan()
    assert (device.soc, device.soc_label, device.htp) == ("SM8750", "Snapdragon 8 Elite", "v79")
    assert device.supported and device.state == AVAILABLE
    assert device.title == "25010PN30G"


def test_unsupported_soc_is_recorded_not_refused():
    props = {("B", "ro.soc.model"): "SM8650", ("B", "ro.product.model"): "Pixel"}
    reg, _ = registry([{"serial": "B", "state": "device", "description": "B usb:1"}], props)
    device, = reg.scan()
    assert device.state == INCOMPATIBLE and not device.supported
    assert device.soc_label == "SM8650"
    assert reg.usable() == []


def test_unauthorized_phone_is_not_probed():
    reg, calls = registry([{"serial": "C", "state": "unauthorized", "description": "C usb:1"}])
    device, = reg.scan()
    assert device.state == UNAUTHORIZED and calls == []


def test_hardware_is_read_once_per_serial():
    reg, calls = registry([{"serial": "A", "state": "device", "description": "A usb:1"}], ELITE)
    reg.scan(); reg.scan(); reg.scan()
    assert len(calls) == 2  # soc and product model, from the first scan only


def test_several_phones_each_get_their_own_client():
    props = {**ELITE, ("D", "ro.soc.model"): "SM8750", ("D", "ro.product.model"): "Second"}
    attached = [{"serial": "A", "state": "device", "description": "A usb:1"},
                {"serial": "D", "state": "device", "description": "D usb:2"}]
    reg, _ = registry(attached, props)
    reg.scan()
    reg.connect("A"); reg.connect("D")
    assert reg.client("A") is not reg.client("D")
    assert reg.client("A").connected == ["A"] and reg.client("D").connected == ["D"]
    assert {d.serial for d in reg.connected()} == {"A", "D"}
    assert reg.get("A").state == READY


def test_disconnect_returns_a_phone_to_available():
    reg, _ = registry([{"serial": "A", "state": "device", "description": "A usb:1"}], ELITE)
    reg.scan(); reg.connect("A")
    reg.disconnect("A")
    assert reg.get("A").state == AVAILABLE and reg.connected() == []


def test_rescan_keeps_an_open_session_marked_ready():
    reg, _ = registry([{"serial": "A", "state": "device", "description": "A usb:1"}], ELITE)
    reg.scan(); reg.connect("A")
    device, = reg.scan()
    assert device.state == READY


def test_forget_drops_the_cached_hardware_reading():
    reg, calls = registry([{"serial": "A", "state": "device", "description": "A usb:1"}], ELITE)
    reg.scan(); reg.forget("A"); reg.scan()
    assert len(calls) == 4


def test_capability_of_an_empty_reading():
    assert capability("") == {"soc": "", "label": "Unknown SoC", "htp": "", "supported": False}
