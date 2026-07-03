#!/usr/bin/env python3
"""Taorluath - developer console.

Run this directly (``python console.py``) - it is NOT imported by main.py and is
not reachable from the app. Access is gated by a password whose hash lives in
Firestore (same Firebase project the app already uses). Once unlocked it can
publish the local working copy to the GitHub repository (force-push), which is
the source the in-app updater pulls from.

Nothing here touches user_data: the publish step ignores it.
"""

import os
import sys
import json
import hashlib
import subprocess
import urllib.request
import urllib.error

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


def test_github_token():
    """Check whether a token can actually write to the repo, without pushing."""
    token = input("GitHub token to test: ").strip()
    if not token:
        print("No token.\n")
        return
    url = "https://api.github.com/repos/%s/%s" % (updater.REPO_OWNER, updater.REPO_NAME)
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token, "User-Agent": "PipersFriend-Console",
        "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        perms = data.get("permissions", {})
        print("Repo:        ", data.get("full_name"))
        print("Push access: ", perms.get("push", False))
        print("Admin access:", perms.get("admin", False))
        print("This token CAN publish.\n" if perms.get("push")
              else "This token CANNOT push - grant Contents: Read and write.\n")
    except urllib.error.HTTPError as e:
        msg = {401: "Bad credentials - token invalid or expired.",
               403: "Forbidden - token lacks access (or SSO not authorised).",
               404: "Repo not found, or the token can't see it."}.get(e.code,
               "GitHub API error %s %s." % (e.code, e.reason))
        print(msg + "\n")
    except Exception as e:
        print("Could not reach GitHub: %s\n" % e)


def version_status():
    """Compare the local version with the one published on GitHub."""
    local = updater.local_version()
    print("Local version: ", local)
    remote = updater.remote_version()
    if remote is None:
        print("Remote version: (couldn't fetch from GitHub)\n")
        return
    print("Remote version:", remote)
    if updater._parse(remote) == updater._parse(local):
        print("In sync.\n")
    else:
        print("Differs - the app would offer an update to users on launch.\n")


def bump_version():
    """Increment src/version.txt (major/minor/patch) for the next release."""
    cur = updater.local_version()
    major, minor, patch = updater._parse(cur)
    print("Current version: %s" % cur)
    print("  [1] Major (%d.0.0)   [2] Minor (%d.%d.0)   [3] Patch (%d.%d.%d)"
          % (major + 1, major, minor + 1, major, minor, patch + 1))
    c = input("Bump which? ").strip()
    if c == "1":
        major, minor, patch = major + 1, 0, 0
    elif c == "2":
        minor, patch = minor + 1, 0
    elif c == "3":
        patch += 1
    else:
        print("Cancelled.\n")
        return
    new = "%d.%d.%d" % (major, minor, patch)
    try:
        with open(updater.VERSION_PATH, "w", encoding="utf-8") as f:
            f.write(new)
        print("version.txt is now %s (publish to release it).\n" % new)
    except Exception as e:
        print("Could not write version.txt: %s\n" % e)


def validate_build():
    """Compile every source file to catch syntax errors before publishing."""
    import py_compile
    files = [os.path.join(BASE_DIR, "main.py"), os.path.join(BASE_DIR, "console.py")]
    src_dir = os.path.join(BASE_DIR, "src")
    if os.path.isdir(src_dir):
        files += [os.path.join(src_dir, f) for f in sorted(os.listdir(src_dir))
                  if f.endswith(".py")]
    ok = True
    for f in files:
        if not os.path.exists(f):
            continue
        rel = os.path.relpath(f, BASE_DIR)
        try:
            py_compile.compile(f, doraise=True)
            print("  OK   %s" % rel)
        except py_compile.PyCompileError as e:
            ok = False
            print("  FAIL %s\n       %s" % (rel, str(e).strip().splitlines()[-1]))
    print("Build OK.\n" if ok else "Build has errors - fix before publishing.\n")


def main():
    print("=" * 52)
    print("  Taorluath - Developer Console")
    print("=" * 52)
    if not _authenticate():
        print("Access denied.")
        return
    actions = {
        "1": publish_to_github,
        "2": test_github_token,
        "3": version_status,
        "4": bump_version,
        "5": validate_build,
    }
    while True:
        print("\n  [1] Publish local files to GitHub (overwrite repo)")
        print("  [2] Test GitHub token (check repo write access)")
        print("  [3] Show version status (local vs GitHub)")
        print("  [4] Bump version (major/minor/patch)")
        print("  [5] Validate build (compile all sources)")
        print("  [q] Quit")
        choice = input("> ").strip().lower()
        if choice in ("q", "quit", "exit"):
            return
        action = actions.get(choice)
        if action:
            action()
        else:
            print("Unknown option.")


if __name__ == "__main__":
    main()
