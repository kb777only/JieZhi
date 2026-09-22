from __future__ import annotations

import html
from pathlib import Path
import subprocess
import threading
import uuid

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRect, QPropertyAnimation
from PySide6.QtGui import QFont, QTextCursor, QShortcut, QKeySequence, QPainter, QColor
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
from .update_view import UpdatesView
from .workflow_view import WorkflowView

from .theme import (
    XS, SM, MD, LG, XL, SIDEBAR, LABEL, SMALL, BASE, RISE, stylesheet, tokens,
)
from .motion import CURVE, fade_in, moving

STYLE = stylesheet(False)

# Destinations grouped by what they are for, over the flat page stack. The
# second value is the stack index, so call sites keep addressing pages by index.
# Three groups of three. The window has nine destinations and the menu shows
# all nine, Settings included: it used to hide behind the gear alone, which is
# how a page ends up forgotten.
NAV_GROUPS = [
    ("WORK", [("Chat", 0), ("Projects", 5), ("Flow canvas", 7)]),
    ("PHONE", [("Welcome & device", 2), ("Phone models", 1), ("Discover models", 4)]),
    ("THIS PC", [("PC Assistant", 6), ("Runtime diagnostics", 3), ("Settings", 8)]),
]


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


class NavList(QListWidget):
    """Grouped navigation over an ungrouped stack.

    Group headings are rows too, so the mapping between a visible row and a
    page index lives here instead of in every caller.
    """
    pageChanged = Signal(int)

    def __init__(self, groups):
        super().__init__(); self.setObjectName("navigation")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.headings = []; self.page_of_row = {}; self.row_of_page = {}
        self.marker = QWidget(self.viewport()); self.marker.setObjectName("navMarker")
        self.marker.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.marker.hide(); self.marker_motion = None
        for title, entries in groups:
            heading = QListWidgetItem(title); heading.setFlags(Qt.ItemFlag.NoItemFlags)
            font = heading.font(); font.setPixelSize(LABEL); font.setBold(True)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
            heading.setFont(font); self.addItem(heading); self.headings.append(heading)
            for text, page in entries:
                self.addItem(QListWidgetItem(text))
                self.page_of_row[self.count() - 1] = page; self.row_of_page[page] = self.count() - 1
        super().currentRowChanged.connect(lambda row: self.pageChanged.emit(self.page_of_row.get(row, -1)))
        super().currentRowChanged.connect(lambda _row: self.slide_marker())

    def fit(self):
        """Size to the rows. Called after the stylesheet lands, since padding
        from the sheet is what decides how tall a row actually is."""
        self.setFixedHeight(sum(self.sizeHintForRow(i) + SM for i in range(self.count())) + SM)

    def slide_marker(self):
        """Travel the marker to the selected row.

        It is a child of the viewport rather than a stylesheet border, because
        a border cannot move and this is the one piece of the window that says
        where you are."""
        row = super().currentRow()
        if row < 0:
            self.marker.hide(); return
        rect = self.visualItemRect(self.item(row))
        target = QRect(0, rect.y() + SM, 3, max(MD, rect.height() - MD))
        resting = self.marker.isHidden() or not moving(self)
        self.marker.setGeometry(target) if resting else None
        if resting:
            self.marker.show(); self.marker.raise_(); return
        animation = QPropertyAnimation(self.marker, b"geometry", self)
        animation.setDuration(BASE); animation.setEasingCurve(CURVE)
        animation.setStartValue(self.marker.geometry()); animation.setEndValue(target)
        self.marker_motion = animation; animation.start()

    def setCurrentRow(self, page):
        super().setCurrentRow(self.row_of_page.get(page, -1))

    def currentRow(self):
        return self.page_of_row.get(super().currentRow(), -1)

    def recolour(self, dark):
        self.fit()
        t = tokens(dark)
        self.marker.setStyleSheet(f'QWidget#navMarker {{ background: {t["accent"]}; border-radius: 3px; }}')
        self.slide_marker()
        ink = QColor(t["ink_3"])
        for heading in self.headings:
            heading.setForeground(ink)


