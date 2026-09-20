"""Observe live phone metrics while another authorized test runs inference."""
import json,time
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from jiezhi.gui import Window
app=QApplication([]);app.setStyle('Fusion');Window.start_scan=lambda s:None
w=Window();w.show();samples=[];started=time.monotonic();original=w.telemetry_panel.receive

def receive(sample):
    samples.append(sample);original(sample)
    if sample['values']['tokens'] and sample['values']['tokens']>0:
        w.grab().save('artifacts/v04/live-telemetry.png')
w.telemetry_panel.receive=receive

def connect():
    if w.busy:QTimer.singleShot(100,connect);return
    w.run_job(lambda _:w.client.connect('f12b60cc'),w.update_status)
def finish():
    if w.workers:QTimer.singleShot(100,finish);return
    Path('artifacts/v04/telemetry-samples.json').write_text(json.dumps(samples,indent=2))
    w.grab().save('artifacts/v04/telemetry-current.png')
    print(json.dumps({'samples':len(samples),'live_rate_samples':sum((s['values']['tokens'] or 0)>0 for s in samples),'cpu_samples':sum(s['values']['cpu'] is not None for s in samples),'temperatures':samples[-1]['sensors'] if samples else []},indent=2))
    w.close();app.quit()
QTimer.singleShot(400,connect);QTimer.singleShot(90_000,finish)
app.exec()
