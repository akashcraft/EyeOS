
import time
import cv2

class CursorMovementCalibrator:
    def __init__(self, cap, face_mesh, wait_time=3):
        self.cap = cap
        self.face_mesh = face_mesh
        self.positions = {}
        self.wait_time = wait_time

    def timed_capture(self, label):
        print(f"Look {label}. Capturing in {self.wait_time} seconds...")
        start = time.time()
        collected = []

        while time.time() - start < self.wait_time:
            ret, frame = self.cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb)

            frame_h, frame_w, _ = frame.shape
            dot_coords = {
                "CENTER": (frame_w // 2, frame_h // 2),
                "LEFT":   (frame_w // 5, frame_h // 2),
                "RIGHT":  (4 * frame_w // 5, frame_h // 2),
                "UP":     (frame_w // 2, frame_h // 5),
                "DOWN":   (frame_w // 2, 4 * frame_h // 5)
            }
            if label in dot_coords:
                cv2.circle(frame, dot_coords[label], 20, (255, 255, 255), -1)
            cv2.putText(frame, f"Look at the dot ({label})...", (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)

            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark
                eye_x = (landmarks[473].x + landmarks[468].x) / 2
                eye_y = (landmarks[473].y + landmarks[468].y) / 2
                collected.append((eye_x, eye_y))

            cv2.imshow("Calibration", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break

        if collected:
            avg_x = sum(x for x, _ in collected) / len(collected)
            avg_y = sum(y for _, y in collected) / len(collected)
            self.positions[label] = (avg_x, avg_y)
            print(f"Captured {label}: ({avg_x:.3f}, {avg_y:.3f})")

    def calibrate(self):
        for label in ["CENTER", "LEFT", "RIGHT", "UP", "DOWN"]:
            self.timed_capture(label)

        # Show message
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            cv2.putText(frame, "Calibration Complete!", (50, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 4)
            cv2.imshow("Calibration", frame)
            cv2.waitKey(2000)

        return self.positions