class EmptyList(QListWidget):
    """A list that says what belongs in it while it is empty."""

    def __init__(self, placeholder, parent=None):
        super().__init__(parent); self.placeholder = placeholder

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count():
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor(tokens(getattr(self.window(), "dark", False))["ink_3"]))
        font = painter.font(); font.setPixelSize(SMALL); painter.setFont(font)
        painter.drawText(self.viewport().rect().adjusted(XL, 0, -XL, 0),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.placeholder)
        painter.end()


def button(text, action, primary=False, kind=""):
    widget = QPushButton(text)
    widget.setObjectName("primary" if primary else kind)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(action)
    return widget


def label(text, kind="", wrap=False):
    widget = QLabel(text); widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(kind); widget.setWordWrap(wrap)
    return widget


def wide(widget, width):
    """Cap a control so it stops growing with the window."""
    widget.setMaximumWidth(width); return widget


def _place(layout, item):
    stretch = 0
    if isinstance(item, tuple):
        item, stretch = item
    if isinstance(item, QWidget):
        layout.addWidget(item, stretch)
    elif item is not None:
        layout.addLayout(item, stretch)


def row(*leading, trailing=(), spacing=SM):
    """A control row that always ends in a stretch.

    Rows without one let Qt spread their buttons over the whole window, which
    is what made every action on a page look equally important.
    """
    layout = QHBoxLayout(); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(spacing)
    for item in leading:
        _place(layout, item)
    # An item that already takes the slack is the stretch; adding another one
    # would halve the space it just claimed.
    if not any(isinstance(item, tuple) and item[1] for item in leading):
        layout.addStretch(1)
    for item in trailing:
        _place(layout, item)
    return layout


def card(*children, spacing=MD, padding=MD):
    """The one container: a surface, a hairline border, one radius."""
    panel = QWidget(); panel.setObjectName("card")
    panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(padding, padding, padding, padding); layout.setSpacing(spacing)
    for child in children:
        _place(layout, child)
    return panel


