"""Fixture shape checks, plus the repo-wide guard against leaking the real MAC.

The author's development unit derives its default administrator password from
its own MAC address, and that MAC is also its mDNS hostname. Publishing the MAC
anywhere in this repository therefore publishes a working credential guess, so
the guard below scans *every tracked file*, not just the JSON fixtures.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The needles are assembled at runtime from fragments so that this file does
# not itself contain the strings it forbids, and therefore cannot self-trigger.
# No file is excluded from the scan.
_HEAD = "AC"
_MID = "A6"
_TAIL = "67"
FORBIDDEN = (
    f"{_MID}:{_TAIL}",  # colon-separated fragment of the real MAC
    f"{_HEAD}{_MID}{_TAIL}",  # separator-free fragment of the real MAC
)


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [REPO_ROOT / name for name in out.split("\0") if name]


def test_live_fixture_has_expected_shape(status_1_01):
    assert status_1_01["model"] == "SX-DC-8-12-120"
    outlets = status_1_01["devices"][0]["outlets"]
    assert len(outlets) == 7
    assert any(o.get("isHidden") for o in outlets)


def test_documented_fixture_has_expected_shape(status_0_5):
    assert status_0_5["model"] == "SX-DC-8-1224"
    measurements = status_0_5["devices"][0]["deviceMeasurements"]
    assert measurements["inputState"] == ["No Ground"]


def test_no_tracked_file_contains_the_real_device_mac():
    """No tracked file may contain the author's real MAC or a fragment of it."""
    tracked = _tracked_files()
    assert tracked, "git ls-files returned nothing; the scan would be vacuous"

    offenders: list[str] = []
    for path in tracked:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:  # pragma: no cover - unreadable file
            continue
        haystack = text.upper()
        for needle in FORBIDDEN:
            if needle in haystack:
                rel = path.relative_to(REPO_ROOT)
                line = next(
                    (
                        n
                        for n, raw in enumerate(text.splitlines(), 1)
                        if needle in raw.upper()
                    ),
                    0,
                )
                offenders.append(f"{rel}:{line} contains a real-MAC fragment")

    assert not offenders, "Real device MAC leaked into tracked files:\n" + "\n".join(
        offenders
    )
