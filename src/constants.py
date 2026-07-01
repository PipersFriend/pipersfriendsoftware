import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
from tkinter import ttk
import json
import uuid
import threading
import time
import os
import io
import wave
import array
import codecs
import base64
from PIL import Image, ImageTk, ImageDraw, ImageFont

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# --- CONSTANTS & DATA STRUCTURES ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "user_data", "user_scores")
os.makedirs(DATA_DIR, exist_ok=True)

SETTINGS_DIR = os.path.join(BASE_DIR, "user_data", "user_settings")
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")
os.makedirs(SETTINGS_DIR, exist_ok=True)

# Global (app-wide) settings, persisted to settings.json.
DEFAULT_SETTINGS = {
    "theme": "dark",                 # "dark" or "light"
    "app_font": "Segoe UI",          # APP UI font (not the score font)
    "app_font_size": 10,
    "accent_color": "#f59e0b",
    "volume": 200,                   # playback loudness (%); samples are amplified to match
    "audio_start_sec": 3.0,          # skip this many seconds of each sample (warm-up)
    "default_instrument": "GHB",     # "GHB" or "chanter"
    "default_tempo": 90,
    "default_time_signature": "4/4",
    "default_tune_type": "March",
    "default_composer": "Unknown",
    "show_page_border": True,
    "show_page_number": True,
    "confirm_clear": True,
    "highlight_color": "#2563eb",   # selected notes / bar outline / ghost note
}


def load_settings():
    data = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            txt = f.read().strip()
        if txt:
            data.update(json.loads(txt))
    except Exception:
        pass
    return data


def save_settings(settings):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass


THEMES = {
    "dark":  {"bg": "#18181b", "panel": "#27272a", "sub": "#202023",
              "fg": "#e4e4e7", "muted": "#a1a1aa", "canvas": "#2a2a2d"},
    "light": {"bg": "#f4f4f5", "panel": "#e4e4e7", "sub": "#d4d4d8",
              "fg": "#18181b", "muted": "#52525b", "canvas": "#9aa0a6"},
}

FALLBACK_KEY = b"PipersFriendSecretKeySystem2026!"

# y_offsets are multiples of LINE_GAP/2 (= 6) so the staff is 15% thinner than
# the original 14px line gap.
# y_offsets are multiples of LINE_GAP/2 (= 7) so notes sit on lines/in spaces.
CHANTER_SCALE = [
    {"name": "High A", "freq": 880.0, "y_offset": -14},
    {"name": "High G", "freq": 784.0, "y_offset": -7},
    {"name": "F",      "freq": 698.0, "y_offset": 0},
    {"name": "E",      "freq": 659.0, "y_offset": 7},
    {"name": "D",      "freq": 587.0, "y_offset": 14},
    {"name": "C",      "freq": 523.0, "y_offset": 21},
    {"name": "B",      "freq": 494.0, "y_offset": 28},
    {"name": "Low A",  "freq": 440.0, "y_offset": 35},
    {"name": "Low G",  "freq": 392.0, "y_offset": 42}
]

NOTE_DURATIONS = {
    "Whole": {"val": 2.0, "hollow": True, "stem": False},
    "Half": {"val": 1.0, "hollow": True, "stem": True},
    "Quarter": {"val": 0.5, "hollow": False, "stem": True},
    "Quaver": {"val": 0.25, "hollow": False, "stem": True},
    "Semiquaver": {"val": 0.125, "hollow": False, "stem": True},
    "Demisemiquaver": {"val": 0.0625, "hollow": False, "stem": True},
    "Hemidemisemiquaver": {"val": 0.03125, "hollow": False, "stem": True},
    "Gracenote": {"val": 0.03125, "hollow": False, "stem": True} 
}

MIN_BPM = 30
MAX_BPM = 120

# Note/grace head widths (logical px) — 15% larger.
NOTE_HEAD_W = 14
GRACE_HEAD_W = 8

# Staff line spacing equals the notehead size.
LINE_GAP = NOTE_HEAD_W       # 14
STAFF_H = 4 * LINE_GAP       # 56: top line to bottom line
STAFF_LINE_W = 2.5           # staff line stroke (logical px)
CLEF_CURL_FRAC = 0.624       # where the G-clef spiral sits within the glyph (top=0)
STAF_1_Y = 175               # leaves room above for the page header
STAF_2_Y = 340
CANVAS_LEFT = 80
CANVAS_RIGHT = 1760          # longer staves
CLEF_SAFE_ZONE = 112         # room for clef + key signature + time signature

# The score sits on a page with the aspect ratio of US Letter (8.5 x 11).
PAGE_MARGIN_R = 60
PAGE_W = CANVAS_RIGHT + PAGE_MARGIN_R
PAGE_H = int(round(PAGE_W * 11.0 / 8.5))
RENDER_AA = 2               # supersampling factor for the page buffer

# Font family -> Windows font files (regular/bold/italic/bold-italic) for the
# header text. Missing variants fall back to the regular file.
FONT_FILES = {
    "Sans Serif":      {"r": "arial.ttf",   "b": "arialbd.ttf", "i": "ariali.ttf",   "bi": "arialbi.ttf"},
    "Serif":           {"r": "georgia.ttf", "b": "georgiab.ttf", "i": "georgiai.ttf", "bi": "georgiaz.ttf"},
    "Cambria":         {"r": "cambria.ttc", "b": "cambriab.ttf", "i": "cambriai.ttf", "bi": "cambriaz.ttf"},
    "Times New Roman": {"r": "times.ttf",   "b": "timesbd.ttf", "i": "timesi.ttf",   "bi": "timesbi.ttf"},
}
HEADER_FONT_CHOICES = list(FONT_FILES.keys())

# Per-element header text styling (font size & style), editable by double-click.
DEFAULT_HEADER_STYLE = {
    "title":     {"font": "Sans Serif", "size": 34, "bold": True,  "italic": False},
    "tune_type": {"font": "Sans Serif", "size": 20, "bold": False, "italic": True},
    "composer":  {"font": "Sans Serif", "size": 18, "bold": False, "italic": False},
}

# Beam geometry (logical px) for barred notes.
BEAM_BELOW_STAVE = 14  # primary beam distance below the bottom stave line
BEAM_GAP = 5           # spacing between stacked beam levels
BEAM_THICK = 3         # beam thickness
BEAM_STUB = 7          # length of a partial / stub beam

# Number of beams per note value, and the set of barred (sub-crotchet) values.
BEAM_COUNTS = {"quaver": 1, "semiquaver": 2, "demisemiquaver": 3, "hemidemisemiquaver": 4}

# Grace-note pitches produced by a doubling, keyed by the melody note it lands on.
DOUBLING_MAP = {
    "High A": ["High A", "High G"],
    "High G": ["High G", "F"],
    "F":      ["High G", "F", "High G"],
    "E":      ["High G", "E", "F"],
    "D":      ["High A", "D", "E"],
    "C":      ["High G", "C", "D"],
    "B":      ["High A", "B", "D"],
    "Low A":  ["High G", "Low A", "D"],
    "Low G":  ["High G", "Low G", "D"],
}

TIME_SIGNATURE_OPTIONS = ["4/4", "2/4", "3/4", "6/8", "9/8", "12/8", "Common", "Cut"]

# Bar boundary styles. Glyphs live in Assets/bar/start/<style>.png and
# Assets/bar/end/<style>.png ("normal" draws nothing extra over the plain line).
BAR_START_STYLES = ["Normal", "Repeat", "Start"]
BAR_END_STYLES = ["Normal", "Repeat", "End"]