class Window(DesktopActionsView, ProjectChatView, SettingsView, UpdatesView, WorkflowView, HubView, AttachmentView, ProjectView, AssistantView, QMainWindow):
    def __init__(self):
        super().__init__()
        self.preferences_path=DATA/'preferences.json';self.preferences=read_json(self.preferences_path,{})
        self.dark=self.preferences.get('dark',False)
        self.client = Client(); self.workers = set(); self.busy = False
        self.initial_scan = True; self.pending_attachments = []; self.setAcceptDrops(True)
        self.current_status = {}; self.messages = []; self.conversation_id = uuid.uuid4().hex
        self.transfer_cancel = threading.Event(); self.generating = False
        self.setWindowTitle("JieZhi · 借智 — Borrow intelligence")
        self.resize(1440, 1008); self.setMinimumSize(1152, 840)
        self.setStyleSheet(STYLE)
        root = QWidget(); self.setCentralWidget(root); layout = QHBoxLayout(root)
        layout.setContentsMargins(LG, LG, LG, SM); layout.setSpacing(XL)
        layout.addWidget(self.build_sidebar())
        content = QVBoxLayout(); content.setContentsMargins(0, XS, 0, 0); content.setSpacing(LG)
        layout.addLayout(content, 1)
        self.pages = QStackedWidget(); content.addWidget(self.pages, 1)
        self.pages.currentChanged.connect(self.page_arrived)
        self.telemetry_panel = TelemetryPanel(self.client, self); content.addWidget(self.telemetry_panel)
        self.build_chat(); self.build_models(); self.build_setup(); self.build_diagnostics(); self.build_hub(); self.build_projects(); self.build_assistant(); self.build_workflows(); self.init_updates(); self.build_settings(); self.init_desktop_popup()
        self.nav.pageChanged.connect(self.pages.setCurrentIndex); self.nav.setCurrentRow(2)
        self.refresh_history(); self.render_chat(); self.apply_appearance()
        self.statusBar().showMessage("Connect your Snapdragon 8 Elite phone to get started.")
        self.heartbeat = QTimer(self); self.heartbeat.setInterval(24_000)
        self.heartbeat.timeout.connect(self.keep_alive); self.heartbeat.start()
        QTimer.singleShot(96, lambda: self.run_job(lambda _: self.hub.restore(), self.hub_account_result, "Restoring account…"))
        QTimer.singleShot(996, self.start_scan)

    def build_sidebar(self):
        panel = QWidget(); panel.setObjectName("sidebar"); panel.setFixedWidth(SIDEBAR)
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sidebar = QVBoxLayout(panel); sidebar.setContentsMargins(MD, LG, MD, MD); sidebar.setSpacing(MD)
        sidebar.addWidget(label("借智  JieZhi", "brand"))
        sidebar.addWidget(label("Intelligence, borrowed.", "fine"))
        self.nav = NavList(NAV_GROUPS); sidebar.addWidget(self.nav)
        sidebar.addWidget(button("＋  New conversation", self.new_chat, True))
        sidebar.addWidget(label("RECENT CONVERSATIONS", "section"))
        self.history = EmptyList("Conversations you send are saved here.")
        self.history.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.history.itemClicked.connect(self.open_chat); sidebar.addWidget(self.history, 1)
        self.delete_button = button("Delete conversation", self.delete_chat, kind="quiet")
        sidebar.addWidget(self.delete_button)
        self.connection = label("○  No phone connected", "status", True); sidebar.addWidget(self.connection)
        self.theme_button = button("☾", self.toggle_dark, kind="corner")
        self.theme_button.setAccessibleName("Toggle dark mode")
        self.settings_button = button("⚙", self.open_settings, kind="corner")
        self.settings_button.setToolTip("Settings"); self.settings_button.setAccessibleName("Open settings")
        sidebar.addLayout(row(label("USB · On-device", "fine"),
                              trailing=(self.theme_button, self.settings_button)))
        return panel

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
        worker.error.connect(lambda message: self.set_connection("○  Connection lost · reconnect in Setup"))
        def finish():
            self.workers.discard(worker); worker.deleteLater()
        worker.finished.connect(finish); worker.start()

    def set_connection(self, text):
        if text == self.connection.text():
            return
        self.connection.setText(text); fade_in(self.connection)

    def page_arrived(self, index):
        """Fade the page that just came forward, from a few pixels below."""
        page = self.pages.widget(index)
        if page is not None:
            fade_in(page, rise=RISE)

    def page(self, title, subtitle, trailing=None):
        """Title, subtitle and one optional status chip, on a single band."""
        page = QWidget(); layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(LG)
        heading = QVBoxLayout(); heading.setContentsMargins(0, 0, 0, 0); heading.setSpacing(2)
        heading.addWidget(label(title, "title")); heading.addWidget(label(subtitle, "subtitle", True))
        head = QHBoxLayout(); head.setContentsMargins(0, 0, 0, 0); head.setSpacing(XL)
        head.addLayout(heading, 1)
        if trailing is not None:
            head.addWidget(trailing, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(head)
        self.pages.addWidget(page)
        return layout

    def build_chat(self):
        self.model_badge = label("No model loaded · choose one in Phone models", "badge")
        layout = self.page("What’s on your mind?", "A private conversation, with room to think.", self.model_badge)
        self.project_badge = label("Personal conversation · No project", "status", True)
        self.project_badge.setVisible(False); layout.addWidget(self.project_badge)
        self.build_project_chat_controls(layout)
        self.transcript = QTextBrowser(); self.transcript.setOpenExternalLinks(False); self.transcript.setAcceptDrops(False)
        layout.addWidget(self.transcript, 1)

        self.attachment_label = label("Spreadsheets, PDF, text and code · drop files anywhere", "fine", True)
        self.preview_files = button("Preview", self.preview_attachments, kind="quiet")
        self.clear_files = button("Remove", self.clear_attachments, kind="quiet")
        attach = button("＋ Attach files", self.attach_files, kind="quiet")
        self.composer = QPlainTextEdit(); self.composer.setObjectName("flat"); self.composer.setAcceptDrops(False)
        self.composer.setPlaceholderText("Ask a question, or attach a document to explore…")
        self.composer.setMinimumHeight(84); self.composer.setMaximumHeight(108)
        self.metrics = label("", "fine")
        self.stop_button = button("Stop", self.stop); self.stop_button.setEnabled(False)
        self.send_button = button("Send message", self.send, True)
        layout.addWidget(card(
            row(self.attachment_label, trailing=(attach, self.preview_files, self.clear_files)),
            self.composer,
            row(self.metrics, trailing=(self.stop_button, self.send_button)),
            spacing=SM,
        ))
        self.update_attachments()
        self.send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.send_shortcut.activated.connect(self.send)
        self.send_button.setToolTip("Ctrl+Enter")

    def build_models(self):
        layout = self.page("Your model library", "Import a GGUF from this PC. It is transferred once, verified, and stored privately on the phone.")
        layout.addLayout(row(button("Import GGUF…", self.import_model, True), button("Refresh library", self.refresh)))
        layout.addWidget(label("Start with Q4_0 models. Architecture, quantization and phone memory determine compatibility.", "fine", True))
        self.models = EmptyList("No models on the phone yet. Import a GGUF to send one over USB.")
        layout.addWidget(self.models, 1)

        self.backend = QComboBox(); self.backend.addItem("Hexagon NPU", "npu"); self.backend.addItem("Phone CPU · diagnostics", "cpu")
        wide(self.backend, 220)
        self.context = QSpinBox(); self.context.setRange(512, 8192); self.context.setSingleStep(512); self.context.setValue(2048)
        wide(self.context, 110)
        layout.addLayout(row(
            label("Backend", "muted"), self.backend, label("Context", "muted"), self.context,
            trailing=(button("Delete from phone", self.delete_model, kind="danger"),
                      button("Unload", self.unload), button("Load model", self.load_model, True)),
            spacing=MD,
        ))
        self.progress = QProgressBar(); self.progress.setValue(0); self.progress.setVisible(False)
        wide(self.progress, 360)
        self.transfer_label = label("Select a local model to begin.", "fine")
        self.pause_button = button("Pause transfer", self.pause_transfer, kind="quiet"); self.pause_button.setEnabled(False)
        layout.addLayout(row(self.progress, self.transfer_label, trailing=(self.pause_button,), spacing=MD))

    def build_setup(self):
        layout = self.page("Welcome to JieZhi", "A phone-powered workspace, built around you.")
        self.welcome_art = DeviceWelcome(); layout.addWidget(self.welcome_art)
        steps = []
        for number, title, desc in [
            ("01", "Enable USB debugging", "On Android, enable Developer options → USB debugging. Connect a data-capable cable and approve this PC on the phone."),
            ("02", "Install the Android client", "Select the USB device below and install JieZhi. Xiaomi may ask you to allow installation over USB."),
            ("03", "Pair with JieZhi", "Connect, then enter the six-digit code displayed by the Android client. Keep the client running while using the desktop app."),
        ]:
            step = QHBoxLayout(); step.setContentsMargins(0, 0, 0, 0); step.setSpacing(MD)
            step.addWidget(label(number, "section"), 0, Qt.AlignmentFlag.AlignTop)
            text = QVBoxLayout(); text.setContentsMargins(0, 0, 0, 0); text.setSpacing(2)
            text.addWidget(label(title, "strong")); text.addWidget(label(desc, "muted", True))
            step.addLayout(text, 1); steps.append(step)
        layout.addWidget(card(*steps, spacing=MD, padding=LG))

        self.device_picker = QComboBox(); wide(self.device_picker, 420)
        self.device_picker.setMinimumWidth(324)
        layout.addLayout(row(
            self.device_picker, button("Find phones", self.scan),
            trailing=(button("Install Android client", self.install_client),
                      button("Disconnect", self.disconnect_phone),
                      button("Connect && pair", self.connect_phone, True)),
            spacing=MD,
        ))
        self.device_details = label("Waiting for a phone…", "status", True)
        layout.addWidget(card(self.device_details, padding=MD))
        layout.addStretch()
        layout.addLayout(row(
            (label("If Linux reports “no permissions”, install the USB access rule. Deepin will request administrator authentication.", "fine", True), 1),
            trailing=(button("Fix USB access…", self.fix_usb, kind="quiet"),), spacing=MD,
        ))

    def build_diagnostics(self):
        layout = self.page("Runtime diagnostics", "The selected backend is a request. Native Hexagon initialization and offload logs provide evidence of NPU use.")
        layout.addLayout(row(button("Read phone runtime logs", self.logs, True), button("Save diagnostics…", self.save_logs)))
        self.log_text = QPlainTextEdit(); self.log_text.setObjectName("console"); self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("Read the phone's runtime logs to see how the model was loaded and where it ran.")
        layout.addWidget(self.log_text, 1)
        layout.addWidget(label("NPU acceleration can still involve CPU tokenization, sampling and unsupported operations. This view does not measure a hardware utilization percentage.", "fine", True))

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
            self.progress.setVisible(False); self.hub_progress.setVisible(False)
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
        self.client.disconnect(); self.current_status = {}; self.set_connection("○  No phone connected")
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
        self.set_connection(f"●  {status.get('phone', 'Phone connected')}")
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
        self.progress.setVisible(True); self.hub_progress.setVisible(True)
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
        t = tokens(self.dark)
        if not self.messages:
            self.transcript.setHtml(
                f'''<div style="margin:56px 12px;color:{t["ink"]}">
                <p style="font-size:20px;font-weight:600;margin:0 0 10px">A fresh conversation.</p>
                <p style="color:{t["ink_2"]};margin:0 0 6px">Explore an idea, bring a document, or pick up a project.</p>
                <p style="color:{t["ink_3"]};margin:0">Your files stay here. Your phone does the thinking.</p></div>''')
            return
        parts = []
        for message in self.messages:
            mine = message["role"] == "user"
            who = "You" if mine else "JieZhi"
            color = t["ink_3"] if mine else t["accent_text"]
            content = html.escape(message["content"]).replace("\n", "<br>")
            files = " · ".join(html.escape(f["name"]) for f in message.get("attachments", []))
            attachment_line = f'<p style="color:{t["ink_3"]};margin:0 0 6px">Attached · {files}</p>' if files else ""
            action_line = "".join(
                f'<p style="color:{t["ink_3"]};margin:4px 0 0">{html.escape(a)}</p>'
                for a in message.get("actions", []))
            parts.append(
                f'<p style="color:{color};margin:26px 0 6px;font-size:11px;font-weight:700;'
                f'letter-spacing:1px">{who.upper()}</p>{attachment_line}'
                f'<p style="color:{t["ink"]};margin:0">{content}</p>{action_line}')
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
        # An update has already replaced this bundle on disk and started its
        # successor, so the usual "finish what you started" guard would only
        # keep a stale process alive.
        if self.workers and not self.restarting:
            self.statusBar().showMessage("Stop the current operation before closing JieZhi."); event.ignore(); return
        if not self.telemetry_panel.shutdown():
            event.ignore(); QTimer.singleShot(250, self.close); return
        self.desktop_popup.close()
        for popup in list(self.quick_results):popup.close()
        self.client.disconnect(); event.accept()
