# backend/settings/pedal.py
import time

class PedalHandler:
    def __init__(self):
        self.last_press_time = 0.0
        self.tap_times = []
        self.is_holding = False

        # Tunables
        self.DOUBLE_TAP_WINDOW = 0.35
        self.HOLD_THRESHOLD = 0.5

    def key_down(self):
        now = time.time()
        self.last_press_time = now
        self.is_holding = True

    def key_up(self):
        now = time.time()
        duration = now - self.last_press_time
        self.is_holding = False

        # HOLD
        if duration >= self.HOLD_THRESHOLD:
            self.tap_times.clear()
            return "HOLD"

        # TAP
        self.tap_times.append(now)

        # Clean old taps
        self.tap_times = [
            t for t in self.tap_times
            if now - t <= self.DOUBLE_TAP_WINDOW
        ]

        count = len(self.tap_times)

        if count == 1:
            return "SINGLE"
        elif count == 2:
            return "DOUBLE"
        elif count >= 3:
            self.tap_times.clear()
            return "TRIPLE"

        return None
