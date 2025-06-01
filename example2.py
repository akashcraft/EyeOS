import cv2
import mediapipe as mp
import pyautogui
import time
import math
from collections import deque

# Disable pyautogui failsafe
pyautogui.FAILSAFE = False

# Setup
screen_width, screen_height = pyautogui.size()
cap = cv2.VideoCapture(0)

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True, max_num_faces=1)

# Eye indices for EAR
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# Blink logic
EAR_THRESHOLD = 0.22
MIN_CONSEC_FRAMES = 2
CLICK_COOLDOWN = 0.5

left_counter = 0
right_counter = 0
last_left_click = 0
last_right_click = 0

# EAR smoothing
ear_queue_left = deque(maxlen=5)
ear_queue_right = deque(maxlen=5)

def euclidean(p1, p2):
    return math.hypot(p1.x - p2.x, p1.y - p2.y)

def get_ear(landmarks, indices):
    p1, p2, p3, p4, p5, p6 = [landmarks[i] for i in indices]
    vertical1 = euclidean(p2, p6)
    vertical2 = euclidean(p3, p5)
    horizontal = euclidean(p1, p4)
    return (vertical1 + vertical2) / (2.0 * horizontal)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame = cv2.flip(frame, 1)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb)
    frame_height, frame_width, _ = frame.shape

    if results.multi_face_landmarks:
        landmarks = results.multi_face_landmarks[0].landmark

        # Cursor movement (mapped from center 25% webcam region)
        left_center = landmarks[473]
        right_center = landmarks[468]
        eye_x = (left_center.x + right_center.x) / 2
        eye_y = (left_center.y + right_center.y) / 2

        # Define control region (center 25% of webcam frame)
        x_range = (0.375, 0.625)
        y_range = (0.375, 0.625)

        # Clamp and normalize eye position
        eye_x = max(min(eye_x, x_range[1]), x_range[0])
        eye_y = max(min(eye_y, y_range[1]), y_range[0])
        norm_x = (eye_x - x_range[0]) / (x_range[1] - x_range[0])
        norm_y = (eye_y - y_range[0]) / (y_range[1] - y_range[0])

        # Move mouse
        pyautogui.moveTo(int(norm_x * screen_width), int(norm_y * screen_height))

        # EAR calculation with smoothing
        ear_left = get_ear(landmarks, LEFT_EYE)
        ear_right = get_ear(landmarks, RIGHT_EYE)
        ear_queue_left.append(ear_left)
        ear_queue_right.append(ear_right)
        avg_ear_left = sum(ear_queue_left) / len(ear_queue_left)
        avg_ear_right = sum(ear_queue_right) / len(ear_queue_right)

        now = time.time()

        # Blink detection for left eye
        if avg_ear_left < EAR_THRESHOLD:
            left_counter += 1
        else:
            if left_counter >= MIN_CONSEC_FRAMES and now - last_left_click > CLICK_COOLDOWN:
                pyautogui.click(button='left')
                print("Left blink → LEFT CLICK")
                last_left_click = now
            left_counter = 0

        # Blink detection for right eye
        if avg_ear_right < EAR_THRESHOLD:
            right_counter += 1
        else:
            if right_counter >= MIN_CONSEC_FRAMES and now - last_right_click > CLICK_COOLDOWN:
                pyautogui.click(button='right')
                print("Right blink → RIGHT CLICK")
                last_right_click = now
            right_counter = 0

    cv2.imshow("Eye Tracker", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()