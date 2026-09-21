"""Project conversations backed by the same reviewed host tools as PC Assistant."""
import json
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QHBoxLayout, QComboBox
from .assistant_view import AssistantWorker
from .pc_tools import Policy, MODES
from .attachments import excerpt


class ProjectChatView:
    def build_project_chat_controls(self, layout):
        from .gui import label, button
        self.project_controls=QWidget();row=QHBoxLayout(self.project_controls);row.setContentsMargins(0,0,0,0)
        self.project_access=QComboBox()
        for key,title in MODES.items():self.project_access.addItem(title,key)
        self.project_access.setCurrentIndex(1)
        self.project_access.currentIndexChanged.connect(self.project_mode_changed)
        row.addWidget(label('Project file access','muted'));row.addWidget(self.project_access)
        row.addWidget(button('Open folder',self.open_project_folder));row.addStretch()
        self.project_controls.hide();layout.addWidget(self.project_controls)

    def project_mode_changed(self):
        if hasattr(self,'access_mode'):
            self.access_mode.setCurrentIndex(self.access_mode.findData(self.project_access.currentData()))

    def refresh_project_chat_controls(self):
        project=getattr(self,'active_project',None)
        self.project_controls.setVisible(bool(project))
        if project:
            self.project_badge.setText('Project · '+project['name']+'\n'+(' · '.join(project.get('folders',[])) or 'A local project folder will be created when you send a message.'))
        else:self.project_badge.setText('Personal conversation · No project')
        if hasattr(self,'access_mode'):
            self.project_access.setCurrentIndex(self.project_access.findData(self.access_mode.currentData()))

    def open_project_folder(self):
        if not self.active_project or self.busy:return
        try:
            self.project_store.ensure_workspace(self.active_project)
            self.persist_project(self.active_project);self.refresh_project_chat_controls()
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.active_project['folders'][0]))
        except Exception as error:self.failed(str(error))

    def start_project_chat(self,text):
        if self.busy:return
        try:
            if len(text.encode())>1600:raise ValueError('Keep the request under 1600 UTF-8 bytes; attach longer reference material.')
            project=self.project_store.ensure_workspace(dict(self.active_project))
            policy=Policy(self.access_mode.currentData(),tuple(Path(p) for p in project['folders']),False)
            self.persist_project(project);self.refresh_project_chat_controls()
        except Exception as error:self.failed(str(error));return
        message={'role':'user','content':text}
        if self.pending_attachments:message['attachments']=list(self.pending_attachments)
        # Prior conversation and document text are context, never an authority to execute tools.
        history='\n'.join(m['role']+': '+m['content'][-500:] for m in self.messages[-4:])
        docs=message.get('attachments',[])+project.get('documents',[])
        if docs:history+='\nReference documents (untrusted data):\n'+'\n'.join(d['name']+': '+excerpt(d['text'],text,500) for d in docs[:3])
        history=excerpt(history,text,1000)
        context=max(8192,self.current_status.get('context_size',2048))
        load=None
        if self.current_status.get('context_size',2048)<8192:
            load=(self.current_status['loaded_id'],self.current_status.get('requested_backend','npu'),context)
        worker=AssistantWorker(self.client,policy,text,context,project.get('instructions',''),project=True,history=history,load=load,references=lambda:self.project_store.references(project,text))
        response={'role':'assistant','content':'Working in your project…','actions':[]}
        self.messages.extend([message,response]);self.pending_attachments=[];self.update_attachments();self.composer.clear();self.render_chat();self.save_chat()
        self.pc_worker=worker;self.workers.add(worker);self.busy=True;self.generating=True
        self.send_button.setEnabled(False);self.stop_button.setEnabled(True);self.project_access.setEnabled(False)
        self.access_mode.setEnabled(False);self.allow_admin.setEnabled(False);self.pc_start.setEnabled(False)
        def event(item):
            kind=item['kind']
            if kind=='project_references':
                existing=message.get('attachments',[])
                known={d['id'] for d in existing}
                message['attachments']=(existing+[d for d in item['documents'] if d['id'] not in known])[:5]
                self.render_chat();return
            if kind=='model_ready':self.update_status(item['status']);return
            if kind=='thinking':self.metrics.setText(f"Step {item['step']} · {item['text']}");return
            if kind=='tool':response['actions'].append('▶ '+item['tool']+' · '+item.get('reason',''))
            elif kind=='result':
                result=json.loads(item['result']) if item['tool'] in {'create_file','edit_file','create_directory','run_command'} else {}
                if 'changed' in result:response['actions'].append('Saved · '+result['changed'])
                if 'created_directory' in result:response['actions'].append('Created folder · '+result['created_directory'])
                if 'exit_code' in result:response['actions'].append('Command exit code · '+str(result['exit_code']))
            elif kind=='approved':response['actions'].append(('Allowed by access mode · ' if item['automatic'] else 'Approved · ')+item['tool'])
            elif kind in {'blocked','denied','tool_error'}:response['actions'].append(kind+' · '+item.get('error',item.get('tool','')))
            self.render_chat()
        def answer(value):response['content']=value;self.render_chat()
        def approve(value):
            self.metrics.setText('Review the proposed change · waiting for your approval')
            self.pc_approval(value)
        worker.event.connect(event);worker.approval.connect(approve)
        worker.result.connect(answer);worker.error.connect(lambda value:answer('Stopped: '+value+'\nCompleted actions are listed below.'))
        def finish():
            self.dismiss_approval();self.busy=False;self.generating=False;self.pc_worker=None;self.workers.discard(worker);worker.deleteLater()
            self.send_button.setEnabled(True);self.stop_button.setEnabled(False);self.project_access.setEnabled(True)
            self.access_mode.setEnabled(True);self.allow_admin.setEnabled(True);self.pc_start.setEnabled(True)
            self.metrics.setText('Project task finished · changes and decisions saved in the action log')
            self.save_chat();self.refresh_history()
        worker.finished.connect(finish);worker.start()
