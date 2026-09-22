from pathlib import Path
import threading

from PySide6.QtCore import Qt, QTimer, QUrl, QSize, QRect
from PySide6.QtGui import QDesktopServices, QColor, QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QCheckBox, QListWidget, QListWidgetItem, QProgressBar, QSplitter, QWidget, QVBoxLayout, QComboBox, QStyledItemDelegate, QStyle, QStyleOptionViewItem

from .hub import Hub, Paused
from .recommendations import CATEGORIES, phone_profile, ranked
from .client import DATA, read_json
from .theme import tokens,SMALL,CAPTION


class ModelResultDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):return QSize(240,96)
    def paint(self,painter,option,index):
        opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index)
        name=opt.text;opt.text='';opt.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem,opt,painter,opt.widget)
        painter.save();rect=option.rect.adjusted(12,6,-12,-6)
        selected=bool(option.state & QStyle.StateFlag.State_Selected)
        font=option.font;font.setPixelSize(SMALL);font.setBold(True);painter.setFont(font)
        dark=getattr(option.widget.window(),'dark',False)
        t=tokens(dark)
        painter.setPen(QColor(t['accent_text'] if selected else t['ink']))
        painter.drawText(QRect(rect.x(),rect.y(),rect.width(),24),Qt.AlignmentFlag.AlignVCenter,QFontMetrics(font).elidedText(name,Qt.TextElideMode.ElideRight,rect.width()))
        font.setBold(False);font.setPixelSize(CAPTION);painter.setFont(font)
        data=index.data(Qt.ItemDataRole.UserRole+1) or {}
        for i,line in enumerate(data.get('lines',[])):
            painter.setPen(QColor(t['accent_text'] if i==0 and data.get('recommended') else t['ink_3']))
            painter.drawText(QRect(rect.x(),rect.y()+24+i*18,rect.width(),18),Qt.AlignmentFlag.AlignVCenter,QFontMetrics(font).elidedText(line,Qt.TextElideMode.ElideRight,rect.width()))
        painter.restore()


