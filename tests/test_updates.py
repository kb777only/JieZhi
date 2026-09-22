import hashlib
import json
import subprocess
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import pytest

from jiezhi import __version__
from jiezhi.updates import (Updates, desktop_exec, fetch_client, notes_for,
                            write_desktop_entry)

REPO = "kb777only/JieZhi"


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


def commit(root, message, **files):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(root, "add", "-A")
    git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=Test", "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def version_file(version):
    return f'"""JieZhi."""\n\n__version__ = "{version}"\n'


@pytest.fixture
def installation(tmp_path):
    """A real checkout of a real origin, with a stand-in for the GitHub API."""
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    commit(origin, "The first commit", **{
        ".gitignore": ".venv\n",
        "host/jiezhi/__init__.py": version_file(__version__),
        "README.md": "one\n",
    })

    root = tmp_path / "install"
    git(tmp_path, "clone", "-q", str(origin), str(root))
    launcher = root / ".venv/bin/jiezhi"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n")
    launcher.chmod(0o755)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlparse(self.path)
            path = url.path
            status, body = 200, b""
            if path == f"/repos/{REPO}/commits/main":
                head = git(origin, "rev-parse", "main")
                body = json.dumps({"sha": head, "commit": {"author": {"date": "2026-09-21T10:00:00Z"}}}).encode()
            elif path.startswith(f"/repos/{REPO}/compare/"):
                base, _, head = path.rsplit("/", 1)[1].partition("...")
                log = git(origin, "log", "--format=%H%x00%B%x01", f"{base}..{head}")
                commits = []
                for entry in [e for e in log.split("\x01") if e.strip()]:
                    sha, _, message = entry.strip().partition("\x00")
                    commits.append({"sha": sha, "commit": {"message": message.strip()}})
                commits.reverse()  # the API hands them back oldest first
                body = json.dumps({"status": "ahead" if commits else "identical",
                                   "ahead_by": len(commits), "commits": commits}).encode()
            elif path == f"/repos/{REPO}/contents/host/jiezhi/__init__.py":
                ref = parse_qs(url.query).get("ref", ["main"])[0]
                body = git(origin, "show", f"{ref}:host/jiezhi/__init__.py").encode()
            else:
                status = 404
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
    updates = Updates(version=__version__, api=f"http://127.0.0.1:{server.server_port}",
                      root=root, desktop_file=tmp_path / "apps/jiezhi.desktop")
    yield updates, origin, root
    server.shutdown()
    server.server_close()
    thread.join()


def test_a_checkout_level_with_main_has_no_update(installation):
    updates, _, _ = installation
    assert updates.check() is None
    assert updates.blocked() == ""


def test_new_commits_become_the_patch_notes(installation):
    updates, origin, _ = installation
    commit(origin, "Teach the chip to move\n\nBefore: it snapped.\nAfter: it slides.", **{"README.md": "two\n"})
    head = commit(origin, "Release JieZhi v99.0.0-alpha.1", **{
        "host/jiezhi/__init__.py": version_file("99.0.0-alpha.1")})

    update = updates.check()
    assert update["head"] == head
    assert update["count"] == 2
    assert update["version"] == "99.0.0-alpha.1"
    # Newest first, with the body kept: these are what the box shows.
    assert update["notes"].index("Release JieZhi") < update["notes"].index("Teach the chip")
    assert "After: it slides." in update["notes"]


def test_update_fast_forwards_the_checkout(installation):
    updates, origin, root = installation
    head = commit(origin, "Teach the chip to move", **{"README.md": "two\n"})

    seen = []
    assert updates.install(updates.check(), lambda percent, message: seen.append(message)) == root

    assert git(root, "rev-parse", "HEAD") == head
    assert (root / "README.md").read_text() == "two\n"
    assert seen[-1].startswith("Updated")
    # The menu entry is rewritten to point at this checkout's launcher.
    assert str(root / "scripts/launch.sh") in (updates.desktop_file).read_text()
    assert updates.check() is None


def test_a_dirty_checkout_is_refused_not_reset(installation):
    updates, origin, root = installation
    commit(origin, "Teach the chip to move", **{"README.md": "two\n"})
    update = updates.check()
    (root / "README.md").write_text("my own work\n")

    assert "uncommitted changes" in updates.blocked()
    with pytest.raises(RuntimeError, match="uncommitted changes"):
        updates.install(update)
    assert (root / "README.md").read_text() == "my own work\n"


