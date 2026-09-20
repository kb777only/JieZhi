#!/bin/sh
# Grant the active local desktop user access to the supported Xiaomi USB device.
set -eu
test "$(id -u)" = 0 || { echo 'Run with pkexec.' >&2; exit 1; }
mkdir -p /etc/udev/rules.d
cat > /etc/udev/rules.d/70-jiezhi-android.rules <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", ATTR{idProduct}=="4e11", TAG+="uaccess"
EOF
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --action=change
