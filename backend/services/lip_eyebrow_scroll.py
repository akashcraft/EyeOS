import time
import numpy as np
import pyautogui
from collections import deque


class LipEyebrowScrollController:
    """
    Lip activation toggles scroll mode direction, eyebrow DOWN triggers scrolling.

    Lip command (hold):
      OFF -> UP -> DOWN -> OFF ...

    Eyebrow gesture:
      Eyebrows DOWN (relative to eyelids) triggers scroll tick in current mode direction.

    Head resistance:
      Uses 3D rigid alignment (Kabsch) on stable face anchors to reduce head motion effects.
    """

    MODE_OFF = 0
    MODE_UP = 1
    MODE_DOWN = 2

    def __init__(
        self,
        # --- Lip activation (pucker + lips-closed) ---
        pucker_threshold=0.62,        # mouth_width / eye_width must go below this
        lips_closed_ratio=0.020,      # mouth_open / mouth_width must stay below this
        toggle_hold_sec=0.55,

        # --- Eyebrow DOWN detection ---
        brow_down_threshold=0.006,    # how far below baseline to count as "down"
        brow_hold_frames=2,           # must be down this many consecutive frames

        # --- Scroll behavior ---
        scroll_amount=90,
        repeat_interval=0.10,         # min seconds between scroll ticks

        # --- Smoothing / baseline ---
        smooth_window=7,
        baseline_alpha=0.01,          # how fast baseline drifts
        baseline_update_band=0.003,   # only update baseline if |delta| below this (prevents adapting during gestures)

        show_debug=False,
    ):
        self.pucker_threshold = pucker_threshold
        self.lips_closed_ratio = lips_closed_ratio
        self.toggle_hold_sec = toggle_hold_sec

        self.brow_down_threshold = brow_down_threshold
        self.brow_hold_frames = max(1, int(brow_hold_frames))

        self.scroll_amount = scroll_amount
        self.repeat_interval = repeat_interval

        self.baseline_alpha = baseline_alpha
        self.baseline_update_band = baseline_update_band
        self.show_debug = show_debug

        self._q = deque(maxlen=max(1, int(smooth_window)))

        self.reset()

        # Face anchors used for 3D head alignment (stable points)
        self._ANCHOR_IDX = [33, 263, 1, 61, 291]  # left eye outer, right eye outer, nose tip, mouth corners

        # Brow + lid points
        self._LBROW, self._RBROW = 105, 334
        self._LLID, self._RLID = 159, 386

    def reset(self):
        self.mode = self.MODE_OFF

        # lip toggle state
        self._lip_start = None
        self._lip_latched = False

        # eyebrow state
        self._ref_anchors = None
        self._neutral = None
        self._last_scroll = 0.0
        self._down_count = 0
        self._q.clear()

    # ----------------- Lip helpers -----------------
    @staticmethod
    def _clamp(v, a, b):
        return a if v < a else b if v > b else v

    def _pucker_metric(self, landmarks):
        # mouth corners
        left_corner = landmarks[61]
        right_corner = landmarks[291]
        mouth_w = abs(right_corner.x - left_corner.x)

        # normalize by eye width
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

    def _lip_activated(self, landmarks):
        pucker_m = self._pucker_metric(landmarks)
        open_r = self._mouth_open_ratio(landmarks)
        activated = (pucker_m < self.pucker_threshold) and (open_r < self.lips_closed_ratio)

        if self.show_debug:
            mode_str = {0: "OFF", 1: "UP", 2: "DOWN"}[self.mode]
            print(f"[Lip] pucker={pucker_m:.3f} openR={open_r:.3f} act={activated} mode={mode_str}")

        return activated

    def _cycle_mode(self):
        # OFF -> UP -> DOWN -> OFF
        if self.mode == self.MODE_OFF:
            self.mode = self.MODE_UP
        elif self.mode == self.MODE_UP:
            self.mode = self.MODE_DOWN
        else:
            self.mode = self.MODE_OFF

    # ----------------- 3D eyebrow alignment -----------------
    @staticmethod
    def _p3(lm):
        return np.array([lm.x, lm.y, lm.z], dtype=np.float32)

    @staticmethod
    def _kabsch_align(P, Q):
        """
        Find R, t such that P @ R + t best matches Q in least squares.
        P, Q: (N,3)
        """
        Pc = P - P.mean(axis=0, keepdims=True)
        Qc = Q - Q.mean(axis=0, keepdims=True)

        H = Pc.T @ Qc
        U, S, Vt = np.linalg.svd(H)
        R = Vt.T @ U.T

        if np.linalg.det(R) < 0:
            Vt[-1, :] *= -1
            R = Vt.T @ U.T

        t = Q.mean(axis=0) - (P.mean(axis=0) @ R)
        return R, t

    def _aligned_point(self, lm, R, t):
        p = self._p3(lm)
        return p @ R + t

    def _brow_metric(self, landmarks):
        """
        Returns average (lid_y - brow_y) in an aligned head frame.
        Eyebrow DOWN => this value decreases.
        """
        anchors = np.stack([self._p3(landmarks[i]) for i in self._ANCHOR_IDX], axis=0)

        if self._ref_anchors is None:
            self._ref_anchors = anchors.copy()

        R, t = self._kabsch_align(anchors, self._ref_anchors)

        L_brow = self._aligned_point(landmarks[self._LBROW], R, t)
        R_brow = self._aligned_point(landmarks[self._RBROW], R, t)
        L_lid = self._aligned_point(landmarks[self._LLID], R, t)
        R_lid = self._aligned_point(landmarks[self._RLID], R, t)

        # y increases downward. lid_y - brow_y is "brow height distance".
        L_val = (L_lid[1] - L_brow[1])
        R_val = (R_lid[1] - R_brow[1])
        return 0.5 * (L_val + R_val)

    # ----------------- Main update -----------------
    def update(self, landmarks, now=None):
        """
        Call once per frame.

        Returns:
          "MODE_UP" / "MODE_DOWN" / "MODE_OFF" / "SCROLL_UP" / "SCROLL_DOWN" / None
        """
        if now is None:
            now = time.time()

        # 1) Lip hold toggles mode
        lip_on = self._lip_activated(landmarks)
        if lip_on:
            if self._lip_start is None:
                self._lip_start = now
                self._lip_latched = False

            if (not self._lip_latched) and ((now - self._lip_start) >= self.toggle_hold_sec):
                self._cycle_mode()
                self._lip_latched = True
                self._down_count = 0  # reset gesture counter on mode change

                if self.mode == self.MODE_UP:
                    return "MODE_UP"
                if self.mode == self.MODE_DOWN:
                    return "MODE_DOWN"
                return "MODE_OFF"
        else:
            self._lip_start = None
            self._lip_latched = False

        # If mode OFF, do nothing else
        if self.mode == self.MODE_OFF:
            return None

        # 2) Eyebrow DOWN gesture triggers scrolling
        val = self._brow_metric(landmarks)
        self._q.append(val)
        smoothed = float(sum(self._q) / len(self._q))

        if self._neutral is None:
            self._neutral = smoothed

        delta = smoothed - self._neutral  # negative => brow distance decreased => eyebrow down

        # Update baseline ONLY when near neutral (prevents head-move from becoming the new "neutral")
        if abs(delta) < self.baseline_update_band:
            self._neutral = (1.0 - self.baseline_alpha) * self._neutral + self.baseline_alpha * smoothed

        if self.show_debug:
            mode_str = "UP" if self.mode == self.MODE_UP else "DOWN"
            print(f"[Brow] val={smoothed:.4f} neutral={self._neutral:.4f} delta={delta:.4f} mode={mode_str}")

        # rate limit scroll ticks
        if (now - self._last_scroll) < self.repeat_interval:
            return None

        # count consecutive "down" frames
        if delta < -self.brow_down_threshold:
            self._down_count += 1
        else:
            self._down_count = 0

        if self._down_count >= self.brow_hold_frames:
            self._down_count = 0
            self._last_scroll = now

            if self.mode == self.MODE_UP:
                pyautogui.scroll(self.scroll_amount)
                return "SCROLL_UP"
            else:
                pyautogui.scroll(-self.scroll_amount)
                return "SCROLL_DOWN"

        return None
