from __future__ import annotations

import html
from pathlib import Path
import subprocess
import threading
import uuid

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QTextCursor, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QStackedWidget, QTextBrowser, QPlainTextEdit,
    QFileDialog, QComboBox, QProgressBar, QInputDialog, QMessageBox, QSpinBox,
)

from .client import Client, DATA, ROOT, asset, devices, read_json, save_json
from .hub_view import HubView
from .attachment_view import AttachmentView
from .attachments import prepare
from .project_view import ProjectView
from .project_chat import ProjectChatView
from .desktop_actions import DesktopActionsView
from .assistant_view import AssistantView
from .telemetry_view import TelemetryPanel
from .appearance import DeviceWelcome
from .settings_view import SettingsView
from .workflow_view import WorkflowView

STYLE = """
QWidget { background: #f3f5fa; color: #202b40; font-size: 14px; font-family: "Noto Sans", sans-serif; }
QMainWindow { background: #f3f5fa; }
QLabel { background: transparent; }
QLabel#brand { color: #386bff; font-size: 28px; font-weight: 700; }
QLabel#title { font-size: 29px; font-weight: 700; color: #17253e; }
QLabel#muted { color: #6d7b92; font-size: 12px; }
QLabel#badge { color: #386bff; background: #e8eeff; border-radius: 12px; padding: 12px; }
QWidget#sidebar { background: #eaf0fc; border-radius: 22px; }
QPushButton { background: #ffffff; border: 1px solid #e0e6f0; border-radius: 12px; padding: 10px 14px; font-weight: 500; }
QPushButton:hover { background: #e8eeff; border-color: #b8caff; }
QPushButton:pressed { background: #dce6ff; }
QPushButton:disabled { color: #a4aec0; background: #edf0f6; border-color: #e9edf4; }
QPushButton#primary { background: #386bff; color: #ffffff; border: 1px solid #386bff; font-weight: 600; }
QPushButton#primary:hover { background: #285be9; }
QPushButton#primary:disabled { background: #b7c8f8; border-color: #b7c8f8; }
QListWidget { background: #ffffff; border: 0; border-radius: 16px; padding: 7px; outline: none; }
QListWidget#navigation { background: transparent; font-size: 15px; }
QListWidget#navigation::item { padding: 8px 10px; }
QListWidget::item { padding: 12px 10px; border-radius: 10px; margin: 2px; }
QListWidget::item:hover { background: #f0f4ff; }
QListWidget::item:selected { background: #dfe8ff; color: #275ae3; }
QTextBrowser, QPlainTextEdit, QLineEdit { background: #ffffff; border: 1px solid #e1e7f1; border-radius: 16px; padding: 13px; selection-background-color: #d8e4ff; selection-color: #17253e; }
QTextBrowser { border: 0; padding: 20px; }
QLineEdit { border-radius: 12px; padding: 10px; }
QPlainTextEdit:focus, QLineEdit:focus { border-color: #89a7ff; }
QComboBox, QSpinBox, QDoubleSpinBox { background: #ffffff; padding: 8px; border: 1px solid #e0e6f0; border-radius: 10px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #dfe8ff; }
QProgressBar { min-height: 10px; border: 0; border-radius: 5px; background: #e3e9f4; text-align: center; font-size: 10px; }
QProgressBar::chunk { background: #386bff; border-radius: 5px; }
QStatusBar { color: #6d7b92; font-size: 12px; padding: 4px 12px; }
QScrollBar:vertical { width: 8px; background: transparent; margin: 4px; }
QScrollBar::handle:vertical { background: #cbd5e7; min-height: 24px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 8px; background: transparent; margin: 0; }
QScrollBar::handle:horizontal { background: #cbd5e7; min-width: 24px; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QSplitter::handle { background: transparent; width: 12px; }
QToolTip { color: #202b40; background: white; border: 1px solid #dfe6f1; padding: 6px; }
"""


class Worker(QThread):
    result = Signal(object)
    error = Signal(str)
    event = Signal(object)
    progress = Signal(int, str)

    def __init__(self, function):
        super().__init__(); self.function = function

    def run(self):
        try:
            self.result.emit(self.function(self))
        except Exception as e:
            self.error.emit(str(e))


