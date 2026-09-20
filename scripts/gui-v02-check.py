"""Exercise document chat and public Hub browsing with the physical paired phone."""
import json
import sys
from pathlib import Path
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from jiezhi.gui import Window

out = Path('artifacts/v02'); out.mkdir(exist_ok=True)
fixture = out / 'project-brief.md'
fixture.write_text('# JieZhi test brief\nThe launch code is WILLOW-742.\nThe handoff date is 14 November 2026.\nThe owner is the robotics team.\n')
app = QApplication([]); app.setStyle('Fusion')
Window.start_scan = lambda self: None
window = Window(); window.show(); result = {}; stage = ['connect']
def failure(message):
    result['error'] = message; stage[0] = 'error'
window.failed = failure

def connect():
    if window.busy: QTimer.singleShot(100, connect); return
    def done(status):
        if not status.get('loaded_id'): failure('Expected a paired phone and loaded model'); return
        window.update_status(status); result['model'] = status['loaded_name']; result['context'] = status['context_size']
        stage[0] = 'attach-ready'
    window.run_job(lambda _: window.client.connect(sys.argv[1]), done)

def watch():
    if not window.busy:
        if stage[0] == 'attach-ready':
            stage[0] = 'attached'; window.add_attachments([fixture])
        elif stage[0] == 'attached':
            assert len(window.pending_attachments) == 1
            window.composer.setPlainText('Using the attached brief, state the launch code and handoff date in one short sentence.')
            QTest.mouseClick(window.send_button, Qt.MouseButton.LeftButton); stage[0] = 'stream'
        elif stage[0] == 'stream' and not window.generating:
            reply = window.messages[-1]['content']
            if 'WILLOW-742' not in reply or 'November' not in reply:
                failure(f'Wrong document answer: {reply}'); return
            result.update(reply=reply, metrics=window.metrics.text(), context_note=window.attachment_label.text())
            window.grab().save(str(out / 'host-document-chat.png'))
            window.open_chat(window.history.item(0))
            assert window.messages[0]['attachments'][0]['text'] == fixture.read_text()
            result['attachment_history_reopened'] = True
            window.nav.setCurrentRow(4); window.hub_query.setText('Qwen3-0.6B'); window.hub_search(); stage[0] = 'search'
        elif stage[0] == 'search':
            assert window.hub_repos.count() > 0
            result['hub_search_results'] = window.hub_repos.count()
            window.hub_query.setText('unsloth/Qwen3-0.6B-GGUF'); window.hub_open_repo(); stage[0] = 'files'
        elif stage[0] == 'files':
            assert window.hub_files.count() > 0
            result['hub_gguf_files'] = window.hub_files.count()
            window.grab().save(str(out / 'host-hub.png')); stage[0] = 'done'
        if stage[0] in ('done', 'error') and not window.workers:
            (out / 'gui-hardware-check.json').write_text(json.dumps(result, indent=2))
            window.close(); app.quit(); return
    QTimer.singleShot(100, watch)
QTimer.singleShot(300, connect); QTimer.singleShot(400, watch)
QTimer.singleShot(120000, lambda: failure('GUI test timed out'))
app.exec(); print(json.dumps(result,indent=2)); sys.exit(1 if 'error' in result else 0)
