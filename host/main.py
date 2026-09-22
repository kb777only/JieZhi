import os
import sys

# Deepin injects its own Qt plugin name; the bundled Qt uses the standard XCB plugin.
if os.environ.get("QT_QPA_PLATFORM", "").split(";")[0] == "dxcb":
    os.environ["QT_QPA_PLATFORM"] = "xcb"
elif os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

if '--probe-image' in sys.argv:
    import json
    from jiezhi.desktop_surface import accessible_image_rect
    print(json.dumps(accessible_image_rect(int(sys.argv[-2]),int(sys.argv[-1]))))
    sys.exit(0)

from jiezhi import __version__


def complain(message: str) -> None:
    """Say why JieZhi did not start, somewhere it will actually be read.

    Started from the application menu there is no terminal, so a failure to
    start looks like nothing happening at all. The reason goes to the log
    every time and to the screen when the desktop offers a way to put it
    there.
    """
    print(message, file=sys.stderr)
    from datetime import datetime
    from pathlib import Path
    from jiezhi.client import DATA
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        log = Path(DATA) / "launch.log"
        log.write_text(f"JieZhi {__version__} could not start · {datetime.now():%Y-%m-%d %H:%M}\n\n{message}\n")
    except OSError:
        log = None

    import shutil
    import subprocess
    headline = message.splitlines()[0]
    body = message if log is None else f"{message}\n\nThis is also in {log}."
    for tool, command in (
        ("zenity", ["zenity", "--error", "--title=JieZhi", "--no-wrap", f"--text={body}"]),
        ("kdialog", ["kdialog", "--title", "JieZhi", "--error", body]),
        ("notify-send", ["notify-send", "--urgency=critical", "JieZhi", headline]),
    ):
        if shutil.which(tool):
            try:
                subprocess.run(command, timeout=30, check=False)
            except (OSError, subprocess.SubprocessError):
                continue
            return


def main():
    from jiezhi.preflight import report
    trouble = report()
    if trouble:
        complain(trouble)
        raise SystemExit(1)

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setApplicationName("JieZhi")
        app.setApplicationVersion(__version__)
        from jiezhi.client import asset
        app.setWindowIcon(QIcon(str(asset("jiezhi.svg"))))
        app.setOrganizationName("JieZhi")
        from jiezhi.gui import Window
        window = Window()
        window.show()
    except Exception:
        # Anything at all that stops the window appearing, rather than a
        # traceback into a terminal that is not there.
        import traceback
        complain("JieZhi could not start.\n\n" + traceback.format_exc())
        raise SystemExit(1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
