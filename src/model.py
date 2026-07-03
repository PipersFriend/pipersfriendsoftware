from .constants import *


def _default_bar_lines(nbars=4):
    return [round(CANVAS_LEFT + (CANVAS_RIGHT - CANVAS_LEFT) * i / nbars)
            for i in range(1, nbars)]


def _default_bar_style():
    return {"start": "Normal", "end": "Normal", "timing": "None"}


class BagpipeScore:
    def __init__(self, title="Untitled Tune", time_signature="4/4", tempo=120, tune_type="March", composer="Unknown"):
        self.title = title
        self.time_signature = time_signature
        self.tempo = tempo
        self.tune_type = tune_type
        self.composer = composer
        self.gap_between_staves = 100   # default gap reduced 50% (was 200)
        self.gap_after_gracenotes = 14
        self.selected_font = "Sans Serif"
        self.header_style = {k: dict(v) for k, v in DEFAULT_HEADER_STYLE.items()}
        # "pipe" = bagpipe notation; "drum" = Berger uniline drum notation.
        self.mode = "pipe"
        self.drum_voice = "Snare"          # Snare / Tenor / Bass (drum mode only)
        self.nodes = []
        self.num_staves = 2
        # Each stave can carry its own time signature.
        self.stave_time_sigs = {1: time_signature, 2: time_signature}
        # Per-staff bar start/end styles + second-timing bracket.
        self.bar_styles = {s: [_default_bar_style() for _ in range(4)] for s in (1, 2)}
        # Bar lines are independent per staff so resizing a bar on one stave
        # does not move the bars on the other stave.
        self.bar_lines = {1: _default_bar_lines(), 2: _default_bar_lines()}

    # --- helpers ----------------------------------------------------------
    def staff_list(self):
        return list(range(1, self.num_staves + 1))

    def num_bars(self, staff):
        return len(self.bar_lines.get(staff, [])) + 1

    def time_sig_for(self, staff):
        return self.stave_time_sigs.get(staff, self.time_signature)

    def insert_stave(self, at):
        """Insert a new empty stave at 1-based position ``at`` (existing staves
        at/after it shift down)."""
        at = max(1, min(self.num_staves + 1, at))
        for n in self.nodes:
            if n.get("staff", 1) >= at:
                n["staff"] += 1
        for d in (self.bar_lines, self.bar_styles, self.stave_time_sigs):
            for s in range(self.num_staves, at - 1, -1):
                d[s + 1] = d.pop(s)
        self.bar_lines[at] = _default_bar_lines()
        self.bar_styles[at] = [_default_bar_style() for _ in range(4)]
        self.stave_time_sigs[at] = self.time_signature
        self.num_staves += 1

    def add_bar(self, staff, at_index):
        """Insert a new bar on ``staff`` at 0-based ``at_index`` and re-space the
        bar lines of that stave evenly."""
        styles = self.bar_styles[staff]
        at_index = max(0, min(len(styles), at_index))
        styles.insert(at_index, _default_bar_style())
        nbars = len(styles)
        self.bar_lines[staff] = _default_bar_lines(nbars)
        for n in self.nodes:
            if n.get("staff", 1) == staff and n.get("bar_index", 0) >= at_index:
                n["bar_index"] += 1

    # --- serialization ----------------------------------------------------
    def to_pipe_format(self):
        score_data = {
            "format_version": "2.0.0",
            "metadata": {
                "title": self.title,
                "time_signature": self.time_signature,
                "tempo": self.tempo,
                "tune_type": self.tune_type,
                "composer": self.composer,
                "gap_between_staves": self.gap_between_staves,
                "gap_after_gracenotes": self.gap_after_gracenotes,
                "selected_font": self.selected_font,
                "header_style": self.header_style,
                "num_staves": self.num_staves,
                "stave_time_sigs": self.stave_time_sigs,
                "mode": self.mode,
                "drum_voice": self.drum_voice,
            },
            "bar_lines": self.bar_lines,
            "bar_styles": self.bar_styles,
            "score_timeline": self.nodes
        }
        return json.dumps(score_data, indent=2)

    def load_from_pipe_format(self, pipe_string):
        data = json.loads(pipe_string)
        meta = data.get("metadata", {})
        self.title = meta.get("title", "Untitled Tune")
        self.time_signature = meta.get("time_signature", "4/4")
        self.tempo = meta.get("tempo", 120)
        self.tune_type = meta.get("tune_type", "March")
        self.composer = meta.get("composer", "Unknown")
        self.mode = meta.get("mode", "pipe")
        self.drum_voice = meta.get("drum_voice", "Snare")
        self.gap_between_staves = meta.get("gap_between_staves", 100)
        self.gap_after_gracenotes = meta.get("gap_after_gracenotes", 14)
        self.selected_font = meta.get("selected_font", "Sans Serif")
        self.header_style = {k: dict(v) for k, v in DEFAULT_HEADER_STYLE.items()}
        for k, v in (meta.get("header_style") or {}).items():
            if k in self.header_style and isinstance(v, dict):
                self.header_style[k].update(v)

        # bar lines
        bl = data.get("bar_lines", _default_bar_lines())
        if isinstance(bl, dict):
            self.bar_lines = {int(k): list(v) for k, v in bl.items()}
        else:
            self.bar_lines = {1: list(bl), 2: list(bl)}

        # how many staves
        self.num_staves = int(meta.get("num_staves", max(2, *([2] + list(self.bar_lines.keys())))))
        for s in self.staff_list():
            self.bar_lines.setdefault(s, _default_bar_lines())

        # bar styles (ensure each has start/end/timing)
        bs = data.get("bar_styles")
        self.bar_styles = {s: [_default_bar_style() for _ in range(self.num_bars(s))]
                           for s in self.staff_list()}
        if isinstance(bs, dict):
            for k, v in bs.items():
                styles = []
                for entry in v:
                    st = _default_bar_style()
                    st.update(entry)
                    styles.append(st)
                self.bar_styles[int(k)] = styles
        elif isinstance(bs, list):
            self.bar_styles = {1: [dict(_default_bar_style(), **x) for x in bs],
                               2: [dict(_default_bar_style(), **x) for x in bs]}

        # per-stave time signatures
        sts = meta.get("stave_time_sigs") or {}
        self.stave_time_sigs = {}
        for s in self.staff_list():
            self.stave_time_sigs[s] = sts.get(str(s), sts.get(s, self.time_signature))

        self.nodes = data.get("score_timeline", [])
