#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
version=$(PYTHONPATH=host .venv/bin/python -c 'from jiezhi import __version__; print(__version__)')
mkdir -p assets
cp android/app/build/outputs/apk/debug/app-debug.apk assets/jiezhi-client.apk
cp scripts/setup-usb.sh assets/setup-usb.sh
mkdir -p assets/platform-tools assets/licenses
cp --remove-destination -R .tools/platform-tools/. assets/platform-tools/
cp THIRD_PARTY.md assets/licenses/
.venv/bin/python - <<'PY'
from importlib.metadata import distributions
from pathlib import Path
import shutil
for dist in distributions():
    for entry in dist.files or []:
        if any(s in str(entry).lower() for s in ('license', 'copying', 'notice')) and '.dist-info/' in str(entry):
            source = Path(dist.locate_file(entry))
            if source.is_file():
                target = Path('assets/licenses') / dist.metadata['Name'] / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
PY
.venv/bin/pyinstaller --noconfirm --clean --name JieZhi --onedir --windowed \
  --hidden-import keyring.backends.SecretService --collect-all pypdf --hidden-import openpyxl --hidden-import xlrd --hidden-import defusedxml.ElementTree \
  --paths host --add-data 'assets:assets' host/main.py
cat > dist/JieZhi/Install-JieZhi.sh <<'EOF'
#!/bin/sh
cd "$(dirname "$0")"
exec ./JieZhi --install
EOF
chmod +x dist/JieZhi/Install-JieZhi.sh
tar -czf "dist/JieZhi-${version}-linux-x86_64.tar.gz" -C dist JieZhi
cat > "dist/JieZhi-${version}-Installer.run" <<'EOF'
#!/bin/sh
set -eu
temporary_dir=$(mktemp -d "${TMPDIR:-/tmp}/jiezhi-installer.XXXXXX")
trap 'rm -rf "$temporary_dir"' EXIT HUP INT TERM
archive_line=$(awk '/^__JIEZHI_ARCHIVE__$/ {print NR + 1; exit}' "$0")
tail -n +"$archive_line" "$0" | tar -xz -C "$temporary_dir"
"$temporary_dir/JieZhi/JieZhi" --install
exit 0
__JIEZHI_ARCHIVE__
EOF
cat "dist/JieZhi-${version}-linux-x86_64.tar.gz" >> "dist/JieZhi-${version}-Installer.run"
chmod +x "dist/JieZhi-${version}-Installer.run"
cp android/app/build/outputs/apk/debug/app-debug.apk "dist/JieZhi-${version}-android-arm64.apk"
(
  cd dist
  sha256sum \
    "JieZhi-${version}-Installer.run" \
    "JieZhi-${version}-linux-x86_64.tar.gz" \
    "JieZhi-${version}-android-arm64.apk" > SHA256SUMS
)
