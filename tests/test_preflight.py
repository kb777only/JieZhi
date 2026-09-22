"""The check that says why Qt will not open a window, before Qt aborts.

Qt 6 needs libxcb-cursor0 where Qt 5 did not, so a desktop full of working Qt 5
applications can still be missing it. Qt's own answer is a line on stderr and
abort(), which from the application menu looks like nothing happening at all.
"""
import ctypes

import pytest

from jiezhi import preflight


def test_the_platform_plugin_is_read_for_what_it_needs():
    plugin = preflight.platform_plugin("xcb")
    assert plugin is not None and plugin.is_file()
    needed = preflight.needed_libraries(plugin)
    # Read out of the file rather than kept in a list, so a dependency a future
    # Qt adds is caught the first time it appears.
    assert "libc.so.6" in needed
    assert "libxcb-cursor.so.0" in needed


def test_something_that_is_not_an_elf_file_says_nothing(tmp_path):
    plain = tmp_path / "notes.txt"
    plain.write_text("not a library")
    assert preflight.needed_libraries(plain) == []
    assert preflight.needed_libraries(tmp_path / "absent.so") == []


def test_what_pyside_carries_is_never_reported_missing(tmp_path, monkeypatch):
    # libQt6Core is beside the plugin, not in /usr/lib, so the loader finds it
    # and nobody should be sent looking for a package that does not exist.
    plugin = tmp_path / "Qt/plugins/platforms/libqxcb.so"
    plugin.parent.mkdir(parents=True)
    plugin.write_bytes(b"")
    carried = tmp_path / "Qt/lib/libQt6Core.so.6"
    carried.parent.mkdir(parents=True)
    carried.write_bytes(b"")

    monkeypatch.setattr(preflight, "needed_libraries",
                        lambda binary: ["libQt6Core.so.6", "libnothing-like-this.so.9"]
                        if binary == plugin else [])
    assert preflight.missing_libraries(plugin) == ["libnothing-like-this.so.9"]


def test_a_missing_library_is_named_with_the_package_that_carries_it(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
    monkeypatch.setattr(preflight, "missing_libraries", lambda plugin: ["libxcb-cursor.so.0"])
    trouble = preflight.report()
    assert "libxcb-cursor.so.0" in trouble
    assert "sudo apt install libxcb-cursor0" in trouble
    # It has to read as one thing to do, not as a broken installation.
    assert "Nothing else is wrong" in trouble


def test_a_library_with_no_package_name_is_reported_as_itself(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
    monkeypatch.setattr(preflight, "missing_libraries", lambda plugin: ["libsomething.so.2"])
    assert "sudo apt install libsomething.so.2" in preflight.report()


def test_nothing_missing_means_nothing_to_say(monkeypatch):
    monkeypatch.setattr(preflight, "missing_libraries", lambda plugin: [])
    assert preflight.report() is None


def test_a_machine_with_no_plugin_to_inspect_lets_qt_speak(monkeypatch):
    monkeypatch.setattr(preflight, "platform_plugin", lambda platform="xcb": None)
    assert preflight.report() is None


@pytest.mark.parametrize("environment, expected", [
    ({"QT_QPA_PLATFORM": "dxcb"}, "xcb"),          # Deepin's own name for it
    ({"QT_QPA_PLATFORM": "wayland"}, "wayland"),
    ({"QT_QPA_PLATFORM": "xcb;wayland"}, "xcb"),
    ({"WAYLAND_DISPLAY": "wayland-0"}, "wayland"),
    ({"DISPLAY": ":0"}, "xcb"),
    ({}, "xcb"),
])
def test_the_platform_this_machine_will_ask_for(environment, expected, monkeypatch):
    for name in ("QT_QPA_PLATFORM", "WAYLAND_DISPLAY", "DISPLAY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    assert preflight.wanted_platform() == expected


def test_a_library_this_machine_does_have_loads(monkeypatch):
    # Guards the check itself: if ctypes stopped finding anything, every
    # installation would be told to install libraries it already has.
    ctypes.CDLL("libc.so.6")
    assert "libc.so.6" not in preflight.missing_libraries()
