"""Bagpipe Music Writer (.bww) import / export for The Piper's Friend.

This targets the real BWW text format used by Bagpipe Music Writer / Bagpipe
Reader so that exported files open in that software (and real .bww files import
here). It is a practical subset: melody notes with durations and dots, barlines
(including repeats), the time signature, the highland key, and the common
embellishments (single gracenotes, doublings, grip/leumluath, taorluath, throw
on D light/heavy, birls). Exotic movements fall back to explicit gracenotes.

The grammar (abridged):
    Bagpipe Reader:1.0
    <numeric mapping/format header lines>
    "Title",(...)  "Tune Type",(...)  "Composer",(...)  "Footer",(...)
    & sharpf sharpc 4_4
    gg LA_4 dbb B_8 'la  !  grp D_4  ''!I
A melody note is <PITCH><dir?>_<dur>; a dot is '<pitch>; embellishments are
lowercase macros placed before the note they ornament.
"""

import re

from .constants import (CHANTER_SCALE, NOTE_DURATIONS, DOUBLING_MAP,
                        CANVAS_LEFT, CANVAS_RIGHT, CLEF_SAFE_ZONE)
from .model import BagpipeScore, _default_bar_lines, _default_bar_style

# --- pitch <-> token --------------------------------------------------------
PITCH_TO_BWW = {"Low G": "LG", "Low A": "LA", "B": "B", "C": "C", "D": "D",
                "E": "E", "F": "F", "High G": "HG", "High A": "HA"}
BWW_TO_PITCH = {v: k for k, v in PITCH_TO_BWW.items()}
# lower-case pitch suffix used by dot tokens and doubling macros (dblg, 'la ...)
PITCH_SUFFIX = {"Low G": "lg", "Low A": "la", "B": "b", "C": "c", "D": "d",
                "E": "e", "F": "f", "High G": "hg", "High A": "ha"}
SUFFIX_PITCH = {v: k for k, v in PITCH_SUFFIX.items()}

# --- duration <-> token -----------------------------------------------------
DUR_TO_BWW = {"whole": "1", "half": "2", "quarter": "4", "quaver": "8",
              "semiquaver": "16", "demisemiquaver": "32", "hemidemisemiquaver": "32"}
BWW_TO_DUR = {"1": "whole", "2": "half", "4": "quarter", "8": "quaver",
              "16": "semiquaver", "32": "demisemiquaver"}
DUR_VALUE = {k: NOTE_DURATIONS[k.capitalize()]["val"] for k in DUR_TO_BWW}

# --- time signature <-> token ----------------------------------------------
TS_TO_BWW = {"4/4": "4_4", "2/4": "2_4", "3/4": "3_4", "6/8": "6_8",
             "9/8": "9_8", "12/8": "12_8", "2/2": "2_2", "Common": "C", "Cut": "C_"}
BWW_TO_TS = {v: k for k, v in TS_TO_BWW.items()}

# --- embellishment macros ---------------------------------------------------
# emb id (our model) -> a function/token producing the bww macro on export.
EMB_TO_MACRO = {"leamluath": "grp", "taorluath": "tar", "d_throw": "thrd",
                "heavy_d_throw": "hthrd", "birl": "birl", "high_g_birl": "gbr"}
# bww macro -> (emb id, pitches-or-None). None means "depends on target pitch".
MACRO_TO_EMB = {"grp": ("leamluath", ["Low G", "D", "Low G"]),
                "tar": ("taorluath", ["Low G", "D", "Low G", "E"]),
                "thrd": ("d_throw", ["Low G", "D", "C"]),
                "hthrd": ("heavy_d_throw", ["Low G", "D", "Low G", "C"]),
                "birl": ("birl", ["Low G", "Low A", "Low G"]),
                "gbr": ("high_g_birl", ["High G", "Low A", "Low G", "Low A", "Low G"])}
# single gracenote token <-> grace pitch
GRACE_TO_TOKEN = {"High G": "gg", "High A": "tg", "F": "fg", "E": "eg",
                  "D": "dg", "C": "cg", "B": "bg", "Low A": "lag", "Low G": "lg"}
