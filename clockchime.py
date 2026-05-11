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
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageDraw

# Tray library
try:
    import pystray
    from pystray import MenuItem as item
except ImportError:
    pystray = None

# Import winreg only on Windows
if sys.platform == "win32":
    import winreg
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

class ClockChimeApp:
    def __init__(self, root=None, headless=False, cli_args=None):
        self.root = root
        self.headless = headless
        
        # Paths (Cross-platform AppData)
        if sys.platform == "win32":
            self.appdata = Path(os.getenv('APPDATA')) / APP_NAME
        else:
            self.appdata = Path.home() / ".config" / APP_NAME
            
        self.appdata.mkdir(parents=True, exist_ok=True)
        self.config_file = self.appdata / "settings.json"
        
        # State
        self.is_running = False
        self.daemon_thread = None
        self.tray_icon = None
        
        # Default Settings
        self.settings = {
            "m_tempo": 0.6,
            "s_tempo": 2.5,
            "quarterly": True,
            "bi_hourly": True,
            "autostart": False,
            "volume": 0.3
        }
        self.load_settings()

        # Override settings with CLI args if provided
        if cli_args:
            if cli_args.m_tempo: self.settings["m_tempo"] = cli_args.m_tempo
            if cli_args.s_tempo: self.settings["s_tempo"] = cli_args.s_tempo
            if cli_args.quarterly: self.settings["quarterly"] = True
            if cli_args.bi_hourly: self.settings["bi_hourly"] = True

        if not self.headless:
            self.setup_ui()
            self.setup_tray()
            self.toggle_daemon()
        else:
            print(f"Starting {APP_NAME} in headless daemon mode...")
            self.is_running = True
            self.daemon_loop()

    def load_settings(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    self.settings.update(json.load(f))
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save_settings(self):
        if self.headless: return
        self.settings["m_tempo"] = float(self.m_tempo_var.get())
        self.settings["s_tempo"] = float(self.s_tempo_var.get())
        self.settings["quarterly"] = self.q_var.get()
        self.settings["bi_hourly"] = self.bh_var.get()
        if sys.platform == "win32":
            self.settings["autostart"] = self.auto_var.get()
        self.settings["volume"] = self.vol_var.get() / 100
        
        with open(self.config_file, 'w') as f:
            json.dump(self.settings, f)
        
        if sys.platform == "win32":
            self.update_registry(self.settings["autostart"])

    def update_registry(self, enable):
        if winreg is None: return
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if enable:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}"')
            else:
                try: winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError: pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Registry error: {e}")

    def create_tray_image(self):
        # Create a simple clock-like icon for the tray
        image = Image.new('RGB', (64, 64), color=(73, 109, 137))
        d = ImageDraw.Draw(image)
        d.ellipse([10, 10, 54, 54], fill=(255, 255, 255), outline=(0, 0, 0))
        d.line([32, 32, 32, 15], fill=(0, 0, 0), width=3)
        d.line([32, 32, 45, 32], fill=(0, 0, 0), width=3)
        return image

    def setup_tray(self):
        if not pystray: return
        menu = (item('Show', self.show_window), item('Exit', self.quit_app))
        self.tray_icon = pystray.Icon("name", self.create_tray_image(), APP_NAME, menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        
        # Override window close behavior
        self.root.protocol('WM_DELETE_WINDOW', self.hide_window)

    def show_window(self):
        self.root.after(0, self.root.deiconify)

    def hide_window(self):
        self.root.withdraw()

    def quit_app(self):
        self.is_running = False
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.destroy)
        sys.exit(0)

    def setup_ui(self):
        padding = {'padx': 20, 'pady': 10}
        
        frame = ttk.LabelFrame(self.root, text="Settings")
        frame.pack(fill="both", expand=True, **padding)

        ttk.Label(frame, text="Melody Tempo (s):").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.m_tempo_var = tk.StringVar(value=str(self.settings["m_tempo"]))
        ttk.Entry(frame, textvariable=self.m_tempo_var, width=10).grid(row=0, column=1, padx=5)

        ttk.Label(frame, text="Strike Tempo (s):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.s_tempo_var = tk.StringVar(value=str(self.settings["s_tempo"]))
        ttk.Entry(frame, textvariable=self.s_tempo_var, width=10).grid(row=1, column=1, padx=5)

        ttk.Label(frame, text="Volume:").grid(row=2, column=0, sticky="w", padx=5)
        self.vol_var = tk.IntVar(value=int(self.settings["volume"] * 100))
        ttk.Scale(frame, from_=0, to=100, variable=self.vol_var, orient="horizontal").grid(row=2, column=1, sticky="ew", padx=5)

        self.q_var = tk.BooleanVar(value=self.settings["quarterly"])
        ttk.Checkbutton(frame, text="Enable 15/45m Chimes", variable=self.q_var).grid(row=3, column=0, columnspan=2, sticky="w", padx=5)

        self.bh_var = tk.BooleanVar(value=self.settings["bi_hourly"])
        ttk.Checkbutton(frame, text="Enable 30m Chimes", variable=self.bh_var).grid(row=4, column=0, columnspan=2, sticky="w", padx=5)

        if sys.platform == "win32":
            self.auto_var = tk.BooleanVar(value=self.settings["autostart"])
            ttk.Checkbutton(frame, text="Start with Windows", variable=self.auto_var).grid(row=5, column=0, columnspan=2, sticky="w", padx=5)

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", **padding)

        self.run_btn = ttk.Button(btn_frame, text="Start Clock", command=self.toggle_daemon)
        self.run_btn.pack(side="left", expand=True, fill="x", padx=2)
        
        ttk.Button(btn_frame, text="Save Settings", command=self.save_settings).pack(side="left", expand=True, fill="x", padx=2)

        ttk.Button(self.root, text="Test Full Chime", command=lambda: threading.Thread(target=self.test_chime).start()).pack(fill="x", padx=20, pady=5)
        ttk.Label(self.root, text="Note: Closing the window hides it to the tray.", font=("", 8)).pack(pady=2)

    def synthesize_tone(self, freq, duration=1.5, decay=3.0):
        t = np.linspace(0, duration, int(SAMPLERATE * duration), False)
        wave = (1.0 * np.sin(2 * np.pi * freq * t) + 
                0.4 * np.sin(2 * np.pi * freq * 2.01 * t) + 
                0.2 * np.sin(2 * np.pi * freq * 3.01 * t))
        envelope = np.exp(-decay * t)
        audio = wave * envelope * self.settings["volume"]
        audio = np.clip(audio, -0.9, 0.9)
        return (audio * 32767).astype(np.int16)

    def play_sequence(self, quarter):
        if quarter not in SEQUENCES: return
        for note in SEQUENCES[quarter]:
            audio = self.synthesize_tone(NOTES[note], duration=1.0, decay=4.0)
            sd.play(audio, SAMPLERATE)
            time.sleep(self.settings["m_tempo"])
        time.sleep(0.8)

    def strike_hour(self, hour):
        count = hour % 12
        if count == 0: count = 12
        gong = self.synthesize_tone(NOTES['B'] / 2, duration=4.0, decay=1.0)
        for _ in range(count):
            sd.play(gong, SAMPLERATE)
            time.sleep(self.settings["s_tempo"])

    def test_chime(self, hour=None):
        self.play_sequence(4)
        h = hour if hour is not None else datetime.now().hour
        self.strike_hour(h)

    def daemon_loop(self):
        last_min = -1
        while self.is_running:
            now = datetime.now()
            if now.minute != last_min:
                if now.minute == 0:
                    self.play_sequence(4)
                    self.strike_hour(now.hour)
                elif self.settings["bi_hourly"] and now.minute == 30:
                    self.play_sequence(2)
                elif self.settings["quarterly"] and (now.minute == 15 or now.minute == 45):
                    self.play_sequence(1 if now.minute == 15 else 3)
                last_min = now.minute
            time.sleep(5)

    def toggle_daemon(self):
        if not self.is_running:
            self.is_running = True
            if not self.headless: self.run_btn.config(text="Stop Clock")
            self.daemon_thread = threading.Thread(target=self.daemon_loop, daemon=True)
            self.daemon_thread.start()
        else:
            self.is_running = False
            if not self.headless: self.run_btn.config(text="Start Clock")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ClockChime Daemon/GUI")
    parser.add_argument("--daemon", action="store_true", help="Run in headless mode")
    parser.add_argument("--test-hour", type=int, help="Trigger melody + X strikes")
    parser.add_argument("--test-q1", action="store_true", help="Manual 15 min chime")
    parser.add_argument("--test-q2", action="store_true", help="Manual 30 min chime")
    parser.add_argument("--test-q3", action="store_true", help="Manual 45 min chime")
    parser.add_argument("--m-tempo", type=float, help="Melody speed override")
    parser.add_argument("--s-tempo", type=float, help="Strike speed override")
    parser.add_argument("--quarterly", action="store_true", help="Enable 15/45 chimes")
    parser.add_argument("--bi-hourly", action="store_true", help="Enable 30 min chimes")

    args = parser.parse_args()

    if any([args.test_hour is not None, args.test_q1, args.test_q2, args.test_q3]):
        app = ClockChimeApp(headless=True, cli_args=args)
        if args.test_hour is not None:
            app.test_chime(hour=args.test_hour)
        elif args.test_q1: app.play_sequence(1)
        elif args.test_q2: app.play_sequence(2)
        elif args.test_q3: app.play_sequence(3)
        sys.exit(0)

    if args.daemon:
        app = ClockChimeApp(headless=True, cli_args=args)
    else:
        root = tk.Tk()
        app = ClockChimeApp(root=root, headless=False, cli_args=args)
        root.mainloop()
