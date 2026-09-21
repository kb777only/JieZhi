import hashlib
import json
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from jiezhi.updates import Updates, clear_leftovers, describe, is_newer, parse_version, swap_bundle


def bundle(path, marker):
    """A directory shaped like a PyInstaller onedir build."""
    path.mkdir(parents=True)
    (path / "JieZhi").write_text(marker)
    (path / "JieZhi").chmod(0o755)
    (path / "_internal").mkdir()
    (path / "_internal/lazy.so").write_text(marker)
    return path


def tarball(source, target):
    with tarfile.open(target, "w:gz") as tar:
        tar.add(source, arcname="JieZhi")
    return target


@pytest.fixture
def feed(tmp_path):
    """A stand-in for the GitHub release API, its assets, and its SHA256SUMS."""
    staged = bundle(tmp_path / "build/JieZhi", "version 0.7.0")
    archive = tarball(staged, tmp_path / "JieZhi-0.7.0-alpha.1-linux-x86_64.tar.gz")
    payload = archive.read_bytes()
    state = {
        "releases": None,
        "sums": None,
        "asset": payload,
        "status": 200,
        "hits": [],
    }

    def release(tag, assets, prerelease=True, draft=False, body="Patch notes."):
        return {"tag_name": tag, "name": f"JieZhi {tag}", "body": body, "draft": draft,
                "prerelease": prerelease, "html_url": f"https://example.invalid/{tag}",
                "published_at": "2026-09-21T10:00:00Z", "assets": assets}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state["hits"].append(self.path)
            if self.path.startswith("/repos/"):
                body = json.dumps(state["releases"]).encode()
                status = state["status"]
            elif self.path == "/SHA256SUMS":
                body = state["sums"]
                status = 200 if body is not None else 404
                body = body or b""
            else:
                body = state["asset"]
                status = 200
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    assets = [
        {"name": archive.name, "size": len(payload), "browser_download_url": f"{base}/{archive.name}"},
        {"name": "SHA256SUMS", "size": 64, "browser_download_url": f"{base}/SHA256SUMS"},
    ]
    state["releases"] = [release("v0.7.0-alpha.1", assets)]
    state["sums"] = f"{hashlib.sha256(payload).hexdigest()}  {archive.name}\n".encode()
    state["release"] = release
    state["assets"] = assets
    updates = Updates(version="0.6.0-alpha.1", api=base, cache=tmp_path / "cache")
    yield updates, state, tmp_path
    server.shutdown()
    server.server_close()
    thread.join()


def test_version_order_puts_a_release_above_its_prereleases():
    assert is_newer("0.7.0-alpha.1", "0.6.0-alpha.1")
    assert is_newer("v0.7.0-alpha.2", "0.7.0-alpha.1")
    assert is_newer("0.7.0", "0.7.0-rc.1")
    assert is_newer("0.7.0-beta.1", "0.7.0-alpha.9")
    assert not is_newer("0.6.0-alpha.1", "0.6.0-alpha.1")
    assert not is_newer("0.5.0-alpha.1", "0.6.0-alpha.1")
    assert not is_newer("0.7.0-alpha.1", "0.7.0")
    # The pyproject spelling of the same version must not read as a different one.
    assert not is_newer("0.6.0a1", "0.6.0-alpha.1")
    # Nothing unparseable is ever treated as newer.
    assert parse_version("nightly") is None
    assert not is_newer("nightly", "0.6.0-alpha.1")
    assert not is_newer("0.7.0-alpha.1", "nightly")


def test_check_picks_the_newest_published_release(feed):
    updates, state, _ = feed
    assert updates.check()["version"] == "0.7.0-alpha.1"

    # An older tag published later must not win, and drafts are not offered.
    state["releases"] = [
        state["release"]("v0.7.0-alpha.1", state["assets"]),
        state["release"]("v0.6.5-alpha.1", state["assets"]),
        state["release"]("v0.9.0-alpha.1", state["assets"], draft=True),
    ]
    assert updates.check()["version"] == "0.7.0-alpha.1"

    # Nothing newer than what is running is not an update.
    state["releases"] = [state["release"]("v0.6.0-alpha.1", state["assets"]),
                         state["release"]("v0.5.0-alpha.1", state["assets"])]
    assert updates.check() is None


def test_release_without_a_linux_bundle_is_reported_not_installed(feed):
    updates, state, _ = feed
    state["releases"] = [state["release"]("v0.7.0-alpha.1", [])]
    release = updates.check()
    assert release["archive"] is None
    with pytest.raises(RuntimeError, match="no Linux bundle"):
        updates.download(release)


def test_download_verifies_the_published_checksum(feed):
    updates, state, tmp_path = feed
    release = updates.check()
    seen = []
    archive = updates.download(release, lambda percent, message: seen.append(percent))
    assert archive.exists() and seen[-1] == 100

    # A bundle of the right length whose bytes are not the published ones is
    # still discarded, and the installation is never reached.
    state["asset"] = state["asset"][:-1] + bytes([state["asset"][-1] ^ 0xFF])
    archive.unlink()
    with pytest.raises(RuntimeError, match="checksum"):
        updates.download(release)
    assert not archive.exists()
    assert not list((tmp_path / "cache").glob("*.partial"))

    # A truncated download is caught before the checksum is even considered.
    state["asset"] = state["asset"][:-64]
    with pytest.raises(RuntimeError, match="published size"):
        updates.download(release)
    assert not list((tmp_path / "cache").glob("*.partial"))


