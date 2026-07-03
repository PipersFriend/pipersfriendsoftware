from .constants import *
from .model import BagpipeScore
from .dialogs import UnifiedSetupDialog
from . import licensing
from . import bww


class PipersFriendApp:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.root.title("Taorluath")
        self.root.geometry("1220x760")
        try:
            icon_path = os.path.join(BASE_DIR, "Assets", "menu", "pf-small.png")
            if os.path.exists(icon_path):
                self._app_icon = ImageTk.PhotoImage(Image.open(icon_path))
                self.root.iconphoto(True, self._app_icon)
        except Exception:
            pass

        self.score = BagpipeScore()
        self.selected_duration = "Quarter"
        self.selected_embellishment = None
        self.drum_rimshot = False          # next drum note is a rimshot (sticks/side)
        self.placing_rest = False          # placing rests rather than notes
        self.selected_instrument = self.settings.get("default_instrument", "GHB")
        self.active_tab = "File"
        self.is_playing = False
        self.active_playback_node_id = None
        self.selected_node_id = None
        self.selected_bar = None           # (staff, bar_index) currently selected
        self.dragging_bar = None           # (staff, bar_index) while dragging a bar line
        self._seq = 0   # monotonic counter to keep grace-note order stable

        self.hover_x = None
        self.hover_y = None
        self.clef_image = None
        self._glyph_cache = {}
        self._wav_cache = {}   # (instrument, pitch) -> raw WAV bytes for gapless playback
        self._font_cache = {}
        self._hover_cache = {}   # (dur_type, zoom) -> translucent preview PhotoImage
        self._bar_img_cache = {}  # (side, style) -> PIL barline glyph
        self.zoom = None       # logical->display px factor; set to fit on first draw
        self.base_dir = BASE_DIR

        self.apply_app_theme()
        self.load_assets()
        self.home_frame = None
        self.editor_frame = None
        self.activation_frame = None
        self.license_tier = licensing.local_license().get("tier")

        # The software must be activated with a purchased key before use; the
        # menu bar only appears once the licence is active.
        if licensing.is_licensed():
            self.setup_system_menu_bar()
            self.show_home_screen()
        else:
            self.show_activation_screen()

        # Check for a newer release shortly after the window is up.
        self.root.after(1200, self.check_for_updates)

    def check_for_updates(self):
        try:
            from . import updater
            rv = updater.update_available()
            if not rv:
                return
            if messagebox.askyesno(
                    "Update available",
                    "A new version (%s) is available - you have %s.\n\n"
                    "Update now? This replaces the installed program files with the "
                    "latest from the repository. Your saved scores are not affected."
                    % (rv, updater.local_version())):
                ok, msg = updater.perform_update()
                (messagebox.showinfo if ok else messagebox.showerror)("Update", msg)
        except Exception:
            pass

    def setup_system_menu_bar(self):
        menubar = tk.Menu(self.root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="New File (Ctrl + N)", command=self.action_create_tune)
        filemenu.add_command(label="Open File (Ctrl + O)", command=self.action_open_file_dialog)
        filemenu.add_command(label="Save Changes (Ctrl + S)", command=self.action_save_changes)
        filemenu.add_separator()
        filemenu.add_command(label="Export to PDF (Ctrl + E)", command=self.action_export_pdf)
        filemenu.add_command(label="Export to BWW (Ctrl + Alt + E)", command=self.action_export_bww)
        filemenu.add_command(label="Export to PIPE (Ctrl + Shift + E)", command=self.action_export_pipe)
        filemenu.add_separator()
        filemenu.add_command(label="Print (Ctrl + P)", command=self.action_print_score)
        filemenu.add_command(label="Clear Score (Ctrl + F10)", command=self.action_clear_all_nodes)
        filemenu.add_separator()
        filemenu.add_command(label="Exit (Ctrl + F12)", command=self.root.quit)
        menubar.add_cascade(label="File", menu=filemenu)
        self.root.config(menu=menubar)
        
        self.root.bind("<Control-n>", lambda e: self.action_create_tune())
        self.root.bind("<Control-o>", lambda e: self.action_open_file_dialog())
        self.root.bind("<Control-s>", lambda e: self.action_save_changes())
        self.root.bind("<Control-e>", lambda e: self.action_export_pdf())
        self.root.bind("<Control-Alt-e>", lambda e: self.action_export_bww())
        self.root.bind("<Control-Shift-E>", lambda e: self.action_export_pipe())
        self.root.bind("<Control-p>", lambda e: self.action_print_score())
        self.root.bind("<Control-F10>", lambda e: self.action_clear_all_nodes())
        self.root.bind("<Control-F12>", lambda e: self.root.quit())

    def apply_app_theme(self):
        name = self.settings.get("theme", "dark")
        self.theme = THEMES.get(name, THEMES["dark"])
        self.accent = self.settings.get("accent_color", "#f59e0b")
        try:
            self.root.configure(bg=self.theme["bg"])
            fam = self.settings.get("app_font", "Segoe UI")
            sz = int(self.settings.get("app_font_size", 10))
            self.root.option_add("*Font", (fam, sz))
        except Exception:
            pass

    def load_assets(self):
        # clef.png now lives under Assets/bar
        asset_path = self._asset_path("bar", "clef.png")
        if os.path.exists(asset_path):
            try:
                img = Image.open(asset_path).convert("RGBA")
                bbox = img.getbbox()
                self.clef_image = img.crop(bbox) if bbox else img
            except Exception:
                pass

    def show_activation_screen(self):
        bg = self.theme["bg"]
        self.activation_frame = tk.Frame(self.root, bg=bg)
        self.activation_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(self.activation_frame, text="Taorluath", fg=self.accent, bg=bg,
                 font=("Arial", 26, "bold")).pack(pady=(64, 10))
        tk.Label(self.activation_frame, text="Enter your email and activation key to continue.",
                 fg=self.theme["fg"], bg=bg, font=("Arial", 13)).pack(pady=4)
        tk.Label(self.activation_frame, text="Both must match the email used to purchase.",
                 fg=self.theme["muted"], bg=bg, font=("Arial", 9)).pack(pady=(0, 16))

        tk.Label(self.activation_frame, text="Email", fg=self.theme["muted"], bg=bg,
                 font=("Arial", 9)).pack()
        self._email_var = tk.StringVar()
        email_entry = tk.Entry(self.activation_frame, textvariable=self._email_var, width=28,
                               font=("Consolas", 13), justify="center")
        email_entry.pack(pady=(2, 10))
        email_entry.focus_set()

        tk.Label(self.activation_frame, text="Activation key  (PF-XXXX-XXXX-XXXX)",
                 fg=self.theme["muted"], bg=bg, font=("Arial", 9)).pack()
        self._key_var = tk.StringVar()
        entry = tk.Entry(self.activation_frame, textvariable=self._key_var, width=24,
                         font=("Consolas", 15), justify="center")
        entry.pack(pady=(2, 6))
        entry.bind("<Return>", lambda e: self._do_activate())
        email_entry.bind("<Return>", lambda e: entry.focus_set())

        self._activate_btn = tk.Button(self.activation_frame, text="Activate",
                                       bg="#16a34a", fg="white", font=("Arial", 11, "bold"),
                                       width=16, height=1, command=self._do_activate)
        self._activate_btn.pack(pady=14)
        self._activation_status = tk.Label(self.activation_frame, text="", fg=self.accent, bg=bg,
                                           font=("Arial", 10))
        self._activation_status.pack(pady=6)
        tk.Label(self.activation_frame,
                 text="Don't have a key? Purchase one to unlock Taorluath.",
                 fg=self.theme["muted"], bg=bg, font=("Arial", 9)).pack(pady=(24, 0))

    def _do_activate(self):
        key = self._key_var.get()
        email = self._email_var.get()
        if not email or "@" not in email:
            self._activation_status.config(text="Enter the email you used to purchase.")
            return
        if not licensing.valid_key_format(key):
            self._activation_status.config(text="Keys look like  PF-XXXX-XXXX-XXXX.")
            return
        self._activate_btn.config(state=tk.DISABLED)
        self._activation_status.config(text="Verifying...")

        def worker():
            ok, msg, tier = licensing.activate(key, email)
            self.root.after(0, lambda: self._activation_done(ok, msg, tier))

        threading.Thread(target=worker, daemon=True).start()

    def _activation_done(self, ok, msg, tier):
        self._activation_status.config(text=msg)
        if ok:
            self.license_tier = tier
            self.setup_system_menu_bar()   # menu appears now that we're activated
            self.show_home_screen()
        else:
            self._activate_btn.config(state=tk.NORMAL)

    def show_home_screen(self):
        if self.activation_frame:
            self.activation_frame.pack_forget()
            self.activation_frame.destroy()
            self.activation_frame = None
        if self.editor_frame:
            self.editor_frame.pack_forget()
            self.editor_frame.destroy()
            self.editor_frame = None
        if self.home_frame:                 # avoid stacking a second dashboard
            self.home_frame.pack_forget()
            self.home_frame.destroy()
            self.home_frame = None

        bg = self.theme["bg"]
        self.home_frame = tk.Frame(self.root, bg=bg)
        self.home_frame.pack(fill=tk.BOTH, expand=True)

        # Settings button (gear) in the top-right.
        topbar = tk.Frame(self.home_frame, bg=bg)
        topbar.pack(fill=tk.X, side=tk.TOP)
        self._settings_icon = None
        try:
            ip = self._asset_path("menu", "settings.png")
            if os.path.exists(ip):
                self._settings_icon = ImageTk.PhotoImage(
                    Image.open(ip).convert("RGBA").resize((26, 26), Image.Resampling.LANCZOS))
        except Exception:
            self._settings_icon = None
        if self._settings_icon is not None:
            tk.Button(topbar, image=self._settings_icon, bg=self.theme["panel"], bd=0,
                      activebackground=self.theme["sub"], command=self.open_settings_dialog).pack(side=tk.RIGHT, padx=12, pady=10)
        else:
            tk.Button(topbar, text="⚙ Settings", bg=self.theme["panel"], fg=self.theme["fg"],
                      command=self.open_settings_dialog).pack(side=tk.RIGHT, padx=12, pady=10)

        lbl_title = tk.Label(self.home_frame, text="Taorluath Workspace", fg=self.accent, bg=bg, font=("Arial", 24, "bold"))
        lbl_title.pack(pady=(10, 30))

        btn_frame = tk.Frame(self.home_frame, bg=bg)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="New Score Layout", bg="#16a34a", fg="white", font=("Arial", 11, "bold"), width=18, height=2, command=self.action_create_tune).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Open Existing Score", bg="#2563eb", fg="white", font=("Arial", 11, "bold"), width=18, height=2, command=self.action_open_file_dialog).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Import BWW", bg="#3f3f46", fg="white", font=("Arial", 11, "bold"), width=18, height=2, command=self.action_import_bww).pack(side=tk.LEFT, padx=10)

        # Drum-score button sits on its own along the very bottom.
        tk.Button(self.home_frame, text="🥁 New Drum Score", bg="#7c3aed", fg="white",
                  font=("Arial", 10, "bold"), command=self.action_write_drums).pack(side=tk.BOTTOM, pady=10)

        self._build_my_scores(self.home_frame)

    def _build_my_scores(self, parent):
        """Dashboard 'My Scores' tab: the .pipe files saved in user_data/user_scores."""
        section = tk.Frame(parent, bg="#18181b")
        section.pack(pady=(24, 30), fill=tk.BOTH, expand=True)

        header = tk.Frame(section, bg="#18181b")
        header.pack()
        tk.Label(header, text="My Scores", fg="#f59e0b", bg="#18181b",
                 font=("Arial", 15, "bold")).pack(side=tk.LEFT, padx=6)
        tk.Button(header, text="↻ Refresh", bg="#3f3f46", fg="white", font=("Arial", 9),
                  command=self._refresh_my_scores).pack(side=tk.LEFT, padx=6)

        list_container = tk.Frame(section, bg="#27272a")
        list_container.pack(pady=8)
        self.scores_listbox = tk.Listbox(list_container, width=52, height=9, bg="#27272a",
                                         fg="#e4e4e7", selectbackground="#2563eb",
                                         highlightthickness=0, bd=0, font=("Consolas", 11),
                                         activestyle="none")
        self.scores_listbox.pack(side=tk.LEFT, fill=tk.BOTH)
        scrollbar = tk.Scrollbar(list_container, command=self.scores_listbox.yview)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)
        self.scores_listbox.config(yscrollcommand=scrollbar.set)
        self.scores_listbox.bind("<Double-Button-1>", lambda e: self.open_selected_score())

        tk.Button(section, text="Open Selected Score", bg="#16a34a", fg="white",
                  font=("Arial", 10, "bold"), command=self.open_selected_score).pack(pady=6)

        self._refresh_my_scores()

    def _refresh_my_scores(self):
        self.scores_listbox.delete(0, tk.END)
        self._score_files = []
        try:
            names = sorted(os.listdir(DATA_DIR))
        except OSError:
            names = []
        for fn in names:
            low = fn.lower()
            if low.endswith(".pipe"):
                self._score_files.append(os.path.join(DATA_DIR, fn))
                self.scores_listbox.insert(tk.END, "  " + fn[:-5])
            elif low.endswith(".drum"):
                self._score_files.append(os.path.join(DATA_DIR, fn))
                self.scores_listbox.insert(tk.END, "  🥁 " + fn[:-5])
        if not self._score_files:
            self.scores_listbox.insert(tk.END, "  (no saved scores yet)")

    def open_selected_score(self):
        sel = self.scores_listbox.curselection()
        if not sel or sel[0] >= len(self._score_files):
            return
        self.open_score_file(self._score_files[sel[0]])

    def open_score_file(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.score = BagpipeScore()
            self.score.load_from_pipe_format(content)
        except Exception as exc:
            messagebox.showerror("Open Failed", f"Could not open score:\n{exc}")
            return
        self.show_editor_screen()

    def action_open_file_dialog(self):
        path = filedialog.askopenfilename(initialdir=DATA_DIR,
                                          filetypes=[("Pipe / Drum scores", "*.pipe *.drum"),
                                                     ("Standard Pipe Files", "*.pipe"),
                                                     ("Drum Scores", "*.drum")])
        if not path: return
        self.open_score_file(path)

    # ----------------------------------------------------------------- settings
    def open_settings_dialog(self):
        s = self.settings
        win = tk.Toplevel(self.root)
        win.title("Global Settings")
        win.configure(bg=self.theme["panel"])
        win.grab_set()
        win.resizable(False, False)

        vars_ = {}
        row = [0]

        def add_row(label, widget):
            tk.Label(win, text=label, bg=self.theme["panel"], fg=self.theme["fg"],
                     anchor="w", width=22).grid(row=row[0], column=0, sticky="w", padx=10, pady=4)
            widget.grid(row=row[0], column=1, sticky="w", padx=10, pady=4)
            row[0] += 1

        def opt(key, choices):
            v = tk.StringVar(value=str(s.get(key)))
            vars_[key] = v
            return tk.OptionMenu(win, v, *choices)

        def entry(key, width=14):
            v = tk.StringVar(value=str(s.get(key)))
            vars_[key] = v
            return tk.Entry(win, textvariable=v, width=width)

        def chk(key):
            v = tk.BooleanVar(value=bool(s.get(key)))
            vars_[key] = v
            return tk.Checkbutton(win, variable=v, bg=self.theme["panel"], activebackground=self.theme["panel"])

        def color_row(key, default):
            from tkinter import colorchooser
            v = tk.StringVar(value=str(s.get(key, default)))
            vars_[key] = v
            frame = tk.Frame(win, bg=self.theme["panel"])
            ent = tk.Entry(frame, textvariable=v, width=10)
            ent.pack(side=tk.LEFT)

            def pick():
                c = colorchooser.askcolor(color=(v.get() or default), parent=win)
                if c and c[1]:
                    v.set(c[1])
                    swatch.config(bg=c[1])
            swatch = tk.Button(frame, bg=(v.get() or default), width=4, command=pick)
            swatch.pack(side=tk.LEFT, padx=6)
            return frame

        tk.Label(win, text="Application", bg=self.theme["panel"], fg=self.accent,
                 font=("Arial", 11, "bold")).grid(row=row[0], column=0, sticky="w", padx=10, pady=(10, 2)); row[0] += 1
        add_row("Theme", opt("theme", ["dark", "light"]))
        add_row("App font", opt("app_font", ["Segoe UI", "Arial", "Calibri", "Verdana", "Tahoma", "Consolas"]))
        add_row("App font size", entry("app_font_size", 6))
        add_row("Accent colour (hex)", entry("accent_color", 10))
        add_row("Highlight colour", color_row("highlight_color", "#2563eb"))

        tk.Label(win, text="Playback", bg=self.theme["panel"], fg=self.accent,
                 font=("Arial", 11, "bold")).grid(row=row[0], column=0, sticky="w", padx=10, pady=(10, 2)); row[0] += 1
        vol = tk.IntVar(value=int(s.get("volume", 200))); vars_["volume"] = vol
        add_row("Volume (%)", tk.Scale(win, from_=0, to=300, orient=tk.HORIZONTAL, variable=vol,
                                       length=200, bg=self.theme["panel"], highlightthickness=0))
        add_row("Audio start (seconds)", entry("audio_start_sec", 6))
        add_row("Default instrument", opt("default_instrument", ["GHB", "chanter"]))

        tk.Label(win, text="New tune defaults", bg=self.theme["panel"], fg=self.accent,
                 font=("Arial", 11, "bold")).grid(row=row[0], column=0, sticky="w", padx=10, pady=(10, 2)); row[0] += 1
        add_row("Default tempo (BPM)", entry("default_tempo", 6))
        add_row("Default time signature", opt("default_time_signature", TIME_SIGNATURE_OPTIONS))
        add_row("Default tune type", entry("default_tune_type"))
        add_row("Default composer", entry("default_composer"))

        tk.Label(win, text="Page", bg=self.theme["panel"], fg=self.accent,
                 font=("Arial", 11, "bold")).grid(row=row[0], column=0, sticky="w", padx=10, pady=(10, 2)); row[0] += 1
        add_row("Show page border", chk("show_page_border"))
        add_row("Show page number", chk("show_page_number"))
        add_row("Confirm before clearing", chk("confirm_clear"))

        def do_save():
            for key, var in vars_.items():
                val = var.get()
                default = DEFAULT_SETTINGS.get(key)
                if isinstance(default, bool):
                    s[key] = bool(val)
                elif isinstance(default, int):
                    try: s[key] = int(float(val))
                    except Exception: pass
                elif isinstance(default, float):
                    try: s[key] = float(val)
                    except Exception: pass
                else:
                    s[key] = val
            s["default_tempo"] = max(MIN_BPM, min(MAX_BPM, int(s.get("default_tempo", 90))))
            save_settings(s)
            self.selected_instrument = s.get("default_instrument", self.selected_instrument)
            self._wav_cache.clear()       # volume / start changed -> re-process samples
            self._font_cache.clear()
            self.apply_app_theme()
            win.destroy()
            if self.home_frame:           # refresh dashboard with the new theme
                self.show_home_screen()

        btns = tk.Frame(win, bg=self.theme["panel"])
        btns.grid(row=row[0], column=0, columnspan=2, pady=12)
        tk.Button(btns, text="Save", bg="#16a34a", fg="white", width=10, command=do_save).pack(side=tk.LEFT, padx=6)
        tk.Button(btns, text="Cancel", bg="#3f3f46", fg="white", width=10, command=win.destroy).pack(side=tk.LEFT, padx=6)

    def action_create_tune(self):
        defaults = {
            "composer": self.settings.get("default_composer", "Unknown"),
            "type": self.settings.get("default_tune_type", "March"),
            "time_sig": self.settings.get("default_time_signature", "4/4"),
        }
        dialog = UnifiedSetupDialog(self.root, defaults=defaults)
        if not dialog.result: return
        self.score = BagpipeScore(
            title=dialog.result["name"],
            composer=dialog.result["composer"],
            tune_type=dialog.result["type"],
            time_signature=dialog.result["time_sig"],
            tempo=int(self.settings.get("default_tempo", 120)),
        )
        self.show_editor_screen()

    def action_save_changes(self):
        ext = ".drum" if getattr(self.score, "mode", "pipe") == "drum" else ".pipe"
        safe_filename = self._safe_title() + ext
        out_path = os.path.join(DATA_DIR, safe_filename)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(self.score.to_pipe_format())
        messagebox.showinfo("Saved", f"Changes committed to user directory:\n{safe_filename}")

    def _safe_title(self):
        return "".join(c for c in self.score.title if c.isalnum() or c in (' ', '_', '-')).rstrip() or "Untitled"

    def _render_page_rgb(self):
        """Full-resolution flattened RGB page image for export/print."""
        page = self._build_page_buffer()
        return page.convert("RGB")

    def action_export_pdf(self):
        if not getattr(self, "canvas", None):
            messagebox.showinfo("Export to PDF", "Open a score first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                            initialfile=self._safe_title() + ".pdf",
                                            filetypes=[("PDF Document", "*.pdf")])
        if not path:
            return
        try:
            self._render_page_rgb().save(path, "PDF", resolution=150.0)
            messagebox.showinfo("Export to PDF", f"Saved:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export to PDF", f"Could not save PDF:\n{exc}")

    def action_print_score(self):
        if not getattr(self, "canvas", None):
            messagebox.showinfo("Print", "Open a score first.")
            return
        try:
            import tempfile
            tmp = os.path.join(tempfile.gettempdir(), self._safe_title() + "_print.pdf")
            self._render_page_rgb().save(tmp, "PDF", resolution=150.0)
            try:
                os.startfile(tmp, "print")   # hand to the default print handler (Windows)
            except Exception:
                os.startfile(tmp)            # fall back to opening it so the user can print
            messagebox.showinfo("Print", "Sent the score to your printer dialog.")
        except Exception as exc:
            messagebox.showerror("Print", f"Could not print:\n{exc}")

    def action_export_bww(self):
        path = filedialog.asksaveasfilename(defaultextension=".bww",
                                            initialfile=self._safe_title() + ".bww",
                                            filetypes=[("Bagpipe Music Writer", "*.bww")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(bww.score_to_bww(self.score))
            messagebox.showinfo("Export to BWW", f"Saved:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export to BWW", f"Could not write BWW:\n{exc}")

    def action_import_bww(self):
        path = filedialog.askopenfilename(filetypes=[("Bagpipe Music Writer", "*.bww")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                self.score = bww.bww_to_score(f.read())
        except Exception as exc:
            messagebox.showerror("Import BWW", f"Could not read BWW:\n{exc}")
            return
        self.show_editor_screen()

    def action_export_pipe(self): self.action_save_changes()

    def action_clear_all_nodes(self):
        if self.settings.get("confirm_clear", True) and not messagebox.askyesno("Clear", "Completely wipe score timeline nodes?"):
            return
        self.score.nodes = []
        self.selected_node_id = None
        self.redraw_canvas_score()

    def show_editor_screen(self):
        if self.home_frame:
            self.home_frame.pack_forget()
            self.home_frame.destroy()
            self.home_frame = None
        if self.editor_frame:               # tear down a prior editor (e.g. on re-import)
            self.editor_frame.pack_forget()
            self.editor_frame.destroy()
            self.editor_frame = None

        self.editor_frame = tk.Frame(self.root, bg=self.theme["bg"])
        self.editor_frame.pack(fill=tk.BOTH, expand=True)

        self.ribbon_tabs_container = tk.Frame(self.editor_frame, bg="#27272a", height=38)
        self.ribbon_tabs_container.pack(fill=tk.X, side=tk.TOP)

        self.ribbon_subpanel = tk.Frame(self.editor_frame, bg="#202023", height=45)
        self.ribbon_subpanel.pack(fill=tk.X, side=tk.TOP)

        tk.Button(self.ribbon_tabs_container, text="← Menu", bg="#4b5563", fg="white", font=("Arial", 9, "bold"), command=self.return_to_dashboard).pack(side=tk.LEFT, padx=6, pady=4)

        # Zoom controls (always visible).
        tk.Button(self.ribbon_tabs_container, text="Fit", bg="#3f3f46", fg="white", font=("Arial", 9, "bold"), command=self.zoom_fit).pack(side=tk.RIGHT, padx=(2, 8), pady=4)
        tk.Button(self.ribbon_tabs_container, text="🔍+", bg="#3f3f46", fg="white", font=("Arial", 9, "bold"), command=self.zoom_in).pack(side=tk.RIGHT, padx=2, pady=4)
        tk.Button(self.ribbon_tabs_container, text="🔍−", bg="#3f3f46", fg="white", font=("Arial", 9, "bold"), command=self.zoom_out).pack(side=tk.RIGHT, padx=2, pady=4)

        self.setup_ribbon_tab_buttons()
        self.activate_ribbon_tab("File")

        self.zoom = None
        self._user_zoom = False

        canvas_wrap = tk.Frame(self.editor_frame, bg=self.theme["canvas"])
        canvas_wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)
        self.canvas = tk.Canvas(canvas_wrap, bg=self.theme["canvas"], highlightthickness=0)
        vbar = tk.Scrollbar(canvas_wrap, orient=tk.VERTICAL, command=self.canvas.yview)
        hbar = tk.Scrollbar(canvas_wrap, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.config(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>", self.handle_canvas_click)
        self.canvas.bind("<Double-Button-1>", self.handle_canvas_double_click)
        self.canvas.bind("<B1-Motion>", self.handle_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.handle_canvas_release)
        self.canvas.bind("<Motion>", self.handle_canvas_motion)
        self.canvas.bind("<Leave>", self.handle_canvas_leave)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)

        # Mode-switch button along the very bottom.
        bottombar = tk.Frame(self.editor_frame, bg="#18181b")
        bottombar.pack(fill=tk.X, side=tk.BOTTOM)
        if self._is_drum():
            switch_text, switch_cmd = "🎼 Write to pipes instead", self.action_create_tune
        else:
            switch_text, switch_cmd = "🥁 Write to drums instead", self.action_write_drums
        tk.Button(bottombar, text=switch_text, bg="#7c3aed", fg="white", bd=0,
                  font=("Arial", 9, "bold"), activebackground="#6d28d9",
                  command=switch_cmd).pack(side=tk.RIGHT, padx=8, pady=3)

        self.status_label = tk.Label(self.editor_frame, text="", bg="#18181b", fg="#f87171", font=("Arial", 10, "italic"))
        self.status_label.pack(fill=tk.X, side=tk.BOTTOM, pady=2)

        self.root.bind("<Delete>", lambda e: self.action_delete_selected())
        self.root.bind("<BackSpace>", lambda e: self.action_delete_selected())
        self.root.bind("<Control-plus>", lambda e: self.zoom_in())
        self.root.bind("<Control-equal>", lambda e: self.zoom_in())
        self.root.bind("<Control-minus>", lambda e: self.zoom_out())

        self.recalculate_note_horizontal_positions()
        self.root.after(60, self.redraw_canvas_score)

    def _on_canvas_configure(self, event):
        if not self._user_zoom and event.width > 50:
            self.zoom = max(0.15, min(1.5, (event.width - 24) / PAGE_W))
        self.redraw_canvas_score()

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_ctrl_wheel(self, event):
        self._apply_zoom((self.zoom or 0.5) * (1.1 if event.delta > 0 else 0.9))
        return "break"

    def _apply_zoom(self, z, user=True):
        self.zoom = max(0.15, min(2.0, z))
        self._user_zoom = user
        self.redraw_canvas_score()

    def zoom_in(self):
        self._apply_zoom((self.zoom or 0.5) * 1.2)

    def zoom_out(self):
        self._apply_zoom((self.zoom or 0.5) / 1.2)

    def zoom_fit(self):
        cw = max(self.canvas.winfo_width(), 200)
        self._apply_zoom(max(0.15, min(1.5, (cw - 24) / PAGE_W)), user=False)

    def return_to_dashboard(self):
        self.audio_stop_stream()
        if self.editor_frame:
            self.editor_frame.pack_forget()
            self.editor_frame.destroy()
        self.show_home_screen()

    def _is_drum(self):
        return getattr(self.score, "mode", "pipe") == "drum"

    def setup_ribbon_tab_buttons(self):
        # In drum mode the Embellishments tab is replaced by a Rests tab.
        second = "Rests" if self._is_drum() else "Embellishments"
        tabs = ["File", "Notes", second, "Stave", "Bar", "Playback", "Settings"]
        self.ribbon_buttons = {}
        for tab in tabs:
            btn = tk.Button(self.ribbon_tabs_container, text=tab, bg="#27272a", fg="#d4d4d8", relief=tk.FLAT,
                            activebackground="#202023", activeforeground="white", font=("Arial", 10, "bold"),
                            command=lambda t=tab: self.activate_ribbon_tab(t))
            btn.pack(side=tk.LEFT, padx=1, pady=(4, 0))
            self.ribbon_buttons[tab] = btn

    def activate_ribbon_tab(self, tab_name):
        # The bar selection persists across the Bar and Playback tabs; switching
        # to any other tab clears it.
        if tab_name not in ("Bar", "Playback") and self.selected_bar is not None:
            self.selected_bar = None
            if getattr(self, "canvas", None):
                self.render_canvas_interactive_overlay()
        self.active_tab = tab_name
        for name, btn in self.ribbon_buttons.items():
            if name == tab_name:
                btn.configure(bg="#202023", fg="#f59e0b")
            else:
                btn.configure(bg="#27272a", fg="#d4d4d8")

        for w in self.ribbon_subpanel.winfo_children():
            w.destroy()

        if tab_name == "File":
            tk.Button(self.ribbon_subpanel, text="New File", bg="#3f3f46", fg="white", command=self.action_create_tune).pack(side=tk.LEFT, padx=4, pady=5)
            tk.Button(self.ribbon_subpanel, text="Open File", bg="#3f3f46", fg="white", command=self.action_open_file_dialog).pack(side=tk.LEFT, padx=4, pady=5)
            tk.Button(self.ribbon_subpanel, text="Save Changes", bg="#16a34a", fg="white", command=self.action_save_changes).pack(side=tk.LEFT, padx=4, pady=5)
            tk.Button(self.ribbon_subpanel, text="Export to PDF", bg="#3f3f46", fg="white", command=self.action_export_pdf).pack(side=tk.LEFT, padx=4, pady=5)
            tk.Button(self.ribbon_subpanel, text="Export to BWW", bg="#3f3f46", fg="white", command=self.action_export_bww).pack(side=tk.LEFT, padx=4, pady=5)
            tk.Button(self.ribbon_subpanel, text="Export to PIPE", bg="#3f3f46", fg="white", command=self.action_export_pipe).pack(side=tk.LEFT, padx=4, pady=5)
            tk.Button(self.ribbon_subpanel, text="Print Score", bg="#3f3f46", fg="white", command=self.action_print_score).pack(side=tk.LEFT, padx=4, pady=5)
            tk.Button(self.ribbon_subpanel, text="Clear Score", bg="#dc2626", fg="white", command=self.action_clear_all_nodes).pack(side=tk.LEFT, padx=4, pady=5)
            tk.Button(self.ribbon_subpanel, text="Exit", bg="#7f1d1d", fg="white", command=self.root.quit).pack(side=tk.LEFT, padx=4, pady=5)

        elif tab_name == "Notes":
            notes = ["Whole", "Half", "Quarter", "Quaver", "Semiquaver", "Demisemiquaver", "Hemidemisemiquaver"]
            for n in notes:
                lbl = f"{n} Note" if "Note" not in n else n
                b_color = "#2563eb" if (self.selected_duration == n and self.selected_embellishment is None
                                        and not self.drum_rimshot and not self.placing_rest) else "#3f3f46"
                tk.Button(self.ribbon_subpanel, text=lbl, bg=b_color, fg="white",
                          command=lambda target=n: self.set_active_note_type(target)).pack(side=tk.LEFT, padx=3, pady=5)
            tk.Button(self.ribbon_subpanel, text="Dot Selected Note", bg="#3f3f46", fg="white",
                      command=self.action_dot_selected).pack(side=tk.LEFT, padx=(12, 3), pady=5)
            if self._is_drum():
                col = "#7c3aed" if self.drum_rimshot else "#3f3f46"
                tk.Button(self.ribbon_subpanel, text="Rimshot", bg=col, fg="white",
                          command=self.toggle_rimshot).pack(side=tk.LEFT, padx=3, pady=5)
                tk.Frame(self.ribbon_subpanel, width=12, bg="#202023").pack(side=tk.LEFT)
                tk.Label(self.ribbon_subpanel, text="Drum:", fg="white", bg="#202023").pack(side=tk.LEFT, padx=(4, 2))
                dv = tk.StringVar(value=self.score.drum_voice)
                m = tk.OptionMenu(self.ribbon_subpanel, dv, "Snare", "Tenor", "Bass",
                                  command=self.set_drum_voice)
                m.config(bg="#3f3f46", fg="white", highlightthickness=0)
                m.pack(side=tk.LEFT, padx=2, pady=5)
            else:
                tk.Button(self.ribbon_subpanel, text="Tie Selected Note", bg="#3f3f46", fg="white",
                          command=self.action_tie_selected).pack(side=tk.LEFT, padx=3, pady=5)

        elif tab_name == "Rests":
            tk.Label(self.ribbon_subpanel, text="Rest:", fg="white", bg="#202023").pack(side=tk.LEFT, padx=(8, 4))
            for n in ["Whole", "Half", "Quarter", "Quaver", "Semiquaver", "Demisemiquaver"]:
                active = (self.placing_rest and self.selected_duration == n)
                col = "#2563eb" if active else "#3f3f46"
                tk.Button(self.ribbon_subpanel, text=n, bg=col, fg="white",
                          command=lambda target=n: self.set_active_rest(target)).pack(side=tk.LEFT, padx=3, pady=5)

        elif tab_name == "Embellishments":
            graces = [("Gracenote", None), ("Doubling", "doubling"), ("D Throw", "d_throw"),
                      ("Heavy D Throw", "heavy_d_throw"), ("Birl", "birl"), ("High G Birl", "high_g_birl"),
                      ("Double-Strike", "double_strike"), ("Leamluath", "leamluath"), ("Taorluath", "taorluath")]
            for name, emb_type in graces:
                is_active = (self.selected_duration == "Gracenote" and self.selected_embellishment == emb_type)
                b_color = "#7c3aed" if is_active else "#3f3f46"
                tk.Button(self.ribbon_subpanel, text=name, bg=b_color, fg="white",
                          command=lambda n=name, e=emb_type: self.set_active_gracenote_embellishment(e)).pack(side=tk.LEFT, padx=3, pady=5)

        elif tab_name == "Stave":
            tk.Label(self.ribbon_subpanel, text=f"{self.score.num_staves} stave(s)",
                     fg="#f59e0b", bg="#202023", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(8, 10))
            cur_staff = self.selected_bar[0] if self.selected_bar else 1
            tk.Label(self.ribbon_subpanel, text="Stave:", fg="white", bg="#202023").pack(side=tk.LEFT, padx=(2, 2))
            self._stave_target = tk.IntVar(value=cur_staff)
            som = tk.OptionMenu(self.ribbon_subpanel, self._stave_target, *self.score.staff_list())
            som.config(bg="#3f3f46", fg="white", highlightthickness=0, width=2)
            som.pack(side=tk.LEFT, padx=2, pady=5)
            tk.Button(self.ribbon_subpanel, text="Add Stave Before", bg="#3f3f46", fg="white",
                      command=lambda: self.action_add_stave("before")).pack(side=tk.LEFT, padx=2, pady=5)
            tk.Button(self.ribbon_subpanel, text="Add Stave After", bg="#3f3f46", fg="white",
                      command=lambda: self.action_add_stave("after")).pack(side=tk.LEFT, padx=2, pady=5)
            tk.Frame(self.ribbon_subpanel, width=14, bg="#202023").pack(side=tk.LEFT)
            tk.Label(self.ribbon_subpanel, text="Stave Time Signature:", fg="white", bg="#202023").pack(side=tk.LEFT, padx=(4, 2))
            ts_var = tk.StringVar(value=self.score.time_sig_for(cur_staff))
            tsom = tk.OptionMenu(self.ribbon_subpanel, ts_var, *TIME_SIGNATURE_OPTIONS,
                                 command=lambda v: self.set_stave_time_sig(self._stave_target.get(), v))
            tsom.config(bg="#3f3f46", fg="white", highlightthickness=0)
            tsom.pack(side=tk.LEFT, padx=2, pady=5)

        elif tab_name == "Bar":
            if self.selected_bar is None:
                tk.Label(self.ribbon_subpanel, text="Click a bar on the stave to select it.",
                         fg="#d4d4d8", bg="#202023").pack(side=tk.LEFT, padx=8, pady=8)
            else:
                staff, b = self.selected_bar
                tk.Label(self.ribbon_subpanel, text=f"Staff {staff}, Bar {b + 1}",
                         fg="#f59e0b", bg="#202023", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(8, 8))
                tk.Button(self.ribbon_subpanel, text="Add Bar Before", bg="#3f3f46", fg="white",
                          command=lambda: self.action_add_bar("before")).pack(side=tk.LEFT, padx=2, pady=5)
                tk.Button(self.ribbon_subpanel, text="Add Bar After", bg="#3f3f46", fg="white",
                          command=lambda: self.action_add_bar("after")).pack(side=tk.LEFT, padx=2, pady=5)
                tk.Frame(self.ribbon_subpanel, width=10, bg="#202023").pack(side=tk.LEFT)
                cur = self.score.bar_styles[staff][b]
                tk.Label(self.ribbon_subpanel, text="Start:", fg="white", bg="#202023").pack(side=tk.LEFT, padx=(4, 2))
                for s in BAR_START_STYLES:
                    col = "#2563eb" if cur.get("start") == s else "#3f3f46"
                    tk.Button(self.ribbon_subpanel, text=s, bg=col, fg="white",
                              command=lambda v=s: self.set_bar_style("start", v)).pack(side=tk.LEFT, padx=2, pady=5)
                tk.Label(self.ribbon_subpanel, text="End:", fg="white", bg="#202023").pack(side=tk.LEFT, padx=(6, 2))
                for s in BAR_END_STYLES:
                    col = "#2563eb" if cur.get("end") == s else "#3f3f46"
                    tk.Button(self.ribbon_subpanel, text=s, bg=col, fg="white",
                              command=lambda v=s: self.set_bar_style("end", v)).pack(side=tk.LEFT, padx=2, pady=5)
                tk.Label(self.ribbon_subpanel, text="Timing:", fg="white", bg="#202023").pack(side=tk.LEFT, padx=(6, 2))
                for label, val in (("None", "None"), ("1st", "1"), ("2nd", "2")):
                    col = "#2563eb" if cur.get("timing", "None") == val else "#3f3f46"
                    tk.Button(self.ribbon_subpanel, text=label, bg=col, fg="white",
                              command=lambda v=val: self.set_bar_timing(v)).pack(side=tk.LEFT, padx=2, pady=5)

        elif tab_name == "Playback":
            if self._is_drum():
                tk.Label(self.ribbon_subpanel, text="Drum:", fg="white", bg="#202023").pack(side=tk.LEFT, padx=(6, 2))
                for voice in ("Bass", "Tenor", "Snare"):
                    active = (self.score.drum_voice == voice)
                    tk.Button(self.ribbon_subpanel, text=voice, bg=("#2563eb" if active else "#3f3f46"),
                              fg="white", command=lambda v=voice: self.pick_drum_voice(v)).pack(side=tk.LEFT, padx=2, pady=5)
            else:
                tk.Label(self.ribbon_subpanel, text="Instrument:", fg="white", bg="#202023").pack(side=tk.LEFT, padx=(6, 2))
                for label, key in (("Bagpipe", "GHB"), ("Practice Chanter", "chanter")):
                    active = (self.selected_instrument == key)
                    tk.Button(self.ribbon_subpanel, text=label, bg=("#2563eb" if active else "#3f3f46"),
                              fg="white", command=lambda k=key: self.set_instrument(k)).pack(side=tk.LEFT, padx=2, pady=5)
            tk.Frame(self.ribbon_subpanel, width=14, bg="#202023").pack(side=tk.LEFT)
            tk.Button(self.ribbon_subpanel, text="▶ Play Entire Score", bg="#16a34a", fg="white", command=self.audio_play_stream).pack(side=tk.LEFT, padx=4, pady=5)
            tk.Button(self.ribbon_subpanel, text="Play from Selected Note", bg="#3f3f46", fg="white", command=lambda: self.audio_play_stream(mode="note")).pack(side=tk.LEFT, padx=4, pady=5)
            tk.Button(self.ribbon_subpanel, text="Play from Selected Bar", bg="#3f3f46", fg="white", command=lambda: self.audio_play_stream(mode="bar")).pack(side=tk.LEFT, padx=4, pady=5)
            tk.Button(self.ribbon_subpanel, text="⬛ Stop", bg="#dc2626", fg="white", command=self.audio_stop_stream).pack(side=tk.LEFT, padx=4, pady=5)

        elif tab_name == "Settings":
            tk.Button(self.ribbon_subpanel, text="Tune Name", bg="#3f3f46", fg="white", command=self.cfg_tune_name).pack(side=tk.LEFT, padx=2, pady=5)
            tk.Button(self.ribbon_subpanel, text="Composer", bg="#3f3f46", fg="white", command=self.cfg_composer).pack(side=tk.LEFT, padx=2, pady=5)
            tk.Button(self.ribbon_subpanel, text="Tune Type", bg="#3f3f46", fg="white", command=self.cfg_tune_type).pack(side=tk.LEFT, padx=2, pady=5)
            tk.Button(self.ribbon_subpanel, text="Time Signature", bg="#3f3f46", fg="white", command=self.cfg_time_sig).pack(side=tk.LEFT, padx=2, pady=5)
            tk.Button(self.ribbon_subpanel, text="BPM", bg="#3f3f46", fg="white", command=self.cfg_bpm).pack(side=tk.LEFT, padx=2, pady=5)
            tk.Button(self.ribbon_subpanel, text="Gap Staves", bg="#3f3f46", fg="white", command=self.cfg_gap_staves).pack(side=tk.LEFT, padx=2, pady=5)
            tk.Button(self.ribbon_subpanel, text="Gap Gracenote", bg="#3f3f46", fg="white", command=self.cfg_gap_grace).pack(side=tk.LEFT, padx=2, pady=5)
            
            tk.Label(self.ribbon_subpanel, text="Font:", fg="white", bg="#202023").pack(side=tk.LEFT, padx=(10, 2))
            font_var = tk.StringVar(value=self.score.selected_font)
            f_menu = tk.OptionMenu(self.ribbon_subpanel, font_var, "Serif", "Sans Serif", "Cambria", "Times New Roman", command=self.cfg_font)
            f_menu.config(bg="#3f3f46", fg="white", highlightthickness=0)
            f_menu.pack(side=tk.LEFT, padx=2)

    def set_active_note_type(self, dur):
        self.selected_duration = dur
        self.selected_embellishment = None
        self.placing_rest = False
        # If a note is selected, change it to the chosen duration as well.
        node = self._selected_normal_node()
        if node is not None:
            node["dur_type"] = dur.lower()
            node["duration"] = NOTE_DURATIONS[dur]["val"]
            self.selected_node_id = None   # deselect after applying
            self.recalculate_note_horizontal_positions()
            self.redraw_canvas_score()
        self.activate_ribbon_tab("Notes")

    def toggle_rimshot(self):
        self.drum_rimshot = not self.drum_rimshot
        self.placing_rest = False
        self.activate_ribbon_tab("Notes")

    def set_drum_voice(self, voice):
        self.score.drum_voice = voice

    def pick_drum_voice(self, voice):
        self.score.drum_voice = voice
        self.activate_ribbon_tab("Playback")   # refresh the active highlight

    def set_active_rest(self, dur):
        self.placing_rest = True
        self.selected_duration = dur
        self.selected_embellishment = None
        self.drum_rimshot = False
        self.activate_ribbon_tab("Rests")

    def action_write_drums(self):
        """Start a fresh drum score (Berger uniline)."""
        self.score = BagpipeScore(title="Untitled Drum Score",
                                  tempo=int(self.settings.get("default_tempo", 90)))
        self.score.mode = "drum"
        self.score.num_staves = 1          # single uniline stave
        self.placing_rest = False
        self.drum_rimshot = False
        self.show_editor_screen()

    def set_instrument(self, key):
        self.selected_instrument = key
        self.activate_ribbon_tab("Playback")

    def set_bar_style(self, side, value):
        if self.selected_bar is None:
            return
        staff, b = self.selected_bar
        self.score.bar_styles[staff][b][side] = value
        self.activate_ribbon_tab("Bar")   # refresh button highlights
        self.recalculate_note_horizontal_positions()  # first-bar start barline room
        self.redraw_canvas_score()

    def set_bar_timing(self, value):
        if self.selected_bar is None:
            return
        staff, b = self.selected_bar
        self.score.bar_styles[staff][b]["timing"] = value
        self.activate_ribbon_tab("Bar")
        self.redraw_canvas_score()

    def action_add_bar(self, where):
        if self.selected_bar is None:
            return
        staff, b = self.selected_bar
        at = b if where == "before" else b + 1
        self.score.add_bar(staff, at)
        self.selected_bar = (staff, at)        # select the newly added bar
        self.activate_ribbon_tab("Bar")
        self.recalculate_note_horizontal_positions()
        self.redraw_canvas_score()

    def action_add_stave(self, where):
        target = getattr(self, "_stave_target", None)
        target = target.get() if target is not None else 1
        at = target if where == "before" else target + 1
        self.score.insert_stave(at)
        self.selected_bar = None
        self.activate_ribbon_tab("Stave")
        self.recalculate_note_horizontal_positions()
        self.redraw_canvas_score()

    def set_stave_time_sig(self, staff, value):
        self.score.stave_time_sigs[staff] = value
        self.recalculate_note_horizontal_positions()
        self.redraw_canvas_score()

    def set_active_gracenote_embellishment(self, emb):
        self.selected_duration = "Gracenote"
        self.selected_embellishment = emb
        self.activate_ribbon_tab("Embellishments")

    def _selected_normal_node(self):
        if not self.selected_node_id:
            return None
        node = next((n for n in self.score.nodes if n["id"] == self.selected_node_id), None)
        if node is None or node["dur_type"] == "gracenote":
            return None
        return node

    def action_dot_selected(self):
        node = self._selected_normal_node()
        if node is None:
            self.status_label.config(text="⚠️ Select a note first to dot it.")
            return
        node["dotted"] = not node.get("dotted", False)
        self.recalculate_note_horizontal_positions()
        self.redraw_canvas_score()

    def action_sharp_selected(self):
        node = self._selected_normal_node()
        if node is None:
            self.status_label.config(text="⚠️ Select a note first to sharpen it.")
            return
        node["sharp"] = not node.get("sharp", False)
        self.redraw_canvas_score()

    def _prev_normal_same_staff(self, node):
        normals = [n for n in self.score.nodes if n["dur_type"] != "gracenote"]
        normals.sort(key=lambda n: (n.get("staff", 1), n.get("bar_index", 0), n.get("raw_x", 0)))
        i = next((k for k, n in enumerate(normals) if n is node), None)
        if i is None:
            return None
        for k in range(i - 1, -1, -1):
            if normals[k].get("staff", 1) == node.get("staff", 1):
                return normals[k]
        return None

    def action_tie_selected(self):
        node = self._selected_normal_node()
        if node is None:
            self.status_label.config(text="⚠️ Select a note first to tie it.")
            return
        if node.get("tied"):
            node["tied"] = False
            self.redraw_canvas_score()
            return
        prev = self._prev_normal_same_staff(node)
        if prev is None:
            self.status_label.config(text="⚠️ No preceding note on this staff to tie to.")
            return
        # A tie joins the same pitch: force the note being tied to (the one
        # before) to match the selected note.
        if prev["pitch"] != node["pitch"]:
            prev["pitch"] = node["pitch"]
            self.status_label.config(text=f"Tied note changed to {node['pitch']} to match.")
        node["tied"] = True  # this note is tied back to the note before it
        self.redraw_canvas_score()

    # --- SETTINGS INPUT HANDLERS ---
    def cfg_tune_name(self):
        val = simpledialog.askstring("Settings", "Change Tune Name:", initialvalue=self.score.title)
        if val is not None: self.score.title = val; self.redraw_canvas_score()
    def cfg_composer(self):
        val = simpledialog.askstring("Settings", "Change Composer:", initialvalue=self.score.composer)
        if val is not None: self.score.composer = val
    def cfg_tune_type(self):
        val = simpledialog.askstring("Settings", "Change Tune Type:", initialvalue=self.score.tune_type)
        if val is not None: self.score.tune_type = val

    def cfg_time_sig(self):
        popup = tk.Toplevel(self.root)
        popup.title("Select Time Signature")
        popup.geometry("300x120")
        popup.resizable(False, False)
        popup.grab_set()

        tk.Label(popup, text="Select Time Signature:", font=("Arial", 10)).pack(pady=10)
        
        selected_sig = tk.StringVar(value=self.score.time_signature)
        current_formatted = self.score.time_signature.strip().capitalize()
        if current_formatted in TIME_SIGNATURE_OPTIONS:
            selected_sig.set(current_formatted)
        elif self.score.time_signature.strip().lower() in ["c", "common"]:
            selected_sig.set("Common")
        elif self.score.time_signature.strip().lower() in ["cut", "c|"]:
            selected_sig.set("Cut")

        dropdown = tk.OptionMenu(popup, selected_sig, *TIME_SIGNATURE_OPTIONS)
        dropdown.pack(pady=5)

        def on_confirm():
            self.score.time_signature = selected_sig.get()
            popup.destroy()
            self.redraw_canvas_score()

        tk.Button(popup, text="OK", width=10, command=on_confirm).pack(pady=5)

    def cfg_bpm(self):
        val = simpledialog.askinteger("Settings", f"Beats per minute ({MIN_BPM}-{MAX_BPM}):",
                                      initialvalue=self.score.tempo, minvalue=MIN_BPM, maxvalue=MAX_BPM)
        if val is not None:
            self.score.tempo = max(MIN_BPM, min(MAX_BPM, val))
    def cfg_gap_staves(self):
        val = simpledialog.askinteger("Settings", "Gap between staves (pixels):", initialvalue=self.score.gap_between_staves)
        if val is not None: self.score.gap_between_staves = val; self.redraw_canvas_score()
    def cfg_gap_grace(self):
        val = simpledialog.askinteger("Settings", "Gap after gracenotes:", initialvalue=self.score.gap_after_gracenotes)
        if val is not None: self.score.gap_after_gracenotes = val; self.recalculate_note_horizontal_positions(); self.redraw_canvas_score()
    def cfg_font(self, font_choice):
        self.score.selected_font = font_choice
        self.redraw_canvas_score()

    def get_bar_boundaries(self, bar_idx, staff):
        lines = self.score.bar_lines[staff]
        start = CANVAS_LEFT if bar_idx == 0 else lines[bar_idx - 1]
        end = CANVAS_RIGHT if bar_idx >= len(lines) else lines[bar_idx]
        return start, end

    def get_bar_index_from_x(self, x, staff):
        if x < CANVAS_LEFT or x > CANVAS_RIGHT: return -1
        lines = self.score.bar_lines[staff]
        for i in range(len(lines)):
            if x < lines[i]: return i
        return len(lines)

    def _staff_base_y(self, staff):
        return STAF_1_Y + (staff - 1) * self.score.gap_between_staves

    def identify_closest_staff_and_pitch(self, y_pos):
        target_staff = min(self.score.staff_list(),
                           key=lambda s: abs(y_pos - self._staff_base_y(s)))
        base_y = self._staff_base_y(target_staff)
        if y_pos < (base_y - 22) or y_pos > (base_y + STAFF_H + 22):
            return None, None, None
        local_offset_y = y_pos - base_y
        closest_pitch = min(CHANTER_SCALE, key=lambda p: abs(local_offset_y - p["y_offset"]))
        return target_staff, base_y, closest_pitch

    def _to_logical(self, event):
        """Map a canvas widget event to logical page coordinates (zoom + scroll)."""
        z = self.zoom or 1.0
        lx = self.canvas.canvasx(event.x) / z
        ly = self.canvas.canvasy(event.y) / z
        return lx, ly

    def handle_canvas_motion(self, event):
        self.hover_x, self.hover_y = self._to_logical(event)
        self.render_canvas_interactive_overlay()

    def handle_canvas_leave(self, event):
        self.hover_x, self.hover_y = None, None
        self.render_canvas_interactive_overlay()

    def _next_seq(self):
        self._seq += 1
        return self._seq

    def recalculate_note_horizontal_positions(self):
        # Order notes left-to-right by their current x so a freshly placed note
        # lands wherever it was clicked (before, between, or after existing
        # notes) rather than always at the end of the bar.
        self.score.nodes.sort(key=lambda n: (n.get("staff", 1),
                                             n.get("bar_index", 0),
                                             n.get("raw_x", 0),
                                             n.get("seq", 0)))
        for staff_num in self.score.staff_list():
            for bar_idx in range(self.score.num_bars(staff_num)):
                start, end = self.get_bar_boundaries(bar_idx, staff_num)
                eff_start = (start + CLEF_SAFE_ZONE) if bar_idx == 0 else start
                # Leave room for a first-bar start barline (after the time sig).
                if bar_idx == 0 and self.score.bar_styles[staff_num][0].get("start", "Normal") != "Normal":
                    eff_start += 34
                eff_width = end - eff_start

                bar_normals = [n for n in self.score.nodes if n["staff"] == staff_num and n.get("bar_index") == bar_idx and n["dur_type"] != "gracenote"]
                num_notes = len(bar_normals)
                for idx, node in enumerate(bar_normals):
                    fraction = (idx + 0.5) / num_notes
                    node["raw_x"] = int(eff_start + (fraction * eff_width))
                
                bar_graces = [n for n in self.score.nodes if n["staff"] == staff_num and n.get("bar_index") == bar_idx and n["dur_type"] == "gracenote"]
                for grace in bar_graces:
                    target_id = grace.get("target_normal_id")
                    target_note = next((n for n in bar_normals if n["id"] == target_id), None)
                    if target_note:
                        siblings = [g for g in bar_graces if g.get("target_normal_id") == target_id]
                        siblings.sort(key=lambda g: g.get("seq", 0))  # keep placement order
                        s_idx = siblings.index(grace)
                        grace["raw_x"] = target_note["raw_x"] - self.score.gap_after_gracenotes - (10 * (len(siblings) - 1 - s_idx))
                    else:
                        grace["raw_x"] = eff_start + 15

    def handle_canvas_click(self, event):
        self.status_label.config(text="")
        x, y = self._to_logical(event)

        # Header double-click is handled separately; bar-line drag detection here.
        band_staff = None
        for s in self.score.staff_list():
            by = self._staff_base_y(s)
            if by - 12 <= y <= by + STAFF_H + 12:
                band_staff = s
                break
        if band_staff is not None:
            for i, lx in enumerate(self.score.bar_lines[band_staff]):
                if abs(x - lx) <= 10:
                    self.dragging_bar = (band_staff, i)
                    return

        if x < CANVAS_LEFT or x > CANVAS_RIGHT: return

        # Clicking a note selects it and jumps back to the Notes tab
        # (which also clears any bar selection).
        hit_margin = 15
        for node in self.score.nodes:
            if node.get("render_x") and node.get("render_y"):
                if abs(node["render_x"] - x) <= hit_margin and abs(node["render_y"] - y) <= hit_margin:
                    self.selected_node_id = node["id"]
                    if self.active_tab != "Notes":
                        self.activate_ribbon_tab("Notes")
                    self.redraw_canvas_score()
                    return

        # Bars can only be selected from the Bar tab.
        if self.active_tab == "Bar":
            if band_staff is not None:
                self.selected_bar = (band_staff, self.get_bar_index_from_x(x, band_staff))
                self.activate_ribbon_tab("Bar")          # refresh the Bar menu
                self.render_canvas_interactive_overlay()  # show the selection outline
            return

        # --- Drum mode: place a beat, a rimshot, or a rest on the uniline. ----
        if self._is_drum():
            if self.active_tab not in ("Notes", "Rests"):
                return
            staff_num = band_staff if band_staff is not None else 1
            clicked_bar_idx = self.get_bar_index_from_x(x, staff_num)
            if clicked_bar_idx < 0:
                return
            dur = self.selected_duration
            # Above or below the uniline, chosen by which side of the line you click.
            uni = self._staff_base_y(staff_num) + 2 * LINE_GAP
            side = "above" if y < uni else "below"
            node = {"id": str(uuid.uuid4())[:8], "pitch": "beat",
                    "dur_type": "rest" if self.placing_rest else dur.lower(),
                    "duration": NOTE_DURATIONS[dur]["val"],
                    "staff": staff_num, "bar_index": clicked_bar_idx,
                    "side": side, "raw_x": x, "seq": self._next_seq()}
            if self.placing_rest:
                node["rest"] = True
                node["rest_dur_type"] = dur.lower()
            elif self.drum_rimshot:
                node["rimshot"] = True
            self.score.nodes.append(node)
            self.recalculate_note_horizontal_positions()
            self.redraw_canvas_score()
            return

        # Notes are only placed while the Notes or Embellishments tab is open.
        if self.active_tab not in ("Notes", "Embellishments"):
            return

        staff_num, base_y, closest_pitch = self.identify_closest_staff_and_pitch(y)
        if staff_num is None:
            self.redraw_canvas_score()
            return

        clicked_bar_idx = self.get_bar_index_from_x(x, staff_num)
        is_grace = (self.selected_duration.lower() == "gracenote")

        target_id = None
        target_pitch = None
        if is_grace:
            bar_normals = [n for n in self.score.nodes if n["staff"] == staff_num and n.get("bar_index") == clicked_bar_idx and n["dur_type"] != "gracenote"]
            following = [n for n in bar_normals if n["raw_x"] > x]
            if not following:
                self.status_label.config(text="⚠️ Gracenotes must precede a normal target note!")
                return
            target = min(following, key=lambda n: n["raw_x"])
            target_id = target["id"]
            target_pitch = target["pitch"]

        calc_duration = NOTE_DURATIONS[self.selected_duration]["val"]

        if is_grace and self.selected_embellishment:
            emb = self.selected_embellishment
            # The note we "come from" (last normal note before the target) lets
            # the leumluath family drop its leading Low G.
            preceding = [n for n in bar_normals if n["raw_x"] <= x]
            prev_pitch = max(preceding, key=lambda n: n["raw_x"])["pitch"] if preceding else None
            pitches, ok, msg = self._embellishment_plan(emb, target_pitch, prev_pitch)
            if not ok:
                self.status_label.config(text="⚠️ " + msg)
                return

            for p_name in pitches:
                self.score.nodes.append({
                    "id": str(uuid.uuid4())[:8],
                    "pitch": p_name,
                    "duration": calc_duration,
                    "dur_type": "gracenote",
                    "staff": staff_num,
                    "bar_index": clicked_bar_idx,
                    "target_normal_id": target_id,
                    "raw_x": x,
                    "emb": emb,                 # which embellishment this grace belongs to
                    "seq": self._next_seq()
                })
        else:
            self.score.nodes.append({
                "id": str(uuid.uuid4())[:8],
                "pitch": closest_pitch["name"],
                "duration": calc_duration,
                "dur_type": self.selected_duration.lower(),
                "staff": staff_num,
                "bar_index": clicked_bar_idx,
                "target_normal_id": target_id,
                "raw_x": x,
                "seq": self._next_seq()
            })

        self.recalculate_note_horizontal_positions()
        self.redraw_canvas_score()

    def handle_canvas_drag(self, event):
        if self.dragging_bar is not None:
            lx, _ = self._to_logical(event)
            staff, idx = self.dragging_bar
            lines = self.score.bar_lines[staff]
            min_x = CANVAS_LEFT + 60 if idx == 0 else lines[idx - 1] + 60
            max_x = CANVAS_RIGHT - 60 if idx == len(lines) - 1 else lines[idx + 1] - 60
            lines[idx] = int(max(min_x, min(max_x, lx)))
            # Lightweight: just move a preview line on the canvas instead of
            # rebuilding the whole page buffer. The full re-render (and note
            # re-spacing) happens once, on release.
            z = self.zoom or 1.0
            base_y = self._staff_base_y(staff)
            x = lines[idx] * z
            self.canvas.delete("dragbar")
            self.canvas.create_line(x, base_y * z, x, (base_y + STAFF_H) * z,
                                    fill=self._hl_hex(), width=2, tags="dragbar")

    def handle_canvas_release(self, event):
        if self.dragging_bar is not None:
            self.dragging_bar = None
            self.canvas.delete("dragbar")
            self.recalculate_note_horizontal_positions()
            self.redraw_canvas_score()

    def handle_canvas_double_click(self, event):
        x, y = self._to_logical(event)
        for name, x0, y0, x1, y1 in getattr(self, "_header_hitboxes", []):
            if x0 - 8 <= x <= x1 + 8 and y0 - 6 <= y <= y1 + 6:
                self._edit_header_style(name)
                return

    def _edit_header_style(self, name):
        labels = {"title": "Tune Name", "tune_type": "Tune Type", "composer": "Composer"}
        attr = {"title": "title", "tune_type": "tune_type", "composer": "composer"}[name]
        st = self.score.header_style.setdefault(name, dict(DEFAULT_HEADER_STYLE[name]))

        win = tk.Toplevel(self.root)
        win.title("Edit " + labels[name])
        win.configure(bg=self.theme["panel"])
        win.grab_set()
        win.resizable(False, False)

        def lbl(t, r):
            tk.Label(win, text=t, bg=self.theme["panel"], fg=self.theme["fg"], anchor="w", width=10).grid(row=r, column=0, sticky="w", padx=10, pady=5)

        text_var = tk.StringVar(value=getattr(self.score, attr))
        font_var = tk.StringVar(value=st.get("font", self.score.selected_font))
        size_var = tk.StringVar(value=str(st.get("size", 20)))
        bold_var = tk.BooleanVar(value=bool(st.get("bold", False)))
        ital_var = tk.BooleanVar(value=bool(st.get("italic", False)))

        lbl("Text", 0); tk.Entry(win, textvariable=text_var, width=24).grid(row=0, column=1, padx=10, pady=5, sticky="w")
        lbl("Font", 1); tk.OptionMenu(win, font_var, *HEADER_FONT_CHOICES).grid(row=1, column=1, padx=10, pady=5, sticky="w")
        lbl("Size", 2); tk.Spinbox(win, from_=8, to=120, textvariable=size_var, width=6).grid(row=2, column=1, padx=10, pady=5, sticky="w")
        tk.Checkbutton(win, text="Bold", variable=bold_var, bg=self.theme["panel"], fg=self.theme["fg"],
                       selectcolor=self.theme["sub"], activebackground=self.theme["panel"]).grid(row=3, column=1, sticky="w", padx=10)
        tk.Checkbutton(win, text="Italic", variable=ital_var, bg=self.theme["panel"], fg=self.theme["fg"],
                       selectcolor=self.theme["sub"], activebackground=self.theme["panel"]).grid(row=4, column=1, sticky="w", padx=10)

        def do_save():
            setattr(self.score, attr, text_var.get())
            st["font"] = font_var.get()
            try:
                st["size"] = max(8, min(120, int(float(size_var.get()))))
            except Exception:
                pass
            st["bold"] = bool(bold_var.get())
            st["italic"] = bool(ital_var.get())
            win.destroy()
            self.redraw_canvas_score()

        btns = tk.Frame(win, bg=self.theme["panel"])
        btns.grid(row=5, column=0, columnspan=2, pady=10)
        tk.Button(btns, text="Apply", bg="#16a34a", fg="white", width=9, command=do_save).pack(side=tk.LEFT, padx=6)
        tk.Button(btns, text="Cancel", bg="#3f3f46", fg="white", width=9, command=win.destroy).pack(side=tk.LEFT, padx=6)

    def action_delete_selected(self):
        if self.selected_node_id:
            self.score.nodes = [n for n in self.score.nodes if n["id"] != self.selected_node_id and n.get("target_normal_id") != self.selected_node_id]
            self.selected_node_id = None
            self.recalculate_note_horizontal_positions()
            self.redraw_canvas_score()

    def draw_staff_background_grid(self, draw, base_y, scale, staff):
        lw = max(1, int(STAFF_LINE_W * scale))            # staff lines
        ew = max(1, int(STAFF_LINE_W * 1.4 * scale))      # left/right edge lines
        blw = max(1, int(STAFF_LINE_W * 0.6 * scale))     # internal bar separators (thinner)
        ink = (24, 24, 27, 255)
        if self._is_drum():
            # Berger uniline: one line, with bar ticks spanning a short height.
            mid = base_y + 2 * LINE_GAP
            top_y, bot_y = base_y + LINE_GAP, base_y + 3 * LINE_GAP
            draw.line([CANVAS_LEFT * scale, mid * scale, CANVAS_RIGHT * scale, mid * scale], fill=ink, width=lw)
            draw.line([CANVAS_LEFT * scale, top_y * scale, CANVAS_LEFT * scale, bot_y * scale], fill=ink, width=ew)
            draw.line([CANVAS_RIGHT * scale, top_y * scale, CANVAS_RIGHT * scale, bot_y * scale], fill=ink, width=ew)
            for end in self.score.bar_lines[staff]:
                draw.line([end * scale, top_y * scale, end * scale, bot_y * scale], fill=(113, 113, 122, 255), width=blw)
            return
        for i in range(5):
            line_y = (base_y + (i * LINE_GAP)) * scale
            draw.line([CANVAS_LEFT * scale, line_y, CANVAS_RIGHT * scale, line_y], fill=ink, width=lw)
        draw.line([CANVAS_LEFT * scale, base_y * scale, CANVAS_LEFT * scale, (base_y + STAFF_H) * scale], fill=ink, width=ew)
        draw.line([CANVAS_RIGHT * scale, base_y * scale, CANVAS_RIGHT * scale, (base_y + STAFF_H) * scale], fill=ink, width=ew)
        for end in self.score.bar_lines[staff]:
            draw.line([end * scale, base_y * scale, end * scale, (base_y + STAFF_H) * scale], fill=(113, 113, 122, 255), width=blw)

    def _bar_glyph(self, side, style):
        """Load Assets/bar/<side>/<style>.png (cropped), cached. None for Normal/missing."""
        if style == "Normal":
            return None
        key = (side, style.lower())
        if key in self._bar_img_cache:
            return self._bar_img_cache[key]
        img = None
        p = self._asset_path("bar", side, style.lower() + ".png")
        if os.path.exists(p):
            try:
                im = Image.open(p).convert("RGBA")
                bb = im.getbbox()
                img = im.crop(bb) if bb else im
            except Exception:
                img = None
        self._bar_img_cache[key] = img
        return img

    def _draw_bar_styles(self, hr_image, base_y, scale, staff):
        """Paste repeat/part barline glyphs at the start/end of bars that have a
        non-Normal style, spanning the stave height."""
        styles = self.score.bar_styles.get(staff, [])
        for b in range(len(styles)):
            st = styles[b]
            start_x, end_x = self.get_bar_boundaries(b, staff)
            if b == 0:
                # The first bar begins just after the clef + time signature,
                # not at the very left edge of the stave.
                start_x = CANVAS_LEFT + CLEF_SAFE_ZONE - 8
            for side, boundary, align_right in (("start", start_x, False), ("end", end_x, True)):
                glyph = self._bar_glyph(side, st.get(side, "Normal"))
                if glyph is None:
                    continue
                gh = max(1, int(STAFF_H * scale))
                gw = max(1, int(gh * glyph.size[0] / glyph.size[1]))
                g = glyph.resize((gw, gh), Image.Resampling.LANCZOS)
                px = int(boundary * scale - gw) if align_right else int(boundary * scale)
                hr_image.paste(g, (px, int(base_y * scale)), g)

    def _draw_key_signature(self, hr_image, base_y, scale, x_left):
        """Draw the highland key signature (F#, C#) starting at ``x_left``.
        Returns the x just past it. Sharps sit on the F line and the C space."""
        g = self._sharp_glyph(scale)
        if g is None:
            return x_left
        ink = self._tint_glyph(g, (24, 24, 27, 255))
        gw, gh = ink.size
        x = x_left
        for pitch in ("F", "C"):
            cfg = next((p for p in CHANTER_SCALE if p["name"] == pitch), None)
            if cfg is None:
                continue
            gy = base_y + cfg["y_offset"]
            hr_image.paste(ink, (int(x * scale), int(gy * scale - gh / 2)), ink)
            x += gw / scale + 3
        return x + 4

    def _draw_time_signature(self, hr_image, base_y, scale, time_sig, x_left=None):
        """Draw a time signature glyph for one stave, spanning the stave height
        and centred on the B line (= base_y + 2*LINE_GAP)."""
        if x_left is None:
            x_left = CANVAS_LEFT + 48
        ts_raw = (time_sig or "4/4").strip().lower()
        is_single_glyph = ts_raw in ("c", "common", "cut", "c|")
        if ts_raw in ("c", "common"):
            fn = "common.png"
        elif ts_raw in ("cut", "c|"):
            fn = "cut.png"
        else:
            fn = ts_raw.replace("/", "_") + ".png"
        ts_path = self._asset_path("time_sigs", fn)
        if not os.path.exists(ts_path):
            return
        try:
            ts_img = Image.open(ts_path).convert("RGBA")
            bb = ts_img.getbbox()
            if bb:
                ts_img = ts_img.crop(bb)
            # Cut/Common are single glyphs: render at half height so they sit in
            # the middle of the stave just after the clef.
            ts_h = STAFF_H * 0.5 if is_single_glyph else STAFF_H
            iw, ih = ts_img.size
            ts_w = ts_h * iw / ih
            ts_r = ts_img.resize((max(1, int(ts_w * scale)), max(1, int(ts_h * scale))),
                                 Image.Resampling.LANCZOS)
            top = (base_y + 2 * LINE_GAP) - ts_h / 2
            hr_image.paste(ts_r, (int(x_left * scale), int(top * scale)), ts_r)
        except Exception:
            pass

    def _draw_timings(self, draw, base_y, scale, staff):
        """Draw 1st/2nd-time (second-timing) brackets above bars marked with a
        timing, with the number at the left. Consecutive bars sharing the same
        timing value merge into a single bracket."""
        styles = self.score.bar_styles.get(staff, [])
        ink = (24, 24, 27, 255)
        font = self._font(int(13 * scale))
        y = base_y - 18                     # above the top stave line
        lw = max(1, int(1.6 * scale))

        # Group consecutive bars that carry the same timing into one run.
        b = 0
        n = len(styles)
        while b < n:
            t = styles[b].get("timing", "None")
            if t not in ("1", "2"):
                b += 1
                continue
            run_start = b
            while b + 1 < n and styles[b + 1].get("timing", "None") == t:
                b += 1
            run_end = b
            start_x = self.get_bar_boundaries(run_start, staff)[0]
            end_x = self.get_bar_boundaries(run_end, staff)[1]
            if run_start == 0:
                start_x = CANVAS_LEFT + CLEF_SAFE_ZONE
            x0, x1 = start_x + 4, end_x - 4
            # horizontal line with a downward tick at each end.
            draw.line([x0 * scale, y * scale, x1 * scale, y * scale], fill=ink, width=lw)
            draw.line([x0 * scale, y * scale, x0 * scale, (y + 8) * scale], fill=ink, width=lw)
            draw.line([x1 * scale, y * scale, x1 * scale, (y + 8) * scale], fill=ink, width=lw)
            draw.text(((x0 + 6) * scale, (y - 16) * scale), f"{t}.", font=font, fill=ink)
            b += 1

    def _build_page_buffer(self):
        """Render the whole Letter page to a high-res RGBA image (no zoom)."""
        scale = RENDER_AA
        # The whole image IS the Letter-shaped page.
        hr_image = Image.new("RGBA", (PAGE_W * scale, PAGE_H * scale), (255, 255, 255, 255))
        draw = ImageDraw.Draw(hr_image)
        # Page border.
        if self.settings.get("show_page_border", True):
            draw.rectangle([1 * scale, 1 * scale, (PAGE_W - 1) * scale, (PAGE_H - 1) * scale],
                           outline=(180, 180, 184, 255), width=max(1, int(1.5 * scale)))

        self._draw_page_header(draw, scale)

        # Prepare the clef glyph once (placed per stave so its spiral sits on
        # the G line = base_y + 3*LINE_GAP).
        clef_r = None
        if self.clef_image:
            clef_h = 6.0 * LINE_GAP
            iw, ih = self.clef_image.size
            clef_r = self.clef_image.resize(
                (max(1, int(clef_h * iw / ih * scale)), max(1, int(clef_h * scale))),
                Image.Resampling.LANCZOS)
        clef_left = CANVAS_LEFT + 8
        clef_x = int(clef_left * scale)
        clef_w = (clef_r.width / scale) if clef_r is not None else 6.0 * LINE_GAP * 0.45

        staves = self.score.staff_list()
        first_staff = staves[0] if staves else 1
        prev_ts = None
        for staff_num in staves:
            base_y = self._staff_base_y(staff_num)
            self.draw_staff_background_grid(draw, base_y, scale, staff_num)
            self._draw_bar_styles(hr_image, base_y, scale, staff_num)
            self._draw_timings(draw, base_y, scale, staff_num)
            drum = self._is_drum()
            if clef_r is not None and not drum:            # drums have no clef
                top = (base_y + 3 * LINE_GAP) - CLEF_CURL_FRAC * (6.0 * LINE_GAP)
                hr_image.paste(clef_r, (clef_x, int(top * scale)), clef_r)
            ts = self.score.time_sig_for(staff_num)
            cursor = (CANVAS_LEFT + 16) if drum else (clef_left + clef_w + 6)
            if staff_num == first_staff:
                if not drum:                               # key signature only in pipe mode
                    cursor = self._draw_key_signature(hr_image, base_y, scale, cursor)
                self._draw_time_signature(hr_image, base_y, scale, ts, cursor)
            elif ts != prev_ts:
                # A later stave shows its time signature only when it changes.
                self._draw_time_signature(hr_image, base_y, scale, ts, cursor)
            prev_ts = ts

        # Position every node by its pitch on the appropriate staff. In drum mode
        # everything sits on the single uniline.
        drum_mode = self._is_drum()
        for node in self.score.nodes:
            if drum_mode:
                node["render_x"] = node.get("raw_x", 140)
                uni = self._staff_base_y(node.get("staff", 1)) + 2 * LINE_GAP
                if node.get("rest"):
                    node["render_y"] = uni
                else:
                    # Notes straddle the line: head resting directly on it (above)
                    # or directly under it (below) - half a notehead off the line.
                    off = NOTE_HEAD_W // 2
                    node["render_y"] = uni - off if node.get("side", "above") == "above" else uni + off
                continue
            pitch_cfg = next((p for p in CHANTER_SCALE if p["name"] == node["pitch"]), None)
            if not pitch_cfg: continue
            node["render_x"] = node.get("raw_x", 140)
            node["render_y"] = self._staff_base_y(node.get("staff", 1)) + pitch_cfg["y_offset"]

        # --- Normal notes -------------------------------------------------
        # Crotchets and longer notes are rendered straight from their PNG glyph.
        # Sub-crotchet notes (quaver -> hemidemisemiquaver) are barred by BEAT
        # (the beat size depends on each stave's own time signature).
        for staff_num in self.score.staff_list():
            ts_raw = self.score.time_sig_for(staff_num).strip().lower()
            is_compound = ts_raw in ("6/8", "9/8", "12/8")
            beat_size = 0.75 if is_compound else 0.5
            for bar_idx in range(self.score.num_bars(staff_num)):
                bar_normals = [n for n in self.score.nodes
                               if n.get("staff", 1) == staff_num
                               and n.get("bar_index") == bar_idx
                               and n["dur_type"] != "gracenote"]
                bar_normals.sort(key=lambda n: n["render_x"])

                # Assign each note to the beat it starts in; beams never cross
                # a beat boundary.
                acc = 0.0
                beats = {}
                for node in bar_normals:
                    b_idx = int(acc / beat_size + 1e-9)
                    beats.setdefault(b_idx, []).append(node)
                    acc += self._eff_dur(node)

                for b_idx in sorted(beats):
                    group = beats[b_idx]
                    beamed = [n for n in group if n["dur_type"] in BEAM_COUNTS]
                    # A sub-crotchet note is only beamed when it is barred to at
                    # least one neighbour in the same beat; a lone one keeps its
                    # own PNG glyph (with its flag).
                    if len(beamed) >= 2:
                        for node in group:
                            if node["dur_type"] not in BEAM_COUNTS:
                                self._draw_single_note(hr_image, draw, node, scale)
                        self._draw_beam_group(hr_image, draw, beamed, scale)
                    else:
                        for node in group:
                            self._draw_single_note(hr_image, draw, node, scale)

        # --- Grace notes --------------------------------------------------
        # A lone grace note is drawn from gracenote.png as-is. When several
        # grace notes share a target (embellishments, or several placed before
        # one note) they are drawn "barred": noteheads from gracenote.png joined
        # by a beam.
        grace_by_target = {}
        for node in self.score.nodes:
            if node["dur_type"] != "gracenote":
                continue
            tgt = node.get("target_normal_id") or node["id"]
            grace_by_target.setdefault(tgt, []).append(node)

        for tgt, members in grace_by_target.items():
            members.sort(key=lambda n: n["render_x"])
            if len(members) == 1:
                node = members[0]
                self._paste_note_asset(hr_image, draw, node, self._node_color(node), scale)
                continue

            # Barred group: take the notehead from gracenote.png for each grace
            # and run shared stems up to a beam. The beam always sits at the top
            # of the stave (above the top line) regardless of grace pitches.
            head = self._get_head("gracenote", GRACE_HEAD_W, scale)
            g_staff = members[0].get("staff", 1)
            g_base = self._staff_base_y(g_staff)
            beam_y = g_base - 22   # always bar at the top of the stave
            stem_xs = []
            for node in members:
                col = self._node_color(node)
                gx, gy = node["render_x"], node["render_y"]
                if head is not None:
                    base, ax, ay = head
                    tinted = self._tint_glyph(base, col)
                    hr_image.paste(tinted, (int(round(gx * scale - ax)),
                                            int(round(gy * scale - ay))), tinted)
                else:
                    rx, ry = 3.2, 2.3
                    draw.ellipse([(gx - rx) * scale, (gy - ry) * scale,
                                  (gx + rx) * scale, (gy + ry) * scale], fill=col)
                stem_x = gx + GRACE_HEAD_W / 2.0 - 0.5
                draw.line([stem_x * scale, gy * scale, stem_x * scale, beam_y * scale],
                          fill=col, width=int(1.2 * scale))
                stem_xs.append(stem_x)
            bar_col = (24, 24, 27, 255)
            for off in (0.0, 3.0):  # double beam barring the grace notes
                draw.line([stem_xs[0] * scale, (beam_y + off) * scale,
                           stem_xs[-1] * scale, (beam_y + off) * scale],
                          fill=bar_col, width=int(2.2 * scale))

        self._draw_ties(hr_image, draw, scale)
        if self.settings.get("show_page_number", True):
            self._draw_page_footer(draw, scale)
        return hr_image

    def redraw_canvas_score(self):
        if not self.canvas or not self.canvas.winfo_exists(): return
        hr_image = self._build_page_buffer()

        # Pick a default zoom (fit the page width to the canvas) the first time.
        if self.zoom is None:
            cw = max(self.canvas.winfo_width(), 200)
            self.zoom = max(0.15, min(1.5, (cw - 24) / PAGE_W))

        disp_w = max(1, int(PAGE_W * self.zoom))
        disp_h = max(1, int(PAGE_H * self.zoom))
        smooth_final_img = hr_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        self.render_buffer_img = ImageTk.PhotoImage(smooth_final_img)
        self.render_canvas_interactive_overlay()

    def _font(self, size_px, family=None, bold=False, italic=False):
        family = family or self.score.selected_font
        variants = FONT_FILES.get(family, FONT_FILES["Sans Serif"])
        if bold and italic:
            fname = variants.get("bi") or variants["r"]
        elif bold:
            fname = variants.get("b") or variants["r"]
        elif italic:
            fname = variants.get("i") or variants["r"]
        else:
            fname = variants["r"]
        key = (fname, size_px)
        if key in self._font_cache:
            return self._font_cache[key]
        fonts_dir = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
        font = None
        for cand in (fname, variants["r"], "arial.ttf"):
            try:
                font = ImageFont.truetype(os.path.join(fonts_dir, cand), size_px)
                break
            except Exception:
                continue
        if font is None:
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
        self._font_cache[key] = font
        return font

    def _draw_header_elem(self, draw, scale, name, text, anchor_x, y, align):
        """Draw one header element with its own font/size/style and record a
        logical-coordinate hitbox for double-click editing."""
        if not text:
            return
        st = self.score.header_style.get(name, DEFAULT_HEADER_STYLE.get(name, {}))
        size = int(st.get("size", 20))
        font = self._font(int(size * scale), st.get("font", self.score.selected_font),
                          bool(st.get("bold", False)), bool(st.get("italic", False)))
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            w = bbox[2] - bbox[0]
        except Exception:
            w = len(text) * size * scale * 0.5
        if align == "center":
            px = anchor_x * scale - w / 2
        elif align == "right":
            px = anchor_x * scale - w
        else:
            px = anchor_x * scale
        draw.text((px, y * scale), text, font=font, fill=(24, 24, 27, 255))
        self._header_hitboxes.append((name, px / scale, y, (px + w) / scale, y + size * 1.4))

    def _draw_page_header(self, draw, scale):
        """Tune name, composer and tune type across the top of the page."""
        self._header_hitboxes = []
        cx = PAGE_W / 2
        self._draw_header_elem(draw, scale, "title", self.score.title, cx, 34, "center")
        self._draw_header_elem(draw, scale, "tune_type", self.score.tune_type, cx, 90, "center")
        self._draw_header_elem(draw, scale, "composer", self.score.composer, CANVAS_RIGHT, 90, "right")

    def _draw_page_footer(self, draw, scale):
        """Page number centred at the bottom of the page."""
        font = self._font(int(18 * scale))
        text = "1"
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            w = bbox[2] - bbox[0]
        except Exception:
            w = 9 * scale
        draw.text(((PAGE_W / 2) * scale - w / 2, (PAGE_H - 46) * scale),
                  text, font=font, fill=(90, 90, 96, 255))

    def _asset_path(self, *parts):
        """Resolve an asset path relative to the script directory, accepting
        either an ``Assets`` or ``assets`` folder."""
        p = os.path.join(self.base_dir, "Assets", *parts)
        if os.path.exists(p):
            return p
        return os.path.join(self.base_dir, "assets", *parts)

    def _hl_hex(self):
        """The user-chosen highlight colour (hex), used for selection + ghost."""
        return self.settings.get("highlight_color", "#2563eb")

    def _hl_rgba(self, alpha=255):
        h = self._hl_hex().lstrip("#")
        try:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except Exception:
            r, g, b = 37, 99, 235
        return (r, g, b, alpha)

    def _node_color(self, node):
        if node["id"] == self.active_playback_node_id:
            return (22, 163, 74, 255)
        if node["id"] == self.selected_node_id:
            return self._hl_rgba()
        return (24, 24, 27, 255)

    def _draw_single_note(self, hr_image, draw, node, scale):
        """Draw one melody note straight from its PNG glyph (stem/flag baked in)."""
        color_tuple = self._node_color(node)
        if node.get("rest"):
            self._draw_rest(draw, node, scale, color_tuple)
            self._draw_dot(draw, node, scale)
            return
        pitch_cfg = next((p for p in CHANTER_SCALE if p["name"] == node["pitch"]), None)
        if pitch_cfg and pitch_cfg["y_offset"] <= -LINE_GAP:  # ledger line for High A
            draw.line([(node["render_x"] - 10) * scale, node["render_y"] * scale,
                       (node["render_x"] + 10) * scale, node["render_y"] * scale],
                      fill=(24, 24, 27, 255), width=int(1.5 * scale))
        self._paste_note_asset(hr_image, draw, node, color_tuple, scale)
        self._draw_dot(draw, node, scale)
        if node.get("rimshot"):
            # Mark a rimshot with a small "x" above the notehead.
            cx, cy = node["render_x"], node["render_y"] - LINE_GAP - 4
            r = 3
            draw.line([(cx - r) * scale, (cy - r) * scale, (cx + r) * scale, (cy + r) * scale],
                      fill=color_tuple, width=max(1, int(1.4 * scale)))
            draw.line([(cx - r) * scale, (cy + r) * scale, (cx + r) * scale, (cy - r) * scale],
                      fill=color_tuple, width=max(1, int(1.4 * scale)))

    def _draw_rest(self, draw, node, scale, color):
        """Draw a stylised rest centred on the uniline, sized by duration."""
        x = node["render_x"]
        y = node.get("render_y", self._staff_base_y(node.get("staff", 1)) + 2 * LINE_GAP)
        dur = node.get("rest_dur_type", node.get("dur_type", "quarter"))
        w = max(1, int(3 * scale))
        if dur in ("whole", "half"):
            # A hanging (whole) or sitting (half) block on the line.
            bx0, bx1 = (x - 6) * scale, (x + 6) * scale
            if dur == "whole":
                by0, by1 = (y - 6) * scale, y * scale
            else:
                by0, by1 = y * scale, (y + 6) * scale
            draw.rectangle([bx0, by0, bx1, by1], fill=color)
            return
        # Quarter and shorter: a slanted body plus a flag dot per extra beam.
        draw.line([(x - 4) * scale, (y - 8) * scale, (x + 4) * scale, (y + 8) * scale],
                  fill=color, width=max(2, int(2.4 * scale)))
        draw.line([(x + 4) * scale, (y + 8) * scale, (x - 2) * scale, (y + 12) * scale],
                  fill=color, width=max(2, int(2.4 * scale)))
        flags = {"quaver": 1, "semiquaver": 2, "demisemiquaver": 3, "hemidemisemiquaver": 4}.get(dur, 0)
        for i in range(flags):
            fy = (y - 6 + i * 4)
            draw.ellipse([(x + 2) * scale, (fy - 2) * scale, (x + 6) * scale, (fy + 2) * scale], fill=color)

    def _eff_dur(self, node):
        """Effective duration including a dot (a dot adds half the value)."""
        return node["duration"] * (1.5 if node.get("dotted") else 1.0)

    def _draw_dot(self, draw, node, scale):
        """Render a dot of augmentation just to the right of a dotted notehead."""
        if not node.get("dotted"):
            return
        col = self._node_color(node)
        gx = node["render_x"] + NOTE_HEAD_W / 2.0 + 5
        gy = node["render_y"]
        r = 2.3
        draw.ellipse([(gx - r) * scale, (gy - r) * scale,
                      (gx + r) * scale, (gy + r) * scale], fill=col)

    def _sharp_glyph(self, scale):
        """Load + cache Assets/sharp.png scaled to ~2.4 line-gaps tall."""
        key = ("__sharp__", scale)
        if key in self._glyph_cache:
            return self._glyph_cache[key]
        img = None
        p = self._asset_path("sharp.png")
        if os.path.exists(p):
            try:
                im = Image.open(p).convert("RGBA")
                bb = im.getbbox()
                if bb:
                    im = im.crop(bb)
                h = max(1, int(2.4 * LINE_GAP * scale))
                w = max(1, int(h * im.size[0] / im.size[1]))
                img = im.resize((w, h), Image.Resampling.LANCZOS)
            except Exception:
                img = None
        self._glyph_cache[key] = img
        return img

    def _draw_sharp(self, hr_image, node, scale, color):
        """Paste a sharp glyph just to the left of a sharpened notehead."""
        g = self._sharp_glyph(scale)
        if g is None:
            return
        g = self._tint_glyph(g, color)
        gw, gh = g.size
        px = int(node["render_x"] * scale - (NOTE_HEAD_W * 0.5 + 3) * scale - gw)
        py = int(node["render_y"] * scale - gh / 2)
        hr_image.paste(g, (px, py), g)

    def _tie_raw(self):
        """Load Assets/tie.png once (or ``None`` if absent -> arc fallback)."""
        if "__tie__" in self._glyph_cache:
            return self._glyph_cache["__tie__"]
        img = None
        p = self._asset_path("notes", "tie.png")
        if os.path.exists(p):
            try:
                img = Image.open(p).convert("RGBA")
            except Exception:
                img = None
        self._glyph_cache["__tie__"] = img
        return img

    def _draw_ties(self, hr_image, draw, scale):
        """Draw a tie from each tied note back to the preceding melody note on
        its staff, using Assets/tie.png (falling back to a drawn arc if it is
        missing)."""
        notes = [n for n in self.score.nodes if n["dur_type"] != "gracenote"
                 and n.get("render_x") is not None]
        notes.sort(key=lambda n: (n.get("staff", 1), n.get("bar_index", 0), n["render_x"]))
        tie_img = self._tie_raw()
        for idx, node in enumerate(notes):
            if not node.get("tied"):
                continue
            prev = next((notes[k] for k in range(idx - 1, -1, -1)
                         if notes[k].get("staff", 1) == node.get("staff", 1)), None)
            if prev is None:
                continue
            # Span from just right of the previous head to just left of this head.
            x1 = prev["render_x"] + NOTE_HEAD_W * 0.30
            x2 = node["render_x"] - NOTE_HEAD_W * 0.30
            if x2 <= x1:
                continue
            y_heads = min(node["render_y"], prev["render_y"])
            tie_h = max(6, min(16, (x2 - x1) * 0.14))  # arch height scales with span
            bottom = y_heads - 5          # ties arc just above the noteheads
            top = bottom - tie_h
            if tie_img is not None:
                w = max(1, int(round((x2 - x1) * scale)))
                h = max(1, int(round(tie_h * scale)))
                ph = tie_img.resize((w, h), Image.Resampling.LANCZOS)
                hr_image.paste(ph, (int(round(x1 * scale)), int(round(top * scale))), ph)
            else:
                mid = (x1 + x2) / 2.0
                pts = []
                for k in range(13):
                    t = k / 12.0
                    bx = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * mid + t ** 2 * x2
                    by = (1 - t) ** 2 * bottom + 2 * (1 - t) * t * top + t ** 2 * bottom
                    pts.append(bx * scale)
                    pts.append(by * scale)
                draw.line(pts, fill=(24, 24, 27, 255), width=int(2 * scale), joint="curve")

    def _draw_beam_group(self, hr_image, draw, group, scale):
        """Bar one beat's worth of sub-crotchet notes together.

        Noteheads come from each note's PNG glyph; stems hang to a flat primary
        beam below the heads. Secondary beams (semiquaver and shorter) stack
        toward the heads, drawn only where notes share that subdivision, with
        partial stubs for isolated subdivisions.
        """
        group = sorted(group, key=lambda n: n["render_x"])
        nb = [BEAM_COUNTS[n["dur_type"]] for n in group]
        n = len(group)

        # Flat primary beam sits just below the bottom line of the stave, so the
        # stems run all the way under the staff.
        staff = group[0].get("staff", 1)
        base_y = self._staff_base_y(staff)
        beam_y = base_y + STAFF_H + BEAM_BELOW_STAVE

        stem_xs = []
        for node in group:
            col = self._node_color(node)
            gx, gy = node["render_x"], node["render_y"]
            pitch_cfg = next((p for p in CHANTER_SCALE if p["name"] == node["pitch"]), None)
            if pitch_cfg and pitch_cfg["y_offset"] <= -LINE_GAP:  # ledger line for High A
                draw.line([(gx - 10) * scale, gy * scale, (gx + 10) * scale, gy * scale],
                          fill=(24, 24, 27, 255), width=int(1.5 * scale))
            head = self._get_head(node["dur_type"], NOTE_HEAD_W, scale)
            if head is not None:
                base, ax, ay = head
                tinted = self._tint_glyph(base, col)
                hr_image.paste(tinted, (int(round(gx * scale - ax)),
                                        int(round(gy * scale - ay))), tinted)
            else:
                rx, ry = 6, 4.5
                draw.ellipse([(gx - rx) * scale, (gy - ry) * scale,
                              (gx + rx) * scale, (gy + ry) * scale], fill=col)
            stem_x = gx - NOTE_HEAD_W / 2.0 + 0.5  # stem on the left of the head
            draw.line([stem_x * scale, gy * scale, stem_x * scale, beam_y * scale],
                      fill=col, width=int(1.6 * scale))
            stem_xs.append(stem_x)
            self._draw_dot(draw, node, scale)

        bar_col = (24, 24, 27, 255)
        max_beams = max(nb)
        for b in range(max_beams):            # b = beam level (0 = primary)
            by = beam_y - b * BEAM_GAP        # secondary beams stack toward heads
            i = 0
            while i < n:
                if nb[i] <= b:
                    i += 1
                    continue
                j = i
                while j + 1 < n and nb[j + 1] > b:
                    j += 1
                if j > i:                     # full beam across the run
                    x0, x1 = stem_xs[i], stem_xs[j]
                else:                         # isolated subdivision -> partial stub
                    if b > 0 and i > 0:       # stub points back toward the group
                        x0, x1 = stem_xs[i] - BEAM_STUB, stem_xs[i]
                    else:
                        x0, x1 = stem_xs[i], stem_xs[i] + BEAM_STUB
                draw.line([x0 * scale, by * scale, x1 * scale, by * scale],
                          fill=bar_col, width=int(BEAM_THICK * scale))
                i = j + 1

    def _find_glyph_head(self, img):
        """Locate the notehead inside a cropped glyph image.

        The notehead is the widest opaque row in the glyph. We scan the whole
        image (not just the top) because melody glyphs have the head at the top
        while the grace glyph has it at the bottom (stem pointing up).
        Returns (head_cx, head_cy, head_w) in image pixels.
        """
        w, h = img.size
        px = img.load()
        limit = h
        best_w, best_row, best_l, best_r = -1, 0, 0, w
        for y in range(limit):
            left = right = None
            for x in range(w):
                if px[x, y][3] > 60:
                    if left is None:
                        left = x
                    right = x
            if left is not None and (right - left) > best_w:
                best_w, best_row, best_l, best_r = right - left, y, left, right
        if best_w < 0:
            return w / 2.0, h / 2.0, float(w)
        return (best_l + best_r) / 2.0, float(best_row), float(best_r - best_l)

    def _get_glyph(self, dur_type, scale):
        """Return (image, anchor_x, anchor_y) for a glyph, cropped to its content
        and scaled so its head matches the target size. The anchor is the head
        centre, so the glyph can be pasted with the head on the pitch line.
        Returns ``None`` if the PNG is missing/unreadable (vector fallback)."""
        key = (dur_type.lower(), scale)
        if key in self._glyph_cache:
            return self._glyph_cache[key]

        note_path = self._asset_path("notes", dur_type.lower() + ".png")
        if not os.path.exists(note_path):
            self._glyph_cache[key] = None
            return None
        try:
            img = Image.open(note_path).convert("RGBA")
        except Exception:
            self._glyph_cache[key] = None
            return None

        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
        gw, gh = img.size
        hx, hy, hw = self._find_glyph_head(img)

        target = (GRACE_HEAD_W if dur_type.lower() == "gracenote" else NOTE_HEAD_W) * scale
        sf = target / max(hw, 1.0)
        new_size = (max(1, round(gw * sf)), max(1, round(gh * sf)))
        img_r = img.resize(new_size, Image.Resampling.LANCZOS)
        entry = (img_r, hx * sf, hy * sf)
        self._glyph_cache[key] = entry
        return entry

    def _get_head(self, dur_type, target_w, scale):
        """Return (image, anchor_x, anchor_y) for just the notehead cropped out
        of ``<dur_type>.png``, scaled so the head is ``target_w`` wide. Used for
        barred groups, where each glyph's own stem/flag is replaced by a shared
        beam. Returns ``None`` if the PNG is missing/unreadable."""
        key = ("__head__", dur_type.lower(), scale)
        if key in self._glyph_cache:
            return self._glyph_cache[key]

        note_path = self._asset_path("notes", dur_type.lower() + ".png")
        if not os.path.exists(note_path):
            self._glyph_cache[key] = None
            return None
        try:
            img = Image.open(note_path).convert("RGBA")
        except Exception:
            self._glyph_cache[key] = None
            return None

        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
        hx, hy, hw = self._find_glyph_head(img)
        hh = hw * 0.7
        left = max(0, int(round(hx - hw / 2)))
        top = max(0, int(round(hy - hh / 2)))
        right = min(img.size[0], int(round(hx + hw / 2)))
        bot = min(img.size[1], int(round(hy + hh / 2)))
        head = img.crop((left, top, right, bot))

        sf = (target_w * scale) / max(hw, 1.0)
        new_size = (max(1, round(head.size[0] * sf)), max(1, round(head.size[1] * sf)))
        head = head.resize(new_size, Image.Resampling.LANCZOS)
        entry = (head, (hx - left) * sf, (hy - top) * sf)
        self._glyph_cache[key] = entry
        return entry

    @staticmethod
    def _tint_glyph(base, color_tuple):
        """Recolour a glyph to ``color_tuple`` while keeping its alpha shape."""
        alpha = base.split()[3]
        solid = Image.new("RGBA", base.size,
                          (color_tuple[0], color_tuple[1], color_tuple[2], 0))
        solid.putalpha(alpha)
        return solid

    def _paste_note_asset(self, hr_image, draw, node, color_tuple, scale):
        glyph = self._get_glyph(node["dur_type"], scale)
        if glyph is not None:
            base, ax, ay = glyph
            tinted = self._tint_glyph(base, color_tuple)
            paste_x = int(round(node["render_x"] * scale - ax))
            paste_y = int(round(node["render_y"] * scale - ay))
            hr_image.paste(tinted, (paste_x, paste_y), tinted)
            return

        # Vector engine fallback layout (used only if the PNG is missing)
        is_grace = (node["dur_type"] == "gracenote")
        rx, ry = (3.5, 2.5) if is_grace else (6, 4.5)
        meta = NOTE_DURATIONS[node["dur_type"].capitalize()]
        if meta["hollow"] and not is_grace:
            draw.ellipse([(node["render_x"] - rx) * scale, (node["render_y"] - ry) * scale, (node["render_x"] + rx) * scale, (node["render_y"] + ry) * scale], outline=color_tuple, width=int(2 * scale))
        else:
            draw.ellipse([(node["render_x"] - rx) * scale, (node["render_y"] - ry) * scale, (node["render_x"] + rx) * scale, (node["render_y"] + ry) * scale], fill=color_tuple)

    def render_canvas_interactive_overlay(self):
        if not self.canvas or not self.render_buffer_img: return
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.render_buffer_img, anchor=tk.NW)
        self.canvas.config(scrollregion=(0, 0, self.render_buffer_img.width(),
                                         self.render_buffer_img.height()))

        # Selected-bar outline (for the Bar menu).
        if self.selected_bar is not None:
            staff, b = self.selected_bar
            z = self.zoom or 1.0
            base_y = self._staff_base_y(staff)
            start_x, end_x = self.get_bar_boundaries(b, staff)
            self.canvas.create_rectangle(start_x * z, base_y * z, end_x * z, (base_y + STAFF_H) * z,
                                         outline=self._hl_hex(), width=2)

        # Hover preview: a translucent ghost of the note/embellishment that would
        # be placed. Only shown while a placeable tool is active (Notes/Embellishments
        # tab); otherwise it disappears.
        if (self.hover_x is not None and self.hover_y is not None
                and not self._is_drum()
                and self.active_tab in ("Notes", "Embellishments")):
            staff_num, base_y, p_target = self.identify_closest_staff_and_pitch(self.hover_y)
            if staff_num is not None:
                z = self.zoom or 1.0
                emb = (self.selected_embellishment
                       if self.selected_duration.lower() == "gracenote" else None)
                if emb:
                    # Show the whole embellishment outline; red if it cannot be
                    # placed in front of a note here.
                    self._draw_embellishment_ghost(emb, staff_num, base_y, z)
                else:
                    gy = base_y + p_target["y_offset"]
                    prev = self._hover_preview(self.selected_duration.lower(), z)
                    if prev is not None:
                        ph, ax, ay = prev
                        self.canvas.create_image(self.hover_x * z - ax, gy * z - ay,
                                                 image=ph, anchor=tk.NW)
                    else:
                        hx, hy = self.hover_x * z, gy * z
                        r = 5 * z
                        self.canvas.create_oval(hx - r, hy - r * 0.75, hx + r * 1.4, hy + r * 0.75,
                                                fill="#93c5fd", outline="#3b82f6", width=1)

    def _draw_embellishment_ghost(self, emb, staff_num, base_y, z):
        """Translucent ghost of a full embellishment before the note the cursor
        is in front of. Drawn in the highlight colour when it can be placed, or
        red when it cannot (illegal on that note, or no following note)."""
        bar_idx = self.get_bar_index_from_x(self.hover_x, staff_num)
        bar_normals = [n for n in self.score.nodes
                       if n["staff"] == staff_num and n.get("bar_index") == bar_idx
                       and n["dur_type"] != "gracenote"]
        following = [n for n in bar_normals if n["raw_x"] > self.hover_x]
        target = min(following, key=lambda n: n["raw_x"]) if following else None

        if target is not None:
            preceding = [n for n in bar_normals if n["raw_x"] <= self.hover_x]
            prev_pitch = max(preceding, key=lambda n: n["raw_x"])["pitch"] if preceding else None
            pitches, ok, _ = self._embellishment_plan(emb, target["pitch"], prev_pitch)
            anchor_x = target["raw_x"]
        else:
            # No note to ornament: show the representative shape in red.
            shape = {
                "doubling": ["High G", "Low A"], "d_throw": ["Low G", "E", "D"],
                "birl": ["Low G", "Low A", "Low G"],
                "high_g_birl": ["High G", "Low A", "Low G", "Low A", "Low G"],
                "double_strike": ["High G", "Low G"], "leamluath": ["Low G", "D", "Low G"],
                "taorluath": ["Low G", "D", "Low G", "E"], "heavy_d_throw": ["Low G", "D", "Low G", "C"],
            }
            pitches, ok, anchor_x = shape.get(emb, ["Low G"]), False, self.hover_x

        rgb = (220, 38, 38) if not ok else self._hl_rgba()[:3]
        col = "#%02x%02x%02x" % rgb
        gap = self.score.gap_after_gracenotes
        n = len(pitches)
        positions = []
        for i, p in enumerate(pitches):
            pcfg = next((c for c in CHANTER_SCALE if c["name"] == p), None)
            if pcfg is None:
                continue
            gx = anchor_x - gap - 10 * (n - 1 - i)
            gy = base_y + pcfg["y_offset"]
            positions.append((gx, gy))
        if not positions:
            return

        # Draw the group barred: a notehead per grace, a stem from each up to a
        # shared beam at the top of the stave, joined by a double beam -- exactly
        # how the finished score renders a barred grace group.
        head = self._ghost_head(z, rgb)
        beam_y = base_y - 22
        stem_xs = []
        for gx, gy in positions:
            if head is not None:
                ph, ax, ay = head
                self.canvas.create_image(gx * z - ax, gy * z - ay, image=ph, anchor=tk.NW)
            else:
                r0 = 3 * z
                self.canvas.create_oval(gx * z - r0, gy * z - r0 * 0.7,
                                        gx * z + r0, gy * z + r0 * 0.7, fill=col, outline=col)
            stem_x = gx + GRACE_HEAD_W / 2.0 - 0.5
            self.canvas.create_line(stem_x * z, gy * z, stem_x * z, beam_y * z,
                                    fill=col, width=max(1, int(1.2 * z)))
            stem_xs.append(stem_x)
        if len(stem_xs) >= 2:
            for off in (0.0, 3.0):             # double beam joining the group
                self.canvas.create_line(stem_xs[0] * z, (beam_y + off) * z,
                                        stem_xs[-1] * z, (beam_y + off) * z,
                                        fill=col, width=max(2, int(2.2 * z)))

    def _embellishment_plan(self, emb, target_pitch, prev_pitch=None):
        """Gracenote pitches that precede a target theme note for an
        embellishment, whether it is legal on that note, and a reason if not.
        Sequences follow the Piper's Dojo Bagpipe Embellishment Guide: the
        leumluath 'grip' core is G-D-G, and that leading Low G is dropped when
        the note we come from is already Low G."""
        order = [p["name"] for p in CHANTER_SCALE]           # high -> low

        def below(a, b):
            return order.index(a) > order.index(b)

        def next_lowest(a):
            return order[min(order.index(a) + 1, len(order) - 1)]

        if not emb:
            return [], True, ""

        # Pre-existing embellishments (behaviour unchanged).
        if emb == "doubling":
            return DOUBLING_MAP.get(target_pitch, ["High G", target_pitch]), True, ""
        if emb == "d_throw":   # light throw: Low G, then a D-gracenote on C
            return ["Low G", "D", "C"], (target_pitch == "D"), "A Throw on D can only be attached to D."
        if emb == "birl":
            return ["Low G", "Low A", "Low G"], (target_pitch == "Low A"), "Birls can only be played on Low A."
        if emb == "high_g_birl":
            return (["High G", "Low A", "Low G", "Low A", "Low G"],
                    (target_pitch == "Low A"), "Birls can only be played on Low A.")

        # Double-Strike: High G gracenote to X, then ONE strike (two sounds).
        if emb == "double_strike":
            if not below(target_pitch, "D"):                 # D or above
                strike = "Low G" if target_pitch == "D" else next_lowest(target_pitch)
            else:                                            # below D
                strike = "Low G"
            return ["High G", strike], True, ""

        # Leumluath family share the G-D-G grip core.
        core = ["D", "Low G"] if prev_pitch == "Low G" else ["Low G", "D", "Low G"]
        if emb == "leamluath":
            return core, True, ""
        if emb == "taorluath":
            return core + ["E"], below(target_pitch, "E"), "A Taorluath must land on D or below."
        if emb == "heavy_d_throw":
            return core + ["C"], (target_pitch == "D"), "A Heavy D Throw can only be attached to D."

        return ["Low G"], True, ""

    def _ghost_glyph(self, dur_type, zoom, rgb):
        """A translucent ghost of the glyph for ``dur_type`` at the current zoom,
        tinted ``rgb``. Returns ``(PhotoImage, ax, ay)`` or ``None``."""
        r, g, b = rgb
        key = (dur_type, round(zoom, 3), r, g, b)
        if key in self._hover_cache:
            return self._hover_cache[key]
        glyph = self._get_glyph(dur_type, RENDER_AA)
        if glyph is None:
            self._hover_cache[key] = None
            return None
        base, ax, ay = glyph                 # base is at RENDER_AA scale
        f = zoom / RENDER_AA
        w = max(1, int(base.width * f))
        h = max(1, int(base.height * f))
        small = base.resize((w, h), Image.Resampling.LANCZOS)
        alpha = small.split()[3].point(lambda a: int(a * 0.5))   # ~50% transparent
        tint = Image.new("RGBA", small.size, (r, g, b, 0))
        tint.putalpha(alpha)
        ph = ImageTk.PhotoImage(tint)
        entry = (ph, ax * f, ay * f)
        self._hover_cache[key] = entry
        return entry

    def _ghost_head(self, zoom, rgb):
        """Translucent gracenote NOTEHEAD (no stem/flag) at the current zoom,
        tinted ``rgb`` -- used for barred ghost groups. ``(PhotoImage, ax, ay)``."""
        r, g, b = rgb
        key = ("__ghosthead__", round(zoom, 3), r, g, b)
        if key in self._hover_cache:
            return self._hover_cache[key]
        head = self._get_head("gracenote", GRACE_HEAD_W, RENDER_AA)
        if head is None:
            self._hover_cache[key] = None
            return None
        base, ax, ay = head
        f = zoom / RENDER_AA
        w = max(1, int(base.width * f))
        h = max(1, int(base.height * f))
        small = base.resize((w, h), Image.Resampling.LANCZOS)
        alpha = small.split()[3].point(lambda a: int(a * 0.6))
        tint = Image.new("RGBA", small.size, (r, g, b, 0))
        tint.putalpha(alpha)
        ph = ImageTk.PhotoImage(tint)
        entry = (ph, ax * f, ay * f)
        self._hover_cache[key] = entry
        return entry

    def _hover_preview(self, dur_type, zoom):
        """Translucent single-glyph ghost tinted with the highlight colour."""
        return self._ghost_glyph(dur_type, zoom, self._hl_rgba()[:3])

    def _playback_bar_order(self):
        """Reading-order list of (staff, bar) keys with repeats expanded. A bar
        whose end style is 'Repeat' replays the section back to the most recent
        'Repeat' start (or the beginning) exactly once before continuing."""
        bars = [(staff, b) for staff in self.score.staff_list()
                for b in range(self.score.num_bars(staff))]
        result = []
        repeat_start = 0
        for i, (staff, b) in enumerate(bars):
            styles = self.score.bar_styles.get(staff, [])
            st = styles[b] if b < len(styles) else {}
            if st.get("start") == "Repeat":
                repeat_start = i
            result.append((staff, b))
            if st.get("end") == "Repeat":
                result.extend(bars[repeat_start:i + 1])   # play the section once more
                repeat_start = i + 1
        return result

    def audio_play_stream(self, mode="all"):
        if not self.is_playing:
            self.is_playing = True
            threading.Thread(target=lambda: self._run_audio_synthesis_loop(mode), daemon=True).start()

    def audio_stop_stream(self):
        self.is_playing = False
        self.active_playback_node_id = None
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)  # silence immediately
        except Exception:
            pass
        self.root.after(0, self.redraw_canvas_score)

    @staticmethod
    def _decode_wav_any(path):
        """Decode a WAV to (mono array('h'), framerate). Handles PCM 16/24/32-bit,
        IEEE float 32/64-bit and WAVE_FORMAT_EXTENSIBLE - Python's stdlib ``wave``
        chokes on the latter two, which user-supplied drum samples often use."""
        import struct
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            return None, 44100
        if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            return None, 44100
        pos, fmt, body_data = 12, None, None
        while pos + 8 <= len(data):
            cid = data[pos:pos + 4]
            size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
            body = data[pos + 8:pos + 8 + size]
            if cid == b"fmt ":
                fmt = body
            elif cid == b"data":
                body_data = body
            pos += 8 + size + (size & 1)
        if fmt is None or body_data is None or len(fmt) < 16:
            return None, 44100
        afmt, nch, fr, _br, _ba, bits = struct.unpack("<HHIIHH", fmt[:16])
        if afmt == 0xFFFE and len(fmt) >= 26:            # extensible -> real subformat
            afmt = struct.unpack("<H", fmt[24:26])[0]
        try:
            if afmt == 1 and bits == 16:
                raw = array.array("h"); raw.frombytes(body_data[:len(body_data) // 2 * 2])
                chans = raw
            elif afmt == 1 and bits == 32:
                raw = array.array("i"); raw.frombytes(body_data[:len(body_data) // 4 * 4])
                chans = array.array("h", (v >> 16 for v in raw))
            elif afmt == 1 and bits == 24:
                n = len(body_data) // 3
                chans = array.array("h")
                for i in range(n):
                    v = body_data[3 * i] | (body_data[3 * i + 1] << 8) | (body_data[3 * i + 2] << 16)
                    if v & 0x800000:
                        v -= 0x1000000
                    chans.append(v >> 8)
            elif afmt == 3:                              # IEEE float
                fl = array.array("f" if bits == 32 else "d")
                step = 4 if bits == 32 else 8
                fl.frombytes(body_data[:len(body_data) // step * step])
                chans = array.array("h", (32767 if x > 1 else (-32768 if x < -1 else int(x * 32767)) for x in fl))
            else:
                return None, fr
        except Exception:
            return None, fr
        if nch == 2:
            chans = array.array("h", chans[0::2])         # down-mix to mono (left)
        return chans, fr

    def _load_drum_sample(self, kind):
        """Amplified 16-bit mono samples for a drum voice ('snare'/'tenor'/'bass')
        or 'rimshot', cached. No warm-up skip - these are short one-shots.
        Returns ``(array('h') | None, framerate)``."""
        key = ("__drum__", kind)
        if key in self._wav_cache:
            return self._wav_cache[key]
        result = (None, 44100)
        src = self._asset_path("drums", kind + ".wav")
        if os.path.exists(src):
            samples, fr = self._decode_wav_any(src)
            if samples:
                peak = max((abs(s) for s in samples), default=0)
                if peak > 0:
                    vol = float(self.settings.get("volume", 200)) / 100.0
                    target = min(2.5, 0.92 * vol)
                    gain = min(25.0, (target * 32767.0) / peak)
                    if gain > 1.02:
                        lo, hi = -32768, 32767
                        samples = array.array("h", (hi if (v := int(s * gain)) > hi
                                                    else (lo if v < lo else v) for s in samples))
                result = (samples, fr)
        self._wav_cache[key] = result
        return result

    def _load_samples(self, pitch):
        """Trimmed + amplified 16-bit mono samples for a pitch on the selected
        instrument, cached. Returns ``(array('h') | None, framerate)``."""
        key = (self.selected_instrument, pitch)
        if key in self._wav_cache:
            return self._wav_cache[key]
        result = (None, 44100)
        name = pitch.lower().replace(" ", "")   # "High A" -> "higha", "Low G" -> "lowg"
        src = self._asset_path("audio", self.selected_instrument, name + ".wav")
        if os.path.exists(src):
            try:
                with wave.open(src, "rb") as w:
                    sw, ch, fr = w.getsampwidth(), w.getnchannels(), w.getframerate()
                    frames = w.readframes(w.getnframes())
                if sw == 2:
                    samples = array.array("h")
                    samples.frombytes(frames)
                    # Skip the quiet warm-up.
                    skip = int(float(self.settings.get("audio_start_sec", 3.0)) * fr) * ch
                    if 0 < skip < len(samples):
                        samples = samples[skip:]
                    # Amplify toward the configured volume.
                    peak = max((abs(s) for s in samples), default=0)
                    if peak > 0:
                        vol = float(self.settings.get("volume", 200)) / 100.0
                        target = min(2.5, 0.92 * vol)
                        gain = min(25.0, (target * 32767.0) / peak)
                        if gain > 1.02:
                            lo, hi = -32768, 32767
                            samples = array.array("h", (hi if (v := int(s * gain)) > hi
                                                        else (lo if v < lo else v) for s in samples))
                    if ch == 2:                       # down-mix to mono
                        samples = array.array("h", samples[0::2])
                    result = (samples, fr)
            except Exception:
                result = (None, 44100)
        self._wav_cache[key] = result
        return result

    def _run_audio_synthesis_loop(self, mode):
        try:
            import winsound
            import tempfile
        except Exception:
            self.audio_stop_stream()
            return
        try:
            # Play in reading order (staff, bar, x), gracenotes included. For the
            # whole score, expand repeat barlines so repeated sections play twice.
            if mode == "all":
                by_bar = {}
                for n in self.score.nodes:
                    by_bar.setdefault((n.get("staff", 1), n.get("bar_index", 0)), []).append(n)
                nodes = []
                for key in self._playback_bar_order():
                    nodes.extend(sorted(by_bar.get(key, []),
                                        key=lambda n: (n.get("raw_x", 0), n.get("seq", 0))))
            else:
                nodes = sorted(self.score.nodes,
                               key=lambda n: (n.get("staff", 1), n.get("bar_index", 0),
                                              n.get("raw_x", 0), n.get("seq", 0)))
            if mode == "note" and self.selected_node_id:
                idx = next((i for i, n in enumerate(nodes) if n["id"] == self.selected_node_id), 0)
                nodes = nodes[idx:]
            elif mode == "bar":
                # Play from the first note of the selected bar through to the end.
                target = self.selected_bar
                if target is None and self.selected_node_id:
                    sel = next((n for n in nodes if n["id"] == self.selected_node_id), None)
                    if sel:
                        target = (sel.get("staff", 1), sel.get("bar_index", 0))
                if target is not None:
                    staff_t, bar_t = target
                    start = next((i for i, n in enumerate(nodes)
                                  if n.get("staff", 1) == staff_t and n.get("bar_index", 0) == bar_t), None)
                    if start is not None:
                        nodes = nodes[start:]

            beat_ms = 60000.0 / max(1, self.score.tempo)
            crotchet = NOTE_DURATIONS["Quarter"]["val"]
            grace_dur = NOTE_DURATIONS["Hemidemisemiquaver"]["val"]   # 1/64

            out = array.array("h")
            schedule = []   # (duration_ms, node_id) for the visual highlight
            fr = 44100

            if self._is_drum():
                # Each note = ONE drum hit, then silence for the rest of its slot.
                # Beats are never sustained or carried into the next note.
                voice = getattr(self.score, "drum_voice", "Snare").lower()
                _vs, base_fr = self._load_drum_sample(voice)
                fr = base_fr or 44100
                for node in nodes:
                    ms = max(1, int((self._eff_dur(node) / crotchet) * beat_ms))
                    nframes = max(1, int(fr * ms / 1000.0))
                    if node.get("rest"):
                        out.extend(array.array("h", [0]) * nframes)   # silence
                    else:
                        kind = "rimshot" if node.get("rimshot") else voice
                        samples, _sr = self._load_drum_sample(kind)
                        hit = samples[:nframes] if samples else array.array("h")
                        out.extend(hit)
                        if len(hit) < nframes:                        # pad, don't tile
                            out.extend(array.array("h", [0]) * (nframes - len(hit)))
                    schedule.append((ms, node["id"]))
            else:
                # Concatenate every note's audio into ONE continuous track, so each
                # note rings up to the next (gapless) and graces flow in.
                for node in nodes:
                    samples, sr = self._load_samples(node["pitch"])
                    if not samples:
                        continue
                    fr = sr
                    dur = grace_dur if node["dur_type"] == "gracenote" else self._eff_dur(node)
                    ms = max(1, int((dur / crotchet) * beat_ms))
                    nframes = max(1, int(sr * ms / 1000.0))
                    if len(samples) >= nframes:
                        chunk = samples[:nframes]
                    else:                                   # tile a short sample to fill
                        chunk = (samples * (nframes // len(samples) + 1))[:nframes]
                    out.extend(chunk)
                    # A gracenote highlights the note it's attached to, not itself.
                    if node["dur_type"] == "gracenote":
                        hl = node.get("target_normal_id") or node["id"]
                    else:
                        hl = node["id"]
                    schedule.append((ms, hl))

            if not out or not self.is_playing:
                self.audio_stop_stream()
                return

            if not getattr(self, "_audio_tmpdir", None):
                self._audio_tmpdir = tempfile.mkdtemp(prefix="pf_audio_")
            tune_path = os.path.join(self._audio_tmpdir, "_tune.wav")
            with wave.open(tune_path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(fr)
                w.writeframes(out.tobytes())

            # One continuous, gapless playback of the whole selection.
            winsound.PlaySound(tune_path, winsound.SND_FILENAME | winsound.SND_ASYNC)

            # Drive the on-screen note highlight in step with the audio.
            for ms, nid in schedule:
                if not self.is_playing:
                    break
                self.active_playback_node_id = nid
                self.root.after(0, self.redraw_canvas_score)
                time.sleep(ms / 1000.0)

            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        except Exception:
            pass
        self.audio_stop_stream()




def main():
    root_window = tk.Tk()
    app = PipersFriendApp(root_window)
    root_window.mainloop()
