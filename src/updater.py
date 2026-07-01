"""Self-update check against the GitHub repository.

The bundled ``src/version.txt`` is compared with the same file in the repo. If
they differ, the app offers to download the repo and overwrite the installed
files. ``user_data`` (saved scores, settings, licence) is NOT part of the repo
and is left untouched.

version.txt is ``MAJOR.MINOR.PATCH``:
  * MAJOR - a full revamp of the software (e.g. v2).
  * MINOR - new features / customisation.
  * PATCH - minor bug fixes and cosmetic tweaks.
"""

import io
import os
import shutil
import zipfile
import urllib.request

from .constants import BASE_DIR

# --- configure to point at YOUR GitHub repo --------------------------------
REPO_OWNER = "PipersFriend"
REPO_NAME = "pipersfriendsoftware"
REPO_BRANCH = "main"
# ---------------------------------------------------------------------------

VERSION_PATH = os.path.join(os.path.dirname(__file__), "version.txt")
REQUEST_TIMEOUT = 8
# Files/folders under BASE_DIR that must never be overwritten by an update.
PROTECTED_TOP = {"user_data"}
# Absolute path to the user's data - NOTHING under here is ever written.
USER_DATA_DIR = os.path.join(BASE_DIR, "user_data")


def _is_protected(dest):
    """True if ``dest`` lives inside the user's data directory (belt & braces)."""
    try:
        return os.path.commonpath([os.path.abspath(dest), USER_DATA_DIR]) == USER_DATA_DIR
    except Exception:
        return False


def configured():
    return "REPLACE_WITH" not in (REPO_OWNER + REPO_NAME)


def _raw_version_url():
    return ("https://raw.githubusercontent.com/"
            f"{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}/src/version.txt")


def _zip_url():
    return ("https://codeload.github.com/"
            f"{REPO_OWNER}/{REPO_NAME}/zip/refs/heads/{REPO_BRANCH}")


def local_version():
    try:
        with open(VERSION_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "0.0.0"


def remote_version():
    try:
        req = urllib.request.Request(_raw_version_url(),
                                     headers={"User-Agent": "PipersFriend"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
            return r.read().decode("utf-8").strip()
    except Exception:
        return None


def _parse(v):
    out = []
    for p in (v or "").split(".")[:3]:
        try:
            out.append(int(p))
        except Exception:
            out.append(0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def update_available():
    """Remote version string if it differs from the local one, else None."""
    if not configured():
        return None
    rv = remote_version()
    if not rv:
        return None
    return rv if _parse(rv) != _parse(local_version()) else None


def perform_update():
    """Download the repo zip and overwrite installed files. -> (ok, message)."""
    if not configured():
        return False, "Updates are not configured."
    try:
        req = urllib.request.Request(_zip_url(), headers={"User-Agent": "PipersFriend"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
        root = (names[0].split("/")[0] + "/") if names else ""
        for name in names:
            if name.endswith("/"):
                continue
            rel = name[len(root):] if name.startswith(root) else name
            if not rel:
                continue
            if rel.split("/")[0] in PROTECTED_TOP:
                continue
            dest = os.path.join(BASE_DIR, *rel.split("/"))
            if _is_protected(dest):        # never write anything into user_data
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(name) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
        return True, "Update installed. Please restart The Piper's Friend."
    except Exception as exc:
        return False, "Update failed: %s" % exc