TOKEN_TO_GRACE = {v: k for k, v in GRACE_TO_TOKEN.items()}


# ===========================================================================
# EXPORT
# ===========================================================================
def _esc(s):
    return str(s or "").replace('"', "'")


def _header(score):
    title = _esc(score.title)
    ttype = _esc(score.tune_type)
    comp = _esc(score.composer)
    return "\n".join([
        "Bagpipe Reader:1.0",
        "MIDINoteMappings,(54,56,58,59,61,63,64,66,68,56,58,60,61,63,65,66,68,70,55,57,59,60,62,64,65,67,69)",
        "FrequencyMappings,(370,415,466,494,554,622,659,734,831,415,466,524,554,622,699,734,831,932,392,440,494,524,587,659,699,784,880)",
        "InstrumentMappings,(71,71,45,33,1000,60,70)",
        "GracenoteDurations,(20,40,30,50,100,200,800,1200,250,250,250,500,200)",
        "FontSizes,(90,100,100,80,250)",
        "TuneFormat,(1,0,F,L,500,500,500,500,L,0,0)",
        "TuneTempo,%d" % int(getattr(score, "tempo", 90) or 90),
        "",
        '"%s",(T,L,0,0,Times New Roman,16,700,0,0,18,0,0,0)' % title,
        '"%s",(Y,C,0,0,Times New Roman,14,400,1,0,18,0,0,0)' % ttype,
        '"%s",(M,R,0,0,Times New Roman,11,400,0,0,18,0,0,0)' % comp,
        '"%s",(F,C,0,0,Times New Roman,10,400,0,0,18,0,0,0)' % _esc(getattr(score, "footer", "")),
        "",
    ])


def _grace_tokens(note, graces):
    """bww tokens for the gracenotes ornamenting one melody note, in order."""
    out = []
    i = 0
    while i < len(graces):
        emb = graces[i].get("emb")
        if emb and emb != "doubling" and emb in EMB_TO_MACRO:
            # all consecutive graces of this emb collapse to one macro
            out.append(EMB_TO_MACRO[emb])
            while i < len(graces) and graces[i].get("emb") == emb:
                i += 1
            continue
        if emb == "doubling":
            out.append("db" + PITCH_SUFFIX.get(note["pitch"], "la"))
            while i < len(graces) and graces[i].get("emb") == "doubling":
                i += 1
            continue
        # plain / unknown -> one explicit single-gracenote token
        out.append(GRACE_TO_TOKEN.get(graces[i]["pitch"], "gg"))
        i += 1
    return out


def _staff_last_bar(score, staff):
    """Index of the last bar on this staff that carries a note or a non-normal
    style, or -1 if the staff is empty."""
    last = -1
    styles = score.bar_styles.get(staff, [])
    for b in range(score.num_bars(staff)):
        has_notes = any(n.get("staff", 1) == staff and n.get("bar_index") == b
                        and n["dur_type"] != "gracenote" for n in score.nodes)
        st = styles[b] if b < len(styles) else {}
        has_style = st.get("start", "Normal") != "Normal" or st.get("end", "Normal") != "Normal"
        if has_notes or has_style:
            last = b
    return last


