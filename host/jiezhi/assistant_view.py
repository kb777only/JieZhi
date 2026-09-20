import json
from pathlib import Path
import shlex
import threading

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QHBoxLayout, QComboBox, QCheckBox, QPlainTextEdit, QListWidget, QFileDialog, QDialog, QVBoxLayout, QDialogButtonBox, QPushButton, QInputDialog
from .assistant import Assistant
from .pc_tools import Tools, Policy, MODES, Cancelled, sensitive
from .client import DATA, read_json, save_json


class AssistantWorker(QThread):
    event=Signal(object); approval=Signal(object); result=Signal(str); error=Signal(str)
    def __init__(self,client,policy,request,context,instructions='',undo_id=None):
        super().__init__();self.client=client;self.policy=policy;self.request=request;self.context=context
        self.instructions=instructions;self.undo_id=undo_id;self.cancelled=threading.Event()
    def approve(self,proposal):
        response={'event':threading.Event(),'approved':False,'proposal':proposal}
        self.approval.emit(response)
        while not response['event'].wait(.1):
            if self.cancelled.is_set():return False
        return response['approved'] and not self.cancelled.is_set()
    def run(self):
        try:
            tools=Tools(self.policy,self.approve,self.event.emit,self.cancelled)
            if self.undo_id:answer=json.dumps(tools.undo(self.undo_id),indent=2)
            else:answer=Assistant(self.client,tools,self.context,self.event.emit).run(self.request,self.instructions)
            self.result.emit(answer)
        except Cancelled as e:self.result.emit(str(e))
        except Exception as e:self.error.emit(str(e))


