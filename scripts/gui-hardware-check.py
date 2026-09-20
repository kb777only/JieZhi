"""Exercise the real GUI against an already paired phone with a loaded model."""
import json
from pathlib import Path
import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from jiezhi.gui import Window

app = QApplication([]); app.setStyle("Fusion")
window = Window(); window.initial_scan = False; window.show()
result = {}; stage = ["connect"]

def failed(message):
    result["error"] = message; stage[0] = "error"
window.failed = failed

def connected(status):
    assert status.get("loaded_id"), "A paired phone and loaded model are required"
    window.update_status(status); window.nav.setCurrentRow(0)
    result["model"] = status["loaded_name"]
    QTimer.singleShot(200, send)

def connect():
    if window.busy:
        QTimer.singleShot(100, connect); return
    window.run_job(lambda _: window.client.connect(sys.argv[1]), connected)

def send():
    window.composer.setPlainText("Reply with one short sentence: what is 2 + 2?")
    QTest.mouseClick(window.send_button, Qt.MouseButton.LeftButton)
    stage[0] = "stream"

def watch():
    if stage[0] == "stream" and not window.busy and not window.generating:
        reply = window.messages[-1]["content"]
        assert "4" in reply, reply
        result["reply"] = reply; result["metrics"] = window.metrics.text()
        result["history_saved"] = window.history.count() > 0
        window.grab().save("artifacts/desktop-1.7B.png")
        window.nav.setCurrentRow(1); app.processEvents()
        window.grab().save("artifacts/desktop-models.png")
        item = window.history.item(0); window.open_chat(item)
        assert window.messages[-1]["content"] == reply
        result["history_reopened"] = True
        stage[0] = "done"
    if stage[0] in ("done", "error") and not window.workers:
        Path("artifacts/gui-hardware-check.json").write_text(json.dumps(result, indent=2))
        window.close(); app.quit(); return
    QTimer.singleShot(100, watch)

QTimer.singleShot(300, connect); QTimer.singleShot(400, watch)
QTimer.singleShot(60_000, lambda: failed("GUI hardware test timed out"))
app.exec()
print(json.dumps(result, indent=2))
if "error" in result:
    sys.exit(1)