def score_to_bww(score):
    lines = [_header(score)]
    # Only emit staves that carry content (skip trailing blank staves).
    staves = [s for s in score.staff_list() if _staff_last_bar(score, s) >= 0]
    if not staves:
        staves = [score.staff_list()[0]]
    last_staff = staves[-1]
    for staff in staves:
        ts = TS_TO_BWW.get(score.time_sig_for(staff), "4_4")
        row = ["& sharpf sharpc %s" % ts]
        styles = score.bar_styles.get(staff, [])
        nbars = max(1, _staff_last_bar(score, staff) + 1)   # trim trailing empty bars
        for b in range(nbars):
            st = styles[b] if b < len(styles) else _default_bar_style()
            if st.get("start") == "Repeat":
                row.append("I!''")
            normals = sorted([n for n in score.nodes
                              if n.get("staff", 1) == staff and n.get("bar_index") == b
                              and n["dur_type"] != "gracenote"],
                             key=lambda n: n.get("raw_x", 0))
            for note in normals:
                graces = sorted([g for g in score.nodes
                                 if g["dur_type"] == "gracenote"
                                 and g.get("target_normal_id") == note["id"]],
                                key=lambda g: (g.get("raw_x", 0), g.get("seq", 0)))
                row.extend(_grace_tokens(note, graces))
                if note.get("sharp"):
                    row.append("sharp" + PITCH_SUFFIX.get(note["pitch"], "f"))
                tok = PITCH_TO_BWW.get(note["pitch"], "LA") + "_" + DUR_TO_BWW.get(note["dur_type"], "4")
                row.append(tok)
                if note.get("dotted"):
                    row.append("'" + PITCH_SUFFIX.get(note["pitch"], "la"))
            # barline after the bar
            is_final = (staff == last_staff and b == nbars - 1)
            if st.get("end") == "Repeat":
                row.append("''!I")
            elif is_final:
                row.append("!I")
            else:
                row.append("!")
        lines.append(" ".join(row))
    return "\n".join(lines) + "\n"


# ===========================================================================
# IMPORT
# ===========================================================================
NOTE_RE = re.compile(r"^(HG|HA|LG|LA|[A-G])([lr]?)_(\d{1,2})$")
DOT_RE = re.compile(r"^'(hg|ha|lg|la|[a-g])$")


def _is_header_line(line):
    s = line.strip()
    if not s:
        return True
    if s.startswith(("Bagpipe Reader", "Bagpipe Music Writer", "MIDINoteMappings",
                     "FrequencyMappings", "InstrumentMappings", "GracenoteDurations",
                     "FontSizes", "TuneFormat", "TuneTempo", "Bagpipe")):
        return True
    if s.startswith('"'):              # "Title",(...) etc.
        return True
    return False


def _macro_pitches(macro, target_pitch):
    """(emb_id, [grace pitches]) for a recognised embellishment macro, or None."""
    if macro in MACRO_TO_EMB:
        return MACRO_TO_EMB[macro]
    if macro.startswith("db"):
        suffix = macro[2:]
        if suffix in SUFFIX_PITCH:
            return ("doubling", list(DOUBLING_MAP.get(target_pitch, ["High G", target_pitch])))
    if macro in TOKEN_TO_GRACE:
        return (None, [TOKEN_TO_GRACE[macro]])
    return None


def bww_to_score(text):
    """Parse .bww text into a BagpipeScore. Notes are laid out 4 bars per stave."""
    score = BagpipeScore()
    # metadata from the header
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r'^"([^"]*)",\(([A-Z])', s)
        if m:
            val, kind = m.group(1), m.group(2)
            if kind == "T":
                score.title = val
            elif kind == "Y":
                score.tune_type = val
            elif kind == "M":
                score.composer = val
            elif kind == "F":
                score.footer = val
        if s.startswith("TuneTempo,"):
            try:
                score.tempo = int(s.split(",")[1])
            except Exception:
                pass

    time_sig = "4/4"
    bars = []                          # list of dicts: notes, start, end
    cur = {"notes": [], "start": "Normal", "end": "Normal"}
    pending_emb = []                   # macros waiting for their target note
    pending_sharp = False              # inline accidental for the next note
    in_key = False                     # inside the "& sharpf sharpc" key group
    acc_re = re.compile(r"^(sharp|natural|flat)(lg|la|hg|ha|b|c|d|e|f|g)$")

    def close_bar(end_style="Normal"):
        nonlocal cur
        cur["end"] = end_style
        if cur["notes"] or cur["start"] != "Normal" or end_style != "Normal":
            bars.append(cur)
        cur = {"notes": [], "start": "Normal", "end": "Normal"}

    tokens = []
    for line in text.splitlines():
        if _is_header_line(line):
            continue
        for tok in line.replace("\t", " ").split():
            tokens.append(tok)

    for tok in tokens:
        if tok == "&":
            in_key = True               # key signature group follows
            continue
        acc = acc_re.match(tok)
        if acc:
            if in_key:
                continue                # part of the key signature, not an accidental
            pending_sharp = (acc.group(1) == "sharp")
            continue
        in_key = False                  # any other token ends the key group
        if tok in BWW_TO_TS:
            time_sig = BWW_TO_TS[tok]
            continue
        # barlines / repeats
        if tok in ("''!I", "'!I"):
            close_bar("Repeat")
            continue
        if tok == "I!''":
            if cur["notes"]:
                close_bar("Normal")
            cur["start"] = "Repeat"      # applies to the bar now being filled
            continue
        if tok in ("!", "!!", "!I", "!t", "!_I", "I!"):
            close_bar("Normal")
            continue
        # dotted note
        dm = DOT_RE.match(tok)
        if dm and cur["notes"]:
            cur["notes"][-1]["dotted"] = True
            continue
        # melody note
        nm = NOTE_RE.match(tok)
        if nm:
            pitch = BWW_TO_PITCH.get(nm.group(1))
            if pitch is None:
                continue
            dur = BWW_TO_DUR.get(nm.group(3), "quarter")
            note = {"pitch": pitch, "dur_type": dur, "graces": list(pending_emb),
                    "sharp": pending_sharp}
            pending_emb = []
            pending_sharp = False
            cur["notes"].append(note)
            continue
        # otherwise: an embellishment macro -> wait for the next melody note
        if re.match(r"^[a-z][a-z0-9']*$", tok):
            pending_emb.append(tok)

    if cur["notes"]:
        close_bar(cur["end"])
    if not bars:
        bars = [{"notes": [], "start": "Normal", "end": "Normal"}]

    _build_score(score, bars, time_sig)
    return score