class HubView:
    def build_hub(self):
        from .gui import button, label, row, wide, EmptyList
        self.hub_phone=read_json(DATA/'recommendation-phone.json',{}); self.hub_phone['cached']=True
        self.hub_repo_data=[]; self.hub_file_data=[]; self.hub_repository=''; self.hub_search_epoch=0
        self.hub = Hub(); self.hub_cancel = threading.Event(); self.downloaded_path = None
        layout = self.page("Find your next model.", "Download from Hugging Face to this PC, then send to your phone over USB.")
        self.account_label = label("Hugging Face · Public downloads are ready", "badge")
        layout.addLayout(row(self.account_label, trailing=(button('Account settings ↗',self.open_settings,kind='quiet'),)))
        self.hub_account_panel=QWidget();account_layout=QVBoxLayout(self.hub_account_panel);account_layout.setContentsMargins(0,0,0,0)
        self.hub_token = QLineEdit(); self.hub_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.hub_token.setPlaceholderText("Hugging Face read token · hf_…")
        wide(self.hub_token, 420); self.hub_token.setMinimumWidth(360)
        account_layout.addLayout(row(self.hub_token, button("Connect account", self.hub_connect, True),
                                     button("Disconnect", self.hub_disconnect)))
        self.remember_account = QCheckBox("Remember in system keyring")
        account_layout.addLayout(row(self.remember_account, trailing=(
            button("Get a read token ↗", lambda: QDesktopServices.openUrl(QUrl("https://huggingface.co/settings/tokens")), kind='quiet'),)));self.hub_account_panel.hide()
        self.hub_query = QLineEdit(); self.hub_query.setPlaceholderText("Search GGUF models, or enter owner/repository")
        self.hub_query.returnPressed.connect(self.hub_search)
        wide(self.hub_query, 456); self.hub_query.setMinimumWidth(456)
        layout.addLayout(row(self.hub_query, button("Search", self.hub_search, True),
                             button("Open repository", self.hub_open_repo)))
        self.hub_category=QComboBox()
        for key,title in CATEGORIES.items():self.hub_category.addItem(title,key)
        wide(self.hub_category, 228); self.hub_category.setMinimumWidth(180)
        self.hub_context=QComboBox()
        for size in [2048,4096,8192]:self.hub_context.addItem(f'{size//1024}K',size)
        self.hub_context.setCurrentIndex(1); wide(self.hub_context, 90)
        layout.addLayout(row(label('Recommend for','muted'), self.hub_category,
                             label('Context','muted'), self.hub_context,
                             trailing=(button('Refresh phone',self.hub_refresh_phone),), spacing=12))
        self.hub_phone_label=label('', 'fine',True);layout.addWidget(self.hub_phone_label)
        self.hub_search_timer=QTimer(self);self.hub_search_timer.setSingleShot(True);self.hub_search_timer.setInterval(450)
        self.hub_search_timer.timeout.connect(self.hub_search)
        self.hub_query.textEdited.connect(lambda _:self.hub_search_timer.start())
        self.hub_category.currentIndexChanged.connect(self.hub_category_changed)
        self.hub_context.currentIndexChanged.connect(self.hub_render)
        self.nav.pageChanged.connect(lambda index:self.hub_search_timer.start() if index==4 and (not self.hub_phone.get('ram_gib') or not self.hub_repo_data and not self.hub_file_data) else None)
        splitter = QSplitter(Qt.Orientation.Horizontal); splitter.setHandleWidth(12)
        self.hub_repos = QListWidget()
        self.hub_repos.currentItemChanged.connect(lambda item,old:self.hub_select_repo(item) if item else None)
        self.hub_files = QListWidget()
        for widget in [self.hub_repos,self.hub_files]:
            widget.setItemDelegate(ModelResultDelegate(widget));widget.setSpacing(3)
            widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for title, widget in [("MODELS · RANKED FOR YOUR PHONE", self.hub_repos), ("FILES · BEST FIT FIRST", self.hub_files)]:
            pane = QWidget(); col = QVBoxLayout(pane); col.setContentsMargins(0, 0, 0, 0)
            col.addWidget(label(title, "section")); col.addWidget(widget); splitter.addWidget(pane)
        layout.addWidget(splitter, 1)
        layout.addWidget(label("Suitability ranks these results, not model quality. Speeds estimate decoding only; hover for assumptions. Compatibility still needs a load test.", "fine", True))
        self.hub_pause = button("Pause", self.hub_cancel.set, kind='quiet'); self.hub_pause.setEnabled(False)
        layout.addLayout(row(button("Model page ↗", self.hub_model_page, kind='quiet'),
                             trailing=(button("Download && send to phone", lambda: self.hub_download(True)),
                                       button("Download to PC", lambda: self.hub_download(False), True))))
        self.hub_progress = QProgressBar(); self.hub_progress.setValue(0); self.hub_progress.setVisible(False)
        wide(self.hub_progress, 360)
        self.hub_note = label("Choose a category for suggestions, or type to search. Public models need no account.", "fine", True)
        layout.addLayout(row(self.hub_progress, (self.hub_note, 1), trailing=(self.hub_pause,), spacing=12))
        self.hub_render()

    def hub_account_result(self, result):
        name = result.get("username")
        self.hub_token.clear()
        self.account_label.setText(f"Connected as {name} · " + ("Saved in system keyring" if result.get("remember") else "This session only") if name else "Hugging Face · Public downloads are ready")
        if hasattr(self,'settings_account_label'):self.settings_account_label.setText(self.account_label.text()+('\n'+result['warning'] if result.get('warning') else ''))
        if result.get("warning"):
            self.hub_note.setText(result["warning"])

    def hub_connect(self):
        if self.busy: return
        token, remember = self.hub_token.text(), self.remember_account.isChecked()
        self.hub_token.clear()
        self.run_job(lambda _: self.hub.connect(token, remember), self.hub_account_result, "Connecting Hugging Face account…")

    def hub_disconnect(self):
        self.run_job(lambda _: self.hub.disconnect(), lambda _: self.hub_account_result({}), "Disconnecting Hugging Face…")

    def hub_category_changed(self):
        self.hub_render()
        self.hub_search_timer.start()

    def hub_refresh_phone(self):
        if self.busy:return
        serial=self.client.serial if self.client.port else self.device_picker.currentData() or ''
        def done(profile):self.hub_phone=profile;self.hub_render()
        self.run_job(lambda _:phone_profile(serial),done,'Reading phone hardware…')

    def hub_render(self):
        profile=self.hub_phone
        if profile.get('ram_gib'):
            source='Last detected phone' if profile.get('cached') else 'Detected over USB'
            self.hub_phone_label.setText(f"{source} · {profile['phone']} · {profile['soc']} · {profile['ram_gib']:.1f} GiB RAM · NPU estimates at {self.hub_context.currentText()} context")
        else:self.hub_phone_label.setText('Connect a USB phone to personalize RAM fit and speed estimates. No model needs to run.')
        category=self.hub_category.currentData();context=self.hub_context.currentData()
        for widget,models,is_file in [(self.hub_repos,self.hub_repo_data,False),(self.hub_files,self.hub_file_data,True)]:
            selected=widget.currentItem().data(Qt.ItemDataRole.UserRole) if widget.currentItem() else None
            widget.blockSignals(True);widget.clear()
            for rank,(model,assessment) in enumerate(ranked(models,profile,category,context),1):
                name=model['name'] if is_file else model.get('id') or model['modelId']
                value=model if is_file else name
                item=QListWidgetItem(f'{rank}.  {name}')
                if is_file:
                    assessment['lines'][2]=f"{model['size']/1024**3:.2f} GiB file · "+assessment['lines'][2]
                item.setData(Qt.ItemDataRole.UserRole,value);item.setData(Qt.ItemDataRole.UserRole+1,assessment)
                item.setToolTip(name+'\n\n'+assessment['details']);widget.addItem(item)
                if value==selected:widget.setCurrentItem(item)
            if widget.count() and widget.currentRow()<0:widget.setCurrentRow(0)
            widget.blockSignals(False)

    def hub_search(self):
        if self.busy or getattr(self,'hub_send_pending',False):self.hub_search_timer.start();return
        self.hub_search_timer.stop()
        query=self.hub_query.text().strip();category=self.hub_category.currentData()
        if '/' in query:
            self.hub_search_epoch+=1;self.hub_load_files(query);return
        self.hub_search_epoch+=1;epoch=self.hub_search_epoch
        serial=self.client.serial if self.client.port else self.device_picker.currentData() or ''
        def work(_):return phone_profile(serial),self.hub.search(query) if query else self.hub.discover(category)
        def done(result):
            if epoch!=self.hub_search_epoch or query!=self.hub_query.text().strip() or category!=self.hub_category.currentData():return
            self.hub_phone,self.hub_repo_data=result;self.hub_file_data=[];self.hub_repository='';self.hub_render()
            self.hub_note.setText(f'{len(self.hub_repo_data)} results ranked for {self.hub_category.currentText().lower()}. Select a model for exact file sizes.')
            item=self.hub_repos.currentItem()
            if item:
                repo=item.data(Qt.ItemDataRole.UserRole)
                QTimer.singleShot(50,lambda:self.hub_load_files(repo,epoch))
        self.run_job(work,done,'Finding models for your phone…')

    def hub_open_repo(self):
        self.hub_search_timer.stop();self.hub_search_epoch+=1
        self.hub_load_files(self.hub_query.text().strip())

    def hub_select_repo(self, item):
        self.hub_search_epoch+=1
        repo=item.data(Qt.ItemDataRole.UserRole)
        self.hub_file_data=[];self.hub_repository='';self.hub_render()
        self.hub_load_files(repo,self.hub_search_epoch)

    def hub_load_files(self, repo, epoch=None):
        if epoch is None:epoch=self.hub_search_epoch
        if epoch!=self.hub_search_epoch:return
        if self.busy or getattr(self,'hub_send_pending',False):
            QTimer.singleShot(100,lambda:self.hub_load_files(repo,epoch));return
        self.hub_file_data=[];self.hub_repository='';self.hub_render()
        serial=self.client.serial if self.client.port else self.device_picker.currentData() or ''
        def done(result):
            if epoch!=self.hub_search_epoch:return
            self.hub_phone,files=result
            self.hub_file_data=files;self.hub_repository=repo;self.hub_render()
            self.hub_note.setText(f'{repo} · {len(files)} files ranked. Hover for the score and estimate basis.')
        self.run_job(lambda _:(phone_profile(serial),self.hub.files(repo)),done,'Reading model files…')

    def hub_model_page(self):
        repo = getattr(self, "hub_repository", "")
        if repo: QDesktopServices.openUrl(QUrl(f"https://huggingface.co/{repo}"))

    def hub_download(self, send):
        if self.busy: return
        item = self.hub_files.currentItem()
        if not item: return
        if send and not self.client.port:
            self.failed("Connect your phone in Device & setup first, or choose Download to PC."); return
        file = item.data(Qt.ItemDataRole.UserRole)
        self.hub_search_timer.stop();self.hub_search_epoch+=1
        self.hub_cancel.clear(); self.hub_pause.setEnabled(True)
        def work(worker):
            try: return self.hub.download(file, worker.progress.emit, self.hub_cancel)
            except Paused: return None
        def done(path):
            if path is None:
                self.hub_note.setText("Paused. Download this file again to resume."); return
            self.downloaded_path = path
            self.hub_note.setText(f"Verified and saved: {path}")
            if send:
                self.hub_send_pending=True
                def transfer():
                    self.hub_send_pending=False;self.transfer_model_path(path)
                QTimer.singleShot(100, transfer)
        self.run_job(work, done, "Downloading from Hugging Face…")
