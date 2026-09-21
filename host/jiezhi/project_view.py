from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QPlainTextEdit, QFileDialog, QInputDialog, QMessageBox, QSplitter, QWidget, QVBoxLayout
from .projects import Projects
from .attachments import extract
from .pc_tools import sensitive


class ProjectView:
    def build_projects(self):
        from .gui import button,label,row,wide,EmptyList,card
        self.project_store=Projects(); self.active_project=None
        layout=self.page('Room for your next idea.', 'One workspace for conversations, documents, folders and shared context.')
        split=QSplitter(Qt.Orientation.Horizontal)
        left=QWidget();rail=QVBoxLayout(left);rail.setContentsMargins(0,0,0,0);rail.setSpacing(8)
        rail.addWidget(button('＋ New project',self.create_project,True))
        self.project_list=EmptyList('No projects yet. A project keeps its own chats, folders and instructions together.')
        self.project_list.setMinimumWidth(205);self.project_list.itemClicked.connect(self.show_project);rail.addWidget(self.project_list,1)
        rail.addWidget(button('Open project chat',self.use_project));rail.addWidget(button('Return to personal chat',self.leave_project,kind='quiet'));split.addWidget(left)
        right=QWidget();detail=QVBoxLayout(right);detail.setContentsMargins(0,0,0,0);detail.setSpacing(16)
        self.project_title=label('Select a project to begin.','badge');detail.addWidget(self.project_title,0,Qt.AlignmentFlag.AlignLeft)
        self.project_notes=QPlainTextEdit();self.project_notes.setPlaceholderText('What are you working toward? Add shared instructions…');self.project_notes.setMinimumHeight(96);self.project_notes.setMaximumHeight(130);detail.addWidget(self.project_notes)
        detail.addLayout(row(button('Link folder…',self.link_project_folder),button('Add files…',self.project_add_files),
                             trailing=(button('Save instructions',self.save_project_notes,True),)))
        detail.addWidget(label('REFERENCE LIBRARY','section'))
        self.project_files=EmptyList('Link a folder or add files, and they show up here for this project’s chats.')
        detail.addWidget(self.project_files,1)
        detail.addLayout(row(button('Refresh folders',self.refresh_project_index,kind='quiet'),
                             button('Remove reference',self.remove_project_reference,kind='quiet'),
                             trailing=(button('Attach to chat',self.project_attach_selected),)))
        detail.addWidget(label('Original files stay in place. Linked folders also define this project’s PC Assistant scope.','fine',True))
        split.addWidget(right);split.setSizes([260,860]);layout.addWidget(split,1);self.reload_projects()
    def reload_projects(self):
        self.project_list.clear()
        for project in self.project_store.all():
            if not project.get('id'):continue
            item=QListWidgetItem(project['name']);item.setData(Qt.ItemDataRole.UserRole,project);self.project_list.addItem(item)
    def chosen_project(self):
        item=self.project_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None
    def create_project(self):
        if self.busy:return
        name,ok=QInputDialog.getText(self,'New project','Project name:')
        if ok and name.strip():
            try: project=self.project_store.create(name)
            except ValueError as e:self.failed(str(e));return
            self.reload_projects()
            for i in range(self.project_list.count()):
                if self.project_list.item(i).data(Qt.ItemDataRole.UserRole)['id']==project['id']:
                    self.project_list.setCurrentRow(i);break
            self.use_project();self.show_project(self.project_list.currentItem());self.nav.setCurrentRow(5)
    def show_project(self,item):
        project=item.data(Qt.ItemDataRole.UserRole)
        self.project_title.setText(project['name']);self.project_notes.setPlainText(project.get('instructions',''));self.project_files.clear()
        for folder in project.get('folders',[]):
            row=QListWidgetItem('Folder · '+folder);row.setData(Qt.ItemDataRole.UserRole,{'kind':'folder','path':folder});self.project_files.addItem(row)
        for doc in project.get('documents',[]):
            row=QListWidgetItem('Reference · '+doc['name']);row.setData(Qt.ItemDataRole.UserRole,{'kind':'document','document':doc});self.project_files.addItem(row)
    def use_project(self):
        if self.busy:return
        project=self.chosen_project()
        if not project:return
        self.active_project=project;self.new_chat();self.refresh_project_chat_controls();self.refresh_history()
    def leave_project(self):
        if self.busy:return
        self.active_project=None;self.new_chat();self.project_badge.setText('Personal conversation · No project');self.refresh_history()
    def persist_project(self,project):
        self.project_store.save(project)
        item=self.project_list.currentItem()
        if item and item.data(Qt.ItemDataRole.UserRole)['id']==project['id']:item.setData(Qt.ItemDataRole.UserRole,project);self.show_project(item)
        if self.active_project and self.active_project['id']==project['id']:self.active_project=project
        self.refresh_project_chat_controls()
    def save_project_notes(self):
        if self.busy:return
        p=self.chosen_project()
        if p:p['instructions']=self.project_notes.toPlainText()[:500];self.persist_project(p)
    def link_project_folder(self):
        if self.busy:return
        p=self.chosen_project()
        if not p:return
        path=QFileDialog.getExistingDirectory(self,'Link a project folder and allow Assistant access')
        if path:
            if sensitive(Path(path)):self.failed('Credential and sensitive folders cannot be linked.');return
            folder=str(Path(path).resolve())
            if folder not in p['folders']:p['folders'].append(folder)
            self.persist_project(p)
    def project_add_files(self):
        if self.busy:return
        p=self.chosen_project()
        if not p:return
        paths,_=QFileDialog.getOpenFileNames(self,'Add project references')
        if not paths:return
        if len(paths)+len(p['documents'])>30:self.failed('A project can hold up to 30 reference files.');return
        def done(docs):p['documents'].extend(docs);self.persist_project(p)
        self.run_job(lambda _:[extract(Path(f)) for f in paths],done,'Reading project references…')
    def refresh_project_index(self):
        p=self.chosen_project()
        if not p:return
        def done(entries):
            selected=self.chosen_project()
            if not selected or selected['id']!=p['id']:return
            self.show_project(self.project_list.currentItem())
            for entry in entries:
                row=QListWidgetItem(entry['name']);row.setData(Qt.ItemDataRole.UserRole,{'kind':'file',**entry});self.project_files.addItem(row)
            self.statusBar().showMessage(f'{len(entries)} supported files indexed; index is limited to 1000 files.')
        self.run_job(lambda _:self.project_store.index(p),done,'Indexing project folders…')
    def project_attach_selected(self):
        if self.busy:return
        item=self.project_files.currentItem()
        if not item:return
        entry=item.data(Qt.ItemDataRole.UserRole)
        if entry['kind']=='file':self.add_attachments([Path(entry['path'])])
        elif entry['kind']=='document':
            if len(self.pending_attachments)>=5:self.failed('Attach at most five files.');return
            self.pending_attachments.append(entry['document']);self.update_attachments();self.nav.setCurrentRow(0)
    def remove_project_reference(self):
        if self.busy:return
        p=self.chosen_project();item=self.project_files.currentItem()
        if not p or not item:return
        entry=item.data(Qt.ItemDataRole.UserRole)
        if entry['kind']=='folder':p['folders'].remove(entry['path'])
        elif entry['kind']=='document':p['documents']=[d for d in p['documents'] if d['id']!=entry['document']['id']]
        else:self.statusBar().showMessage('Unlink its folder to remove indexed files. Original files are never deleted here.');return
        self.persist_project(p)
