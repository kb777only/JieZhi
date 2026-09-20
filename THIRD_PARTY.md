# Third-party components

The prototype depends on:

- Qualcomm GenieX Android 0.7.0: https://github.com/qualcomm/GenieX . The published
  Maven artifact declares BSD-3-Clause and Qualcomm Terms of Use. Bundled native
  runtimes and their notices remain subject to their respective terms.
- llama.cpp / GGML, supplied through GenieX: https://github.com/ggml-org/llama.cpp
- NanoHTTPD 2.3.1: https://github.com/NanoHttpd/nanohttpd (BSD-3-Clause).
- Kotlin, kotlinx-coroutines, kotlinx-serialization: https://github.com/JetBrains/kotlin
- PySide6 / Qt: https://www.qt.io/qt-for-python (LGPL/GPL/commercial, as applicable).
  The desktop bundle uses dynamic Qt libraries; installed package license texts
  are included with the distribution.
- openpyxl: https://openpyxl.readthedocs.io/ (MIT), with et-xmlfile.
- xlrd: https://xlrd.readthedocs.io/ (BSD), for legacy XLS.
- defusedxml: https://github.com/tiran/defusedxml (PSF), for bounded XML parsing.
- pypdf: https://github.com/py-pdf/pypdf (BSD-3-Clause).
- keyring / SecretStorage / jeepney: https://github.com/jaraco/keyring and their bundled license notices.
- Python: https://www.python.org/psf/license/
- Requests and its dependencies: https://requests.readthedocs.io/
- Android Platform Tools: https://developer.android.com/tools/releases/platform-tools
  The complete platform-tools directory includes its NOTICE.txt.
- PyInstaller: https://pyinstaller.org/ (GPL with bootloader distribution exception).

The starter model is downloaded separately and is not included in the installer.
See its model card for model terms. This file records provenance and is not a
replacement for upstream license texts. Release redistribution review remains
part of production packaging work.
