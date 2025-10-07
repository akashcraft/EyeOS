
import time
import math
import cv2

class EyeBlinkCalibrator:
    def __init__(self, cap, face_mesh, duration=5):
        self.cap = cap
        self.face_mesh = face_mesh
        self.duration = duration
        self.left_ears = []
        self.right_ears = []

    def euclidean(self, p1, p2):
        return math.hypot(p1.x - p2.x, p1.y - p2.y)

    def get_ear(self, landmarks, indices):
        p = [landmarks[i] for i in indices]
        vertical1 = self.euclidean(p[1], p[5])
        vertical2 = self.euclidean(p[2], p[4])
        horizontal = self.euclidean(p[0], p[3])
        return (vertical1 + vertical2) / (2.0 * horizontal)

    def calibrate(self, LEFT_EYE, RIGHT_EYE, save_fn):
        print("Blink Calibration: Please keep your eyes open and face the screen.")
        start_time = time.time()

        while time.time() - start_time < self.duration:
            ret, frame = self.cap.read()
            if not ret:
                break
            rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb)

            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark
                self.left_ears.append(self.get_ear(landmarks, LEFT_EYE))
                self.right_ears.append(self.get_ear(landmarks, RIGHT_EYE))

            cv2.putText(frame, "Calibrating EAR... Keep eyes open", (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
            cv2.imshow("Calibration", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break

        left_avg = sum(self.left_ears) / len(self.left_ears) if self.left_ears else 0.18
        right_avg = sum(self.right_ears) / len(self.right_ears) if self.right_ears else 0.18
        threshold = 0.85 * min(left_avg, right_avg)
        print(f"AR Threshold calibrated to: {threshold:.3f}")
        save_fn({"EAR_THRESHOLD": threshold})
        return threshold
