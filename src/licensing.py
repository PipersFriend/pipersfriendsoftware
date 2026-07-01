"""Firestore-backed activation / licensing for The Piper's Friend.

Activation flow (web-style Firestore REST, stdlib only):
  1. GET   licenses/<key>                 -> 404 = invalid key
  2. if    fields.activated == true       -> already used
  3. PATCH activated=true + expiration    -> consume the key, store a local token

The local token alone is NOT trusted: on every launch the license is
re-validated against Firestore and every field must match the database exactly
(activated, tier, expiration-date). This stops users hand-editing license.json
to grant or extend themselves a licence. When the database is unreachable
(offline) the app falls back to the locally-recorded expiry as a grace period.

The licence duration is set by the `tier` at activation time:
  * "Personal 6-month"   -> 6 months
  * "Personal 12-month"  -> 12 months
  * "Personal Lifetime"  -> never expires
"""

import os
import re
import json
import calendar
from datetime import date, datetime
import urllib.request
import urllib.error

from .constants import SETTINGS_DIR

# ---------------------------------------------------------------------------
# Configure these for YOUR Firebase project before distributing the app.
# ---------------------------------------------------------------------------
PROJECT_ID = "database-pipersfriend"     # <-- set to your Firestore project id
FIREBASE_API_KEY = "AIzaSyA4WbnNDONAVFuAg2uJOsYVDPxztPMjUwA"   # Web API key (?key=...)
# ---------------------------------------------------------------------------

FIRESTORE_BASE_URL = (
    "https://firestore.googleapis.com/v1/projects/"
    f"{PROJECT_ID}/databases/(default)/documents"
)

LICENSE_PATH = os.path.join(SETTINGS_DIR, "license.json")
REQUEST_TIMEOUT = 8

# Keys always start with "PF" and look like  PF-83K2-91QA-PL09
KEY_RE = re.compile(r"^PF-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")

# How long each tier lasts (months); None == lifetime / never expires.
TIER_MONTHS = {
    "Personal 6-month": 6,
    "Personal 12-month": 12,
    "Personal Lifetime": None,
}


# --- key helpers -----------------------------------------------------------
def normalize_key(raw):
    return (raw or "").strip().upper()


def valid_key_format(raw):
    return bool(KEY_RE.match(normalize_key(raw)))


# --- expiry helpers --------------------------------------------------------
def _add_months(d, months):
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def compute_expiration(tier, today=None):
    """Expiration date string (MM-DD-YYYY) for a tier, or 'Lifetime'."""
    today = today or date.today()
    months = TIER_MONTHS.get(tier, None)
    if months is None:
        return "never"
    return _add_months(today, months).strftime("%m-%d-%Y")


def is_expired(expiration):
    if not expiration or expiration in ("never", "Lifetime"):
        return False
    try:
        d = datetime.strptime(expiration, "%m-%d-%Y").date()
    except Exception:
        return True   # unparseable -> treat as invalid/expired
    return date.today() > d


