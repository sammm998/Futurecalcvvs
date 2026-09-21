"""The image must carry the system libraries the installed packages ask the loader for.

This was got wrong once by reasoning instead of looking: the OCR cross-check failed in the container, I said
onnxruntime needed libgomp, and it does not. What fails is OpenCV, which the recogniser imports and which links
against libGL and glib - neither of them in a slim Python image.

The image cannot be built here (the registry is blocked by the egress policy), so the claim is checked the only
way it can be: read what the Dockerfile installs, read what the packages actually need, and let the two disagree
out loud rather than in a deployment.
"""
import glob
import os
import re
import subprocess

import pytest
import sys

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Debian loader dependencies require a Linux host")

# Everything a bare debian-slim already carries. Anything else has to be installed by name.
IN_BASE = ("libc.so", "libm.so", "libdl.so", "libpthread.so", "librt.so", "libstdc++.so", "libgcc_s.so",
           "ld-linux", "libutil.so", "libresolv.so", "libcrypt.so", "libnsl.so", "libz.so")

# Which apt package provides a library, for the ones that are not vendored inside a wheel.
PROVIDED_BY = {
    "libGL.so.1": "libgl1", "libGLX.so.0": "libgl1", "libGLdispatch.so.0": "libgl1",
    "libglib-2.0.so.0": "libglib2.0-0", "libgthread-2.0.so.0": "libglib2.0-0",
    "libgomp.so.1": "libgomp1",
}


def _needed_by(module: str) -> set[str]:
    """Libraries the loader will look for outside the wheel, for every shared object this package ships."""
    try:
        m = __import__(module)
    except Exception:
        pytest.skip(f"{module} är inte installerat här")
    out: set[str] = set()
    for so in glob.glob(os.path.join(os.path.dirname(m.__file__), "**", "*.so*"), recursive=True):
        if "qxcb" in so or "/qt/" in so:
            continue        # the Qt GUI plug-ins are never loaded by a server
        r = subprocess.run(["ldd", so], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            if "=>" not in line:
                continue
            lib = line.split("=>")[0].strip()
            if not lib.startswith("lib") or any(lib.startswith(b) for b in IN_BASE):
                continue
            # a wheel that ships its own copy stamps a hash into the name: libpng16-529cb57a.so.16. A version
            # in the name is not that - libglib-2.0.so.0 is the system's own, and reading the hyphen alone as a
            # hash hid the very library this test exists to catch.
            if re.search(r"-[0-9a-f]{8,}", lib):
                continue
            out.add(lib)
    return out


def _dockerfile_installs() -> set[str]:
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    text = open(os.path.join(root, "Dockerfile"), encoding="utf-8").read()
    pkgs: set[str] = set()
    for line in text.splitlines():
        if "apt-get install" not in line:
            continue
        for tok in line.replace("\\", " ").split():
            if tok.startswith("lib") or tok in ("ca-certificates", "curl"):
                pkgs.add(tok)
    return pkgs


def test_the_image_installs_what_the_ocr_chain_asks_the_loader_for():
    need = _needed_by("cv2") | _needed_by("onnxruntime")
    installed = _dockerfile_installs()
    missing = sorted(lib for lib in need
                     if lib in PROVIDED_BY and PROVIDED_BY[lib] not in installed)
    assert not missing, (
        "Dockerfile installerar inte allt OCR-kedjan behöver: "
        + ", ".join(f"{lib} (paket {PROVIDED_BY[lib]})" for lib in missing))


def test_no_package_is_installed_on_a_guess():
    """A package in the image that nothing asks for is a claim nobody checked - which is how this went wrong."""
    need = _needed_by("cv2") | _needed_by("onnxruntime") | _needed_by("PIL")
    wanted = {PROVIDED_BY[lib] for lib in need if lib in PROVIDED_BY}
    for pkg in _dockerfile_installs():
        if pkg in ("ca-certificates", "curl"):
            continue
        assert pkg in wanted, f"{pkg} installeras men ingen installerad modul frågar efter något ur det"
