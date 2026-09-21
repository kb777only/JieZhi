"""The update surface: a toast that rises into the corner, and the patch notes behind it.

Nothing here reaches for the network or the filesystem itself; that is all in
`updates.py`, so the window only decides what to say and when to say it.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import threading

from PySide6.QtCore import Qt, QTimer, QPoint, QUrl, Signal, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QDialog, QTextBrowser, QProgressBar, QGroupBox, QCheckBox, QGraphicsOpacityEffect,
)

from . import __version__
from .client import save_json
from .theme import SM, MD, LG, XL
from .updates import INSTALL_DIR, Cancelled, RELEASES_PAGE, Updates, clear_leftovers, restart

# The toast rises this far as it fades in, over this long. Slow enough to be
# noticed at the edge of vision, short enough never to be waited on.
TOAST_RISE = 28
TOAST_SLIDE = 260
TOAST_WIDTH = 380
TOAST_LIFE = 9000

# Far enough after launch that the window has settled and the first scan is under way.
CONSENT_DELAY = 2000
STARTUP_CHECK_DELAY = 3500


def pretty_date(stamp: str) -> str:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).strftime("%d %B %Y")
    except ValueError:
        return ""


class Toast(QWidget):
    """A small panel that rises into the window's corner and fades in.

    It is a child of the window rather than an item in a layout, so it never
    reflows the page underneath it; `place` puts it back on every resize.
    """
    clicked = Signal()
    closed = Signal()

    def __init__(self, parent, title, detail="", actions=(), clickable=False):
        from .gui import label, button, row

        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(TOAST_WIDTH)
        self.clickable = clickable
        self.home = QPoint()
        self.animation = None
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.transparency = QGraphicsOpacityEffect(self)
        self.transparency.setOpacity(0.0)
        self.setGraphicsEffect(self.transparency)
        box = QVBoxLayout(self)
        box.setContentsMargins(MD, MD, MD, MD)
        box.setSpacing(SM)
        self.heading = label(title, "strong", True)
        box.addWidget(self.heading)
        self.detail = label(detail, "fine", True) if detail else None
        if self.detail is not None:
            box.addWidget(self.detail)
        self.buttons = []
        if actions:
            for text, action, primary in actions:
                widget = button(text, action, primary, "" if primary else "quiet")
                self.buttons.append(widget)
            box.addLayout(row(trailing=tuple(self.buttons)))

    def place(self):
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        bottom = parent.height() - (parent.statusBar().height() if hasattr(parent, "statusBar") else 0)
        self.home = QPoint(max(XL, parent.width() - self.width() - XL), max(XL, bottom - self.height() - MD))

    def slide_in(self):
        self.place()
        self.move(self.home + QPoint(0, TOAST_RISE))
        self.show()
        self.raise_()
        self.animation = self.travel(self.home + QPoint(0, TOAST_RISE), self.home, 0.0, 1.0)
        self.animation.start()

    def slide_out(self):
        if self.animation is not None:
            self.animation.stop()
        self.animation = self.travel(self.pos(), self.pos() + QPoint(0, TOAST_RISE // 2), self.transparency.opacity(), 0.0)
        self.animation.finished.connect(self.finish)
        self.animation.start()

    def travel(self, start, end, from_opacity, to_opacity):
        group = QParallelAnimationGroup(self)
        move = QPropertyAnimation(self, b"pos", group)
        move.setDuration(TOAST_SLIDE); move.setStartValue(start); move.setEndValue(end)
        move.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade = QPropertyAnimation(self.transparency, b"opacity", group)
        fade.setDuration(TOAST_SLIDE); fade.setStartValue(from_opacity); fade.setEndValue(to_opacity)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(move); group.addAnimation(fade)
        return group

    def finish(self):
        self.hide()
        self.closed.emit()
        self.deleteLater()

    def mouseReleaseEvent(self, event):
        if self.clickable and event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class UpdateDialog(QDialog):
    """What the release says, and the two buttons that decide what happens to it."""
    update_requested = Signal()

    def __init__(self, parent, release, current, reason=""):
        from .gui import label, button, row, card

        super().__init__(parent)
        self.release = release
        self.setWindowTitle(f"JieZhi {release['version']}")
        self.setModal(False)
        self.resize(640, 560)
        self.setStyleSheet(parent.styleSheet())
        box = QVBoxLayout(self)
        box.setContentsMargins(XL, XL, XL, XL)
        box.setSpacing(LG)
        box.addWidget(label(f"JieZhi {release['version']} is available", "title"))
        published = pretty_date(release.get("published", ""))
        box.addWidget(label(
            f"You are running {current}." + (f" This release was published on {published}." if published else ""),
            "subtitle", True))
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(release.get("notes") or "This release published no patch notes.")
        box.addWidget(notes, 1)

        self.note = label("", "status", True)
        self.note.setVisible(False)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        box.addWidget(self.note)
        box.addWidget(self.progress)

        self.exit_button = button("Exit", self.reject, kind="quiet")
        self.update_button = button("Update", self.begin, True)
        trailing = [self.exit_button, self.update_button]
        if reason or not release.get("archive"):
            self.update_button.setEnabled(False)
            self.note.setText(reason or "This release has no Linux bundle attached, so it cannot be installed from here.")
            self.note.setVisible(True)
            trailing.insert(0, button("Open the release page", self.open_page, kind="quiet"))
        box.addWidget(card(row(label("The update replaces the installed app and restarts it.", "fine"),
                               trailing=tuple(trailing)), spacing=SM))

    def open_page(self):
        QDesktopServices.openUrl(QUrl(self.release.get("url") or RELEASES_PAGE))

    def begin(self):
        self.update_button.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.note.setText("Starting…")
        self.note.setVisible(True)
        self.update_requested.emit()

    def advance(self, percent, message):
        self.progress.setRange(0, 100 if percent else 0)
        self.progress.setValue(percent)
        self.note.setText(message)

    def failed(self, message):
        self.progress.setVisible(False)
        self.note.setText(message)
        self.note.setVisible(True)
        self.update_button.setEnabled(bool(self.release.get("archive")))


class UpdatesView:
    """Update checking, wired into the window's preferences, toasts and settings."""

    def init_updates(self):
        self.updates = Updates()
        self.update_toast = None
        self.update_dialog = None
        self.update_release = None
        self.update_checking = False
        self.consent_toast = None
        self.update_cancel = threading.Event()
        self.restarting = False
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.dismiss_toast)
        # Whatever the last update left behind is a few hundred megabytes, and the
        # process that was holding it open is gone by now.
        threading.Thread(target=clear_leftovers, args=(self.updates.bundle() or INSTALL_DIR,), daemon=True).start()
        if "auto_update_check" not in self.preferences:
            QTimer.singleShot(CONSENT_DELAY, self.ask_about_updates)
        elif self.preferences.get("auto_update_check"):
            QTimer.singleShot(STARTUP_CHECK_DELAY, lambda: self.check_updates(announce=False))

    # Settings ---------------------------------------------------------------

    def build_update_settings(self, col):
        from .gui import label, button, row

        box = QGroupBox("Updates"); form = QVBoxLayout(box)
        self.auto_update_choice = QCheckBox("Check for a new version when JieZhi starts")
        self.auto_update_choice.setChecked(bool(self.preferences.get("auto_update_check", False)))
        form.addWidget(self.auto_update_choice)
        where = self.updates.bundle()
        form.addWidget(label(
            f"This is version {__version__}, " + (f"installed in {where}." if where else "running from a source checkout."),
            "fine", True))
        form.addWidget(label(
            "Checking reads the public release list on GitHub. An update downloads the published "
            "bundle, verifies its checksum, replaces the installed app and restarts it. The phone "
            "client is not touched: reinstall it from Device setup after a version change.", "muted", True))
        form.addLayout(row(button("Check for updates", lambda: self.check_updates(announce=True), True),
                           button("Release notes", lambda: QDesktopServices.openUrl(QUrl(RELEASES_PAGE)), kind="quiet")))
        col.addWidget(box)
        self.auto_update_choice.toggled.connect(self.update_settings_changed)

    def update_settings_changed(self):
        self.preferences["auto_update_check"] = self.auto_update_choice.isChecked()
        save_json(self.preferences_path, self.preferences)
        # Answering the question here answers it: the panel must not still be asking.
        if self.update_toast is not None and self.update_toast is self.consent_toast:
            self.dismiss_toast()

    # Toasts -----------------------------------------------------------------

    def show_toast(self, title, detail="", actions=(), clickable=False, life=0):
        self.dismiss_toast(animate=False)
        toast = Toast(self, title, detail, actions, clickable)
        toast.setStyleSheet(self.styleSheet())
        # Only the toast still on screen may clear the slot: an old one finishing
        # its fade must not take its replacement down with it.
        toast.closed.connect(lambda gone=toast: self.forget_toast(gone))
        self.update_toast = toast
        toast.slide_in()
        self.toast_timer.stop()
        if life:
            self.toast_timer.start(life)
        return toast

    def forget_toast(self, toast):
        if self.update_toast is toast:
            self.update_toast = None

    def dismiss_toast(self, animate=True):
        toast = self.update_toast
        self.toast_timer.stop()
        if toast is None:
            return
        self.update_toast = None
        if animate:
            toast.slide_out()
        else:
            toast.hide(); toast.deleteLater()

    def restyle_updates(self):
        """The toast and the patch-notes box hold their own copy of the sheet."""
        for widget in (self.update_toast, self.update_dialog):
            if widget is not None:
                widget.setStyleSheet(self.styleSheet())

    def place_toast(self):
        if self.update_toast is not None:
            self.update_toast.place()
            self.update_toast.move(self.update_toast.home)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.place_toast()

    # Asking, checking, announcing -------------------------------------------

    def ask_about_updates(self):
        """The first-launch question. It stays up until one of the two answers is given."""
        self.consent_toast = self.show_toast(
            "Check for updates automatically?",
            "JieZhi can look for a new version each time it starts. It only reads the public "
            "release list, and never installs anything without asking.",
            actions=(("Check for updates", lambda: self.check_updates(announce=True), False),
                     ("No", lambda: self.answer_updates(False), False),
                     ("Yes", lambda: self.answer_updates(True), True)),
        )

    def answer_updates(self, automatic):
        self.preferences["auto_update_check"] = bool(automatic)
        save_json(self.preferences_path, self.preferences)
        if hasattr(self, "auto_update_choice"):
            self.auto_update_choice.blockSignals(True)
            self.auto_update_choice.setChecked(bool(automatic))
            self.auto_update_choice.blockSignals(False)
        self.dismiss_toast()
        self.statusBar().showMessage(
            "JieZhi will check for updates when it starts." if automatic
            else "Automatic update checks are off. Check any time from Settings.")
        if automatic:
            self.check_updates(announce=False)

    def check_updates(self, announce=True):
        """Ask GitHub what the newest release is. `announce` also reports no news."""
        from .gui import Worker

        if self.update_checking:
            return
        self.update_checking = True
        self.statusBar().showMessage("Checking for updates…")
        worker = Worker(lambda _: self.updates.check())
        self.workers.add(worker)
        worker.result.connect(lambda release: self.update_check_result(release, announce))
        worker.error.connect(lambda message: self.update_check_failed(message, announce))
        def finish():
            self.update_checking = False
            self.workers.discard(worker); worker.deleteLater()
        worker.finished.connect(finish)
        worker.start()

    def update_check_result(self, release, announce):
        if release:
            self.update_release = release
            self.announce_update(release)
            return
        self.statusBar().showMessage(f"JieZhi {__version__} is the latest version.")
        if announce:
            self.show_toast(f"JieZhi {__version__} is up to date",
                            "This is the newest release published for the app.", life=TOAST_LIFE)

    def update_check_failed(self, message, announce):
        self.statusBar().showMessage(message)
        if announce:
            self.show_toast("Could not check for updates", message, life=TOAST_LIFE)

    def announce_update(self, release):
        self.statusBar().showMessage(f"JieZhi {release['version']} is available.")
        self.show_toast(f"JieZhi {release['version']} is available",
                        "Click to see what has changed.", clickable=True).clicked.connect(self.open_update_dialog)

    def open_update_dialog(self):
        if not self.update_release:
            return
        self.dismiss_toast()
        if self.update_dialog is not None:
            self.update_dialog.raise_(); self.update_dialog.activateWindow(); return
        dialog = UpdateDialog(self, self.update_release, __version__, self.updates.blocked())
        dialog.update_requested.connect(self.start_update)
        dialog.finished.connect(self.close_update_dialog)
        self.update_dialog = dialog
        dialog.show()

    def close_update_dialog(self, *_):
        # Leaving the box is also how a download in progress is abandoned; the
        # installation is only touched once the download has finished and verified.
        self.update_cancel.set()
        dialog = self.update_dialog
        self.update_dialog = None
        if dialog is not None:
            dialog.deleteLater()

    # Downloading, installing, restarting -------------------------------------

    def start_update(self):
        from .gui import Worker

        release = self.update_release
        destination = self.updates.bundle()
        dialog = self.update_dialog
        if not release or destination is None or dialog is None:
            return
        self.update_cancel = threading.Event()
        cancel = self.update_cancel

        def work(worker):
            def progress(percent, message):
                worker.progress.emit(percent, message)
            archive = self.updates.download(release, progress, cancel)
            if cancel.is_set():
                raise Cancelled()
            return self.updates.install(archive, destination, progress)

        worker = Worker(work)
        self.workers.add(worker)
        worker.progress.connect(dialog.advance)
        worker.result.connect(self.finish_update)
        worker.error.connect(self.update_failed)
        def finish():
            self.workers.discard(worker); worker.deleteLater()
        worker.finished.connect(finish)
        worker.start()

    def update_failed(self, message):
        if message == "":
            message = "The update was cancelled. Nothing was changed."
        self.statusBar().showMessage(message)
        if self.update_dialog is not None:
            self.update_dialog.failed(message)

    def finish_update(self, destination):
        """Hand over to the new bundle. The old one stays on disk until it has exited."""
        self.restarting = True
        self.statusBar().showMessage("Updated. Restarting JieZhi…")
        if self.update_dialog is not None:
            self.update_dialog.advance(100, "Updated. Restarting JieZhi…")
        restart(Path(destination) / "JieZhi")
        QTimer.singleShot(400, self.close)
