"""Exercise a project conversation with an XLSX reference on the phone."""
import json
from pathlib import Path
from openpyxl import Workbook
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QListWidgetItem
from jiezhi.gui import Window
from jiezhi.projects import Projects
from jiezhi.attachments import extract
out=Path('artifacts/v03');out.mkdir(exist_ok=True)
book=Workbook();s=book.active;s.title='Budget';s.append(['Milestone','Budget (EUR)']);s.append(['Willow pilot',742]);s.append(['Oak pilot',1250]);book.save(out/'project-budget.xlsx')
app=QApplication([]);app.setStyle('Fusion');Window.start_scan=lambda s:None
w=Window();w.show();w.project_store=Projects(out/'test-projects')
project=w.project_store.create('Launch planning · QA');project['documents']=[extract(out/'project-budget.xlsx')];w.project_store.save(project);w.reload_projects();w.project_list.setCurrentRow(0);w.use_project()
result={};stage=['connect']
def failed(error):result['error']=error;stage[0]='done'
w.failed=failed
def watch():
    global result
    if not w.busy:
        if stage[0]=='connect':
            stage[0]='connected';w.run_job(lambda _:w.client.connect('f12b60cc'),w.update_status)
        elif stage[0]=='connected':
            w.composer.setPlainText('What is the budget in EUR for the Willow pilot in the project spreadsheet? Answer in one sentence.')
            stage[0]='reply';QTest.mouseClick(w.send_button,Qt.MouseButton.LeftButton)
        elif stage[0]=='reply' and not w.generating and w.messages and w.messages[-1]['role']=='assistant':
            result={'reply':w.messages[-1]['content'],'model':w.current_status['loaded_name'],'project_refs':len(w.messages[0].get('attachments',[])),'metrics':w.metrics.text()}
            assert '742' in result['reply'],result
            w.nav.setCurrentRow(0);app.processEvents();w.grab().save(str(out/'spreadsheet-chat.png'))
            w.nav.setCurrentRow(5);w.show_project(w.project_list.currentItem());app.processEvents();w.grab().save(str(out/'projects.png'))
            # Remove only this test conversation from real history; the report retains its answer.
            from jiezhi.client import DATA
            (DATA/'conversations'/f'{w.conversation_id}.json').unlink(missing_ok=True)
            stage[0]='done'
        if stage[0]=='done' and not w.workers:
            (out/'project-hardware.json').write_text(json.dumps(result,indent=2));print(result);w.close();app.quit();return
    QTimer.singleShot(100,watch)
QTimer.singleShot(500,watch);QTimer.singleShot(90000,lambda:failed('Timed out'))
app.exec()
