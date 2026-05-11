import numpy as np
import sounddevice as sd
import time
import json
import os
import sys
import threading
import argparse
from datetime import datetime
from pathlib import Path
from scipy.io import wavfile
from scipy import signal

# High-DPI Awareness for Windows 10/11
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# Constants
SAMPLERATE = 44100
APP_NAME = "ClockChime"
# Westminster Chime Notes in Hz
NOTES = {
    'G_sharp': 415.30,
    'F_sharp': 369.99,
    'E': 329.63,
    'B': 246.94
}
SEQUENCES = {
    1: ['G_sharp', 'F_sharp', 'E', 'B'],
    2: ['E', 'G_sharp', 'F_sharp', 'B', 'E', 'F_sharp', 'G_sharp', 'E'],
    3: ['G_sharp', 'E', 'F_sharp', 'B', 'B', 'F_sharp', 'G_sharp', 'E', 'G_sharp', 'F_sharp', 'E', 'B'],
    4: ['E', 'G_sharp', 'F_sharp', 'B', 'E', 'F_sharp', 'G_sharp', 'E', 'G_sharp', 'E', 'F_sharp', 'B', 'B', 'F_sharp', 'G_sharp', 'E']
}

class ClockChimeCore:
    def __init__(self, config_path=None):
        if config_path:
            self.config_file = Path(config_path)
            self.appdata = self.config_file.parent
        else:
            if sys.platform == "win32":
                self.appdata = Path(os.getenv('APPDATA')) / APP_NAME
            elif sys.platform == "android":
                from android.storage import app_storage_path
                self.appdata = Path(app_storage_path())
            else:
                self.appdata = Path.home() / ".config" / APP_NAME
            self.config_file = self.appdata / "settings.json"
            
        self.appdata.mkdir(parents=True, exist_ok=True)
        
        self.is_running = False
        self.settings = {
            "m_tempo": 0.6,
            "s_tempo": 2.5,
            "quarterly": True,
            "bi_hourly": True,
            "autostart": False,
            "volume": 0.3,
            "filter": "none", 
            "custom_melody_path": "",
            "custom_strike_path": "",
            "m_base_freq": 415.30, 
            "s_base_freq": 246.94  
        }
        self.load_settings()

    def load_settings(self):
        """Loads settings from the config file if it exists."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    new_settings = json.load(f)
                    for k in self.settings.keys():
                        if k in new_settings:
                            self.settings[k] = new_settings[k]
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save_settings(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception: pass

    def detect_fundamental_freq(self, file_path):
        try:
            fs, data = wavfile.read(file_path)
            if len(data.shape) > 1: data = data[:, 0]
            start = int(len(data) * 0.1)
            end = min(int(len(data) * 0.6), start + 44100)
            segment = data[start:end]
            window = np.hanning(len(segment))
            sig = segment * window
            fft = np.abs(np.fft.rfft(sig))
            freqs = np.fft.rfftfreq(len(sig), 1.0/fs)
            idx = np.argmax(fft)
            return round(float(freqs[idx]), 2)
        except Exception:
            return 440.0

    def apply_filters(self, audio):
        f_type = self.settings.get("filter", "none")
        if f_type == "none": return audio.astype(np.int16)
        
        audio_f = audio.astype(float)
        
        if f_type == "8bit":
            steps = 16
            audio_f = np.round(audio_f / (32767 / steps)) * (32767 / steps)
            for i in range(0, len(audio_f), 4):
                audio_f[i:i+4] = audio_f[i]
        elif f_type == "vinyl":
            crackle = (np.random.rand(len(audio_f)) > 0.998).astype(float) * 5000
            audio_f += crackle
            b, a = signal.butter(2, 0.15, btype='low')
            audio_f = signal.lfilter(b, a, audio_f)
        elif f_type == "echo":
            delay_samples = int(SAMPLERATE * 0.2)
            echo = np.zeros_like(audio_f)
            echo[delay_samples:] = audio_f[:-delay_samples] * 0.4
            audio_f = (audio_f + echo) * 0.8
        elif f_type == "bitcrush":
            audio_f = np.clip(audio_f, -15000, 15000)
            audio_f = np.round(audio_f / 2000) * 2000
        elif f_type == "telephone":
            b, a = signal.butter(4, [0.05, 0.2], btype='bandpass')
            audio_f = signal.lfilter(b, a, audio_f)
        elif f_type == "lowpass":
            b, a = signal.butter(4, 0.1, btype='low')
            audio_f = signal.lfilter(b, a, audio_f)
        elif f_type == "highpass":
            b, a = signal.butter(2, 0.3, btype='high')
            audio_f = signal.lfilter(b, a, audio_f)
            
        return np.clip(audio_f, -32767, 32767).astype(np.int16)

    def process_custom_audio(self, data, target_freq, base_freq, target_duration):
        pitch_ratio = target_freq / (base_freq if base_freq > 0 else 440.0)
        new_sample_count = int(len(data) / pitch_ratio)
        pitched_data = signal.resample(data, new_sample_count)
        target_sample_count = int(target_duration * SAMPLERATE)
        if len(pitched_data) > target_sample_count:
            return pitched_data[:target_sample_count]
        return np.pad(pitched_data, (0, max(0, target_sample_count - len(pitched_data))))

    def get_audio_resource(self, freq, duration, custom_path=None, base_freq=440.0):
        if custom_path and os.path.exists(custom_path):
            try:
                fs, data = wavfile.read(custom_path)
                if len(data.shape) > 1: data = data[:, 0]
                data = data.astype(float) / (np.max(np.abs(data)) if np.max(np.abs(data)) != 0 else 1)
                processed = self.process_custom_audio(data, freq, base_freq, duration)
                audio = (processed * 32767 * self.settings["volume"]).astype(np.int16)
            except Exception:
                return self.synthesize_tone(freq, duration)
        else:
            audio = self.synthesize_tone(freq, duration)
        return self.apply_filters(audio)

    def synthesize_tone(self, freq, duration=1.5, decay=3.0):
        t = np.linspace(0, duration, int(SAMPLERATE * duration), False)
        wave = (1.0 * np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * freq * 2.01 * t))
        envelope = np.exp(-decay * t)
        audio = wave * envelope * (self.settings["volume"])
        return (np.clip(audio, -0.9, 0.9) * 32767).astype(np.int16)

    def play_sequence(self, quarter):
        if quarter not in SEQUENCES: return
        for note in SEQUENCES[quarter]:
            audio = self.get_audio_resource(NOTES[note], 1.0, 
                                           self.settings["custom_melody_path"], 
                                           self.settings["m_base_freq"])
            sd.play(audio, SAMPLERATE)
            time.sleep(self.settings["m_tempo"])
        time.sleep(0.5)

    def strike_hour(self, hour):
        count = hour % 12
        if count == 0: count = 12
        for _ in range(count):
            audio = self.get_audio_resource(NOTES['B'] / 2, 4.0, 
                                           self.settings["custom_strike_path"], 
                                           self.settings["s_base_freq"])
            sd.play(audio, SAMPLERATE)
            time.sleep(self.settings["s_tempo"])

    def check_trigger(self, minute, hour):
        self.load_settings()
        if minute == 0:
            self.play_sequence(4)
            self.strike_hour(hour)
        elif self.settings.get("bi_hourly") and minute == 30:
            self.play_sequence(2)
        elif self.settings.get("quarterly") and (minute == 15 or minute == 45):
            self.play_sequence(1 if minute == 15 else 3)

    def test_chime(self):
        """Plays a short test sequence and one strike."""
        threading.Thread(target=self._run_test, daemon=True).start()

    def _run_test(self):
        self.play_sequence(4)
        self.strike_hour(1)

    def daemon_loop(self):
        last_min = -1
        print(f"Daemon started using config: {self.config_file}")
        while self.is_running:
            now = datetime.now()
            if now.minute != last_min:
                self.check_trigger(now.minute, now.hour)
                last_min = now.minute
            time.sleep(5)

# --- DESKTOP UI ---
def run_desktop(headless=False, cli_overrides=None, config_path=None, run_test=False):
    import tkinter as tk
    from tkinter import messagebox, ttk, filedialog
    from PIL import Image
    try:
        import pystray
        from pystray import MenuItem as item
    except ImportError:
        pystray = None

    class DesktopApp(ClockChimeCore):
        def __init__(self, root):
            super().__init__(config_path=config_path)
            self.root = root
            self.unsaved_changes = False
            
            if cli_overrides:
                for key, value in cli_overrides.items():
                    if value is not None:
                        self.settings[key] = value

            if not headless:
                self.setup_ui()
                if pystray: self.setup_tray()
            
            if run_test:
                self.test_chime()
            
            if headless or not run_test:
                self.toggle_daemon()

        def mark_unsaved(self, *args):
            self.unsaved_changes = True
            self.save_btn.config(text="Save *")

        def setup_ui(self):
            self.root.title(f"{APP_NAME}")
            notebook = ttk.Notebook(self.root)
            notebook.pack(fill="both", expand=True, padx=10, pady=10)

            gen = ttk.Frame(notebook, padding=20)
            notebook.add(gen, text="General")
            
            vars_to_setup = [
                ("m_tempo", "Melody Tempo (s):", 0),
                ("s_tempo", "Strike Tempo (s):", 1)
            ]
            self.ui_vars = {}
            for key, label, row in vars_to_setup:
                ttk.Label(gen, text=label).grid(row=row, column=0, sticky="w", pady=5)
                var = tk.StringVar(value=str(self.settings[key]))
                var.trace_add("write", self.mark_unsaved)
                self.ui_vars[key] = var
                ttk.Entry(gen, textvariable=var, width=10).grid(row=row, column=1, padx=10)

            ttk.Label(gen, text="Volume:").grid(row=2, column=0, sticky="w", pady=5)
            self.vol_var = tk.IntVar(value=int(self.settings["volume"] * 100))
            ttk.Scale(gen, from_=0, to=100, variable=self.vol_var, orient="horizontal", command=self.mark_unsaved).grid(row=2, column=1, sticky="ew", padx=10)

            self.q_var = tk.BooleanVar(value=self.settings["quarterly"])
            ttk.Checkbutton(gen, text="Enable 15/45m", variable=self.q_var, command=self.mark_unsaved).grid(row=3, column=0, sticky="w")
            self.bh_var = tk.BooleanVar(value=self.settings["bi_hourly"])
            ttk.Checkbutton(gen, text="Enable 30m", variable=self.bh_var, command=self.mark_unsaved).grid(row=4, column=0, sticky="w")
            
            ttk.Label(gen, text="Filter:").grid(row=5, column=0, sticky="w", pady=5)
            self.filter_var = tk.StringVar(value=self.settings["filter"])
            filters = ["none", "8bit", "vinyl", "echo", "bitcrush", "telephone", "lowpass", "highpass"]
            self.filter_menu = ttk.OptionMenu(gen, self.filter_var, self.settings["filter"], *filters, command=self.mark_unsaved)
            self.filter_menu.grid(row=5, column=1, sticky="w", padx=10)

            adv = ttk.Frame(notebook, padding=20)
            notebook.add(adv, text="Sound Design")
            
            self.m_path_var = tk.StringVar(value=self.settings["custom_melody_path"])
            self.m_hz_var = tk.StringVar(value=str(self.settings["m_base_freq"]))
            self.s_path_var = tk.StringVar(value=self.settings["custom_strike_path"])
            self.s_hz_var = tk.StringVar(value=str(self.settings["s_base_freq"]))

            def add_path_row(frame, label, path_var, hz_var, row, key):
                ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
                ttk.Entry(frame, textvariable=path_var, width=15).grid(row=row, column=1)
                ttk.Button(frame, text="...", width=3, command=lambda: self.browse_file(key)).grid(row=row, column=2)
                ttk.Label(frame, text="Hz:").grid(row=row+1, column=0, sticky="e")
                ttk.Entry(frame, textvariable=hz_var, width=8).grid(row=row+1, column=1, sticky="w", padx=10)

            add_path_row(adv, "Melody WAV:", self.m_path_var, self.m_hz_var, 0, "custom_melody_path")
            add_path_row(adv, "Strike WAV:", self.s_path_var, self.s_hz_var, 2, "custom_strike_path")

            btns = ttk.Frame(self.root, padding=10)
            btns.pack(fill="x")
            self.run_btn = ttk.Button(btns, text="Stop Clock", command=self.toggle_daemon)
            self.run_btn.pack(side="left", padx=5)
            
            ttk.Button(btns, text="Test Chime", command=self.test_chime).pack(side="left", padx=5)
            
            self.save_btn = ttk.Button(btns, text="Save", command=self.save_desktop_settings)
            self.save_btn.pack(side="right", padx=5)

        def browse_file(self, setting_key):
            path = filedialog.askopenfilename(filetypes=[("WAV files", "*.wav")])
            if path:
                hz = self.detect_fundamental_freq(path)
                if setting_key == "custom_melody_path":
                    self.m_path_var.set(path)
                    self.m_hz_var.set(str(hz))
                else:
                    self.s_path_var.set(path)
                    self.s_hz_var.set(str(hz))
                self.mark_unsaved()

        def save_desktop_settings(self):
            try:
                self.settings["m_tempo"] = float(self.ui_vars["m_tempo"].get())
                self.settings["s_tempo"] = float(self.ui_vars["s_tempo"].get())
                self.settings["quarterly"] = self.q_var.get()
                self.settings["bi_hourly"] = self.bh_var.get()
                self.settings["volume"] = self.vol_var.get() / 100
                self.settings["filter"] = self.filter_var.get()
                self.settings["custom_melody_path"] = self.m_path_var.get()
                self.settings["custom_strike_path"] = self.s_path_var.get()
                self.settings["m_base_freq"] = float(self.m_hz_var.get())
                self.settings["s_base_freq"] = float(self.s_hz_var.get())
                self.save_settings()
                self.unsaved_changes = False
                self.save_btn.config(text="Save")
            except Exception as e:
                messagebox.showerror("Error", str(e))

        def toggle_daemon(self):
            if not self.is_running:
                self.is_running = True
                if hasattr(self, 'run_btn'): self.run_btn.config(text="Stop Clock")
                threading.Thread(target=self.daemon_loop, daemon=True).start()
            else:
                self.is_running = False
                if hasattr(self, 'run_btn'): self.run_btn.config(text="Start Clock")

        def setup_tray(self):
            image = Image.new('RGB', (64, 64), color=(73, 109, 137))
            menu = (item('Show', lambda: self.root.after(0, self.root.deiconify)), item('Exit', self.quit_app))
            self.tray_icon = pystray.Icon(APP_NAME, image, APP_NAME, menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
            self.root.protocol('WM_DELETE_WINDOW', lambda: self.root.withdraw())
        
        def quit_app(self):
            self.is_running = False
            if hasattr(self, 'tray_icon') and self.tray_icon: self.tray_icon.stop()
            self.root.quit()

    root = tk.Tk()
    if headless: root.withdraw()
    app = DesktopApp(root)
    root.mainloop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true", help="Run without UI")
    parser.add_argument("--config", type=str, help="Path to settings.json")
    parser.add_argument("--test", action="store_true", help="Play a test chime and exit")
    parser.add_argument("--m-tempo", type=float)
    parser.add_argument("--s-tempo", type=float)
    parser.add_argument("--quarterly", type=str, choices=['true', 'false'])
    parser.add_argument("--bi-hourly", type=str, choices=['true', 'false'])
    parser.add_argument("--filter", type=str)
    
    args = parser.parse_args()

    cli_quarterly = None if args.quarterly is None else args.quarterly.lower() == 'true'
    cli_bi_hourly = None if args.bi_hourly is None else args.bi_hourly.lower() == 'true'
    
    overrides = {
        "m_tempo": args.m_tempo, 
        "s_tempo": args.s_tempo,
        "quarterly": cli_quarterly,
        "bi_hourly": cli_bi_hourly,
        "filter": args.filter
    }

    # If test mode is on, we run the app logic then exit
    run_desktop(headless=args.daemon or args.test, 
                cli_overrides=overrides, 
                config_path=args.config, 
                run_test=args.test)