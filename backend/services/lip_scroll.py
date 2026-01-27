import time
import pyautogui


class LipScrollController:
    def __init__(
        self,
        pucker_threshold=0.62,        # mouth_width / eye_width must go below this
        lips_closed_ratio=0.020,      # mouth_open / mouth_width must stay below this
        toggle_hold_sec=0.55,
        scroll_amount=90,
        repeat_interval=0.10,
        gaze_up_thresh=0.40,
        gaze_down_thresh=0.60,
        gaze_deadband=(0.45, 0.55),
        show_debug=False,
    ):
        self.pucker_threshold = pucker_threshold
        self.lips_closed_ratio = lips_closed_ratio
        self.toggle_hold_sec = toggle_hold_sec
        self.scroll_amount = scroll_amount
        self.repeat_interval = repeat_interval
        self.gaze_up_thresh = gaze_up_thresh
        self.gaze_down_thresh = gaze_down_thresh
        self.gaze_deadband = gaze_deadband
        self.show_debug = show_debug

        self.mode_on = False
        self._start = None
        self._latched = False
        self._last_scroll = 0.0

    def reset(self):
        self.mode_on = False
        self._start = None
        self._latched = False
        self._last_scroll = 0.0

    @staticmethod
    def _clamp(v, a, b):
        return a if v < a else b if v > b else v

    def _pucker_metric(self, landmarks):
        left_corner = landmarks[61]
        right_corner = landmarks[291]
        mouth_w = abs(right_corner.x - left_corner.x)

        l_eye_outer = landmarks[33]
        r_eye_outer = landmarks[263]
        eye_w = abs(r_eye_outer.x - l_eye_outer.x) + 1e-6

        return mouth_w / eye_w

    def _mouth_open_ratio(self, landmarks):
        left_corner = landmarks[61]
        right_corner = landmarks[291]
        upper_lip = landmarks[13]
        lower_lip = landmarks[14]

        mouth_open = abs(lower_lip.y - upper_lip.y)
        mouth_w = abs(right_corner.x - left_corner.x) + 1e-6
        return mouth_open / mouth_w

    def _gaze_vertical_pos(self, landmarks):
        iris_r = landmarks[468]
        iris_l = landmarks[473]

        up_l = landmarks[159]
        lo_l = landmarks[145]
        up_r = landmarks[386]
        lo_r = landmarks[374]

        def eye_pos(iris, up, lo):
            denom = (lo.y - up.y)
            if abs(denom) < 1e-6:
                return 0.5
            p = (iris.y - up.y) / denom
            return self._clamp(p, 0.0, 1.0)

        return 0.5 * (eye_pos(iris_l, up_l, lo_l) + eye_pos(iris_r, up_r, lo_r))

    def update(self, landmarks, now=None):
        if now is None:
            now = time.time()

        pucker_m = self._pucker_metric(landmarks)
        open_r = self._mouth_open_ratio(landmarks)

        # Activation = puckered AND lips closed-ish
        activated = (pucker_m < self.pucker_threshold) and (open_r < self.lips_closed_ratio)

        if self.show_debug:
            print(
                f"pucker={pucker_m:.3f} openR={open_r:.3f} "
                f"act={activated} mode={'ON' if self.mode_on else 'OFF'}"
            )

        if activated:
            if self._start is None:
                self._start = now
                self._latched = False

            if (not self._latched) and ((now - self._start) >= self.toggle_hold_sec):
                self.mode_on = not self.mode_on
                self._latched = True
                return "SCROLL_MODE_ON" if self.mode_on else "SCROLL_MODE_OFF"
        else:
            self._start = None
            self._latched = False

        if not self.mode_on:
            return None

        if (now - self._last_scroll) < self.repeat_interval:
            return None

        gaze = self._gaze_vertical_pos(landmarks)

        if self.gaze_deadband[0] <= gaze <= self.gaze_deadband[1]:
            return None

        if gaze < self.gaze_up_thresh:
            pyautogui.scroll(self.scroll_amount)
            self._last_scroll = now
            return "SCROLL_UP"

        if gaze > self.gaze_down_thresh:
            pyautogui.scroll(-self.scroll_amount)
            self._last_scroll = now
            return "SCROLL_DOWN"

        return None
