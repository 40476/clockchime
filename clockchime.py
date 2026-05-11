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
        for _ in range(count):
            audio = self.synthesize_tone(NOTES['B'] / 2, duration=4.0, decay=1.0)
            sd.play(audio, SAMPLERATE)
            time.sleep(self.settings["s_tempo"])

    def check_trigger(self, minute, hour):
        if minute == 0:
            self.play_sequence(4)
            self.strike_hour(hour)
        elif self.settings["bi_hourly"] and minute == 30:
            self.play_sequence(2)
        elif self.settings["quarterly"] and (minute == 15 or minute == 45):
            self.play_sequence(1 if minute == 15 else 3)

    def test_chime(self):
        """Plays a short test sequence and a single hour strike."""
        threading.Thread(target=self._run_test, daemon=True).start()

    def _run_test(self):
        self.play_sequence(4)
        gong = self.synthesize_tone(NOTES['B'] / 2, duration=4.0, decay=1.0)
        sd.play(gong, SAMPLERATE)

# --- DESKTOP UI (Tkinter) ---
def run_desktop(headless=False, cli_overrides=None):
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
            
            # Apply CLI overrides to settings if provided
            if cli_overrides:
                if cli_overrides.get("m_tempo") is not None:
                    self.settings["m_tempo"] = cli_overrides["m_tempo"]
                if cli_overrides.get("s_tempo") is not None:
                    self.settings["s_tempo"] = cli_overrides["s_tempo"]

            if not headless:
                self.setup_ui()
                if pystray: self.setup_tray()
            
            # Auto-start daemon
            self.toggle_daemon()

        def setup_ui(self):
            self.root.title(f"{APP_NAME} (Desktop)")
            style = ttk.Style()
            style.configure("TButton", padding=6)
            
            main_frame = ttk.Frame(self.root, padding="20")
            main_frame.pack(fill="both", expand=True)

            # Melody Tempo
            ttk.Label(main_frame, text="Melody Tempo (s):").grid(row=0, column=0, sticky="w", pady=5)
            self.m_tempo_var = tk.StringVar(value=str(self.settings["m_tempo"]))
            ttk.Entry(main_frame, textvariable=self.m_tempo_var, width=10).grid(row=0, column=1, padx=10)

            # Strike Tempo
            ttk.Label(main_frame, text="Strike Tempo (s):").grid(row=1, column=0, sticky="w", pady=5)
            self.s_tempo_var = tk.StringVar(value=str(self.settings["s_tempo"]))
            ttk.Entry(main_frame, textvariable=self.s_tempo_var, width=10).grid(row=1, column=1, padx=10)

            # Volume
            ttk.Label(main_frame, text="Volume:").grid(row=2, column=0, sticky="w", pady=5)
            self.vol_var = tk.IntVar(value=int(self.settings["volume"] * 100))
            ttk.Scale(main_frame, from_=0, to=100, variable=self.vol_var, orient="horizontal").grid(row=2, column=1, sticky="ew", padx=10)

            # Checkboxes
            self.q_var = tk.BooleanVar(value=self.settings["quarterly"])
            ttk.Checkbutton(main_frame, text="Enable 15/45m Chimes", variable=self.q_var).grid(row=3, column=0, columnspan=2, sticky="w")

            self.bh_var = tk.BooleanVar(value=self.settings["bi_hourly"])
            ttk.Checkbutton(main_frame, text="Enable 30m Chimes", variable=self.bh_var).grid(row=4, column=0, columnspan=2, sticky="w")

            if sys.platform == "win32":
                self.auto_var = tk.BooleanVar(value=self.settings["autostart"])
                ttk.Checkbutton(main_frame, text="Start with Windows", variable=self.auto_var).grid(row=5, column=0, columnspan=2, sticky="w")

            # Buttons
            btn_frame = ttk.Frame(main_frame)
            btn_frame.grid(row=6, column=0, columnspan=2, pady=20)

            self.run_btn = ttk.Button(btn_frame, text="Stop Clock", command=self.toggle_daemon)
            self.run_btn.pack(side="left", padx=5)
            
            ttk.Button(btn_frame, text="Test Chime", command=self.test_chime).pack(side="left", padx=5)
            
            ttk.Button(btn_frame, text="Save Settings", command=self.save_desktop_settings).pack(side="left", padx=5)

        def save_desktop_settings(self):
            try:
                self.settings["m_tempo"] = float(self.m_tempo_var.get())
                self.settings["s_tempo"] = float(self.s_tempo_var.get())
                self.settings["quarterly"] = self.q_var.get()
                self.settings["bi_hourly"] = self.bh_var.get()
                self.settings["volume"] = self.vol_var.get() / 100
                
                if sys.platform == "win32":
                    self.settings["autostart"] = self.auto_var.get()
                    self.update_registry(self.settings["autostart"])
                
                self.save_settings()
                messagebox.showinfo("Success", "Settings saved!")
            except Exception as e:
                messagebox.showerror("Error", f"Could not save: {e}")

        def update_registry(self, enable):
            if winreg is None: return
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                if enable:
                    exec_path = sys.executable if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
                    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exec_path)
                else:
                    try: winreg.DeleteValue(key, APP_NAME)
                    except FileNotFoundError: pass
                winreg.CloseKey(key)
            except Exception: pass

        def toggle_daemon(self):
            if not self.is_running:
                self.is_running = True
                if not headless: self.run_btn.config(text="Stop Clock")
                threading.Thread(target=self.daemon_loop, daemon=True).start()
            else:
                self.is_running = False
                if not headless: self.run_btn.config(text="Start Clock")

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
            menu = (item('Show', lambda: self.root.after(0, self.root.deiconify)), 
                    item('Exit', self.quit_app))
            self.tray_icon = pystray.Icon(APP_NAME, image, APP_NAME, menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
            self.root.protocol('WM_DELETE_WINDOW', lambda: self.root.withdraw())
        
        def quit_app(self):
            self.is_running = False
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.tray_icon.stop()
            self.root.quit()

    root = tk.Tk()
    if headless: root.withdraw()
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

            self.bh_switch = Switch(active=self.settings['bi_hourly'])
            layout.add_widget(Label(text="30m Chimes"))
            layout.add_widget(self.bh_switch)
            
            test_btn = Button(text="Test Chime", size_hint_y=None, height='50dp')
            test_btn.bind(on_press=lambda x: self.test_chime())
            layout.add_widget(test_btn)
            
            save_btn = Button(text="Save Settings", size_hint_y=None, height='50dp')
            save_btn.bind(on_press=self.apply_settings)
            layout.add_widget(save_btn)

            Clock.schedule_interval(self.update_tick, 30)
            return layout

        def apply_settings(self, instance):
            self.settings['volume'] = self.vol_slider.value
            self.settings['quarterly'] = self.q_switch.active
            self.settings['bi_hourly'] = self.bh_switch.active
            self.save_settings()

        def update_tick(self, dt):
            now = datetime.now()
            if now.second < 35:
                self.check_trigger(now.minute, now.hour)

    AndroidApp().run()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true", help="Run without UI")
    parser.add_argument("--test-hour", type=int, help="Test a specific hour chime (1-12)")
    parser.add_argument("--m-tempo", type=float, help="Override melody tempo")
    parser.add_argument("--s-tempo", type=float, help="Override strike tempo")
    args = parser.parse_args()

    if sys.platform == "android":
        run_android()
    elif args.test_hour is not None:
        # Direct CLI test mode
        core = ClockChimeCore()
        # Apply tempo overrides for this session
        if args.m_tempo: core.settings["m_tempo"] = args.m_tempo
        if args.s_tempo: core.settings["s_tempo"] = args.s_tempo
        
        print(f"Testing Hour: {args.test_hour}")
        core.play_sequence(4)
        core.strike_hour(args.test_hour)
    else:
        overrides = {"m_tempo": args.m_tempo, "s_tempo": args.s_tempo}
        run_desktop(headless=args.daemon, cli_overrides=overrides)