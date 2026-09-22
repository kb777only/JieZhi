from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox

from . import attachments
from .motion import present


class AttachmentView:
    def attach_files(self):
        if self.busy: return
        filenames, _ = QFileDialog.getOpenFileNames(self, "Attach documents or code", str(Path.home()), "Documents and spreadsheets (*.xlsx *.xlsm *.xls *.ods *.pdf *.txt *.md *.csv *.py *.js *.ts *.json *.yaml *.kt *.cpp);;All files (*)")
        if filenames: self.add_attachments([Path(f) for f in filenames])

    def add_attachments(self, paths):
        if self.busy: return
        if len(self.pending_attachments) + len(paths) > attachments.MAX_FILES:
            self.failed("Attach up to five files at a time."); return
        def done(files):
            existing = {f['id'] for f in self.pending_attachments}
            self.pending_attachments.extend(f for f in files if f['id'] not in existing)
            self.update_attachments(); self.nav.setCurrentRow(0)
        self.run_job(lambda _: [attachments.extract(p) for p in paths], done, "Reading documents locally…")

    def update_attachments(self):
        files = self.pending_attachments
        self.attachment_label.setText("  ·  ".join(f["name"] + (" (extracted text limited)" if f["truncated"] else "") for f in files) if files else "Spreadsheets, PDF, text & code · Drop files here")
        self.preview_files.setEnabled(bool(files)); self.clear_files.setEnabled(bool(files))

    def clear_attachments(self):
        if self.busy: return
        self.pending_attachments = []; self.update_attachments()

    def preview_attachments(self):
        dialog = QDialog(self); dialog.setWindowTitle("Attachment preview · extracted text"); dialog.resize(720, 552)
        layout = QVBoxLayout(dialog); content = QPlainTextEdit(); content.setReadOnly(True)
        content.setPlainText("\n\n".join(f"━━ {f['name']} ━━\n{f['text']}" for f in self.pending_attachments)); layout.addWidget(content)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons); present(dialog)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if not paths: return
        event.acceptProposedAction()
        if any(p.suffix.lower() == ".gguf" for p in paths):
            if len(paths) != 1:
                self.failed("Drop one GGUF model at a time, separately from chat attachments."); return
            self.transfer_model_path(paths[0])
        else: self.add_attachments(paths)