# --- local activation token ------------------------------------------------
def local_license():
    try:
        with open(LICENSE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def normalize_email(raw):
    return (raw or "").strip().lower()


LICENSE_WARNING = (
    "Do NOT, under ANY circumstances, change this data. Doing so will break your "
    "license and you will have to purchase a new one, and you will still not have "
    "access to the software. If you have any questions, please contact "
    "ewanferreira@outlook.com."
)


def save_license(key, tier, expiration, email):
    try:
        with open(LICENSE_PATH, "w", encoding="utf-8") as f:
            json.dump({"licensed": True, "key": key, "tier": tier,
                       "expiration-date": expiration, "email": email,
                       "WARNING": LICENSE_WARNING}, f, indent=2)
    except Exception:
        pass


# --- Firestore REST --------------------------------------------------------
def _url(path):
    url = FIRESTORE_BASE_URL + path
    if FIREBASE_API_KEY:
        url += ("&" if "?" in path else "?") + "key=" + FIREBASE_API_KEY
    return url


def _request(path, method="GET", body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(_url(path), data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8") or "{}")


def _configured():
    return PROJECT_ID not in ("", "your-project-id")


# --- re-validation (called every launch) -----------------------------------
def is_licensed():
    """Re-validate the local token against Firestore. Every DB-backed field must
    match exactly, the licence must not be expired, and the key must still be
    activated. Falls back to the local expiry only when the DB is unreachable."""
    local = local_license()
    key = normalize_key(local.get("key"))
    if local.get("licensed") is not True or not valid_key_format(key):
        return False

    expiration = local.get("expiration-date")
    if is_expired(expiration):
        return False
    if not _configured():
        return False

    try:
        try:
            _status, doc = _request(f"/licenses/{key}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False               # key no longer exists -> tampered
            return not is_expired(expiration)   # transient server error -> grace
        fields = doc.get("fields", {})
        if not fields.get("activated", {}).get("booleanValue", False):
            return False
        if fields.get("tier", {}).get("stringValue") != local.get("tier"):
            return False
        if fields.get("expiration-date", {}).get("stringValue", "") != (expiration or ""):
            return False
        if fields.get("status", {}).get("stringValue", "") == "pending review":
            return False
        db_email = normalize_email(fields.get("email", {}).get("stringValue", ""))
        if db_email and db_email != normalize_email(local.get("email")):
            return False
        return True
    except (urllib.error.URLError, OSError):
        return not is_expired(expiration)  # offline grace
    except Exception:
        return not is_expired(expiration)


# --- activation ------------------------------------------------------------
def _flag_pending_review(key):
    try:
        _request(f"/licenses/{key}?updateMask.fieldPaths=status",
                 method="PATCH",
                 body={"fields": {"status": {"stringValue": "pending review"}}})
    except Exception:
        pass


def activate(raw_key, raw_email):
    """Validate + consume a license key against Firestore. Both the key AND the
    email must match the record; otherwise the licence is deactivated and flagged
    for review.

    Returns ``(ok: bool, message: str, tier: str | None)``.
    """
    key = normalize_key(raw_key)
    email = normalize_email(raw_email)
    if not key:
        return False, "Please enter a license key.", None
    if not valid_key_format(key):
        return False, "Keys look like  PF-XXXX-XXXX-XXXX.", None
    if not email or "@" not in email:
        return False, "Please enter the email you used to purchase.", None
    if not _configured():
        return False, "Activation isn't configured yet (set PROJECT_ID).", None

    try:
        # 1. Fetch the license document.
        try:
            _status, doc = _request(f"/licenses/{key}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, "Invalid license key. Please check your spelling.", None
            return False, f"Activation failed (server {e.code}).", None

        fields = doc.get("fields", {})
        status = fields.get("status", {}).get("stringValue", "")
        already = fields.get("activated", {}).get("booleanValue", False)
        tier = fields.get("tier", {}).get("stringValue", "Standard")
        db_email = normalize_email(fields.get("email", {}).get("stringValue", ""))

        # 2. Already-flagged or already-used keys.
        if status == "pending review":
            return False, "This licence is under review. Please contact support.", None
        if already:
            return False, "This license key has already been activated.", None

        # 3. Email must match the key. If it doesn't, deactivate and flag.
        if db_email and email != db_email:
            _flag_pending_review(key)
            return False, ("That email does not match this key. The licence has "
                           "been deactivated and is now pending review."), None

        # 4. Consume the key: activated=true, computed expiration, and the email.
        # "expiration-date" has a hyphen so its field path is backtick-quoted (%60).
        expiration = compute_expiration(tier)
        mask = ("updateMask.fieldPaths=activated"
                "&updateMask.fieldPaths=%60expiration-date%60"
                "&updateMask.fieldPaths=email")
        body = {"fields": {
            "activated": {"booleanValue": True},
            "expiration-date": {"stringValue": expiration},
            "email": {"stringValue": email},
        }}
        try:
            _request(f"/licenses/{key}?{mask}", method="PATCH", body=body)
        except urllib.error.HTTPError as e:
            return False, f"Activation failed during sync (server {e.code}).", None

        save_license(key, tier, expiration, email)
        when = "never expires" if expiration == "never" else f"valid until {expiration}"
        return True, f"Activation successful! {tier} - {when}.", tier

    except (urllib.error.URLError, OSError):
        return False, "Connection error. Please ensure you are online.", None
    except Exception:
        return False, "Connection error. Please ensure you are online.", None
