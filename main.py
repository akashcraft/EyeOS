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
from pynput import keyboard
from pynput.mouse import Button, Controller
from backend.services import settings
from backend.services.pedal import PedalHandler
import global_var
import utilities

# ------------------- GLOBALS -------------------
pyautogui.FAILSAFE = False
screen_width, screen_height = pyautogui.size()
isSettingsOpen = False

mouse = Controller()

cap = None
tracking_active = threading.Event()
stop_event = threading.Event()

# Pedal
pedal = PedalHandler()
HOLD_THRESHOLD = 0.35
press_time = 0
dragging = False
hold_timer = None

# ------------------- MEDIAPIPE -------------------
mp_face_mesh = mp.solutions.face_mesh  # pyright: ignore
face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True, max_num_faces=1)

# Eye indices
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# ------------------- SETTINGS -------------------
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

# ------------------- PEDAL CALLBACKS -------------------
def on_key_press(key):
    global press_time, dragging, hold_timer

    if key != keyboard.Key.f12:
        return

    press_time = time.time()
    pedal.key_down()
    dragging = False

    def start_drag():
        global dragging
        if not dragging:
            mouse.press(Button.left)
            dragging = True
            print("Pedal → DRAG START")

    hold_timer = threading.Timer(HOLD_THRESHOLD, start_drag)
    hold_timer.start()

def on_key_release(key):
    global dragging, hold_timer

    if key != keyboard.Key.f12:
        return

    if hold_timer:
        hold_timer.cancel()

    action = pedal.key_up()

    # END DRAG
    if dragging:
        mouse.release(Button.left)
        dragging = False
        print("Pedal → DRAG END")
        return

    # TAP ACTIONS
    if action == "SINGLE":
        mouse.click(Button.left)
        print("Pedal → LEFT CLICK")

    elif action == "DOUBLE":
        mouse.click(Button.right)
        print("Pedal → RIGHT CLICK")

    elif action == "TRIPLE":
        mouse.click(Button.left, 2)
        print("Pedal → DOUBLE CLICK")


# Start listener ONCE
keyboard.Listener(
    on_press=on_key_press,
    on_release=on_key_release,
    daemon=True
).start()

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
    global left_counter, right_counter
    global last_left_click, last_right_click
    global cap
    cap = cv2.VideoCapture(utilities.get_camera_input())
    while not stop_event.is_set():

        if global_var.camera_input_changed:
            global_var.camera_input_changed = False
            if cap:
                cap.release()
            cap = cv2.VideoCapture(utilities.get_camera_input())

        if cap is None or not cap.isOpened():
            continue

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
    global isSettingsOpen
    if isSettingsOpen:
        return
    settings_btn.configure(state="disabled")
    win = ctk.CTkToplevel()
    win.title("Settings")
    win.geometry("360x540")
    win.attributes("-topmost", True)
    isSettingsOpen = True

    def on_close():
        global isSettingsOpen
        isSettingsOpen = False
        settings_btn.configure(state="normal")
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)

    raw_cameras = utilities.get_available_cameras()

    # 3. Create unique display names
    camera_map = {}
    for cam in raw_cameras:
        display_name = f"{cam['name']}" 
        camera_map[display_name] = cam

    display_names = list(camera_map.keys())

    def on_camera_select(selected_display_name):
        cam_data = camera_map.get(selected_display_name)
        if cam_data:
            utilities.set_camera_input(cam_data["index"])

    dropdown_frame = ctk.CTkFrame(win)
    dropdown_frame.pack(fill="x", padx=10, pady=(10,5))
    
    ctk.CTkLabel(dropdown_frame, text="Select Camera").pack(anchor="w", padx=5)

    camera_menu = ctk.CTkOptionMenu(
        dropdown_frame, 
        values=display_names,
        command=on_camera_select
    )
    camera_menu.pack(fill="x", padx=5, pady=10)

    # 4. Set initial selection based on saved index
    saved_index = utilities.get_camera_input()
    
    current_selection = None
    for name, cam_data in camera_map.items():
        # Match purely on index
        if str(cam_data["index"]) == str(saved_index):
            current_selection = name
            break
    
    if current_selection:
        camera_menu.set(current_selection)
    elif display_names:
        camera_menu.set(display_names[0])

    # Dark/Light mode toggle
    def toggle_mode(choice):
        ctk.set_appearance_mode(choice.lower())

    mode_frame = ctk.CTkFrame(win)
    mode_frame.pack(fill="x", padx=10, pady=(5,0))
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

    left_slider = ctk.CTkSlider(left_frame, from_=0.1, to=0.5, number_of_steps=50, command=update_left) # pyright: ignore[reportArgumentType]
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

    right_slider = ctk.CTkSlider(right_frame, from_=0.1, to=0.5, number_of_steps=50, command=update_right) # pyright: ignore[reportArgumentType]
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

    move_slider = ctk.CTkSlider(move_frame, from_=0.3, to=1.5, number_of_steps=60, command=update_gain) # pyright: ignore[reportArgumentType]
    move_slider.set(MOVEMENT_GAIN)
    move_slider.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

    # Keyboard Gap
    gap_frame = ctk.CTkFrame(win)
    gap_frame.pack(fill="x", padx=10, pady=5)
    gap_frame.columnconfigure(0, weight=1)
    ctk.CTkLabel(gap_frame, text="On-Screen Keyboard Gap").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    gap_val_lbl = ctk.CTkLabel(gap_frame, text=f"{settings.read_settings('gap', '.vscode/settings.json', default=10)}") # type: ignore
    gap_val_lbl.grid(row=0, column=1, sticky="e", padx=5, pady=5)  

    def update_gap(v):
        settings.write_settings("gap", int(v), ".vscode/settings.json")
        gap_val_lbl.configure(text=f"{int(v)}")

    gap_slider = ctk.CTkSlider(gap_frame, from_=5, to=40, number_of_steps=35, command=update_gap) # pyright: ignore[reportArgumentType]
    gap_slider.set(settings.read_settings("gap", ".vscode/settings.json", default=10)) # type: ignore
    gap_slider.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

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

keyboard_btn = ctk.CTkButton(bar, text="Keyboard", image=keyboard_icon, command=utilities.open_onscreen_keyboard, compound="left", font=("Arial", 13))
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