class AssistantView:
    def build_assistant(self):
        from .gui import button,label
        self.pc_worker=None;self.approval_dialog=None;self.pending_approval=None
        settings=read_json(DATA/'assistant-settings.json',{})
        layout=self.page('Your PC, with a helping hand.', 'Investigate crashes, inspect your system and review proposed repairs. Reasoning runs on your phone; approved tools run on this PC.')
        row=QHBoxLayout();row.addWidget(label('Access mode'))
        self.access_mode=QComboBox()
        for key,title in MODES.items():self.access_mode.addItem(title,key)
        self.access_mode.setCurrentIndex(max(0,self.access_mode.findData(settings.get('mode','confirm'))));row.addWidget(self.access_mode)
        self.allow_admin=QCheckBox('Allow administrator requests');self.allow_admin.setChecked(False);row.addWidget(self.allow_admin);row.addStretch();layout.addLayout(row)
        self.pc_mode_note=label('','muted',True);layout.addWidget(self.pc_mode_note)
        self.pc_roots=QListWidget();self.pc_roots.setMaximumHeight(75);self.pc_roots.addItems(settings.get('roots',[]));layout.addWidget(self.pc_roots)
        row=QHBoxLayout();row.addWidget(button('Allow folder…',self.pc_add_root));row.addWidget(button('Remove selected folder',self.pc_remove_root));row.addWidget(button('PC overview',self.pc_overview));row.addWidget(button('Restore a file edit…',self.pc_undo));layout.addLayout(row)
        self.pc_output=QPlainTextEdit();self.pc_output.setReadOnly(True);self.pc_output.setPlaceholderText('Diagnostic steps, approval decisions, command output and repair results appear here.');layout.addWidget(self.pc_output,1)
        history_row=QHBoxLayout();history_row.addWidget(button('Previous investigations…',self.pc_history));history_row.addStretch();layout.addLayout(history_row)
        self.pc_request=QPlainTextEdit();self.pc_request.setMaximumHeight(85);self.pc_request.setPlaceholderText('Example: Program X crashes on startup. Find the cause, propose a fix, and verify it.');layout.addWidget(self.pc_request)
        row=QHBoxLayout();self.pc_state=label('Ready · load a model with at least 4096 context tokens','muted',True);row.addWidget(self.pc_state,1)
        self.pc_stop=button('Stop',self.stop_assistant);self.pc_stop.setEnabled(False);row.addWidget(self.pc_stop)
        self.pc_start=button('Start investigation',self.start_assistant,True);row.addWidget(self.pc_start);layout.addLayout(row)
        layout.addWidget(label('Only selected folders and the active project’s linked folders are readable/editable through file tools. System diagnostics include OS, apps, processes and recent user logs. Logs/configuration may contain private data; common secrets are redacted before model use. Commands require separate approval and can act beyond selected folders.','muted',True))
        self.access_mode.currentIndexChanged.connect(self.pc_settings_changed);self.allow_admin.toggled.connect(self.pc_settings_changed);self.pc_mode_description()
    def pc_mode_description(self):
        descriptions={'inspect':'Read-only: diagnostics and selected-file reads. All writes and arbitrary commands are blocked.',
            'confirm':'Diagnose automatically. Every file edit, command and rollback requires your approval.',
            'workspace':'Reversible file edits inside allowed folders can run automatically. Commands, startup files and rollback still require approval.'}
        self.pc_mode_note.setText(descriptions[self.access_mode.currentData()])
    def pc_settings_changed(self):
        self.pc_mode_description()
        save_json(DATA/'assistant-settings.json',{'mode':self.access_mode.currentData(),'roots':[self.pc_roots.item(i).text() for i in range(self.pc_roots.count())]})
    def pc_add_root(self):
        if self.pc_worker:return
        path=QFileDialog.getExistingDirectory(self,'Allow Assistant access to this folder')
        if path:
            if sensitive(Path(path)):self.failed('Select a folder outside credential stores.');return
            existing=[self.pc_roots.item(i).text() for i in range(self.pc_roots.count())]
            if str(Path(path).resolve()) not in existing:self.pc_roots.addItem(str(Path(path).resolve()))
            self.pc_settings_changed()
    def pc_remove_root(self):
        if self.pc_worker:return
        self.pc_roots.takeItem(self.pc_roots.currentRow());self.pc_settings_changed()
    def pc_policy(self):
        roots=[Path(self.pc_roots.item(i).text()) for i in range(self.pc_roots.count())]
        if self.active_project:roots.extend(Path(p) for p in self.active_project.get('folders',[]))
        return Policy(self.access_mode.currentData(),tuple(dict.fromkeys(roots)),self.allow_admin.isChecked())
    def pc_overview(self):
        if self.busy:return
        try:policy=self.pc_policy()
        except Exception as e:self.failed(str(e));return
        self.run_job(lambda _:Tools(policy).inventory(),lambda info:self.pc_output.setPlainText(json.dumps(info,indent=2,ensure_ascii=False)),'Reading PC overview…')
    def start_assistant(self,undo_id=None):
        if self.busy:return
        if not undo_id and not self.current_status.get('loaded_id'):self.failed('Connect your phone and load a model first.');return
        request=self.pc_request.toPlainText().strip()
        if not request and not undo_id:return
        try:policy=self.pc_policy()
        except Exception as e:self.failed(str(e));return
        context=self.current_status.get('context_size',2048)
        if not undo_id and context<4096:self.failed('In Phone models, set Context to 4096 or more and reload the model.');return
        instructions=self.active_project.get('instructions','') if self.active_project else ''
        worker=AssistantWorker(self.client,policy,request,context,instructions,undo_id)
        self.pc_worker=worker;self.workers.add(worker);self.busy=True;self.pc_output.clear()
        self.pc_output.appendPlainText(f'Mode: {MODES[policy.mode]}\nAllowed folders: '+(', '.join(map(str,policy.roots)) or 'None')+'\n')
        self.pc_start.setEnabled(False);self.pc_stop.setEnabled(True);self.access_mode.setEnabled(False);self.allow_admin.setEnabled(False)
        worker.event.connect(self.pc_event);worker.approval.connect(self.pc_approval)
        worker.result.connect(lambda answer:self.pc_output.appendPlainText('\nMODEL ASSESSMENT · CHECK THE RECORDED EVIDENCE\n'+answer))
        worker.error.connect(lambda error:self.pc_output.appendPlainText('\nStopped with error: '+error))
        def finish():
            self.dismiss_approval();self.busy=False;self.pc_worker=None;self.workers.discard(worker);worker.deleteLater()
            self.pc_start.setEnabled(True);self.pc_stop.setEnabled(False);self.access_mode.setEnabled(True);self.allow_admin.setEnabled(True)
            self.pc_state.setText('Finished · review the result and action log');self.statusBar().showMessage('PC Assistant finished. Action log saved locally.')
        worker.finished.connect(finish);worker.start()
    def pc_event(self,event):
        kind=event['kind']
        if kind=='thinking':self.pc_state.setText(f"Step {event['step']} · Reasoning on phone");return
        if kind=='result':self.pc_output.appendPlainText(f"\n{event['tool']} → {event['result']}")
        elif kind=='tool':self.pc_output.appendPlainText(f"\n▶ {event['tool']} · {event.get('reason','')}")
        elif kind in {'blocked','tool_error','denied','approved','rollback'}:self.pc_output.appendPlainText(json.dumps(event,ensure_ascii=False))
        elif kind=='invalid_model_reply':self.pc_output.appendPlainText('Model returned an invalid instruction; asking it to correct the format.')
    def pc_approval(self,response):
        if not self.pc_worker or self.pc_worker.cancelled.is_set():response['event'].set();return
        self.pending_approval=response;proposal=response['proposal']
        dialog=QDialog(self);self.approval_dialog=dialog;dialog.setWindowTitle('Review Assistant action');dialog.resize(850,600)
        layout=QVBoxLayout(dialog)
        from .gui import label
        layout.addWidget(label('Approve this action once?','title',True));layout.addWidget(label(proposal.get('reason',''),'muted',True));layout.addWidget(label(proposal['risk'],'badge',True))
        view=QPlainTextEdit();view.setReadOnly(True)
        if proposal['tool']=='run_command':text=('ADMINISTRATOR\n' if proposal['admin'] else '')+'Working directory: '+proposal['cwd']+'\n\n'+shlex.join(proposal['argv'])
        else:text=proposal.get('path','')+'\n\n'+proposal.get('diff','')
        view.setPlainText(text);layout.addWidget(view,1)
        buttons=QDialogButtonBox();reject=buttons.addButton('Reject',QDialogButtonBox.ButtonRole.RejectRole);approve=buttons.addButton('Approve once',QDialogButtonBox.ButtonRole.AcceptRole)
        reject.setDefault(True);approve.setAutoDefault(False);layout.addWidget(buttons)
        def finish(accepted):
            response['approved']=accepted;response['event'].set();self.pending_approval=None;self.approval_dialog=None
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);dialog.accepted.connect(lambda:finish(True));dialog.rejected.connect(lambda:finish(False));dialog.show()
        self.pc_state.setText('Waiting for your approval · no action has run')
    def dismiss_approval(self):
        if self.pending_approval:self.pending_approval['approved']=False;self.pending_approval['event'].set();self.pending_approval=None
        if self.approval_dialog:self.approval_dialog.reject();self.approval_dialog=None
    def stop_assistant(self):
        if not self.pc_worker:return
        self.pc_worker.cancelled.set();self.dismiss_approval();self.pc_state.setText('Stopping… partial command side effects may need inspection')
        # Separate session avoids waiting for the model stream to finish.
        from .gui import Worker
        worker=Worker(lambda _:self.client.cancel());self.workers.add(worker)
        def finish():self.workers.discard(worker);worker.deleteLater()
        worker.finished.connect(finish);worker.start()
    def pc_undo(self):
        if self.busy:return
        backups=sorted((DATA/'assistant/backups').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        if not backups:self.pc_state.setText('No file-edit backups yet.');return
        choices=[p.stem+' · '+read_json(p,{}).get('path','') for p in backups[:30]]
        selected,ok=QInputDialog.getItem(self,'Restore an Assistant edit','Choose a file edit to review and restore:',choices,0,False)
        if ok:self.start_assistant(selected.split(' · ')[0])

    def pc_history(self):
        if self.pc_worker:return
        logs=sorted((DATA/'assistant/runs').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:40]
        if not logs:self.pc_state.setText('No previous investigations yet.');return
        choices=[]
        for path in logs:
            data=read_json(path,{})
            task=next((e.get('request','') for e in data.get('events',[]) if e.get('kind')=='task'),'File rollback')
            choices.append(path.stem+' · '+task[:80])
        choice,ok=QInputDialog.getItem(self,'Previous investigations','Choose a local action log:',choices,0,False)
        if ok:self.pc_output.setPlainText(json.dumps(read_json(logs[choices.index(choice)],{}),ensure_ascii=False,indent=2))