def test_a_checkout_on_another_branch_is_left_alone(installation):
    updates, origin, root = installation
    commit(origin, "Teach the chip to move", **{"README.md": "two\n"})
    git(root, "checkout", "-q", "-b", "my-feature")

    assert "not main" in updates.blocked()
    with pytest.raises(RuntimeError, match="my-feature"):
        updates.install(updates.check())
    assert git(root, "rev-parse", "--abbrev-ref", "HEAD") == "my-feature"


def test_a_failed_update_puts_the_old_commit_back(installation, monkeypatch):
    updates, origin, root = installation
    before = git(root, "rev-parse", "HEAD")
    commit(origin, "Teach the chip to move", **{"README.md": "two\n"})
    update = updates.check()

    def explode():
        raise RuntimeError("pip said no")
    monkeypatch.setattr(type(updates), "touches_dependencies", lambda self, a, b: True)
    monkeypatch.setattr(type(updates), "rebuild", lambda self: explode())

    with pytest.raises(RuntimeError, match="pip said no"):
        updates.install(update)
    assert git(root, "rev-parse", "HEAD") == before
    assert (root / "README.md").read_text() == "one\n"


def test_dependencies_are_only_rebuilt_when_they_changed(installation):
    updates, origin, root = installation
    before = git(root, "rev-parse", "HEAD")
    plain = commit(origin, "Only prose", **{"README.md": "two\n"})
    touched = commit(origin, "Add a dependency", **{"pyproject.toml": "[project]\nname='jiezhi'\n"})
    git(root, "fetch", "-q", "origin", "main")

    assert updates.touches_dependencies(before, plain) is False
    assert updates.touches_dependencies(before, touched) is True
    # A revision this checkout has not fetched cannot be read, and an
    # unnecessary reinstall beats an update that leaves a dependency behind.
    assert updates.touches_dependencies(before, "f" * 40) is True


def test_a_checkout_that_is_not_one_cannot_update(tmp_path):
    updates = Updates(root=tmp_path / "somewhere-else")
    assert "not a git checkout" in updates.blocked()
    assert updates.check() is None


def test_notes_are_capped_so_the_box_stays_a_summary():
    commits = [{"sha": f"{n:040x}", "commit": {"message": f"Change {n}"}} for n in range(60)]
    notes = notes_for(commits)
    assert "Change 0\n" in notes + "\n"
    assert "…and 20 more." in notes


def test_desktop_entry_points_at_the_checkout(tmp_path):
    entry = write_desktop_entry(tmp_path / "opt/jiezhi", tmp_path / "apps/jiezhi.desktop")
    text = entry.read_text()
    # Through the wrapper, so a launch that dies leaves something to read.
    assert f"Exec={tmp_path}/opt/jiezhi/scripts/launch.sh" in text
    assert f"Icon={tmp_path}/opt/jiezhi/assets/jiezhi.svg" in text


def test_an_ordinary_path_is_not_quoted(tmp_path):
    # The whole Exec value used to be wrapped in quotes. A launcher that does
    # not unquote it looks for a program whose name starts with a quotation
    # mark, and clicking JieZhi in the menu does nothing at all.
    assert desktop_exec(Path("/home/user/.local/opt/jiezhi/scripts/launch.sh")) == \
        "/home/user/.local/opt/jiezhi/scripts/launch.sh"


def test_a_path_that_needs_quoting_gets_it(tmp_path):
    assert desktop_exec(Path("/home/a user/jiezhi/scripts/launch.sh")) == \
        '"/home/a user/jiezhi/scripts/launch.sh"'
    # Backslash, quote, backtick and dollar survive being unescaped twice: once
    # by the desktop file parser and once by the launcher.
    assert desktop_exec(Path('/home/$HOME "x"/launch.sh')) == \
        '"/home/\\\\$HOME \\\\"x\\\\"/launch.sh"'


