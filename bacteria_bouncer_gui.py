import customtkinter as ctk
from tkinter import filedialog
import os
import sys
import multiprocessing
import threading
import time
import re
import bacteria_bouncer_engine as engine
import bacteria_bouncer_config as config 

class BacteriaBouncerGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Bacteria Bouncer v1.3")
        self.geometry("1120x560")
        
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
        self.strain_widgets = {}
        self.image_folder = None
        self.folder_well_index = {}
        self.baseline_strain = None
        self.analysis_running = False
        self.abort_requested = False
        self.setup_ui()

    def setup_ui(self):
        self.label = ctk.CTkLabel(self, text="Bacteria Bouncer", font=("Arial", 24, "bold"))
        self.label.pack(pady=15)

        self.ctrl = ctk.CTkFrame(self)
        self.ctrl.pack(fill="x", padx=20, pady=5)

        ctk.CTkButton(self.ctrl, text="Add Strain", width=100, command=self.add_strain_dialog).pack(side="left", padx=10)
        ctk.CTkButton(self.ctrl, text="Load Image Folder", width=130, command=self.select_image_folder).pack(side="left", padx=5)
        self.folder_label = ctk.CTkLabel(self.ctrl, text="No folder selected", text_color="gray")
        self.folder_label.pack(side="left", padx=(5, 15))
        
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
        baseline_btn = ctk.CTkButton(
            f,
            text="",
            width=18,
            height=18,
            corner_radius=9,
            fg_color="#777777",
            hover_color="#5f5f5f",
            command=lambda n=name: self.set_baseline_strain(n),
        )
        baseline_btn.pack(side="left", padx=(10, 6))
        ctk.CTkLabel(f, text=name, width=95, font=("Arial", 12, "bold")).pack(side="left", padx=10)
        lbl = ctk.CTkLabel(f, text="0 Wells Added", text_color="gray")
        lbl.pack(side="left", padx=20)
        ctk.CTkButton(f, text="Add Well", width=70, command=lambda n=name: self.add_well(n)).pack(side="left", padx=10)
        selected_well = ctk.StringVar(value="No Wells")
        well_menu = ctk.CTkOptionMenu(f, values=["No Wells"], variable=selected_well, width=105, state="disabled")
        well_menu.pack(side="left", padx=10)
        ctk.CTkButton(f, text="Delete Well", width=90, fg_color="#993333",
                      command=lambda n=name: self.delete_selected_well(n)).pack(side="left", padx=10)
        auto_entry = ctk.CTkEntry(f, width=200, placeholder_text="A1, A2, A3")
        auto_entry.pack(side="left", padx=10)
        ctk.CTkButton(f, text="Auto Load", width=80, command=lambda n=name: self.auto_load_wells(n)).pack(side="left", padx=10)
        ctk.CTkButton(f, text="Delete Strain", width=95, fg_color="#7A2E2E",
                      command=lambda n=name: self.delete_strain(n)).pack(side="left", padx=10)
        self.strain_widgets[name] = {
            "frame": f,
            "baseline_btn": baseline_btn,
            "label": lbl,
            "menu": well_menu,
            "selected": selected_well,
            "auto_entry": auto_entry,
        }
        if self.baseline_strain is None:
            self.baseline_strain = name
        self.refresh_baseline_buttons()
        self.refresh_strain_controls(name)

    def set_baseline_strain(self, name):
        if name not in self.experiment_data:
            return
        self.baseline_strain = name
        self.refresh_baseline_buttons()
        self.status_label.configure(text=f"Baseline strain set to {name}", text_color="white")

    def refresh_baseline_buttons(self):
        for strain_name, widgets in self.strain_widgets.items():
            is_selected = strain_name == self.baseline_strain
            widgets["baseline_btn"].configure(
                fg_color="#33AA55" if is_selected else "#777777",
                hover_color="#2b8c47" if is_selected else "#5f5f5f"
            )

    def select_image_folder(self):
        folder = filedialog.askdirectory(title="Select Folder With All Well Images")
        if not folder:
            return

        folder = os.path.normpath(folder)
        self.image_folder = folder
        self.folder_well_index = self.index_well_images(folder)
        folder_name = os.path.basename(folder) or folder
        self.folder_label.configure(text=folder_name, text_color="#66CC66")

        well_count = len(self.folder_well_index)
        tif_count = sum(len(files) for files in self.folder_well_index.values())
        self.status_label.configure(
            text=f"Loaded folder: {folder_name} | {well_count} wells | {tif_count} frames",
            text_color="white"
        )

    def index_well_images(self, folder):
        index = {}
        for entry in os.scandir(folder):
            if not entry.is_file():
                continue

            lower_name = entry.name.lower()
            if not (lower_name.endswith(".tif") or lower_name.endswith(".tiff")):
                continue

            well_code = self.extract_well_code(entry.name)
            if not well_code:
                continue

            index.setdefault(well_code, []).append(os.path.normpath(entry.path))

        for well_code, files in index.items():
            index[well_code] = sorted(files, key=self.frame_sort_key)
        return index

    def extract_well_code(self, filename):
        match = re.match(r'^([A-Za-z]+\d+)_', filename)
        if not match:
            return None
        return match.group(1).upper()

    def frame_sort_key(self, path):
        filename = os.path.basename(path)
        match = re.search(r'_(\d+)\.(?:tif|tiff)$', filename, re.IGNORECASE)
        if match:
            return (int(match.group(1)), filename.lower())
        return (float("inf"), filename.lower())

    def parse_well_codes(self, raw_text):
        parts = re.split(r'[\s,]+', raw_text.strip())
        seen = set()
        ordered = []
        for part in parts:
            if not part:
                continue
            well_code = part.upper()
            if well_code in seen:
                continue
            seen.add(well_code)
            ordered.append(well_code)
        return ordered

    def get_next_well_id(self, name):
        #finding next open well number
        existing = self.experiment_data.get(name, {})
        used = []
        for well_id in existing:
            try:
                used.append(int(well_id.split("_")[-1]))
            except ValueError:
                continue

        next_num = 1
        while next_num in used:
            next_num += 1
        return f"Well_{next_num}"

    def refresh_strain_controls(self, name):
        widgets = self.strain_widgets.get(name)
        if not widgets:
            self.refresh_run_button()
            return

        #sorting wells in numeric order
        def well_sort_key(wid):
            manual_match = re.match(r'^Well_(\d+)$', wid, re.IGNORECASE)
            if manual_match:
                return (0, int(manual_match.group(1)), wid)

            plate_match = re.match(r'^([A-Za-z]+)(\d+)$', wid)
            if plate_match:
                return (1, plate_match.group(1).upper(), int(plate_match.group(2)), wid)

            return (2, wid.upper(), wid)

        well_ids = sorted(
            self.experiment_data.get(name, {}).keys(),
            key=well_sort_key
        )
        well_count = len(well_ids)
        label = widgets["label"]
        menu = widgets["menu"]
        selected = widgets["selected"]

        if well_count == 0:
            label.configure(text="0 Wells Added", text_color="gray")
            menu.configure(values=["No Wells"], state="disabled")
            selected.set("No Wells")
        else:
            label.configure(text=f"{well_count} Wells Loaded", text_color="#66CC66")
            menu.configure(values=well_ids, state="normal")
            if selected.get() not in well_ids:
                selected.set(well_ids[0])

        self.refresh_run_button()

    #keeping run button synced to loaded wells
    def refresh_run_button(self):
        if self.analysis_running:
            self.run_btn.configure(state="normal", text="ABORT ANALYSIS", command=self.abort_analysis, fg_color="#993333")
            return
        has_wells = any(wells for wells in self.experiment_data.values())
        self.run_btn.configure(
            state="normal" if has_wells else "disabled",
            text="RUN ANALYSIS",
            command=self.start_thread,
            fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"]
        )

    #add well button
    def add_well(self, name):
        files = filedialog.askopenfilenames(title=f"Select frames for {name}", filetypes=[("TIF files", "*.tif")])
        if files:
            norm_files = sorted((os.path.normpath(f) for f in files), key=self.frame_sort_key)
            wid = self.get_next_well_id(name)
            self.experiment_data[name][wid] = norm_files
            self.refresh_strain_controls(name)

    def auto_load_wells(self, name):
        if not self.image_folder or not self.folder_well_index:
            self.status_label.configure(text="ERROR: Load the image folder first.", text_color="red")
            return

        widgets = self.strain_widgets.get(name)
        if not widgets:
            return

        requested_wells = self.parse_well_codes(widgets["auto_entry"].get())
        if not requested_wells:
            self.status_label.configure(text=f"ERROR: Enter well names for {name} like A1, A2, A3.", text_color="red")
            return

        loaded = 0
        missing = []
        for well_code in requested_wells:
            files = self.folder_well_index.get(well_code)
            if not files:
                missing.append(well_code)
                continue
            self.experiment_data[name][well_code] = list(files)
            loaded += 1

        self.refresh_strain_controls(name)

        if loaded == 0:
            self.status_label.configure(
                text=f"No matching files found for {name}. Missing: {', '.join(missing)}",
                text_color="red"
            )
            return

        status = f"Loaded {loaded} wells for {name}"
        if missing:
            status += f" | Missing: {', '.join(missing)}"
        self.status_label.configure(text=status, text_color="white")

    def delete_selected_well(self, name):
        widgets = self.strain_widgets.get(name)
        if not widgets:
            return

        #removing selected well from strain
        well_id = widgets["selected"].get()
        if well_id in self.experiment_data.get(name, {}):
            del self.experiment_data[name][well_id]
            self.refresh_strain_controls(name)

    #delete strain button
    def delete_strain(self, name):
        widgets = self.strain_widgets.pop(name, None)
        if widgets:
            widgets["frame"].destroy()
        if name in self.experiment_data:
            del self.experiment_data[name]
        if self.baseline_strain == name:
            self.baseline_strain = next(iter(self.experiment_data), None)
        self.refresh_baseline_buttons()
        self.refresh_run_button()

    #abort analysis button
    def abort_analysis(self):
        self.abort_requested = True
        self.status_label.configure(text="Aborting Analysis...")

    #clear data button
    def clear_data(self):
        self.experiment_data = {}
        self.strain_widgets = {}
        self.image_folder = None
        self.folder_well_index = {}
        self.baseline_strain = None
        for w in self.scroll_frame.winfo_children(): w.destroy()
        self.folder_label.configure(text="No folder selected", text_color="gray")
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
        if self.analysis_running:
            self.abort_analysis()
            return

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

        self.analysis_running = True
        self.abort_requested = False
        self.refresh_run_button()
        self.status_label.configure(text="Initializing Workers...")
        threading.Thread(target=self.run_analysis, args=(out, k, c, b, s), daemon=True).start()

    #passing inputs to engine
    def run_analysis(self, out, k, c, b, s):
        save = True if out else False
        data, dur, aborted = engine.run_full_analysis(
            self.experiment_data,
            save,
            out,
            self.update_progress,
            lambda: self.abort_requested,
            k, c, b, s
        )
        self.after(0, lambda: self.finalize_ui(data, dur, aborted))

    def finalize_ui(self, data, dur, aborted):
        self.analysis_running = False
        self.abort_requested = False
        self.refresh_run_button()
        mins, secs = divmod(dur, 60)
        if aborted:
            self.status_label.configure(text=f"Analysis Aborted After: {mins}:{secs:02d}")
            self.progress_bar.set(0)
            return
        self.status_label.configure(text=f"Finished! Total Time: {mins}:{secs:02d}")
        engine.show_interactive_plot(data, self.baseline_strain)

if __name__ == '__main__':
    multiprocessing.freeze_support()
    ctk.set_appearance_mode("System")
    app = BacteriaBouncerGUI()
    app.mainloop()
