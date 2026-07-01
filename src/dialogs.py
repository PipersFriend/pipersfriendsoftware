from .constants import *


class UnifiedSetupDialog(simpledialog.Dialog):
    def __init__(self, parent, defaults=None):
        self._defaults = defaults or {}
        super().__init__(parent)

    def body(self, master):
        self.title("Score Custom Setup Wizard")
        d = self._defaults

        tk.Label(master, text="Tune Name:").grid(row=0, column=0, sticky="w", pady=4, padx=5)
        self.entry_name = tk.Entry(master, width=25)
        self.entry_name.grid(row=0, column=1, pady=4)
        self.entry_name.insert(0, "Untitled Tune")

        tk.Label(master, text="Composer:").grid(row=1, column=0, sticky="w", pady=4, padx=5)
        self.entry_composer = tk.Entry(master, width=25)
        self.entry_composer.grid(row=1, column=1, pady=4)
        self.entry_composer.insert(0, d.get("composer", "Unknown"))

        tk.Label(master, text="Tune Type:").grid(row=2, column=0, sticky="w", pady=4, padx=5)
        self.entry_type = tk.Entry(master, width=25)
        self.entry_type.grid(row=2, column=1, pady=4)
        self.entry_type.insert(0, d.get("type", "March"))

        tk.Label(master, text="Time Signature:").grid(row=3, column=0, sticky="w", pady=4, padx=5)

        self.time_sig_var = tk.StringVar(value=d.get("time_sig", "4/4"))
        self.opt_time = tk.OptionMenu(master, self.time_sig_var, *TIME_SIGNATURE_OPTIONS)
        self.opt_time.config(width=21)
        self.opt_time.grid(row=3, column=1, pady=4, sticky="w")
        
        return self.entry_name

    def validate(self):
        self.result = {
            "name": self.entry_name.get().strip() or "Untitled Tune",
            "composer": self.entry_composer.get().strip() or "Unknown",
            "type": self.entry_type.get().strip() or "March",
            "time_sig": self.time_sig_var.get()
        }
        return True


