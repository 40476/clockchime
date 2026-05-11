import numpy as np
import sounddevice as sd
import argparse
import time
from datetime import datetime

SAMPLERATE = 44100

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

def synthesize_tone(freq, duration=1.5, volume=0.4, decay=3.0):
    t = np.linspace(0, duration, int(SAMPLERATE * duration), False)
    # Layered harmonics for a "bell" profile
    wave = (1.0 * np.sin(2 * np.pi * freq * t) + 
            0.4 * np.sin(2 * np.pi * freq * 2.01 * t) + 
            0.2 * np.sin(2 * np.pi * freq * 3.01 * t))
    
    envelope = np.exp(-decay * t)
    audio = wave * envelope * volume
    
    # Simple Soft Limiter to prevent "farting"/clipping
    audio = np.clip(audio, -0.9, 0.9)
    return (audio * 32767).astype(np.int16)

def play_chime_sequence(quarter, melody_tempo):
    if quarter not in SEQUENCES: return
    print(f"Chiming Quarter {quarter}...")
    for note in SEQUENCES[quarter]:
        audio = synthesize_tone(NOTES[note], duration=1.0, decay=4.0, volume=0.3)
        sd.play(audio, SAMPLERATE)
        time.sleep(melody_tempo) 
    time.sleep(0.8)

def strike_hour(hour, strike_tempo):
    strike_count = hour % 12
    if strike_count == 0: strike_count = 12
    print(f"Striking {strike_count} times...")
    
    # Deep gong tone
    gong_audio = synthesize_tone(NOTES['B'] / 2, duration=4.0, volume=0.5, decay=1.0)
    
    for _ in range(strike_count):
        sd.play(gong_audio, SAMPLERATE)
        time.sleep(strike_tempo)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Customizable Grandfather Clock")
    # Manual Triggers
    parser.add_argument("--test-hour", type=int, help="Trigger melody + X strikes")
    parser.add_argument("--test-q1", action="store_true", help="Manual 15 min chime")
    parser.add_argument("--test-q2", action="store_true", help="Manual 30 min chime")
    parser.add_argument("--test-q3", action="store_true", help="Manual 45 min chime")
    
    # Tempo Controls
    parser.add_argument("--m-tempo", type=float, default=0.6, help="Melody speed (seconds between notes). Default 0.6")
    parser.add_argument("--s-tempo", type=float, default=2.5, help="Strike speed (seconds between gongs). Default 2.5")
    
    # Daemon Flags
    parser.add_argument("--daemon", action="store_true", help="Run background monitor")
    parser.add_argument("--quarterly", action="store_true", help="Enable 15/45 chimes")
    parser.add_argument("--bi-hourly", action="store_true", help="Enable 30 min chimes")

    args = parser.parse_args()

    # Execution Logic
    if args.test_hour is not None:
        play_chime_sequence(4, args.m_tempo)
        strike_hour(args.test_hour, args.s_tempo)
    elif args.test_q1:
        play_chime_sequence(1, args.m_tempo)
    elif args.test_q2:
        play_chime_sequence(2, args.m_tempo)
    elif args.test_q3:
        play_chime_sequence(3, args.m_tempo)
    elif args.daemon:
        print("Daemon running. Press Ctrl+C to stop.")
        last_min = -1
        while True:
            now = datetime.now()
            if now.minute != last_min:
                if now.minute == 0:
                    play_chime_sequence(4, args.m_tempo)
                    strike_hour(now.hour, args.s_tempo)
                elif args.bi_hourly and now.minute == 30:
                    play_chime_sequence(2, args.m_tempo)
                elif args.quarterly and (now.minute == 15 or now.minute == 45):
                    play_chime_sequence(1 if now.minute == 15 else 3, args.m_tempo)
                last_min = now.minute
            time.sleep(5)
    else:
        parser.print_help()
