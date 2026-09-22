"""What a machine needs before Qt can open a window.

PySide6 carries its own Qt, but Qt's X11 plugin links against system libraries
that a working desktop does not necessarily have. Qt 6 added a dependency on
libxcb-cursor that Qt 5 never had, so a machine full of perfectly good Qt 5
applications — Deepin's own desktop among them — can still be missing it. The
plugin then fails to load and Qt calls abort() with a message on stderr, which
nobody sees when the app was started from the application menu: the window
simply never appears.

So the libraries are checked before Qt is touched, while a readable answer is
still possible.
"""
from __future__ import annotations

import ctypes
import os
import struct
from pathlib import Path

# The Debian package that carries each library, for the one line of advice at
# the end. Anything not named here is reported by its own file name, which is
# still enough to search for.
PACKAGES = {
    "libxcb-cursor.so.0": "libxcb-cursor0",
    "libxcb-icccm.so.4": "libxcb-icccm4",
    "libxcb-image.so.0": "libxcb-image0",
    "libxcb-keysyms.so.1": "libxcb-keysyms1",
    "libxcb-randr.so.0": "libxcb-randr0",
    "libxcb-render-util.so.0": "libxcb-render-util0",
    "libxcb-render.so.0": "libxcb-render0",
    "libxcb-shape.so.0": "libxcb-shape0",
    "libxcb-shm.so.0": "libxcb-shm0",
    "libxcb-sync.so.1": "libxcb-sync1",
    "libxcb-util.so.1": "libxcb-util1",
    "libxcb-xfixes.so.0": "libxcb-xfixes0",
    "libxcb-xinerama.so.0": "libxcb-xinerama0",
    "libxcb-xkb.so.1": "libxcb-xkb1",
    "libxcb.so.1": "libxcb1",
    "libxkbcommon-x11.so.0": "libxkbcommon-x11-0",
    "libxkbcommon.so.0": "libxkbcommon0",
    "libEGL.so.1": "libegl1",
    "libGL.so.1": "libgl1",
    "libfontconfig.so.1": "libfontconfig1",
    "libdbus-1.so.3": "libdbus-1-3",
}


def needed_libraries(binary: Path) -> list[str]:
    """The sonames an ELF file asks the loader for, in the order it asks.

    Read from the file rather than kept in a list here, so a new dependency in
    a future Qt is caught the first time it appears instead of the first time
    somebody remembers to add it.
    """
    try:
        data = Path(binary).read_bytes()
    except OSError:
        return []
    if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        return []  # Not a little-endian 64-bit ELF; nothing to say about it.
    phoff, = struct.unpack_from("<Q", data, 0x20)
    phentsize, phnum = struct.unpack_from("<HH", data, 0x36)

    loads, dynamic = [], None
    for index in range(phnum):
        at = phoff + index * phentsize
        kind, = struct.unpack_from("<I", data, at)
        offset, vaddr = struct.unpack_from("<QQ", data, at + 8)
        size, = struct.unpack_from("<Q", data, at + 32)
        if kind == 1:      # PT_LOAD
            loads.append((vaddr, offset, size))
        elif kind == 2:    # PT_DYNAMIC
            dynamic = (offset, size)
    if dynamic is None:
        return []

    def at_address(address: int) -> int | None:
        for vaddr, offset, size in loads:
            if vaddr <= address < vaddr + size:
                return offset + address - vaddr
        return None

    offset, size = dynamic
    wanted, strtab = [], None
    for at in range(offset, offset + size, 16):
        tag, value = struct.unpack_from("<qQ", data, at)
        if tag == 0:       # DT_NULL
            break
        if tag == 1:       # DT_NEEDED, an offset into the string table
            wanted.append(value)
        elif tag == 5:     # DT_STRTAB, an address
            strtab = at_address(value)
    if strtab is None:
        return []
    return [data[strtab + start:data.index(b"\0", strtab + start)].decode() for start in wanted]


def platform_plugin(platform: str = "xcb") -> Path | None:
    """Where PySide6 keeps the Qt plugin for a windowing system."""
    try:
        import PySide6
    except ImportError:
        return None
    plugin = Path(PySide6.__file__).parent / "Qt/plugins/platforms" / f"libq{platform}.so"
    return plugin if plugin.is_file() else None


def bundled_directories(plugin: Path) -> list[Path]:
    """Where the loader finds the Qt that PySide6 ships, beside the plugin."""
    return [plugin.parent, plugin.parent.parent.parent / "lib"]


def missing_libraries(plugin: Path | None = None) -> list[str]:
    """The libraries the platform plugin needs that this machine cannot load.

    Walks into the Qt that PySide6 ships rather than stopping at the plugin,
    because the plugin asks for libQt6Gui and it is libQt6Gui that asks for
    libEGL. A library PySide6 carries is never reported: it is right there, and
    telling somebody to install it would send them looking for a package that
    does not exist.
    """
    plugin = plugin if plugin is not None else platform_plugin()
    if plugin is None:
        return []
    bundled = bundled_directories(plugin)
    missing: list[str] = []
    seen: set[str] = set()
    queue = [plugin]
    while queue:
        for soname in needed_libraries(queue.pop()):
            if soname in seen:
                continue
            seen.add(soname)
            carried = next((where / soname for where in bundled if (where / soname).is_file()), None)
            if carried is not None:
                queue.append(carried)
                continue
            try:
                ctypes.CDLL(soname)
            except OSError:
                missing.append(soname)
    return missing


def wanted_platform() -> str:
    """The windowing system this machine will actually ask Qt for."""
    platform = os.environ.get("QT_QPA_PLATFORM", "").split(";")[0]
    if platform and platform != "dxcb":  # Deepin's own name for xcb
        return platform
    if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
        return "wayland"
    return "xcb"


def report() -> str | None:
    """Why Qt will not start here, or None when it will.

    Returns something a person can act on without knowing what a platform
    plugin is.
    """
    platform = wanted_platform()
    plugin = platform_plugin(platform)
    if plugin is None:
        return None  # No plugin to inspect; let Qt speak for itself.
    missing = missing_libraries(plugin)
    if not missing:
        return None
    packages = sorted({PACKAGES.get(soname, soname) for soname in missing})
    lines = [
        "JieZhi cannot open a window on this machine yet.",
        "",
        f"Qt's {platform} support needs these libraries, and they are not installed:",
        *(f"    {soname}" for soname in missing),
        "",
        "Install them and try again:",
        "",
        f"    sudo apt install {' '.join(packages)}",
        "",
        "Nothing else is wrong with the installation.",
    ]
    return "\n".join(lines)
