import threading
import time
import cv2
import mediapipe as mp
import pyautogui
import customtkinter as ctk
import math
from collections import deque

# Eye tracking worker encapsulated for start/stop
class EyeTracker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._running = threading.Event()
        self._stop = threading.Event()
        self.screen_width, self.screen_height = pyautogui.size()
        self.cap = None
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(refine_landmarks=True, max_num_faces=1)
        self.LEFT_EYE = [33, 160, 158, 133, 153, 144]
        self.RIGHT_EYE = [362, 385, 387, 263, 373, 380]
        # Blink thresholds (independent, adjustable via UI)
        self.EAR_THRESHOLD_LEFT = 0.22
        self.EAR_THRESHOLD_RIGHT = 0.22
        # Cursor movement gain (sensitivity multiplier adjustable via UI)
        self.MOVEMENT_GAIN = 1.0
        self.MIN_CONSEC_FRAMES = 2
        self.CLICK_COOLDOWN = 0.5
        self.left_counter = 0
        self.right_counter = 0
        self.last_left_click = 0
        self.last_right_click = 0
        self.ear_queue_left = deque(maxlen=5)
        self.ear_queue_right = deque(maxlen=5)

    def run(self):
        pyautogui.FAILSAFE = False
        self.cap = cv2.VideoCapture(0)
        while not self._stop.is_set():
            if not self._running.is_set():
                time.sleep(0.05)
                continue
            ret, frame = self.cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb)
            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark
                # Cursor control
                left_center = landmarks[473]
                right_center = landmarks[468]
                eye_x = (left_center.x + right_center.x) / 2
                eye_y = (left_center.y + right_center.y) / 2
                x_range = (0.375, 0.625)
                y_range = (0.375, 0.625)
                eye_x = max(min(eye_x, x_range[1]), x_range[0])
                eye_y = max(min(eye_y, y_range[1]), y_range[0])
                norm_x = (eye_x - x_range[0]) / (x_range[1] - x_range[0])
                norm_y = (eye_y - y_range[0]) / (y_range[1] - y_range[0])
                # Apply movement gain (clamp for safety)
                gain = max(0.1, min(2.0, self.MOVEMENT_GAIN))
                target_x = int(norm_x * self.screen_width * gain)
                target_y = int(norm_y * self.screen_height * gain)
                # Clamp to screen
                target_x = max(0, min(self.screen_width - 1, target_x))
                target_y = max(0, min(self.screen_height - 1, target_y))
                pyautogui.moveTo(target_x, target_y)
                # EAR
                ear_left = self._ear(landmarks, self.LEFT_EYE)
                ear_right = self._ear(landmarks, self.RIGHT_EYE)
                self.ear_queue_left.append(ear_left)
                self.ear_queue_right.append(ear_right)
                avg_ear_left = sum(self.ear_queue_left) / len(self.ear_queue_left)
                avg_ear_right = sum(self.ear_queue_right) / len(self.ear_queue_right)
                now = time.time()
                # Left
                if avg_ear_left < self.EAR_THRESHOLD_LEFT:
                    self.left_counter += 1
                else:
                    if self.left_counter >= self.MIN_CONSEC_FRAMES and now - self.last_left_click > self.CLICK_COOLDOWN:
                        pyautogui.click(button='left')
                        self.last_left_click = now
                    self.left_counter = 0
                # Right
                if avg_ear_right < self.EAR_THRESHOLD_RIGHT:
                    self.right_counter += 1
                else:
                    if self.right_counter >= self.MIN_CONSEC_FRAMES and now - self.last_right_click > self.CLICK_COOLDOWN:
                        pyautogui.click(button='right')
                        self.last_right_click = now
                    self.right_counter = 0
            cv2.waitKey(1)
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()

    def start_tracking(self):
        self._running.set()

    def pause_tracking(self):
        self._running.clear()

    def stop(self):
        self._stop.set()
        self._running.set()  # wake thread

    @staticmethod
    def _euclidean(p1, p2):
        return math.hypot(p1.x - p2.x, p1.y - p2.y)

    def _ear(self, landmarks, indices):
        p1, p2, p3, p4, p5, p6 = [landmarks[i] for i in indices]
        vertical1 = self._euclidean(p2, p6)
        vertical2 = self._euclidean(p3, p5)
        horizontal = self._euclidean(p1, p4)
        return (vertical1 + vertical2) / (2.0 * horizontal)