def _build_score(score, bars, time_sig, bars_per_stave=4):
    import uuid
    nstaves = max(1, (len(bars) + bars_per_stave - 1) // bars_per_stave)
    score.num_staves = nstaves
    score.time_signature = time_sig
    score.stave_time_sigs = {s: time_sig for s in range(1, nstaves + 1)}
    score.bar_lines = {}
    score.bar_styles = {}
    score.nodes = []
    seq = [0]

    def nx():
        seq[0] += 1
        return seq[0]

    for s in range(1, nstaves + 1):
        chunk = bars[(s - 1) * bars_per_stave: s * bars_per_stave]
        if not chunk:
            chunk = [{"notes": [], "start": "Normal", "end": "Normal"}]
        nb = len(chunk)
        score.bar_lines[s] = _default_bar_lines(nb)
        score.bar_styles[s] = []
        for bi, bar in enumerate(chunk):
            style = _default_bar_style()
            style["start"] = bar.get("start", "Normal")
            style["end"] = bar.get("end", "Normal")
            score.bar_styles[s].append(style)
            left, right = _bar_bounds(score, s, bi, nb)
            notes = bar["notes"]
            span = right - left
            for k, nd in enumerate(notes):
                rx = left + span * (k + 1) / (len(notes) + 1)
                tid = str(uuid.uuid4())[:8]
                score.nodes.append({
                    "id": tid, "pitch": nd["pitch"], "dur_type": nd["dur_type"],
                    "duration": DUR_VALUE.get(nd["dur_type"], 0.5),
                    "dotted": nd.get("dotted", False), "sharp": nd.get("sharp", False),
                    "staff": s, "bar_index": bi,
                    "target_normal_id": tid, "raw_x": rx, "seq": nx(),
                })
                # expand and attach this note's embellishments
                for macro in nd.get("graces", []):
                    res = _macro_pitches(macro, nd["pitch"])
                    if not res:
                        continue
                    emb_id, pitches = res
                    for p in pitches:
                        score.nodes.append({
                            "id": str(uuid.uuid4())[:8], "pitch": p,
                            "dur_type": "gracenote", "duration": 0.03125,
                            "staff": s, "bar_index": bi, "target_normal_id": tid,
                            "raw_x": rx - 5, "emb": emb_id, "seq": nx(),
                        })


def _bar_bounds(score, staff, b, nbars):
    lines = score.bar_lines.get(staff, _default_bar_lines(nbars))
    left = (CANVAS_LEFT + CLEF_SAFE_ZONE) if b == 0 else lines[b - 1]
    right = CANVAS_RIGHT if b >= len(lines) else lines[b]
    return left, right