def test_download_refuses_when_the_checksum_cannot_be_read(feed):
    updates, state, _ = feed
    release = updates.check()
    state["sums"] = None
    with pytest.raises(RuntimeError, match="checksums"):
        updates.download(release)


def test_cancelling_a_download_leaves_nothing_behind(feed):
    from jiezhi.updates import Cancelled

    updates, _, tmp_path = feed
    release = updates.check()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        updates.download(release, cancel=cancel)
    assert not list((tmp_path / "cache").glob("*.partial"))


def test_install_swaps_the_bundle_and_keeps_the_old_one(feed):
    updates, _, tmp_path = feed
    destination = bundle(tmp_path / "opt/jiezhi", "version 0.6.0")
    open_file = (destination / "_internal/lazy.so").open("rb")
    archive = updates.download(updates.check())

    updates.install(archive, destination)

    assert (destination / "JieZhi").read_text() == "version 0.7.0"
    # The replaced bundle is still readable: the process being updated is still
    # running out of it and loads parts of itself lazily.
    assert open_file.read() == b"version 0.6.0"
    open_file.close()
    previous = destination.with_name("jiezhi.previous")
    assert (previous / "_internal/lazy.so").read_text() == "version 0.6.0"
    assert not destination.with_name("jiezhi.unpack").exists()

    clear_leftovers(destination)
    assert not previous.exists()


def test_a_failed_swap_puts_the_previous_bundle_back(tmp_path):
    destination = bundle(tmp_path / "opt/jiezhi", "version 0.6.0")
    stage = tmp_path / "opt/jiezhi.installing"
    stage.mkdir()  # no JieZhi executable inside

    with pytest.raises(RuntimeError, match="Incomplete installer"):
        swap_bundle(stage, destination, desktop_file=None)
    assert (destination / "JieZhi").read_text() == "version 0.6.0"

    bundle(tmp_path / "opt/jiezhi.staged", "version 0.7.0")
    (tmp_path / "opt/jiezhi.staged").rename(stage)
    swap_bundle(stage, destination, desktop_file=None, keep_backup=True)
    assert (destination / "JieZhi").read_text() == "version 0.7.0"
    assert (destination.with_name("jiezhi.previous") / "JieZhi").read_text() == "version 0.6.0"


def test_a_tarball_cannot_write_outside_the_staging_directory(feed, tmp_path):
    updates, _, _ = feed
    destination = bundle(tmp_path / "opt/jiezhi", "version 0.6.0")
    escape = tmp_path / "hostile.tar.gz"
    victim = tmp_path / "opt/victim"
    victim.write_text("untouched")
    with tarfile.open(escape, "w:gz") as tar:
        info = tarfile.TarInfo("../victim")
        payload = b"owned"
        info.size = len(payload)
        import io
        tar.addfile(info, io.BytesIO(payload))

    with pytest.raises(Exception):
        updates.install(escape, destination)
    assert victim.read_text() == "untouched"
    assert (destination / "JieZhi").read_text() == "version 0.6.0"


def test_describe_reads_the_assets_package_sh_uploads():
    release = describe({
        "tag_name": "v0.7.0-alpha.1", "body": " notes ", "prerelease": True,
        "html_url": "https://example.invalid/r", "published_at": "2026-09-21T10:00:00Z",
        "assets": [
            {"name": "JieZhi-0.7.0-alpha.1-android-arm64.apk", "size": 1, "browser_download_url": "a"},
            {"name": "JieZhi-0.7.0-alpha.1-Installer.run", "size": 2, "browser_download_url": "b"},
            {"name": "JieZhi-0.7.0-alpha.1-linux-x86_64.tar.gz", "size": 3, "browser_download_url": "c"},
            {"name": "SHA256SUMS", "size": 4, "browser_download_url": "d"},
        ],
    })
    assert release["version"] == "0.7.0-alpha.1"
    assert release["notes"] == "notes"
    assert release["archive"] == {"name": "JieZhi-0.7.0-alpha.1-linux-x86_64.tar.gz", "url": "c", "size": 3}
    assert release["checksums"] == "d"


def window(qtbot, tmp_path, monkeypatch, updates):
    """The real window, with the network and the phone scan taken out."""
    from PySide6.QtWidgets import QApplication
    import jiezhi.gui as gui
    import jiezhi.hub as hub
    import jiezhi.update_view as update_view
    from jiezhi.gui import Window

    monkeypatch.setattr(gui, "DATA", tmp_path / "data")
    monkeypatch.setattr(hub, "DATA", tmp_path / "data")
    monkeypatch.setattr(Window, "start_scan", lambda self: None)
    monkeypatch.setattr(hub.Hub, "restore", lambda self: {})
    monkeypatch.setattr(update_view, "Updates", lambda: updates)
    monkeypatch.setattr(update_view, "clear_leftovers", lambda destination: None)
    monkeypatch.setattr(update_view, "CONSENT_DELAY", 0)
    monkeypatch.setattr(update_view, "STARTUP_CHECK_DELAY", 0)
    w = Window(); qtbot.addWidget(w); w.show(); qtbot.wait(150)
    QApplication.processEvents()
    return w


