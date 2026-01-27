import time
import pyautogui


class MouthClicker:
    """
    Per-frame mouth gesture click detector.

    Gesture mapping (same behavior as your old script):
    - Mouth open then close (short open) -> LEFT CLICK
    - Two mouth opens close together -> DOUBLE CLICK
    - Hold mouth open long enough -> RIGHT CLICK

    Use:
        clicker = MouthClicker(...)
        action = clicker.update(landmarks, now=time.time())
        if action: print(action)
    """

    def __init__(
        self,
        arm_mouth_open_ratio=0.25,
        close_ratio=0.015,
        cooldown_sec=0.35,
        double_click_window=1.8,
        right_click_hold_sec=0.7,
        show_debug=False,
    ):
        self.arm_mouth_open_ratio = arm_mouth_open_ratio
        self.close_ratio = close_ratio
        self.cooldown_sec = cooldown_sec
        self.double_click_window = double_click_window
        self.right_click_hold_sec = right_click_hold_sec
        self.show_debug = show_debug

        self.reset()

    def reset(self):
        self.mouth_is_open = False
        self.open_start_time = 0.0
        self.right_click_fired = False

        self.last_action_time = 0.0
        self.last_open_event_time = 0.0

    def update(self, landmarks, now=None):
        """
        landmarks: mediapipe face landmarks list (results.multi_face_landmarks[0].landmark)
        now: optional timestamp (time.time())

        returns: "LEFT CLICK" / "RIGHT CLICK" / "DOUBLE CLICK" / None
        """
        if now is None:
            now = time.time()

        # Mediapipe mouth landmarks
        left_corner = landmarks[61]
        right_corner = landmarks[291]
        upper_lip = landmarks[13]
        lower_lip = landmarks[14]

        mouth_open = abs(lower_lip.y - upper_lip.y)
        mouth_width = abs(right_corner.x - left_corner.x) + 1e-6
        open_ratio = mouth_open / mouth_width

        action = None

        # Transition: closed -> open
        if (not self.mouth_is_open) and (open_ratio > self.arm_mouth_open_ratio):
            self.mouth_is_open = True
            self.open_start_time = now
            self.right_click_fired = False

            # Double click detection happens on the "open" event
            if (now - self.last_action_time) > self.cooldown_sec:
                if (
                    self.last_open_event_time != 0.0
                    and (now - self.last_open_event_time) <= self.double_click_window
                ):
                    pyautogui.doubleClick()
                    self.last_action_time = now
                    self.last_open_event_time = 0.0
                    action = "DOUBLE CLICK"
                else:
                    self.last_open_event_time = now

        # While open
        elif self.mouth_is_open:
            # Hold-open -> right click
            if (
                (not self.right_click_fired)
                and (now - self.open_start_time) >= self.right_click_hold_sec
                and (now - self.last_action_time) > self.cooldown_sec
            ):
                pyautogui.rightClick()
                self.last_action_time = now
                self.right_click_fired = True
                action = "RIGHT CLICK"

            # Transition: open -> closed
            if open_ratio < self.close_ratio:
                self.mouth_is_open = False

                # If we didn't right-click, then close triggers left click
                if (
                    (not self.right_click_fired)
                    and (now - self.last_action_time) > self.cooldown_sec
                    and self.last_open_event_time != 0.0
                ):
                    pyautogui.leftClick()
                    self.last_action_time = now
                    action = "LEFT CLICK"

        return action


# Optional: keep a standalone test runner (opens its own camera)
def mouth_gesture_clicker(
    camera_index=0,
    arm_mouth_open_ratio=0.25,
    close_ratio=0.015,
    cooldown_sec=0.35,
    double_click_window=1.8,
    right_click_hold_sec=0.7,
    show_debug=True,
):
    import cv2
    import mediapipe as mp

    mp_face = mp.solutions.face_mesh
    face_mesh = mp_face.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    cap = cv2.VideoCapture(camera_index)
    clicker = MouthClicker(
        arm_mouth_open_ratio=arm_mouth_open_ratio,
        close_ratio=close_ratio,
        cooldown_sec=cooldown_sec,
        double_click_window=double_click_window,
        right_click_hold_sec=right_click_hold_sec,
        show_debug=show_debug,
    )

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = face_mesh.process(rgb)

        now = time.time()
        action = None

        if res.multi_face_landmarks:
            landmarks = res.multi_face_landmarks[0].landmark
            action = clicker.update(landmarks, now)

        if show_debug:
            cv2.putText(
                frame,
                f"Action: {action or 'NONE'}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (255, 255, 255),
                2,
            )
            cv2.imshow("Mouth Clicker (ESC to quit)", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break

    cap.release()
    if show_debug:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    mouth_gesture_clicker(show_debug=True)
