#!/usr/bin/env python3
"""The Piper's Friend - developer console.

Run this directly (``python console.py``) - it is NOT imported by main.py and is
not reachable from the app. Access is gated by a password whose hash lives in
Firestore (same Firebase project the app already uses). Once unlocked it can
publish the local working copy to the GitHub repository (force-push), which is
the source the in-app updater pulls from.

Nothing here touches user_data: the publish step ignores it.
"""

import os
import sys
import hashlib
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from src import licensing            # reuse the existing Firebase config/helpers
from src import updater              # repo owner/name/branch live here

# The password lives in Firestore: collection "password", any document, field
# "pwd" (plaintext) - matching how it was set up in the Firebase console.
_PWD_COLLECTION = "/password"
# SHA-256 of the developer password - used only as an offline fallback.
_SEED_HASH = "a95bab6cca6df38d33f296cfcb54bfe765b13b0ab2f72835934cbcccc20dd52f"

# Personal data that must never be published to the public repo.
_IGNORE = ["user_data/", "*.pyc", "__pycache__/"]


def _sha256(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _stored_password():
    """Read the console password (plaintext) from the Firestore 'password'
    collection - the ``pwd`` field of the first document. Returns None if it
    can't be read (offline / missing)."""
    try:
        _st, doc = licensing._request(_PWD_COLLECTION)
        for d in doc.get("documents", []):
            pw = d.get("fields", {}).get("pwd", {}).get("stringValue")
            if pw:
                return pw
    except Exception:
        pass
    return None


def _authenticate():
    stored = _stored_password()
    for _ in range(3):
        # input() (not getpass) so it works in every terminal - it will be
        # visible as you type.
        entered = input("Password: ").strip()
        if stored is not None:
            if entered == stored:
                return True
        elif _sha256(entered) == _SEED_HASH:      # offline fallback
            return True
        print("Incorrect.\n")
    return False


def _run(args, **kw):
    return subprocess.run(args, cwd=BASE_DIR, capture_output=True, text=True, **kw)


def publish_to_github():
    """Force-push the local working copy to the configured GitHub repo."""
    owner, repo, branch = updater.REPO_OWNER, updater.REPO_NAME, updater.REPO_BRANCH
    print("\nThis OVERWRITES https://github.com/%s/%s (branch %s) with your local"
          " files.\nuser_data is excluded." % (owner, repo, branch))
    if input('Type OVERWRITE to continue: ').strip() != "OVERWRITE":
        print("Cancelled.\n")
        return
    token = input("GitHub token (repo write access): ").strip()
    if not token:
        print("No token - cancelled.\n")
        return

    # Make sure personal data is never committed.
    gi = os.path.join(BASE_DIR, ".gitignore")
    existing = ""
    if os.path.exists(gi):
        with open(gi, "r", encoding="utf-8") as f:
            existing = f.read()
    with open(gi, "a", encoding="utf-8") as f:
        for line in _IGNORE:
            if line not in existing:
                f.write(("" if existing.endswith("\n") or not existing else "\n") + line + "\n")
                existing += line + "\n"

    remote = "https://%s@github.com/%s/%s.git" % (token, owner, repo)
    steps = [
        ["git", "init"],
        ["git", "checkout", "-B", branch],
        ["git", "rm", "-r", "--cached", "--quiet", "user_data"],   # untrack if present
        ["git", "add", "-A"],
        ["git", "-c", "user.name=PipersFriend Dev", "-c", "user.email=dev@pipersfriend.local",
         "commit", "--allow-empty", "-m", "Publish local build via dev console"],
        # credential.helper= disables Git Credential Manager so the token in the
        # URL is actually used (otherwise Windows may inject a cached login).
        ["git", "-c", "credential.helper=", "push", "-f", remote, "%s:%s" % (branch, branch)],
    ]
    for args in steps:
        res = _run(args)
        # `git rm --cached user_data` fails harmlessly when nothing is tracked yet.
        if res.returncode != 0 and args[:2] != ["git", "rm"]:
            shown = " ".join(a for a in args if not a.startswith("https://"))
            print("Step failed: %s\n%s" % (shown, (res.stderr or res.stdout).strip()))
            return
    print("Published to https://github.com/%s/%s (%s).\n" % (owner, repo, branch))


def main():
    print("=" * 52)
    print("  The Piper's Friend - Developer Console")
    print("=" * 52)
    if not _authenticate():
        print("Access denied.")
        return
    while True:
        print("\n  [1] Publish local files to GitHub (overwrite repo)")
        print("  [q] Quit")
        choice = input("> ").strip().lower()
        if choice == "1":
            publish_to_github()
        elif choice in ("q", "quit", "exit"):
            return
        else:
            print("Unknown option.")


if __name__ == "__main__":
    main()
