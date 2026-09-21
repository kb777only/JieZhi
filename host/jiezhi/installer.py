from pathlib import Path
import os
import shutil
import subprocess
import sys

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QProgressBar, QMessageBox

from .gui import STYLE, Worker, label
from .updates import INSTALL_DIR, DESKTOP_FILE, install_bundle  # noqa: F401  (the installer's public surface)


class Installer(QWidget):
    def __init__(self):
        super().__init__(); self.worker = None
        self.setWindowTitle("Install JieZhi · 借智"); self.resize(650, 450); self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self); layout.setContentsMargins(36, 36, 36, 36); layout.setSpacing(20)
        layout.addWidget(label("借智  JieZhi", "brand"))
        layout.addWidget(label("Your phone powers your assistant.", "title", True))
        layout.addWidget(label("Install the Linux app, Android client package, and USB tools for your account. No administrator password is needed for the app itself.", "muted", True))
        layout.addWidget(label(f"Location: {INSTALL_DIR}", "muted", True))
        self.status = label("Deepin 25 / Debian · x86_64 · V1 prototype", "muted", True); layout.addWidget(self.status)
        self.progress = QProgressBar(); self.progress.hide(); layout.addWidget(self.progress)
        layout.addStretch()
        self.install_button = QPushButton("Install JieZhi"); self.install_button.setObjectName("primary"); self.install_button.clicked.connect(self.install); layout.addWidget(self.install_button)
        self.remove_button = QPushButton("Uninstall existing desktop app"); self.remove_button.setEnabled(INSTALL_DIR.exists()); self.remove_button.clicked.connect(self.uninstall); layout.addWidget(self.remove_button)

    def install(self):
        if not getattr(sys, "frozen", False):
            QMessageBox.warning(self, "Build required", "Run this installer from the packaged distribution."); return
        self.install_button.setEnabled(False); self.remove_button.setEnabled(False)
        self.progress.setRange(0, 0); self.progress.show(); self.status.setText("Installing app and bundled Android client…")
        self.worker = Worker(lambda _: install_bundle(Path(sys.executable).parent))
        self.worker.result.connect(self.installed); self.worker.error.connect(self.failed)
        self.worker.finished.connect(self.finished); self.worker.start()

    def finished(self):
        self.progress.hide()
        self.worker.deleteLater(); self.worker = None

    def installed(self, _):
        self.status.setText("Installed. JieZhi is now in your application menu.")
        self.install_button.setText("Open JieZhi"); self.install_button.setEnabled(True)
        self.install_button.clicked.disconnect(); self.install_button.clicked.connect(self.launch)
        self.remove_button.setEnabled(True)

    def launch(self):
        subprocess.Popen([str(INSTALL_DIR / "JieZhi")], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.close()

    def failed(self, message):
        self.status.setText(message); self.install_button.setEnabled(True)

    def uninstall(self):
        if QMessageBox.question(self, "Uninstall JieZhi", "Remove the desktop application? Your conversations and phone models will be kept.") != QMessageBox.StandardButton.Yes:
            return
        if INSTALL_DIR.exists():
            shutil.rmtree(INSTALL_DIR)
        DESKTOP_FILE.unlink(missing_ok=True)
        self.status.setText("Desktop app removed. Conversations and phone data are retained.")
        self.remove_button.setEnabled(False)

    def closeEvent(self, event):
        if self.worker:
            event.ignore()
        else:
            event.accept()
