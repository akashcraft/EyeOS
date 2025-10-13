import os
import cv2
import mediapipe as mp
import pyautogui
import time
import math
import threading
from collections import deque
import customtkinter as ctk
from PIL import Image
import tkinter.filedialog as fd
import global_var
import utilities

# ------------------- GLOBALS -------------------
pyautogui.FAILSAFE = False
screen_width, screen_height = pyautogui.size()

cap = None
tracking_active = threading.Event()
stop_event = threading.Event()

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True, max_num_faces=1)

# Eye indices
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# Settings (adjustable by UI)
EAR_THRESHOLD_LEFT = 0.22
EAR_THRESHOLD_RIGHT = 0.22
MOVEMENT_GAIN = 1.0

MIN_CONSEC_FRAMES = 2
CLICK_COOLDOWN = 0.5

# Blink counters
left_counter = 0
right_counter = 0
last_left_click = 0
last_right_click = 0

# EAR smoothing
ear_queue_left = deque(maxlen=5)
ear_queue_right = deque(maxlen=5)


# ------------------- HELPERS -------------------
def euclidean(p1, p2):
    return math.hypot(p1.x - p2.x, p1.y - p2.y)


def get_ear(landmarks, indices):
    p1, p2, p3, p4, p5, p6 = [landmarks[i] for i in indices]
    vertical1 = euclidean(p2, p6)
    vertical2 = euclidean(p3, p5)
    horizontal = euclidean(p1, p4)
    return (vertical1 + vertical2) / (2.0 * horizontal)


# ------------------- TRACKING LOOP -------------------
def tracking_loop():
    global left_counter, right_counter, last_left_click, last_right_click
    global EAR_THRESHOLD_LEFT, EAR_THRESHOLD_RIGHT, MOVEMENT_GAIN

    global cap
    cap = cv2.VideoCapture(utilities.get_camera_input())
    while not stop_event.is_set():

        if global_var.camera_input_changed == True or cap is None:
            global_var.camera_input_changed = False
            cap = cv2.VideoCapture(utilities.get_camera_input())

        if not tracking_active.is_set():
            time.sleep(0.05)
            continue

        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)

        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0].landmark

            # Cursor movement
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

            gain = max(0.1, min(2.0, MOVEMENT_GAIN))
            target_x = int(norm_x * screen_width * gain)
            target_y = int(norm_y * screen_height * gain)

            pyautogui.moveTo(target_x, target_y)

            # EAR blink detection
            ear_left = get_ear(landmarks, LEFT_EYE)
            ear_right = get_ear(landmarks, RIGHT_EYE)
            ear_queue_left.append(ear_left)
            ear_queue_right.append(ear_right)
            avg_ear_left = sum(ear_queue_left) / len(ear_queue_left)
            avg_ear_right = sum(ear_queue_right) / len(ear_queue_right)

            now = time.time()

            # Left blink
            if avg_ear_left < EAR_THRESHOLD_LEFT:
                left_counter += 1
            else:
                if left_counter >= MIN_CONSEC_FRAMES and now - last_left_click > CLICK_COOLDOWN:
                    pyautogui.click(button="left")
                    print("Left blink → LEFT CLICK")
                    last_left_click = now
                left_counter = 0

            # Right blink
            if avg_ear_right < EAR_THRESHOLD_RIGHT:
                right_counter += 1
            else:
                if right_counter >= MIN_CONSEC_FRAMES and now - last_right_click > CLICK_COOLDOWN:
                    pyautogui.click(button="right")
                    print("Right blink → RIGHT CLICK")
                    last_right_click = now
                right_counter = 0

    if cap:
        cap.release()
    cv2.destroyAllWindows()


# ------------------- UI -------------------
def start_pause():
    if tracking_active.is_set():
        tracking_active.clear()
        toggle_btn.configure(text="Start", image=start_icon)
        status_lbl.configure(text="Status: Paused")
    else:
        tracking_active.set()
        toggle_btn.configure(text="Pause", image=pause_icon)
        status_lbl.configure(text="Status: Running")


def quit_app():
    stop_event.set()
    tracking_active.set()
    root.destroy()


