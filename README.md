# The Piper's Friend

A desktop **bagpipe sheet-music editor and player** for Great Highland Bagpipe
(GHB) and Practice Chanter tunes. Write tunes on a two-stave, Letter-sized page,
hear them back with real instrument samples, and export or print the result.

Built with **Python + Tkinter** (UI) and **Pillow** (rendering). Audio uses the
Windows `winsound` module. Access requires a **purchased activation key**
verified against Firebase.

---

## Features

- **Score editor** on a US-Letter-proportioned page with title / composer /
  tune-type header (each editable by double-clicking) and a page number.
- **Two independent staves** with a G-clef (spiral on the G line) and a
  full-height time signature centred on the B line.
- **Notes** from whole down to hemidemisemiquaver, with **dots** and **ties**
  (ties force matching pitch).
- **Bagpipe beaming** — sub-crotchet notes are barred by beat with correct beam
  counts and partial beams; no loose flags.
- **Gracenotes & embellishments** — single gracenotes plus **Doubling**,
  **Throw on D**, **Birl**, **High G Birl**, with placement rules (birls only on
  Low A, throw-on-D only on D, doublings tied to the note they attach to).
  Barred gracenotes always beam at the top of the stave.
- **Bar styles** — set each bar's start/end to Normal, Repeat, or Part barlines.
- **Translucent hover preview** of the note/gracenote about to be placed.
- **Zoom & scroll**, draggable barlines (independent per stave) with a
  lightweight drag preview.
- **Gapless playback** — notes ring until the next note; gracenotes play as 1/64
  with no cooldown; the playing note is highlighted. Choose Bagpipe or Practice
  Chanter.
- **Save/Open** `.pipe` files, **Export to PDF**, and **Print**.
- **Global settings** (theme, app font, volume, defaults, …) in `settings.json`,
  plus per-tune settings.

---

## Requirements

- **Windows** (audio uses `winsound`; header text uses Windows fonts).
- **Python 3.8+** (developed on 3.13).
- **Pillow**: `pip install pillow`. Tkinter ships with Python.
- An internet connection for first-time **activation**.

---

## Running

```
python main.py
```

`main.py` is a thin launcher; all code lives in the `src/` package.

---

## Project structure

```
Pipers Friend/
├── main.py                 # launcher  ->  from src.app import main
├── README.md
├── src/
│   ├── __init__.py
│   ├── constants.py        # constants, settings load/save, themes, fonts, maps
│   ├── model.py            # BagpipeScore: document + .pipe (de)serialization
│   ├── dialogs.py          # UnifiedSetupDialog (new-tune wizard)
│   ├── licensing.py        # Firestore activation-key verification
│   └── app.py              # PipersFriendApp: UI, rendering, audio, events
├── Assets/                 # notes/, bar/, time_sigs/, audio/{GHB,chanter}/, menu/
└── user_data/
    ├── user_scores/        # saved *.pipe tunes
    └── user_settings/      # settings.json, license.json
```

---

## Using the app

**Dashboard** — New Score (wizard), Open Existing, a **My Scores** list, and a
**⚙ Settings** button (top-right) for global settings.

**Editor ribbon**

| Tab | What it does |
|-----|--------------|
| **File** | New / Open / Save / Export PDF / Export PIPE / Print / Clear / Exit |
| **Notes** | Pick a duration; Dot / Tie the selected note |
| **Gracenotes** | Single gracenote and embellishments |
| **Bar** | Select a bar, then set its Start and End style |
| **Playback** | Instrument + Play (all / from note / from bar) / Stop |
| **Settings** | Per-tune: name, composer, type, time sig, BPM, gaps, score font |

**On the page** — hover to preview a note; click empty stave to place a note
*and* select that bar; click a note to select it and return to the Notes tab;
double-click the header to edit text/font; drag a barline to resize a bar;
Delete/Backspace removes the selected note. Zoom with 🔍/Fit, Ctrl+wheel, or
Ctrl +/-; wheel scrolls.

---

## File formats