@pytest.fixture
def prebuilt(tmp_path):
    """The branch CI publishes the phone client to, and its manifest."""
    payload = b"PK\x03\x04" + b"apk" * 5000
    state = {"apk": payload, "manifest": None, "pieces": {}}

    def publish():
        """Split the APK the way scripts/publish-client.sh does."""
        apk = state["apk"]
        step = 4096
        cuts = [apk[at:at + step] for at in range(0, len(apk), step)]
        state["pieces"] = {f"jiezhi-client.apk.{n:03d}": cut for n, cut in enumerate(cuts)}
        state["manifest"] = json.dumps({
            "version": "0.8.0-alpha.1", "commit": "a" * 40, "name": "jiezhi-client.apk",
            "sha256": hashlib.sha256(apk).hexdigest(), "size": len(apk),
            "parts": [{"name": name, "sha256": hashlib.sha256(cut).hexdigest(), "size": len(cut)}
                      for name, cut in state["pieces"].items()],
        }).encode()

    publish()
    state["publish"] = publish

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path.endswith("manifest.json"):
                body = state["manifest"]
            else:
                body = state["pieces"].get(self.path.lstrip("/"))
            status = 404 if body is None else 200
            body = body or b""
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
    yield f"http://127.0.0.1:{server.server_port}", state
    server.shutdown()
    server.server_close()
    thread.join()


def test_phone_client_is_joined_from_its_pieces_and_verified(prebuilt, tmp_path):
    base, state = prebuilt
    # The APK is past the 100 MB a repository holds in one file, so it arrives
    # in pieces and has to come back out as the file that was published.
    assert len(state["pieces"]) > 1
    apk = fetch_client(base=base, cache=tmp_path / "cache")
    assert apk.read_bytes() == state["apk"]
    # A second call is served from the cache rather than downloaded again.
    assert fetch_client(base=base, cache=tmp_path / "cache") == apk


def test_a_bad_piece_is_named_and_the_client_discarded(prebuilt, tmp_path):
    base, state = prebuilt
    spoiled = sorted(state["pieces"])[1]
    state["pieces"][spoiled] = b"\x00" + state["pieces"][spoiled][1:]
    with pytest.raises(RuntimeError, match=f"{spoiled} failed its checksum"):
        fetch_client(base=base, cache=tmp_path / "cache")
    assert not list((tmp_path / "cache").glob("*"))


def test_a_client_that_does_not_match_its_manifest_is_discarded(prebuilt, tmp_path):
    base, state = prebuilt
    # Every piece is intact but the whole is not what was published.
    state["manifest"] = state["manifest"].replace(
        hashlib.sha256(state["apk"]).hexdigest().encode(), b"f" * 64, 1)
    with pytest.raises(RuntimeError, match="The phone client failed its checksum"):
        fetch_client(base=base, cache=tmp_path / "cache")
    assert not list((tmp_path / "cache").glob("*.partial"))


def test_a_manifest_without_pieces_is_one_piece(prebuilt, tmp_path):
    base, state = prebuilt
    state["pieces"] = {"jiezhi-client.apk": state["apk"]}
    state["manifest"] = json.dumps({
        "name": "jiezhi-client.apk", "sha256": hashlib.sha256(state["apk"]).hexdigest(),
        "size": len(state["apk"]),
    }).encode()
    assert fetch_client(base=base, cache=tmp_path / "cache").read_bytes() == state["apk"]


def test_no_published_client_says_how_to_build_one(prebuilt, tmp_path):
    base, state = prebuilt
    state["manifest"] = None
    with pytest.raises(RuntimeError, match="build-android"):
        fetch_client(base=base, cache=tmp_path / "cache")


def window(qtbot, tmp_path, monkeypatch, updates):
    """The real window, with the network and the phone scan taken out."""
    import jiezhi.gui as gui
    import jiezhi.hub as hub
    import jiezhi.update_view as update_view
    from jiezhi.gui import Window

    monkeypatch.setattr(gui, "DATA", tmp_path / "data")
    monkeypatch.setattr(hub, "DATA", tmp_path / "data")
    monkeypatch.setattr(Window, "start_scan", lambda self: None)
    monkeypatch.setattr(hub.Hub, "restore", lambda self: {})
    monkeypatch.setattr(update_view, "Updates", lambda: updates)
    monkeypatch.setattr(update_view, "CONSENT_DELAY", 0)
    monkeypatch.setattr(update_view, "STARTUP_CHECK_DELAY", 0)
    w = Window(); qtbot.addWidget(w); w.show(); qtbot.wait(150)
    return w