def button(text, action, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(action)
    return widget


def label(text, kind="", wrap=False):
    widget = QLabel(text); widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(kind); widget.setWordWrap(wrap)
    return widget


class Window(DesktopActionsView, ProjectChatView, SettingsView, WorkflowView, HubView, AttachmentView, ProjectView, AssistantView, QMainWindow):
    def __init__(self):
        super().__init__()
        self.preferences_path=DATA/'preferences.json';self.preferences=read_json(self.preferences_path,{})
        self.dark=self.preferences.get('dark',False)
        self.client = Client(); self.workers = set(); self.busy = False
        self.initial_scan = True; self.pending_attachments = []; self.setAcceptDrops(True)
        self.current_status = {}; self.messages = []; self.conversation_id = uuid.uuid4().hex
        self.transfer_cancel = threading.Event(); self.generating = False
        self.setWindowTitle("JieZhi · 借智 — Borrow intelligence")
        self.resize(1440, 1000); self.setMinimumSize(1160, 840)
        self.setStyleSheet(STYLE)
        root = QWidget(); self.setCentralWidget(root); layout = QHBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18); layout.setSpacing(22)
        sidebar_panel = QWidget(); sidebar_panel.setObjectName("sidebar"); sidebar_panel.setFixedWidth(216)
        sidebar = QVBoxLayout(sidebar_panel); sidebar.setContentsMargins(16, 24, 16, 20); sidebar.setSpacing(14)
        sidebar.addWidget(label("借智  JieZhi", "brand"))
        sidebar.addWidget(label("Intelligence, borrowed.", "muted"))
        self.nav = QListWidget(); self.nav.setObjectName("navigation"); self.nav.setFixedHeight(370)
        self.nav.addItems(["Chat", "Phone models", "Welcome & device", "Diagnostics", "Discover models", "Projects", "PC Assistant", "Flow canvas"])
        sidebar.addWidget(self.nav)
        sidebar.addWidget(button("＋  New conversation", self.new_chat))
        sidebar.addWidget(label("RECENT CONVERSATIONS", "muted"))
        self.history = QListWidget(); self.history.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.history.itemClicked.connect(self.open_chat); sidebar.addWidget(self.history)
        sidebar.addWidget(button("Delete conversation", self.delete_chat))
        self.connection = label("○  No phone connected", "muted", True); sidebar.addWidget(self.connection)
        sidebar.addWidget(label("USB connection · Local inference", "muted"))
        layout.addWidget(sidebar_panel)
        content = QVBoxLayout(); content.setSpacing(12); layout.addLayout(content, 1)
        header=QHBoxLayout();header.addWidget(label('JIEZHI  /  YOUR LOCAL WORKSPACE','muted'));header.addStretch()
        self.theme_button=button('☾',self.toggle_dark);self.theme_button.setObjectName('corner');self.theme_button.setAccessibleName('Toggle dark mode');header.addWidget(self.theme_button)
        self.settings_button=button('⚙',self.open_settings);self.settings_button.setObjectName('corner');self.settings_button.setToolTip('Settings');self.settings_button.setAccessibleName('Open settings');header.addWidget(self.settings_button);content.addLayout(header)
        self.pages = QStackedWidget(); content.addWidget(self.pages, 1)
        self.telemetry_panel = TelemetryPanel(self.client, self); content.addWidget(self.telemetry_panel)
        self.build_chat(); self.build_models(); self.build_setup(); self.build_diagnostics(); self.build_hub(); self.build_projects(); self.build_assistant(); self.build_workflows(); self.build_settings(); self.init_desktop_popup()
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex); self.nav.setCurrentRow(2)
        self.refresh_history(); self.render_chat(); self.apply_appearance()
        self.statusBar().showMessage("Connect your Snapdragon 8 Elite phone to get started.")
        self.heartbeat = QTimer(self); self.heartbeat.setInterval(20_000)
        self.heartbeat.timeout.connect(self.keep_alive); self.heartbeat.start()
        QTimer.singleShot(100, lambda: self.run_job(lambda _: self.hub.restore(), self.hub_account_result, "Restoring account…"))
        QTimer.singleShot(1000, self.start_scan)

    def start_scan(self):
        if self.busy:
            QTimer.singleShot(500, self.start_scan)
        else:
            self.scan()

    def keep_alive(self):
        if not self.client.port or (self.busy and not self.pc_worker):
            return
        worker = Worker(lambda _: self.client.status()); self.workers.add(worker)
        worker.result.connect(self.update_status)
        worker.error.connect(lambda message: self.connection.setText("○  Connection lost · reconnect in Setup"))
        def finish():
            self.workers.discard(worker); worker.deleteLater()
        worker.finished.connect(finish); worker.start()

    def page(self, title, subtitle):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(14)
        layout.addWidget(label(title, "title")); layout.addWidget(label(subtitle, "muted", True))
        self.pages.addWidget(page)
        return layout

    def build_chat(self):
        layout = self.page("What’s on your mind?", "A private conversation, with room to think.")
        self.project_badge = label("Personal conversation · No project", "muted"); layout.addWidget(self.project_badge)
        self.build_project_chat_controls(layout)
        self.model_badge = label("No model loaded · Open Phone models to choose one", "badge", True); layout.addWidget(self.model_badge)
        self.transcript = QTextBrowser(); self.transcript.setOpenExternalLinks(False); self.transcript.setAcceptDrops(False); layout.addWidget(self.transcript, 1)
        self.attachment_label = label("Spreadsheets, PDF, text & code · Drop files here", "muted", True); layout.addWidget(self.attachment_label)
        files_row = QHBoxLayout(); files_row.addWidget(button("＋ Attach files", self.attach_files))
        self.preview_files = button("Preview", self.preview_attachments); files_row.addWidget(self.preview_files)
        self.clear_files = button("Remove attachments", self.clear_attachments); files_row.addWidget(self.clear_files); files_row.addStretch(); layout.addLayout(files_row)
        self.update_attachments()
        self.composer = QPlainTextEdit(); self.composer.setAcceptDrops(False); self.composer.setPlaceholderText("Ask a question, or attach a document to explore…"); self.composer.setMinimumHeight(95); self.composer.setMaximumHeight(125); layout.addWidget(self.composer)
        row = QHBoxLayout(); self.metrics = label("", "muted"); row.addWidget(self.metrics, 1)
        self.stop_button = button("Stop", self.stop); self.stop_button.setEnabled(False); row.addWidget(self.stop_button)
        self.send_button = button("Send message", self.send, True); row.addWidget(self.send_button); layout.addLayout(row)
        self.send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.send_shortcut.activated.connect(self.send)
        self.send_button.setToolTip("Ctrl+Enter")

    def build_models(self):
        layout = self.page("Your model library", "Import a GGUF from this PC. It is transferred once, verified, and stored privately on the phone.")
        row = QHBoxLayout()
        row.addWidget(button("Import GGUF…", self.import_model, True))
        row.addWidget(button("Refresh library", self.refresh)); row.addStretch(); layout.addLayout(row)
        layout.addWidget(label("Start with Q4_0 models. Architecture, quantization, and phone memory determine compatibility.", "muted", True))
        self.models = QListWidget(); layout.addWidget(self.models, 1)
        row = QHBoxLayout()
        self.backend = QComboBox(); self.backend.addItem("Hexagon NPU", "npu"); self.backend.addItem("Phone CPU · diagnostics", "cpu")
        row.addWidget(self.backend); row.addWidget(label("Context"))
        self.context = QSpinBox(); self.context.setRange(512, 8192); self.context.setSingleStep(512); self.context.setValue(2048); row.addWidget(self.context)
        row.addStretch(); row.addWidget(button("Load model", self.load_model, True)); row.addWidget(button("Unload", self.unload)); layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(button("Delete selected from phone", self.delete_model)); row.addStretch()
        self.pause_button = button("Pause transfer", self.pause_transfer); self.pause_button.setEnabled(False); row.addWidget(self.pause_button); layout.addLayout(row)
        self.progress = QProgressBar(); self.progress.setValue(0); layout.addWidget(self.progress)
        self.transfer_label = label("Select a local model to begin.", "muted"); layout.addWidget(self.transfer_label)

    def build_setup(self):
        layout = self.page("Welcome to JieZhi", "A phone-powered workspace, built around you.")
        self.welcome_art=DeviceWelcome();layout.addWidget(self.welcome_art)
        cached=read_json(DATA/'recommendation-phone.json',{})
        if cached.get('phone'):self.welcome_art.device(cached['phone'],cached.get('soc',''))
        for title, desc in [
            ("01  Enable USB debugging", "On Android, enable Developer options → USB debugging. Connect a data-capable cable and approve this PC on the phone."),
            ("02  Install the Android client", "Select the USB device below and install JieZhi. Xiaomi may ask you to allow installation over USB."),
            ("03  Pair with JieZhi", "Connect, then enter the six-digit code displayed by the Android client. Keep the client running while using the desktop app."),
        ]:
            layout.addWidget(label(title)); layout.addWidget(label(desc, "muted", True))
        row = QHBoxLayout(); self.device_picker = QComboBox(); row.addWidget(self.device_picker, 1)
        row.addWidget(button("Find phones", self.scan)); layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(button("Install Android client", self.install_client))
        row.addWidget(button("Connect && pair", self.connect_phone, True)); row.addWidget(button("Disconnect", self.disconnect_phone)); layout.addLayout(row)
        self.device_details = label("Waiting for a phone…", "muted", True); layout.addWidget(self.device_details)
        layout.addStretch()
        layout.addWidget(label("If Linux reports “no permissions”, install the USB access rule. Deepin will request administrator authentication.", "muted", True))
        layout.addWidget(button("Fix USB access…", self.fix_usb))

    def build_diagnostics(self):
        layout = self.page("Runtime diagnostics", "The selected backend is a request. Native Hexagon initialization and offload logs provide evidence of NPU use.")
        row = QHBoxLayout(); row.addWidget(button("Read phone runtime logs", self.logs)); row.addWidget(button("Save diagnostics…", self.save_logs)); row.addStretch(); layout.addLayout(row)
        self.log_text = QPlainTextEdit(); self.log_text.setReadOnly(True); self.log_text.setFont(QFont("monospace", 11)); layout.addWidget(self.log_text, 1)
        layout.addWidget(label("NPU acceleration can still involve CPU tokenization, sampling, and unsupported operations. This view does not measure a hardware utilization percentage.", "muted", True))

    def run_job(self, function, done=lambda _: None, message="Working…", exclusive=True, events=None):
        if exclusive and self.busy:
            self.statusBar().showMessage("Wait for the current operation, or stop it first."); return
        if exclusive:
            self.busy = True
        self.statusBar().showMessage(message)
        worker = Worker(function); self.workers.add(worker)
        worker.result.connect(done); worker.error.connect(self.failed)
        worker.progress.connect(self.on_progress)
        if events:
            worker.event.connect(events)
        def finish():
            if exclusive:
                self.busy = False
            self.workers.discard(worker); worker.deleteLater()
            if self.generating and exclusive:
                self.generating = False; self.stop_button.setEnabled(False); self.send_button.setEnabled(True)
                self.save_chat(); self.refresh_history()
            self.pause_button.setEnabled(False); self.hub_pause.setEnabled(False)
        worker.finished.connect(finish); worker.start()

    def failed(self, message):
        self.statusBar().showMessage(message)
        self.device_details.setText(message)
        if self.generating:
            self.metrics.setText("Generation interrupted · partial reply saved")
        QMessageBox.warning(self, "JieZhi", message)

    def scan(self):
        def done(found):
            self.device_picker.clear()
            for d in found:
                self.device_picker.addItem(f"{d['serial']}  ·  {d['state']}", d["serial"])
            self.device_details.setText(f"{len(found)} USB phone(s) detected." if found else "No USB phone found. Check the cable and USB debugging.")
            if self.initial_scan:
                self.initial_scan = False
                pairs = read_json(DATA / "pairing.json", {})
                ready = [d for d in found if d["state"] == "device" and d["serial"] in pairs]
                if len(ready) == 1 and self.preferences.get('auto_connect',True):
                    self.device_picker.setCurrentIndex(self.device_picker.findData(ready[0]["serial"]))
                    QTimer.singleShot(100, self.connect_phone)
        self.run_job(lambda _: devices(), done, "Looking for USB phones…")

    def serial(self):
        serial = self.device_picker.currentData()
        if not serial:
            raise RuntimeError("Select a connected phone first.")
        return serial

    def install_client(self):
        try:
            serial = self.serial()
        except Exception as e:
            self.failed(str(e)); return
        self.run_job(lambda _: self.client.install(serial), lambda _: self.device_details.setText("Android client installed. Click Connect & pair."), "Installing APK · check phone for approval…")

    def connect_phone(self):
        try:
            serial = self.serial()
        except Exception as e:
            self.failed(str(e)); return
        def done(result):
            if result.get("needs_pairing"):
                # Queue until the connection worker releases the operation lock.
                QTimer.singleShot(100, self.ask_pair)
            else:
                self.update_status(result)
                self.nav.setCurrentRow(0 if result.get("loaded_id") else 1)
        self.run_job(lambda _: self.client.connect(serial), done, "Connecting over USB…")

    def ask_pair(self):
        code, ok = QInputDialog.getText(self, "Pair your phone", "Enter the six-digit code displayed in JieZhi on the phone:")
        if ok:
            self.run_job(lambda _: self.client.pair(code), self.update_status, "Pairing…")

    def disconnect_phone(self):
        if self.busy:
            self.stop(); return
        self.client.disconnect(); self.current_status = {}; self.connection.setText("○  No phone connected")
        self.model_badge.setText("Connect a phone and load a model."); self.models.clear()

    def update_status(self, status):
        self.current_status = status
        if status.get('loaded_id') and self.preferences.get('last_text_model')!=status['loaded_id']:
            self.preferences['last_text_model']=status['loaded_id'];save_json(self.preferences_path,self.preferences)
        if hasattr(self,"desktop_model_choices"):self.fill_desktop_models()
        self.welcome_art.device(status.get('phone',''),status.get('soc',''))
        if self.client.port and self.hub_phone.get('serial')!=self.client.serial:
            self.hub_phone={};self.hub_render()
            if self.nav.currentRow()==4:self.hub_search_timer.start()
        self.connection.setText(f"●  {status.get('phone', 'Phone connected')}")
        self.device_details.setText(f"{status['phone']} · {status['soc']} · Android {status['android']}\n{status['state']}\n{status['free_bytes'] / 1024**3:.1f} GiB storage available · Thermal status {status['thermal_status']}")
        name = status.get("loaded_name")
        self.model_badge.setText(f"{name}  ·  {status['requested_backend'].upper()} requested" if name else "No model loaded · Open Models to choose one")
        selected = self.selected_model()
        self.models.clear()
        for m in status.get("models", []):
            active = "  ·  Loaded" if m["id"] == status.get("loaded_id") else ""
            item = QListWidgetItem(f"{m['name']}\n{m['size']/1024**3:.2f} GiB{active}")
            item.setData(Qt.ItemDataRole.UserRole, m); self.models.addItem(item)
            if selected and selected["id"] == m["id"]:
                self.models.setCurrentItem(item)
        if self.models.count() and not self.models.currentItem():
            self.models.setCurrentRow(0)
        self.statusBar().showMessage("Phone connected. All inference runs on Android.")

    def refresh(self):
        self.run_job(lambda _: self.client.status(), self.update_status, "Refreshing phone…")

    def selected_model(self):
        item = self.models.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def import_model(self):
        if self.busy:
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Import a GGUF model", str(Path.home()), "GGUF models (*.gguf)")
        if filename:
            self.transfer_model_path(Path(filename))

    def transfer_model_path(self, path):
        if self.busy: return
        if not self.client.port:
            self.failed("Connect your phone in Device & setup before importing a model."); return
        self.nav.setCurrentRow(1)
        self.transfer_cancel.clear(); self.pause_button.setEnabled(True)
        self.run_job(lambda w: self.client.import_model(Path(path), w.progress.emit, self.transfer_cancel), self.update_status, "Preparing model transfer…")

    def on_progress(self, percent, text):
        self.progress.setValue(percent); self.transfer_label.setText(f"{text} · {percent}%")
        self.hub_progress.setValue(percent); self.hub_note.setText(f"{text} · {percent}%")

    def pause_transfer(self):
        self.transfer_cancel.set()

    def load_model(self):
        selected = self.selected_model()
        if selected:
            backend, context = self.backend.currentData(), self.context.value()
            self.run_job(lambda _: self.client.load(selected["id"], backend, context), self.update_status, f"Loading on phone {backend.upper()}…")

    def unload(self):
        def work(_):
            self.client.request("POST", "/unload", json={}); return self.client.status()
        self.run_job(work, self.update_status, "Unloading model…")

    def delete_model(self):
        selected = self.selected_model()
        if not selected or self.busy:
            return
        if QMessageBox.question(self, "Delete model", f"Delete {selected['name']} from the phone? The PC file is kept.") != QMessageBox.StandardButton.Yes:
            return
        def work(_):
            self.client.request("DELETE", f"/models/{selected['id']}"); return self.client.status()
        self.run_job(work, self.update_status, "Removing model…")

    def render_chat(self):
        if not self.messages:
            ink='#dce6ff' if self.dark else '#273c66'
            self.transcript.setHtml(f'<div style="margin:48px 28px;color:{ink}"><h1>A fresh conversation.</h1><p>Explore an idea, bring a document, or pick up a project.</p><p style="color:#8393b0">Your files stay here. Your phone does the thinking.</p></div>');return
        parts = []
        for message in self.messages:
            who = "YOU" if message["role"] == "user" else "JIEZHI"
            color = ("#a8b5cd" if self.dark else "#6d7b92") if who == "YOU" else ("#90b1ff" if self.dark else "#386bff")
            content = html.escape(message["content"]).replace("\n", "<br>")
            files = " · ".join(html.escape(f["name"]) for f in message.get("attachments", []))
            attachment_line = f'<p style="color:#d17832">Attached: {files}</p>' if files else ""
            action_line="".join("<p style=\"color:#8393b0\">"+html.escape(a)+"</p>" for a in message.get("actions",[]))
            parts.append(f'<p style="color:{color};margin-top:22px"><b>{who}</b></p>{attachment_line}<p>{content}</p>{action_line}')
        self.transcript.setHtml("".join(parts)); self.transcript.moveCursor(QTextCursor.MoveOperation.End)

    def send(self):
        text = self.composer.toPlainText().strip()
        if self.busy or not text:
            return
        if not self.current_status.get("loaded_id"):
            self.failed("Load a model in Models before sending a message."); return
        if self.active_project:
            self.start_project_chat(text)
        else:
            self.send_with_references(text, [])

    def send_with_references(self, text, references, instructions=""):
        if self.busy: return
        message = {"role": "user", "content": text}
        references = references[:max(0, 5-len(self.pending_attachments))]
        if self.pending_attachments or references: message["attachments"] = references + list(self.pending_attachments)
        context_size = self.current_status.get("context_size", 2048)
        output_tokens = min(512, context_size // 4)
        try:
            payload, note = prepare(self.messages + [message], context_size - len(instructions.encode()) - (32 if instructions else 0), output_tokens)
            if instructions: payload.insert(0, {"role":"system", "content":"Project instructions: " + instructions})
        except ValueError as e:
            self.failed(str(e)); return
        self.messages.append(message)
        self.pending_attachments = []; self.update_attachments()
        self.context_note = note
        self.messages.append({"role": "assistant", "content": ""})
        self.composer.clear(); self.render_chat(); self.generating = True
        self.send_button.setEnabled(False); self.stop_button.setEnabled(True); self.metrics.setText("Waiting for the first token…")
        self.attachment_label.setText(note or "Spreadsheets, PDF, text & code · Drop files here")
        self.run_job(lambda w: self.client.chat(payload, w.event.emit, max_tokens=output_tokens), message="Generating on phone…", events=self.chat_event)

    def chat_event(self, event):
        if event["type"] == "token":
            self.messages[-1]["content"] += event["text"]; self.render_chat()
        if event["type"] == "done":
            p = event["profile"]
            prefix = "Stopped · " if event.get("cancelled") else ""
            self.metrics.setText(f"{prefix}{p['tokens_per_second']:.1f} tokens/s  ·  First token {p['ttft_ms']/1000:.2f}s  ·  {p['tokens']} tokens")
            self.statusBar().showMessage("Response generated on the phone.")

    def stop(self):
        if self.pc_worker:
            self.stop_assistant(); return
        self.transfer_cancel.set()
        self.run_job(lambda _: self.client.cancel(), message="Stopping generation…", exclusive=False)

    def new_chat(self):
        if self.busy:
            return
        self.messages = []; self.pending_attachments = []; self.update_attachments(); self.conversation_id = uuid.uuid4().hex
        self.refresh_project_chat_controls()
        self.metrics.clear(); self.composer.clear(); self.render_chat(); self.nav.setCurrentRow(0)

    def save_chat(self):
        if self.messages:
            save_json(DATA / "conversations" / f"{self.conversation_id}.json", {"messages": self.messages, "model": self.current_status.get("loaded_name", ""), "project_id": self.active_project["id"] if self.active_project else None})

    def refresh_history(self):
        self.history.clear()
        paths = sorted((DATA / "conversations").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths[:40]:
            chat = read_json(path, {}); messages = chat.get("messages", [])
            if chat.get("project_id") != (self.active_project["id"] if self.active_project else None): continue
            if messages:
                item = QListWidgetItem(messages[0]["content"][:45]); item.setData(Qt.ItemDataRole.UserRole, str(path)); self.history.addItem(item)

    def open_chat(self, item):
        if self.busy:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole)); data = read_json(path, {})
        self.messages = data.get("messages", []); self.conversation_id = path.stem
        self.pending_attachments = []; self.update_attachments(); self.composer.clear()
        self.render_chat(); self.nav.setCurrentRow(0)

    def delete_chat(self):
        item = self.history.currentItem()
        if not item or self.busy:
            return
        if QMessageBox.question(self, "Delete conversation", "Delete this saved conversation from the PC?") != QMessageBox.StandardButton.Yes:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        path.unlink(missing_ok=True)
        if path.stem == self.conversation_id:
            self.new_chat()
        self.refresh_history()

    def logs(self):
        self.run_job(lambda _: self.client.diagnostics(), self.log_text.setPlainText, "Reading scoped Android logs…")

    def save_logs(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save diagnostics", "jiezhi-diagnostics.txt", "Text files (*.txt)")
        if filename:
            Path(filename).write_text(self.log_text.toPlainText())

    def fix_usb(self):
        rule = asset("setup-usb.sh")
        if not rule.exists():
            rule = ROOT / "scripts/setup-usb.sh"
        def work(_):
            p = subprocess.run(["pkexec", "/bin/sh", str(rule)], capture_output=True, text=True)
            if p.returncode:
                raise RuntimeError(p.stderr or "USB rule was not installed.")
        self.run_job(work, lambda _: self.device_details.setText("USB rule installed. Reconnect the cable and find phones again."), "Waiting for Deepin administrator authentication…")

    def closeEvent(self, event):
        self.save_flow_draft()
        if self.workers:
            self.statusBar().showMessage("Stop the current operation before closing JieZhi."); event.ignore(); return
        if not self.telemetry_panel.shutdown():
            event.ignore(); QTimer.singleShot(250, self.close); return
        self.desktop_popup.close()
        for popup in self.quick_results:popup.close()
        self.client.disconnect(); event.accept()
