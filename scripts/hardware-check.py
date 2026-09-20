"""Run against an already paired, loaded phone. No simulator or CPU substitution."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import struct
import time

from jiezhi.client import Client, adb

parser = argparse.ArgumentParser()
parser.add_argument("serial")
parser.add_argument("--seconds", type=int, default=600)
args = parser.parse_args()
c = Client()
status = c.connect(args.serial)
assert status.get("loaded_id"), "Pair and load an NPU model first"
assert status["requested_backend"] == "npu"
report = {"device": status["phone"], "soc": status["soc"], "model": status["loaded_name"], "checks": {}, "runs": []}
output = Path("artifacts/hardware-check.json"); output.parent.mkdir(exist_ok=True)

def save():
    output.write_text(json.dumps(report, indent=2))

# Reject unauthenticated requests.
response = c.session.get(c.url("/status"), timeout=5)
assert response.status_code == 401
report["checks"]["unauthenticated_rejected"] = True

# Prove cancellation returns a terminal event, and the next request still works.
events = []
stopped = [False]
def cancel_event(event):
    events.append(event)
    if event["type"] == "token" and not stopped[0] and len(events) >= 12:
        stopped[0] = True; c.cancel()
c.chat([{"role": "user", "content": "Write a detailed 1000-word guide to learning Python programming."}], cancel_event, max_tokens=1024)
assert stopped[0] and events[-1]["type"] == "done" and events[-1]["cancelled"]
report["checks"]["cancellation"] = events[-1]

# A conflicting load must fail while generation owns the runtime.
tested = [False]
def conflict(event):
    if event["type"] == "token" and not tested[0]:
        tested[0] = True
        try:
            c.load(status["loaded_id"])
        except RuntimeError as error:
            assert "busy" in str(error).lower()
            report["checks"]["concurrent_load_rejected"] = True
        else:
            raise AssertionError("Concurrent model load was accepted")
c.chat([{"role": "user", "content": "List ten useful Linux commands with explanations."}], conflict, max_tokens=200)

# Integrity rejection on the real Android model store; clean up only test data.
payload = b"GGUF" + struct.pack("<IQQ", 3, 0, 0) + b"JieZhi integrity probe"
fake_id = hashlib.sha256(payload + b"corrupted").hexdigest()
c.request("POST", "/uploads", json={"id": fake_id, "name": "integrity-probe.gguf", "size": len(payload)})
r = c.session.put(c.url(f"/uploads/{fake_id}"), headers={**c.headers(), "X-Offset": "0"}, data=payload, timeout=10)
assert r.ok
try:
    c.request("POST", "/commit", json={"id": fake_id})
except RuntimeError as error:
    assert "SHA-256" in str(error)
    report["checks"]["corrupt_upload_rejected"] = True
else:
    raise AssertionError("Corrupt upload accepted")
c.request("DELETE", f"/models/{fake_id}")

# Drop and recreate our own USB tunnel, retaining the phone model and pairing.
c.disconnect(); reconnect = c.connect(args.serial)
assert reconnect["loaded_id"] == status["loaded_id"]
report["checks"]["usb_tunnel_reconnection"] = True
save(); print("Functional hardware checks passed", flush=True)

start = time.monotonic()
while time.monotonic() - start < args.seconds:
    events = []; wall_start = time.monotonic(); first = [None]
    def event(e):
        if e["type"] == "token" and first[0] is None:
            first[0] = time.monotonic() - wall_start
        events.append(e)
    c.chat([{"role": "user", "content": "Explain why the sky looks blue, then describe a simple experiment about light."}], event, max_tokens=256)
    assert events[-1]["type"] == "done" and events[-1]["profile"]["tokens"] > 0
    profile = {**events[-1]["profile"], "wall_seconds": time.monotonic() - wall_start,
        "host_first_token_seconds": first[0], "thermal_status": c.status()["thermal_status"]}
    report["runs"].append(profile)
    report["elapsed_seconds"] = time.monotonic() - start
    save()
    print(f"Run {len(report['runs'])}: {profile['tokens_per_second']:.1f} tok/s; thermal {profile['thermal_status']}; {report['elapsed_seconds']:.0f}s elapsed", flush=True)
    time.sleep(2)
rates = [r["tokens_per_second"] for r in report["runs"]]
report["summary"] = {"runs": len(rates), "median_tokens_per_second": statistics.median(rates),
    "min_tokens_per_second": min(rates), "max_tokens_per_second": max(rates),
    "max_thermal_status": max(r["thermal_status"] for r in report["runs"])}
save(); print(report["summary"], flush=True)
c.disconnect()