### `.pipe` (score) — JSON, format version `2.0.0`
Metadata (title, composer, type, time sig, tempo, gaps, font, per-element header
styles), per-stave `bar_lines` and `bar_styles`, and a `score_timeline` of
note/gracenote nodes (`id`, `pitch`, `duration`, `dur_type`, `staff`,
`bar_index`, `raw_x`, `target_normal_id`, `seq`). Pitches:
`High A, High G, F, E, D, C, B, Low A, Low G`.

### `settings.json` (global)
Theme, app font/size, accent colour, volume, audio start-second, default
instrument/tempo/time-signature/type/composer, page toggles, confirm-on-clear.

### `license.json`
Local activation token written after a successful activation.

---

## Audio

Per-pitch `.wav` samples in `Assets/audio/{GHB,chanter}` are trimmed by
`audio_start_sec` (default 3s, to skip the reedy warm-up) and amplified toward
the `volume` setting (default 200%). On playback the whole selection is
concatenated into one continuous WAV and played via `SND_FILENAME`, so notes are
gapless and gracenotes flow straight into the next note.

---

## Licensing / activation

The app is gated behind a **purchased activation key** verified against
**Firebase Firestore**. On first launch the user is asked for a key; once
activated, a local token (`user_data/user_settings/license.json`) opens the app
straight to the dashboard.

Keys always start with `PF` and look like:

```
PF-83K2-91QA-PL09
```

### Firestore setup

1. Create a Firestore project, then a collection named **`licenses`**.
2. Add one document **per key** — the **document ID is the key itself** — with
   fields:
   | field | type | value |
   |-------|------|-------|
   | `activated` | boolean | `false` |
   | `tier` | string | `"Personal 6-month"`, `"Personal 12-month"`, or `"Personal Lifetime"` |
   | `expiration-date` | string | left blank; written on activation as `MM-DD-YYYY` |
3. In **`src/licensing.py`**, set `PROJECT_ID` to your project id (optionally
   `FIREBASE_API_KEY`).
4. Security rules that allow reading a license and flipping only `activated`
   and `expiration-date`:
   ```
   match /licenses/{key} {
     allow get: if true;
     allow update: if request.resource.data.diff(resource.data)
                        .affectedKeys().hasOnly(['activated', 'expiration-date'])
                    && resource.data.activated == false
                    && request.resource.data.activated == true;
     allow create, delete, list: if false;
   }
   ```

### Tiers and expiry

The **`tier`** sets how long the licence lasts; the **expiration date is
computed at activation** (activation date + the tier's duration) and written to
both the database and the local token as `MM-DD-YYYY`:

| tier | duration |
|------|----------|
| `Personal 6-month` | 6 months |
| `Personal 12-month` | 12 months |
| `Personal Lifetime` | never expires (`expiration-date` = `never`) |

### How activation works

1. `GET licenses/<key>` — `404` ⇒ invalid key.
2. If `activated` is already `true` ⇒ key already used, rejected.
3. Otherwise `PATCH` sets `activated = true` **and** the computed
   `expiration-date`, consuming the key, and writes the local token.

### Anti-tamper

The local token is **not trusted on its own**. On every launch the app
**re-validates against Firestore**: the key must still exist, be `activated`,
and its `tier` and `expiration-date` must **match the database exactly**, and the
licence must not be expired. So editing `license.json` to grant or extend a
licence fails the moment the app is online. When the database is unreachable, the
app falls back to the locally-recorded expiry as an offline grace period.

Activation uses the **Firestore REST API** via the standard library — no extra
dependency, and (importantly) no bundled service-account secret. A distributed
desktop app must never ship `firebase-admin` credentials.

---

## Known limitations / TODO

- **Windows only** (winsound + Windows font files).
- **BWW export** is a placeholder.
- The local activation token is not strong DRM (see above).
- The full-page render buffer is large; very dense editing/playback can feel
  heavy on slower machines.
- At very slow tempos a long note can exceed its sample length, in which case
  the sample is tiled to fill.

---
