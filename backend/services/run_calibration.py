import cv2
import mediapipe as mp
from calibration_utils import save_calibration
from cursor_calibrator import CursorMovementCalibrator
from eye_blink_calibrator import EyeBlinkCalibrator

# Setup
cap = cv2.VideoCapture(0)
mp_face_mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=True)

# Eye indices (for EAR calculation)
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# Calibrate EAR (blink detection)
blink_calibrator = EyeBlinkCalibrator(cap, mp_face_mesh)
ear_threshold = blink_calibrator.calibrate(LEFT_EYE, RIGHT_EYE, lambda data: None)  # We'll combine save later

# Calibrate cursor movement
cursor_calibrator = CursorMovementCalibrator(cap, mp_face_mesh)
positions = cursor_calibrator.calibrate()

# Save combined calibration data
combined_data = {
    "EAR_THRESHOLD": ear_threshold,
    "GAZE_POSITIONS": positions
}
save_calibration(combined_data)

print("\nAll calibrations complete and saved!")

cap.release()
cv2.destroyAllWindows()
