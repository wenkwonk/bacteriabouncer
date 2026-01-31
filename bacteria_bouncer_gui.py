import customtkinter as ctk
from tkinter import filedialog
import os
import sys
import multiprocessing
import threading
import time
import bacteria_bouncer_engine as engine
import bacteria_bouncer_config as config 

class BacteriaBouncerGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Bacteria Bouncer v1.0")
        self.geometry("800x500")
        
        #resource path for PyInstaller
        if getattr(sys, 'frozen', False):
            self.base_path = sys._MEIPASS
        else:
            self.base_path = os.path.dirname(os.path.abspath(__file__))

        #icon loading
        try:
            if sys.platform.startswith('win'):
                icon_path = os.path.join(self.base_path, "icon.ico")
                self.iconbitmap(icon_path)
            elif sys.platform.startswith('darwin'):
                icon_path = os.path.join(self.base_path, "icon.icns")
                if os.path.exists(icon_path):
                    self.tk.call('wm', 'iconset', self._w, icon_path)
        except: 
            pass

        self.experiment_data = {}
        self.setup_ui()

    def setup_ui(self):
        self.label = ctk.CTkLabel(self, text="Bacteria Bouncer", font=("Arial", 24, "bold"))
        self.label.pack(pady=15)

        self.ctrl = ctk.CTkFrame(self)
        self.ctrl.pack(fill="x", padx=20, pady=5)

        ctk.CTkButton(self.ctrl, text="Add Strain", width=100, command=self.add_strain_dialog).pack(side="left", padx=10)
        
        #blur setting
        ctk.CTkLabel(self.ctrl, text="Blur:").pack(side="left", padx=(10, 2))
        self.blur_entry = ctk.CTkEntry(self.ctrl, width=35)
        self.blur_entry.insert(0, str(config.gaussian_kernel_size))
        self.blur_entry.pack(side="left", padx=5)

        #crop setting
        ctk.CTkLabel(self.ctrl, text="Crop:").pack(side="left", padx=(10, 2))
        self.crop_entry = ctk.CTkEntry(self.ctrl, width=35)
        self.crop_entry.insert(0, str(config.crop_radius_ratio))
        self.crop_entry.pack(side="left", padx=5)

        #buffer setting
        ctk.CTkLabel(self.ctrl, text="Buffer:").pack(side="left", padx=(10, 2))
        self.buffer_entry = ctk.CTkEntry(self.ctrl, width=50)
        self.buffer_entry.insert(0, str(config.safety_buffer))
        self.buffer_entry.pack(side="left", padx=5)

        #std dev setting
        ctk.CTkLabel(self.ctrl, text="StdDev Mult:").pack(side="left", padx=(10, 2))
        self.stddev_entry = ctk.CTkEntry(self.ctrl, width=25)
        self.stddev_entry.insert(0, str(config.std_dev_multiplier))
        self.stddev_entry.pack(side="left", padx=5)

        #mask saving option
        self.mask_switch = ctk.CTkSwitch(self.ctrl, text="Save Masks")
        self.mask_switch.pack(side="left", padx=15)

        ctk.CTkButton(self.ctrl, text="Clear", fg_color="#993333", width=60, command=self.clear_data).pack(side="right", padx=10)

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Loaded Strains")
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.pack(fill="x", padx=30, pady=10); self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(self, text="Ready...")
        self.status_label.pack()

        self.run_btn = ctk.CTkButton(self, text="RUN ANALYSIS", state="disabled", height=40, command=self.start_thread)
        self.run_btn.pack(pady=15)

    #new strain button
    def add_strain_dialog(self):
        d = ctk.CTkInputDialog(text="Strain Name:", title="New Strain")
        name = d.get_input()
        if name and name not in self.experiment_data:
            self.experiment_data[name] = {}
            self.render_strain_ui(name)

    #render strain UI
    def render_strain_ui(self, name):
        f = ctk.CTkFrame(self.scroll_frame); f.pack(fill="x", pady=2, padx=5)
        ctk.CTkLabel(f, text=name, width=120, font=("Arial", 12, "bold")).pack(side="left", padx=10)
        lbl = ctk.CTkLabel(f, text="0 Wells Added", text_color="gray")
        lbl.pack(side="left", padx=20)
        ctk.CTkButton(f, text="Add Well", width=60, command=lambda n=name, l=lbl: self.add_well(n, l)).pack(side="right", padx=10)

    #add well button
    def add_well(self, name, lbl):
        files = filedialog.askopenfilenames(title=f"Select frames for {name}", filetypes=[("TIF files", "*.tif")])
        if files:
            norm_files = [os.path.normpath(f) for f in sorted(list(files))]
            wid = f"Well_{len(self.experiment_data[name])+1}"
            self.experiment_data[name][wid] = norm_files
            lbl.configure(text=f"{len(self.experiment_data[name])} Wells Loaded", text_color="#66CC66")
            self.run_btn.configure(state="normal")

    #clear data button
    def clear_data(self):
        self.experiment_data = {}
        for w in self.scroll_frame.winfo_children(): w.destroy()
        self.run_btn.configure(state="disabled"); self.progress_bar.set(0)
        self.status_label.configure(text="Ready...")

    #update progress bar and ETA
    def update_progress(self, done, total, start_time):
        perc = done / total
        self.progress_bar.set(perc)
        elapsed = time.time() - start_time
        eta = int((elapsed / done) * (total - done)) if done > 0 else 0
        mins, secs = divmod(eta, 60)
        self.status_label.configure(text=f"Progress: {int(perc*100)}% ({done}/{total}) | ETA: {mins}:{secs:02d}")
        self.update_idletasks()

    #start analysis thread
    def start_thread(self):
        try:
            k = int(self.blur_entry.get())
            c = float(self.crop_entry.get())
            b = int(self.buffer_entry.get())
            s = float(self.stddev_entry.get())
        except:
            self.status_label.configure(text="ERROR: Check input values!", text_color="red")
            return
            
        out = filedialog.askdirectory(title="Select Output Folder") if self.mask_switch.get() else None
        if self.mask_switch.get() and not out: return

        self.run_btn.configure(state="disabled")
        self.status_label.configure(text="Initializing Workers...")
        threading.Thread(target=self.run_analysis, args=(out, k, c, b, s), daemon=True).start()

    #passing inputs to engine
    def run_analysis(self, out, k, c, b, s):
        save = True if out else False
        data, dur = engine.run_full_analysis(self.experiment_data, save, out, self.update_progress, k, c, b, s)
        self.after(0, lambda: self.finalize_ui(data, dur))

    def finalize_ui(self, data, dur):
        self.run_btn.configure(state="normal")
        mins, secs = divmod(dur, 60)
        self.status_label.configure(text=f"Finished! Total Time: {mins}:{secs:02d}")
        engine.show_interactive_plot(data)

if __name__ == '__main__':
    multiprocessing.freeze_support()
    ctk.set_appearance_mode("System")
    app = BacteriaBouncerGUI()
    app.mainloop()