# Third-party components

The prototype depends on:

- Nightmare Mobile v1.5.533 / LocalDream NPU media backend (CC BY-NC 4.0):
  https://github.com/AbrahamPaulJ/nightmare-mobile and
  https://github.com/xororz/local-dream . Selected Kotlin video pipeline files are
  adapted with attribution in `third_party/nightmare-mobile`. Native components
  are staged from a checksum-pinned upstream release. This NPU component is
  **non-commercial licensed**, separately from JieZhi's MIT code. Qualcomm QNN
  runtime and model terms remain separate; the prototype build includes this
  component for evaluation. See the original LICENSE/NOTICE in that directory.

- stable-diffusion.cpp (MIT), pinned to `c678dfe704a2230342376b46add9c8ca736a653d`:
  https://github.com/leejet/stable-diffusion.cpp . The Android CPU executable also
  includes its pinned GGML, oniguruma, utf8proc and darts-clone dependencies.
  Their license texts are included in the APK and desktop distribution. Embedded
  header notices cover stb, miniz, json and zip; WebP/WebM are disabled in this build.

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