class ControlBar(ctk.CTk):
    def __init__(self, tracker: EyeTracker):
        super().__init__()
        self.tracker = tracker
        self.title("EyeOS Control")
        self.geometry("600x70")
        self.resizable(False, False)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Key bindings
        self.bind('<space>', lambda e: self._toggle())
        self.bind('<Escape>', lambda e: self._on_close())
        self.settings_window = None

    def _build(self):
        bar = ctk.CTkFrame(self)
        bar.pack(fill="both", expand=True, padx=8, pady=8)

        self.toggle_btn = ctk.CTkButton(bar, text="Start", width=100, command=self._toggle)
        self.toggle_btn.pack(side="left", padx=4)

        self.status_label = ctk.CTkLabel(bar, text="Status: Idle")
        self.status_label.pack(side="left", padx=10)
        self.settings_btn = ctk.CTkButton(bar, text="Settings", command=self._open_settings)
        self.settings_btn.pack(side="left", padx=4)

        self.quit_btn = ctk.CTkButton(bar, text="Quit", fg_color="#9b1c1c", command=self._on_close)
        self.quit_btn.pack(side="right", padx=4)

    def _toggle(self):
        if self.tracker._running.is_set():
            self.tracker.pause_tracking()
            self.toggle_btn.configure(text="Start")
            self.status_label.configure(text="Status: Paused")
        else:
            self.tracker.start_tracking()
            self.toggle_btn.configure(text="Pause")
            self.status_label.configure(text="Status: Running")

    def _on_close(self):
        self.tracker.stop()
        self.destroy()

    # Settings window
    def _open_settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.focus_force()
            return
        win = ctk.CTkToplevel(self)
        win.title("Settings")
        win.geometry("360x350")
        win.resizable(False, False)
        self.settings_window = win

        # Left blink sensitivity slider
        left_frame = ctk.CTkFrame(win)
        left_frame.pack(fill='x', padx=10, pady=(10,5))
        ctk.CTkLabel(left_frame, text="Left Blink Threshold").pack(anchor='w', padx=5, pady=5)
        self.left_value_lbl = ctk.CTkLabel(left_frame, text=f"{self.tracker.EAR_THRESHOLD_LEFT:.2f}")
        self.left_value_lbl.pack(anchor='e', padx=5, pady=5)
        left_slider = ctk.CTkSlider(left_frame, from_=0.1, to=0.5, number_of_steps=50, command=self._update_left_threshold)
        left_slider.set(self.tracker.EAR_THRESHOLD_LEFT)
        left_slider.pack(fill='x', padx=5, pady=5)

        # Right blink sensitivity slider
        right_frame = ctk.CTkFrame(win)
        right_frame.pack(fill='x', padx=10, pady=5)
        ctk.CTkLabel(right_frame, text="Right Blink Threshold").pack(anchor='w', padx=5, pady=5)
        self.right_value_lbl = ctk.CTkLabel(right_frame, text=f"{self.tracker.EAR_THRESHOLD_RIGHT:.2f}")
        self.right_value_lbl.pack(anchor='e', padx=5, pady=5)
        right_slider = ctk.CTkSlider(right_frame, from_=0.1, to=0.5, number_of_steps=50, command=self._update_right_threshold)
        right_slider.set(self.tracker.EAR_THRESHOLD_RIGHT)
        right_slider.pack(fill='x', padx=5, pady=5)

        # Head movement sensitivity
        move_frame = ctk.CTkFrame(win)
        move_frame.pack(fill='x', padx=10, pady=5)
        ctk.CTkLabel(move_frame, text="Head Movement Sensitivity").pack(anchor='w', padx=5, pady=5)
        self.move_value_lbl = ctk.CTkLabel(move_frame, text=f"{self.tracker.MOVEMENT_GAIN:.2f}")
        self.move_value_lbl.pack(anchor='e', padx=5, pady=5)
        move_slider = ctk.CTkSlider(move_frame, from_=0.3, to=1.5, number_of_steps=60, command=self._update_movement_gain)
        move_slider.set(self.tracker.MOVEMENT_GAIN)
        move_slider.pack(fill='x', padx=5, pady=5)

    def _update_left_threshold(self, value):
        self.tracker.EAR_THRESHOLD_LEFT = float(value)
        if hasattr(self, 'left_value_lbl'):
            self.left_value_lbl.configure(text=f"{float(value):.2f}")

    def _update_right_threshold(self, value):
        self.tracker.EAR_THRESHOLD_RIGHT = float(value)
        if hasattr(self, 'right_value_lbl'):
            self.right_value_lbl.configure(text=f"{float(value):.2f}")

    def _update_movement_gain(self, value):
        self.tracker.MOVEMENT_GAIN = float(value)
        if hasattr(self, 'move_value_lbl'):
            self.move_value_lbl.configure(text=f"{float(value):.2f}")


def main():
    tracker = EyeTracker()
    tracker.start()  # thread starts in paused state
    app = ControlBar(tracker)
    app.mainloop()


if __name__ == "__main__":
    main()