def press(qtbot, toast, text):
    from PySide6.QtCore import Qt
    target = next(b for b in toast.buttons if b.text() == text)
    qtbot.mouseClick(target, Qt.MouseButton.LeftButton)


def test_first_launch_asks_before_it_checks_anything(qtbot, tmp_path, monkeypatch, feed):
    updates, _, _ = feed
    w = window(qtbot, tmp_path, monkeypatch, updates)

    # The question rises into the corner and waits there for an answer.
    qtbot.waitUntil(lambda: w.update_toast is not None, timeout=5000)
    assert "automatically" in w.update_toast.heading.text()
    assert "auto_update_check" not in w.preferences
    qtbot.wait(400)
    assert w.update_toast.transparency.opacity() == 1.0

    press(qtbot, w.update_toast, "No")
    assert w.preferences["auto_update_check"] is False
    assert w.auto_update_choice.isChecked() is False
    qtbot.waitUntil(lambda: not w.workers, timeout=5000)
    w.close()


def test_saying_yes_checks_and_offers_the_release(qtbot, tmp_path, monkeypatch, feed):
    from PySide6.QtWidgets import QTextBrowser

    updates, _, _ = feed
    w = window(qtbot, tmp_path, monkeypatch, updates)
    qtbot.waitUntil(lambda: w.update_toast is not None, timeout=5000)
    press(qtbot, w.update_toast, "Yes")
    assert w.preferences["auto_update_check"] is True

    qtbot.waitUntil(lambda: w.update_toast is not None and "available" in w.update_toast.heading.text(), timeout=5000)
    assert w.update_release["version"] == "0.7.0-alpha.1"
    w.update_toast.clicked.emit()
    qtbot.waitUntil(lambda: w.update_dialog is not None, timeout=5000)
    dialog = w.update_dialog
    assert "Patch notes" in dialog.findChild(QTextBrowser).toPlainText()
    # Running from a checkout, there is nothing to replace, and the box says so.
    assert not dialog.update_button.isEnabled()
    assert "source checkout" in dialog.note.text()

    dialog.reject()
    qtbot.waitUntil(lambda: w.update_dialog is None and not w.workers, timeout=5000)
    w.close()


def test_update_replaces_the_bundle_and_asks_to_restart(qtbot, tmp_path, monkeypatch, feed):
    import jiezhi.update_view as update_view

    updates, _, _ = feed
    destination = bundle(tmp_path / "opt/jiezhi", "version 0.6.0")
    monkeypatch.setattr(type(updates), "bundle", lambda self: destination)
    monkeypatch.setattr(type(updates), "blocked", lambda self: "")
    started = []
    monkeypatch.setattr(update_view, "restart", started.append)

    w = window(qtbot, tmp_path, monkeypatch, updates)
    qtbot.waitUntil(lambda: w.update_toast is not None, timeout=5000)
    press(qtbot, w.update_toast, "Yes")
    qtbot.waitUntil(lambda: w.update_release is not None, timeout=5000)
    w.open_update_dialog()
    assert w.update_dialog.update_button.isEnabled()

    w.update_dialog.begin()
    qtbot.waitUntil(lambda: w.restarting, timeout=15000)
    assert (destination / "JieZhi").read_text() == "version 0.7.0"
    assert started == [destination / "JieZhi"]
    qtbot.waitUntil(lambda: not w.workers, timeout=5000)
    w.close()


def test_no_update_says_so_only_when_it_was_asked_for(qtbot, tmp_path, monkeypatch, feed):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton

    updates, state, _ = feed
    state["releases"] = [state["release"]("v0.5.0-alpha.1", state["assets"])]
    w = window(qtbot, tmp_path, monkeypatch, updates)
    qtbot.waitUntil(lambda: w.update_toast is not None, timeout=5000)

    # Answering yes runs a silent startup check: no news, no toast.
    press(qtbot, w.update_toast, "Yes")
    qtbot.waitUntil(lambda: not w.update_checking and not w.workers, timeout=5000)
    qtbot.wait(400)
    assert w.update_toast is None
    assert "latest version" in w.statusBar().currentMessage()

    # Asking from Settings always answers. Pressed for real: the clicked signal
    # carries a bool, and binding it straight to check_updates silenced it.
    w.open_settings()
    check = next(b for b in w.findChildren(QPushButton) if b.text() == "Check for updates")
    qtbot.mouseClick(check, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: w.update_toast is not None, timeout=5000)
    assert "up to date" in w.update_toast.heading.text()
    qtbot.waitUntil(lambda: not w.workers, timeout=5000)
    w.close()
