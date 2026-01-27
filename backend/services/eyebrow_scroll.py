import time
import pyautogui
import numpy as np
from collections import deque


class EyebrowScroller:
    """
    Eyebrow-only scrolling (robust to head translation/scale/roll).

    We align the face each frame using eye corners (similarity transform),
    then measure eyebrow-to-upper-lid vertical distance in the aligned space.

    - Eyebrow UP -> scroll up
    - Eyebrow DOWN (super down) -> scroll down
    """

    def __init__(
        self,
        up_threshold=0.010,
        down_threshold=0.012,
        scroll_amount=90,
        repeat_interval=0.09,
        baseline_alpha=0.02,
        smooth_window=5,
        show_debug=False,
    ):
        self.up_threshold = up_threshold
        self.down_threshold = down_threshold
        self.scroll_amount = scroll_amount
        self.repeat_interval = repeat_interval
        self.baseline_alpha = baseline_alpha
        self.show_debug = show_debug

        self._q = deque(maxlen=max(1, int(smooth_window)))
        self._neutral = None
        self._last_scroll = 0.0

        # canonical eye positions in "aligned face space"
        self._L_CAN = np.array([-0.5, 0.0], dtype=np.float32)
        self._R_CAN = np.array([+0.5, 0.0], dtype=np.float32)

    def reset(self):
        self._q.clear()
        self._neutral = None
        self._last_scroll = 0.0

    @staticmethod
    def _pt(lm):
        return np.array([lm.x, lm.y], dtype=np.float32)

    def _make_similarity(self, L, R):
        """
        Returns 2x2 matrix A and translation t such that:
            p_aligned = A @ p + t
        mapping eye corners to canonical positions.
        """
        mid = (L + R) * 0.5
        v = R - L
        dist = float(np.linalg.norm(v)) + 1e-9

        # rotate so eye-line is horizontal
        c = v[0] / dist
        s = v[1] / dist
        Rmat = np.array([[c, s], [-s, c]], dtype=np.float32)  # rotation to horizontal

        # scale so inter-eye distance becomes 1.0 (from canonical -0.5..+0.5)
        Smat = (1.0 / dist) * np.eye(2, dtype=np.float32)

        A = Smat @ Rmat
        # translate so mid maps to (0,0)
        t = -A @ mid
        return A, t

    def _aligned_y(self, A, t, p):
        return float((A @ p + t)[1])

    def _metric(self, landmarks):
        # Eye corners
        L_eye_outer = self._pt(landmarks[33])
        L_eye_inner = self._pt(landmarks[133])
        R_eye_outer = self._pt(landmarks[362])
        R_eye_inner = self._pt(landmarks[263])

        # Pick a stable left/right corner pair for alignment (outer corners work well)
        L = L_eye_outer
        R = R_eye_outer

        A, t = self._make_similarity(L, R)

        # Eyebrows + upper eyelids
        L_brow = self._pt(landmarks[105])
        R_brow = self._pt(landmarks[334])
        L_lid  = self._pt(landmarks[159])
        R_lid  = self._pt(landmarks[386])

        # In aligned space, measure vertical distance (brow - lid)
        # Bigger distance => brow is higher relative to eye (raised eyebrow)
        L_val = self._aligned_y(A, t, L_lid) - self._aligned_y(A, t, L_brow)
        R_val = self._aligned_y(A, t, R_lid) - self._aligned_y(A, t, R_brow)


        return (L_val + R_val) * 0.5

    def update(self, landmarks, now=None):
        if now is None:
            now = time.time()

        val = self._metric(landmarks)

        self._q.append(val)
        smoothed = sum(self._q) / len(self._q)

        if self._neutral is None:
            self._neutral = smoothed
        else:
            self._neutral = (1.0 - self.baseline_alpha) * self._neutral + self.baseline_alpha * smoothed

        delta = smoothed - self._neutral

        if (now - self._last_scroll) < self.repeat_interval:
            return None

        if delta > self.up_threshold:
            pyautogui.scroll(self.scroll_amount)
            self._last_scroll = now
            return "SCROLL_UP"

        if delta < -self.down_threshold:
            pyautogui.scroll(-self.scroll_amount)
            self._last_scroll = now
            return "SCROLL_DOWN"

        return None
