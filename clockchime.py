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

# High-DPI Awareness for Windows 10/11
if sys.platform == "win32":
    import winreg
    import ctypes
    try:
        # This prevents the "blurry" look on high-resolution Windows 11 screens
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
else:
    winreg = None

# Constants
SAMPLERATE = 44100
APP_NAME = "ClockChime"
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
    """Shared logic for sound synthesis and timing triggers."""
    def __init__(self):
        # Paths
        if sys.platform == "win32":
            self.appdata = Path(os.getenv('APPDATA')) / APP_NAME
        elif sys.platform == "android":
            from android.storage import app_storage_path
            self.appdata = Path(app_storage_path())
        else:
            self.appdata = Path.home() / ".config" / APP_NAME
            
        self.appdata.mkdir(parents=True, exist_ok=True)
        self.config_file = self.appdata / "settings.json"
        
        self.is_running = False
        self.settings = {
            "m_tempo": 0.6,
            "s_tempo": 2.5,
            "quarterly": True,
            "bi_hourly": True,
            "autostart": False,
            "volume": 0.3
        }
        self.load_settings()

    def load_settings(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    self.settings.update(json.load(f))
            except Exception: pass

    def save_settings(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f)
        except Exception: pass

    def synthesize_tone(self, freq, duration=1.5, decay=3.0):
        t = np.linspace(0, duration, int(SAMPLERATE * duration), False)
        wave = (1.0 * np.sin(2 * np.pi * freq * t) + 
                0.4 * np.sin(2 * np.pi * freq * 2.01 * t) + 
                0.2 * np.sin(2 * np.pi * freq * 3.01 * t))
        envelope = np.exp(-decay * t)
        audio = wave * envelope * (self.settings["volume"])
        return (np.clip(audio, -0.9, 0.9) * 32767).astype(np.int16)

    def play_sequence(self, quarter):
        if quarter not in SEQUENCES: return
        for note in SEQUENCES[quarter]:
            audio = self.synthesize_tone(NOTES[note], duration=1.0, decay=4.0)
            sd.play(audio, SAMPLERATE)
            time.sleep(self.settings["m_tempo"])
        time.sleep(0.5)

    def strike_hour(self, hour):
        count = hour % 12
        if count == 0: count = 12
        gong = self.synthesize_tone(NOTES['B'] / 2, duration=4.0, decay=1.0)
        for _ in range(count):
            sd.play(gong, SAMPLERATE)
            time.sleep(self.settings["s_tempo"])

    def check_trigger(self, minute, hour):
        if minute == 0:
            self.play_sequence(4)
            self.strike_hour(hour)
        elif self.settings["bi_hourly"] and minute == 30:
            self.play_sequence(2)
        elif self.settings["quarterly"] and (minute == 15 or minute == 45):
            self.play_sequence(1 if minute == 15 else 3)

# --- DESKTOP UI (Tkinter) ---
def run_desktop():
    import tkinter as tk
    from tkinter import messagebox, ttk
    from PIL import Image
    try:
        import pystray
        from pystray import MenuItem as item
    except ImportError:
        pystray = None

    class DesktopApp(ClockChimeCore):
        def __init__(self, root):
            super().__init__()
            self.root = root
            self.setup_ui()
            if pystray: self.setup_tray()
            self.toggle_daemon()

        def setup_ui(self):
            self.root.title(f"{APP_NAME} (Desktop)")
            main_frame = ttk.Frame(self.root, padding="20")
            main_frame.pack(fill="both", expand=True)

            self.m_tempo_var = tk.StringVar(value=str(self.settings["m_tempo"]))
            ttk.Label(main_frame, text="Melody Tempo:").grid(row=0, column=0, sticky="w")
            ttk.Entry(main_frame, textvariable=self.m_tempo_var).grid(row=0, column=1)

            self.vol_var = tk.IntVar(value=int(self.settings["volume"] * 100))
            ttk.Label(main_frame, text="Volume:").grid(row=1, column=0, sticky="w")
            ttk.Scale(main_frame, from_=0, to=100, variable=self.vol_var, orient="horizontal").grid(row=1, column=1, sticky="ew")

            self.q_var = tk.BooleanVar(value=self.settings["quarterly"])
            ttk.Checkbutton(main_frame, text="Quarterly Chimes", variable=self.q_var).grid(row=2, columnspan=2)

            self.run_btn = ttk.Button(main_frame, text="Stop Clock", command=self.toggle_daemon)
            self.run_btn.grid(row=3, column=0, pady=10)
            
            ttk.Button(main_frame, text="Save", command=self.save_desktop_settings).grid(row=3, column=1)

        def save_desktop_settings(self):
            self.settings["m_tempo"] = float(self.m_tempo_var.get())
            self.settings["quarterly"] = self.q_var.get()
            self.settings["volume"] = self.vol_var.get() / 100
            self.save_settings()
            messagebox.showinfo("Saved", "Settings updated!")

        def toggle_daemon(self):
            if not self.is_running:
                self.is_running = True
                self.run_btn.config(text="Stop Clock")
                threading.Thread(target=self.daemon_loop, daemon=True).start()
            else:
                self.is_running = False
                self.run_btn.config(text="Start Clock")

        def daemon_loop(self):
            last_min = -1
            while self.is_running:
                now = datetime.now()
                if now.minute != last_min:
                    self.check_trigger(now.minute, now.hour)
                    last_min = now.minute
                time.sleep(10)

        def setup_tray(self):
            image = Image.new('RGB', (64, 64), color=(73, 109, 137))
            menu = (item('Show', lambda: self.root.deiconify()), item('Exit', self.root.quit))
            self.tray_icon = pystray.Icon(APP_NAME, image, APP_NAME, menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
            self.root.protocol('WM_DELETE_WINDOW', lambda: self.root.withdraw())

    root = tk.Tk()
    DesktopApp(root)
    root.mainloop()

# --- ANDROID UI (Kivy) ---
def run_android():
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.label import Label
    from kivy.uix.switch import Switch
    from kivy.uix.slider import Slider
    from kivy.uix.button import Button
    from kivy.clock import Clock

    class AndroidApp(App, ClockChimeCore):
        def build(self):
            ClockChimeCore.__init__(self)
            layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
            
            layout.add_widget(Label(text=f"{APP_NAME} Android", font_size='24sp'))
            
            layout.add_widget(Label(text="Volume"))
            self.vol_slider = Slider(min=0, max=1, value=self.settings['volume'])
            layout.add_widget(self.vol_slider)
            
            self.q_switch = Switch(active=self.settings['quarterly'])
            layout.add_widget(Label(text="Quarterly Chimes"))
            layout.add_widget(self.q_switch)
            
            btn = Button(text="Save Settings", size_hint_y=None, height='50dp')
            btn.bind(on_press=self.apply_settings)
            layout.add_widget(btn)

            # Android 'Trigger' logic - checks every 30s
            Clock.schedule_interval(self.update_tick, 30)
            return layout

        def apply_settings(self, instance):
            self.settings['volume'] = self.vol_slider.value
            self.settings['quarterly'] = self.q_switch.active
            self.save_settings()

        def update_tick(self, dt):
            # This logic triggers sound based on time without a daemon loop
            now = datetime.now()
            if now.second < 35: # Only trigger at start of minute
                self.check_trigger(now.minute, now.hour)

    AndroidApp().run()

if __name__ == "__main__":
    if sys.platform == "android":
        run_android()
    else:
        run_desktop()
