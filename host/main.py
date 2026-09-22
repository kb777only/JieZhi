import os
import sys


def settle_platform() -> None:
    """Ask Qt for a windowing system the Qt we actually have can provide.

    A desktop sets QT_QPA_PLATFORM for the applications it starts, naming the
    plugin its own Qt build has: Deepin says dxcb, and there are others. PySide6
    brings its own Qt, which ships none of them, and Qt answers a name it does
    not have by aborting before anything reaches the screen. A terminal sets
    nothing, which is why the same command works there and clicking the menu
    entry appears to do nothing at all.
    """
    from jiezhi.preflight import platform_plugin
    asked = [name for name in os.environ.get("QT_QPA_PLATFORM", "").split(";") if name]
    usable = [name for name in asked if platform_plugin(name) is not None]
    if usable:
        os.environ["QT_QPA_PLATFORM"] = ";".join(usable)
        return
    wayland = os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY")
    os.environ["QT_QPA_PLATFORM"] = "wayland" if wayland else "xcb"


settle_platform()

if '--probe-image' in sys.argv:
    import json
    from jiezhi.desktop_surface import accessible_image_rect
    print(json.dumps(accessible_image_rect(int(sys.argv[-2]),int(sys.argv[-1]))))
    sys.exit(0)

from jiezhi import __version__


def complain(message: str) -> None:
    """Say why JieZhi did not start, somewhere it will actually be read.

    scripts/launch.sh keeps everything this process prints and puts it on
    screen itself, so under it this only has to speak. Run straight from a
    menu entry someone wrote by hand, there is nothing else, so put it up.
    """
    print(message, file=sys.stderr)
    if os.environ.get("JIEZHI_LAUNCHED_BY"):
        return

    import shutil
    import subprocess
    headline = message.splitlines()[0]
    for tool, command in (
        ("zenity", ["zenity", "--error", "--title=JieZhi", "--no-wrap", f"--text={message}"]),
        ("kdialog", ["kdialog", "--title", "JieZhi", "--error", message]),
        ("notify-send", ["notify-send", "--urgency=critical", "JieZhi", headline]),
    ):
        if shutil.which(tool):
            try:
                subprocess.run(command, timeout=30, check=False)
            except (OSError, subprocess.SubprocessError):
                continue
            return


def build(argv):
    """Everything a launch does, up to the window being on screen."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    app = QApplication(argv)
    app.setStyle("Fusion")
    app.setApplicationName("JieZhi")
    app.setApplicationVersion(__version__)
    from jiezhi.client import asset
    app.setWindowIcon(QIcon(str(asset("jiezhi.svg"))))
    app.setOrganizationName("JieZhi")
    from jiezhi.gui import Window
    window = Window()
    window.show()
    return app, window


def self_test() -> int:
    """Open the window and close it again, so an install can prove it works.

    Everything that has gone wrong here so far only went wrong on the machine
    it was installed on. This is the installer's way of finding that out while
    somebody is still watching the terminal.
    """
    from jiezhi.preflight import report
    trouble = report()
    if trouble:
        print(trouble, file=sys.stderr)
        return 1
    try:
        app, window = build(sys.argv[:1])
        app.processEvents()
        showing = window.isVisible()
        window.close()
        app.processEvents()
    except Exception:
        import traceback
        print("JieZhi could not start.\n\n" + traceback.format_exc(), file=sys.stderr)
        return 1
    if not showing:
        print("JieZhi started but never put a window on screen.", file=sys.stderr)
        return 1
    print(f"JieZhi {__version__} opened a window on {os.environ['QT_QPA_PLATFORM']} and closed it again.")
    return 0


def main():
    from jiezhi.preflight import report
    trouble = report()
    if trouble:
        complain(trouble)
        raise SystemExit(1)

    if "--self-test" in sys.argv:
        sys.stdout.flush()
        sys.stderr.flush()
        # Window() leaves a scan thread running, and this process has nothing
        # left to do but report its verdict.
        os._exit(self_test())

    try:
        app, _window = build(sys.argv)
    except Exception:
        # Anything at all that stops the window appearing, rather than a
        # traceback into a terminal that is not there.
        import traceback
        complain("JieZhi could not start.\n\n" + traceback.format_exc())
        raise SystemExit(1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
