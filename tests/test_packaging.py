"""The packaging files must agree with each other and with the code."""

import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import marker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ID = marker.__app_id__


def read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_flatpak_vendor_sources_match_the_pinned_files():
    """flatpak/vendor-sources.json is generated; it must not drift from
    scripts/vendor-files.txt and scripts/vendor.sha256."""
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "flatpak-sources.py"), "--check"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_every_vendor_file_has_a_checksum():
    listed = [line.split("|")[0] for line in read("scripts", "vendor-files.txt").splitlines()
              if line.strip() and not line.startswith("#")]
    summed = [line.split()[1] for line in read("scripts", "vendor.sha256").splitlines() if line.strip()]
    assert sorted(listed) == sorted(summed)
    assert len(listed) == len(set(listed))


def test_app_id_is_the_same_everywhere():
    for name in (f"{APP_ID}.desktop", f"{APP_ID}.svg", f"{APP_ID}.metainfo.xml"):
        assert os.path.exists(os.path.join(ROOT, "data", name)), name
    assert f"app-id: {APP_ID}\n" in read("flatpak", f"{APP_ID}.yml")
    assert f'APP_ID="{APP_ID}"' in read("scripts", "install-desktop.sh")
    desktop = read("data", f"{APP_ID}.desktop")
    assert f"Icon={APP_ID}\n" in desktop and f"StartupWMClass={APP_ID}\n" in desktop

    metainfo = ET.fromstring(read("data", f"{APP_ID}.metainfo.xml"))
    assert metainfo.findtext("id") == APP_ID
    assert metainfo.findtext("launchable") == f"{APP_ID}.desktop"


def test_metainfo_lists_the_current_version():
    metainfo = ET.fromstring(read("data", f"{APP_ID}.metainfo.xml"))
    versions = [release.get("version") for release in metainfo.iter("release")]
    assert versions[0] == marker.__version__


def test_license_file_is_shipped():
    assert "GNU GENERAL PUBLIC LICENSE" in read("COPYING")[:200]
    assert re.search(r'license-files\s*=\s*\["COPYING"\]', read("pyproject.toml"))
