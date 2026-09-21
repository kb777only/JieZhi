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

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from jiezhi import __version__


def main():
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
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
