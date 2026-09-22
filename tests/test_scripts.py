"""Nothing imports the shell scripts, so nothing else would notice a syntax
error in them until somebody ran the one-liner and it failed halfway."""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted((ROOT / "scripts").glob("*.sh"))

# What a Debian /bin/sh is: dash, not bash. The one-liner is piped into `sh`.
BASHISMS = (
    (re.compile(r"\[\["), "[[ ... ]] is a bash test"),
    (re.compile(r"^\s*function\s+\w+", re.M), "function keyword"),
    (re.compile(r"^\s*local\s+", re.M), "local"),
    (re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\[[^]]"), "array subscript"),
    (re.compile(r"&>"), "&> redirection"),
)


def test_there_are_scripts_to_check():
    assert {script.name for script in SCRIPTS} >= {"install.sh", "launch.sh"}


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda script: script.name)
def test_the_script_parses_as_posix_sh(script):
    subprocess.run(["sh", "-n", str(script)], check=True)


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda script: script.name)
def test_the_script_keeps_to_posix_sh(script):
    text = script.read_text()
    found = [reason for pattern, reason in BASHISMS if pattern.search(text)]
    assert not found, f"{script.name} uses {', '.join(found)}"


@pytest.mark.parametrize("name", ["install.sh", "launch.sh"], ids=str)
def test_the_script_is_executable(name):
    # launch.sh is what the menu entry runs and install.sh is fetched with
    # curl; a mode that lost its executable bit breaks both silently.
    assert (ROOT / "scripts" / name).stat().st_mode & 0o111
