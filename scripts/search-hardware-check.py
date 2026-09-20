"""Exercise discovery with live Hub metadata and read-only phone detection. No inference."""
import json,time
from pathlib import Path
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QApplication
from jiezhi.gui import Window
app=QApplication([]);app.setStyle('Fusion');Window.start_scan=lambda s:None
w=Window();w.heartbeat.stop();w.telemetry_panel.timer.stop();w.show();w.nav.setCurrentRow(4)
started=time.monotonic()
def check():
    if time.monotonic()-started>90:
        print('Timed out',flush=True);w.close();app.exit(1);return
    if w.busy or w.workers or not w.hub_file_data:QTimer.singleShot(200,check);return
    w.grab().save('artifacts/v05/model-search.png')
    result={'phone':w.hub_phone,'repositories':w.hub_repos.count(),'files':w.hub_files.count(),
            'top_repository':w.hub_repos.item(0).text(),'top_file':w.hub_files.item(0).text(),
            'assessment':w.hub_files.item(0).data(Qt.ItemDataRole.UserRole+1),'window_size':[w.width(),w.height()]}
    Path('artifacts/v05/search-hardware.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)
    w.close();app.quit()
QTimer.singleShot(1000,check);app.exec()