def press(qtbot, toast, text):
    from PySide6.QtCore import Qt
    qtbot.mouseClick(next(b for b in toast.buttons if b.text() == text), Qt.MouseButton.LeftButton)


def test_first_launch_asks_before_it_checks_anything(qtbot, tmp_path, monkeypatch, installation):
    updates, _, _ = installation
    w = window(qtbot, tmp_path, monkeypatch, updates)

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


def test_saying_yes_offers_the_new_commits_and_takes_them(qtbot, tmp_path, monkeypatch, installation):
    from PySide6.QtWidgets import QTextBrowser
    import jiezhi.update_view as update_view

    updates, origin, root = installation
    head = commit(origin, "Teach the chip to move\n\nBefore: it snapped.\nAfter: it slides.",
                  **{"README.md": "two\n"})
    started = []
    monkeypatch.setattr(update_view, "restart", started.append)

    w = window(qtbot, tmp_path, monkeypatch, updates)
    qtbot.waitUntil(lambda: w.update_toast is not None, timeout=5000)
    press(qtbot, w.update_toast, "Yes")
    assert w.preferences["auto_update_check"] is True

    qtbot.waitUntil(lambda: w.update_toast is not None and "1 new change" in w.update_toast.heading.text(), timeout=5000)
    w.update_toast.clicked.emit()
    qtbot.waitUntil(lambda: w.update_dialog is not None, timeout=5000)
    assert "After: it slides." in w.update_dialog.findChild(QTextBrowser).toPlainText()
    assert w.update_dialog.update_button.isEnabled()

    w.update_dialog.begin()
    qtbot.waitUntil(lambda: w.restarting, timeout=20000)
    assert git(root, "rev-parse", "HEAD") == head
    # Restarted through the wrapper, so an update that breaks the app leaves
    # a reason behind instead of just not coming back.
    assert started == [root / "scripts/launch.sh"]
    qtbot.waitUntil(lambda: not w.workers, timeout=5000)
    w.close()


def test_a_dirty_checkout_is_told_why_it_cannot_update(qtbot, tmp_path, monkeypatch, installation):
    updates, origin, root = installation
    commit(origin, "Teach the chip to move", **{"README.md": "two\n"})
    (root / "README.md").write_text("my own work\n")

    w = window(qtbot, tmp_path, monkeypatch, updates)
    qtbot.waitUntil(lambda: w.update_toast is not None, timeout=5000)
    press(qtbot, w.update_toast, "Yes")
    qtbot.waitUntil(lambda: w.update_available is not None, timeout=5000)
    w.open_update_dialog()

    assert not w.update_dialog.update_button.isEnabled()
    assert "uncommitted changes" in w.update_dialog.note.text()
    w.update_dialog.reject()
    qtbot.waitUntil(lambda: w.update_dialog is None and not w.workers, timeout=5000)
    assert (root / "README.md").read_text() == "my own work\n"
    w.close()


def test_no_new_commits_says_so_only_when_it_was_asked_for(qtbot, tmp_path, monkeypatch, installation):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton

    updates, _, _ = installation
    w = window(qtbot, tmp_path, monkeypatch, updates)
    qtbot.waitUntil(lambda: w.update_toast is not None, timeout=5000)

    press(qtbot, w.update_toast, "Yes")
    qtbot.waitUntil(lambda: not w.update_checking and not w.workers, timeout=5000)
    qtbot.wait(400)
    assert w.update_toast is None
    assert "up to date" in w.statusBar().currentMessage()

    # Asking from Settings always answers. Pressed for real: the clicked signal
    # carries a bool, and binding it straight to check_updates silenced it.
    w.open_settings()
    check = next(b for b in w.findChildren(QPushButton) if b.text() == "Check for updates")
    qtbot.mouseClick(check, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: w.update_toast is not None, timeout=5000)
    assert "up to date" in w.update_toast.heading.text()
    qtbot.waitUntil(lambda: not w.workers, timeout=5000)
    w.close()