def open_settings():
    win = ctk.CTkToplevel(root)
    win.title("Settings")
    win.geometry("360x460")
    win.resizable(False, False)

    # Input Dropdown Menus
    dropdown_frame = ctk.CTkFrame(win)
    dropdown_frame.pack(fill="x", padx=10, pady=5)
    ctk.CTkLabel(dropdown_frame, text="Input Source").pack(anchor="w", padx=5, pady=5)
    ctk.CTkOptionMenu(dropdown_frame, values=["Webcam", "Phone", "Screen Capture"]).pack(fill="x", padx=5, pady=5)
    #utilities.set_camera_input(1)

    # Dark/Light mode toggle
    def toggle_mode(choice):
        ctk.set_appearance_mode(choice.lower())

    mode_frame = ctk.CTkFrame(win)
    mode_frame.pack(fill="x", padx=10, pady=5)
    ctk.CTkLabel(mode_frame, text="Appearance").pack(anchor="w", padx=5, pady=5)
    ctk.CTkOptionMenu(mode_frame, values=["Dark", "Light"], command=toggle_mode).pack(fill="x", padx=5, pady=5)

    # Left blink
    left_frame = ctk.CTkFrame(win)
    left_frame.pack(fill="x", padx=10, pady=(10, 5))
    left_frame.columnconfigure(0, weight=1)
    ctk.CTkLabel(left_frame, text="Left Blink Threshold").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    left_val_lbl = ctk.CTkLabel(left_frame, text=f"{EAR_THRESHOLD_LEFT:.2f}")
    left_val_lbl.grid(row=0, column=1, sticky="e", padx=5, pady=5)

    def update_left(v):
        global EAR_THRESHOLD_LEFT
        EAR_THRESHOLD_LEFT = float(v)
        left_val_lbl.configure(text=f"{float(v):.2f}")

    left_slider = ctk.CTkSlider(left_frame, from_=0.1, to=0.5, number_of_steps=50, command=update_left)
    left_slider.set(EAR_THRESHOLD_LEFT)
    left_slider.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

    # Right blink
    right_frame = ctk.CTkFrame(win)
    right_frame.pack(fill="x", padx=10, pady=5)
    right_frame.columnconfigure(0, weight=1)
    ctk.CTkLabel(right_frame, text="Right Blink Threshold").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    right_val_lbl = ctk.CTkLabel(right_frame, text=f"{EAR_THRESHOLD_RIGHT:.2f}")
    right_val_lbl.grid(row=0, column=1, sticky="e", padx=5, pady=5)

    def update_right(v):
        global EAR_THRESHOLD_RIGHT
        EAR_THRESHOLD_RIGHT = float(v)
        right_val_lbl.configure(text=f"{float(v):.2f}")

    right_slider = ctk.CTkSlider(right_frame, from_=0.1, to=0.5, number_of_steps=50, command=update_right)
    right_slider.set(EAR_THRESHOLD_RIGHT)
    right_slider.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

    # Movement gain
    move_frame = ctk.CTkFrame(win)
    move_frame.pack(fill="x", padx=10, pady=5)
    move_frame.columnconfigure(0, weight=1)
    ctk.CTkLabel(move_frame, text="Head Movement Sensitivity").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    move_val_lbl = ctk.CTkLabel(move_frame, text=f"{MOVEMENT_GAIN:.2f}")
    move_val_lbl.grid(row=0, column=1, sticky="e", padx=5, pady=5)

    def update_gain(v):
        global MOVEMENT_GAIN
        MOVEMENT_GAIN = float(v)
        move_val_lbl.configure(text=f"{float(v):.2f}")

    move_slider = ctk.CTkSlider(move_frame, from_=0.3, to=1.5, number_of_steps=60, command=update_gain)
    move_slider.set(MOVEMENT_GAIN)
    move_slider.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

    # Import/Export Settings
    def import_settings():
        fd.askopenfilename(title="Import Settings", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])

    def export_settings():
        fd.asksaveasfilename(title="Export Settings", defaultextension=".json", filetypes=[("JSON files", "*.json")])

    io_frame = ctk.CTkFrame(win)
    io_frame.pack(fill="x", padx=10, pady=5)
    ctk.CTkButton(io_frame, text="Import Settings", command=import_settings).pack(side="left", expand=True, fill="x", padx=5, pady=10)
    ctk.CTkButton(io_frame, text="Export Settings", command=export_settings).pack(side="right", expand=True, fill="x", padx=5, pady=10)


# ------------------- MAIN -------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.title("EyeOS Control")
root.geometry("800x70")
root.resizable(False, False)

bar = ctk.CTkFrame(root)
bar.pack(fill="both", expand=True, padx=8, pady=8)

# Load icons
def load_icon(name, size=(20, 20)):
    return ctk.CTkImage(Image.open(os.path.join("resources", name)), size=size)

start_icon = load_icon("start.png")
pause_icon = load_icon("pause.png")
settings_icon = load_icon("settings.png")
quit_icon = load_icon("quit.png")
voice_icon = load_icon("voice.png")
keyboard_icon = load_icon("keyboard.png")

toggle_btn = ctk.CTkButton(bar, text="Start", image=start_icon, width=100, command=start_pause, compound="left", font=("Arial", 13))
toggle_btn.pack(side="left", padx=4)

status_lbl = ctk.CTkLabel(bar, text="Status: Idle")
status_lbl.pack(side="left", padx=10)

voice_btn = ctk.CTkButton(bar, text="Voice", image=voice_icon, command=lambda: print("Voice Pressed"), compound="left", font=("Arial", 13))
voice_btn.pack(side="left", padx=4)

keyboard_btn = ctk.CTkButton(bar, text="Keyboard", image=keyboard_icon, command=lambda: print("Keyboard Pressed"), compound="left", font=("Arial", 13))
keyboard_btn.pack(side="left", padx=4)

settings_btn = ctk.CTkButton(bar, text="Settings", image=settings_icon, command=open_settings, compound="left", font=("Arial", 13))
settings_btn.pack(side="left", padx=4)

quit_btn = ctk.CTkButton(bar, text="Quit", image=quit_icon, fg_color="#9b1c1c", command=quit_app, compound="left", font=("Arial", 13))
quit_btn.pack(side="right", padx=4)

# Start tracking thread
threading.Thread(target=tracking_loop, daemon=True).start()

root.bind("<space>", lambda e: start_pause())
root.bind("<Escape>", lambda e: quit_app())
root.protocol("WM_DELETE_WINDOW", quit_app)
root.mainloop()
