from __future__ import annotations

import threading
import time
import sys
from dataclasses import dataclass
from typing import Optional, Tuple

import pyautogui
import tkinter as tk

try:
    from AppKit import NSApplication
    from AppKit import (
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorTransient,
        NSWindowCollectionBehaviorFullScreenAuxiliary,
        NSStatusWindowLevel,
    )
    _HAS_PYOBJC = True
except Exception:
    _HAS_PYOBJC = False

try:
    from Quartz import (
        CGEventCreateMouseEvent,
        CGEventPost,
        CGEventSetIntegerValueField,
        CGPoint,
        kCGHIDEventTap,
        kCGEventLeftMouseDown,
        kCGEventLeftMouseDragged,
        kCGEventLeftMouseUp,
        kCGMouseButtonLeft,
        kCGMouseEventClickState,
        CGGetActiveDisplayList,
        CGDisplayBounds,
    )
    _HAS_QUARTZ = True
except Exception:
    _HAS_QUARTZ = False

pyautogui.FAILSAFE = False


@dataclass
class DwellConfig:
    dwell_time_sec: float = 1.2
    dwell_radius_px: int = 45
    arm_delay_sec: float = 0.15
    cooldown_sec: float = 0.6
    tick_sec: float = 0.01
    button: str = "left"
    double_click_interval_sec: float = 0.18
    hold_button: str = "left"
    hold_release_dwell_sec: float = 0.75


@dataclass
class ZoneConfig:
    enabled: bool = True
    size_px: int = 90
    hold_sec: float = 1.0
    cooldown_sec: float = 0.9


@dataclass
class OverlayConfig:
    show: bool = True
    update_ms: int = 33
    w: int = 64
    h: int = 8
    border: int = 1
    offset_x: int = 0
    offset_y: int = 22
    hide_when_idle: bool = True
    alpha_fallback: float = 0.55

    bg: str = "#ff00ff"
    empty: str = "#111111"

    outline: str = "#3a3a3a"
    fill: str = "#00E5FF"


class DwellBarOverlay:
    """Tiny always-on-top dwell progress bar that follows the cursor."""

    def __init__(self, root: tk.Misc, cfg: OverlayConfig):
        self.root = root
        self.cfg = cfg

        self._progress = 0.0
        self._active = False

        self._win: Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas] = None
        self._fill_rect = None
        self._outline_rect = None
        self._using_transparent = False

    def start(self) -> None:
        if not self.cfg.show:
            return
        if self._win is None:
            self._create()
        self._tick()

    def set_progress(self, p: float, active: bool) -> None:
        self._progress = max(0.0, min(1.0, float(p)))
        self._active = bool(active)

    @staticmethod
    def _configure_macos_overlay(tk_toplevel: tk.Toplevel) -> None:
        """macOS: keep overlay visible over full-screen apps + on all Spaces, and make it click-through."""
        if not _HAS_PYOBJC:
            return

        try:
            app = NSApplication.sharedApplication()
            try:
                tk_toplevel.update_idletasks()
            except Exception:
                pass

            wins = list(app.windows())
            if not wins:
                return

            desired_title = ""
            try:
                desired_title = tk_toplevel.title()
            except Exception:
                desired_title = ""

            target = None
            if desired_title:
                for w in reversed(wins):
                    try:
                        if str(w.title()) == str(desired_title):
                            target = w
                            break
                    except Exception:
                        continue

            if target is None:
                target = wins[-1]

            try:
                target.setLevel_(NSStatusWindowLevel)
            except Exception:
                pass

            try:
                target.setIgnoresMouseEvents_(True)
            except Exception:
                pass

            try:
                behavior = (
                    NSWindowCollectionBehaviorCanJoinAllSpaces
                    | NSWindowCollectionBehaviorFullScreenAuxiliary
                    | NSWindowCollectionBehaviorTransient
                )
                target.setCollectionBehavior_(behavior)
            except Exception:
                pass

            try:
                target.setHidesOnDeactivate_(False)
            except Exception:
                pass

        except Exception:
            return

    def _create(self) -> None:
        win = tk.Toplevel(self.root)

        try:
            win.title("EyeOS_DwellBarOverlay")
        except Exception:
            pass

        win.overrideredirect(True)
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass

        self._configure_macos_overlay(win)
        try:
            self.root.after(200, lambda: self._configure_macos_overlay(win))
        except Exception:
            pass

        try:
            win.attributes("-takefocus", 0)
        except Exception:
            pass

        self._using_transparent = False
        try:
            win.configure(bg=self.cfg.bg)
            win.wm_attributes("-transparentcolor", self.cfg.bg)
            self._using_transparent = True
        except Exception:
            win.configure(bg=self.cfg.empty)
            try:
                win.attributes("-alpha", self.cfg.alpha_fallback)
            except Exception:
                pass

        win.geometry(f"{self.cfg.w}x{self.cfg.h}+0+0")

        canvas = tk.Canvas(
            win,
            width=self.cfg.w,
            height=self.cfg.h,
            highlightthickness=0,
            bd=0,
            bg=self.cfg.bg if self._using_transparent else win["bg"],
        )
        canvas.pack(fill="both", expand=True)

        x0 = self.cfg.border
        y0 = self.cfg.border
        x1 = self.cfg.w - self.cfg.border
        y1 = self.cfg.h - self.cfg.border

        outline = canvas.create_rectangle(
            x0, y0, x1, y1,
            outline=self.cfg.outline,
            width=1,
        )

        fill = canvas.create_rectangle(
            x0, y0, x0, y1,
            outline="",
            fill=self.cfg.fill,
            width=0,
        )

        self._win = win
        self._canvas = canvas
        self._outline_rect = outline
        self._fill_rect = fill

        try:
            win.attributes("-alpha", 0.0)
        except Exception:
            pass

    def _tick(self) -> None:
        if not self.cfg.show:
            return
        if self._win is None or self._canvas is None or self._fill_rect is None:
            return

        try:
            cx, cy = pyautogui.position()
            x = int(cx - (self.cfg.w // 2) + self.cfg.offset_x)
            y = int(cy + self.cfg.offset_y)
            self._win.geometry(f"{self.cfg.w}x{self.cfg.h}+{x}+{y}")

            if self.cfg.hide_when_idle and not self._active:
                try:
                    self._win.attributes("-alpha", 0.0)
                except Exception:
                    pass
            else:
                try:
                    alpha = 1.0 if self._using_transparent else self.cfg.alpha_fallback
                    self._win.attributes("-alpha", alpha)
                except Exception:
                    pass

            p = self._progress
            x0 = self.cfg.border
            y0 = self.cfg.border
            x1 = self.cfg.w - self.cfg.border
            y1 = self.cfg.h - self.cfg.border
            fill_x1 = int(x0 + p * (x1 - x0))
            self._canvas.coords(self._fill_rect, x0, y0, fill_x1, y1)

            if p > 0.0:
                self._canvas.itemconfigure(self._outline_rect, outline="#5a5a5a")
            else:
                self._canvas.itemconfigure(self._outline_rect, outline=self.cfg.outline)

        except Exception:
            pass

        try:
            self.root.after(self.cfg.update_ms, self._tick)
        except Exception:
            pass


class GazeClickService:
    """Background service that performs dwell-to-click using the OS cursor position."""

    def __init__(
        self,
        cfg: Optional[DwellConfig] = None,
        overlay: Optional[OverlayConfig] = None,
        zones: Optional[ZoneConfig] = None,
    ):
        self.cfg = cfg or DwellConfig()
        self.zone_cfg = zones or ZoneConfig()

        self._next_action: Optional[str] = None

        self._clicking_enabled: bool = True

        self._screen_w, self._screen_h = pyautogui.size()

        self._in_tr_zone_prev = False
        self._tr_enter_time: float = 0.0
        self._tr_fired: bool = False
        self._tr_last_fire: float = 0.0

        self._in_tl_zone_prev = False
        self._tl_enter_time: float = 0.0
        self._tl_fired: bool = False
        self._tl_last_fire: float = 0.0

        self._in_bl_zone_prev = False
        self._bl_enter_time: float = 0.0
        self._bl_fired: bool = False
        self._bl_last_fire: float = 0.0

        self._in_br_zone_prev = False
        self._br_enter_time: float = 0.0
        self._br_fired: bool = False
        self._br_last_fire: float = 0.0

        self.overlay_cfg = overlay or OverlayConfig()
        self._overlay: Optional[DwellBarOverlay] = None

        self._tracking_active = threading.Event()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._candidate: Optional[Tuple[int, int]] = None
        self._arm_start: float = 0.0
        self._dwell_start: float = 0.0
        self._cooldown_until: float = 0.0
        self._progress: float = 0.0

        self._holding_active: bool = False
        self._hold_armed: bool = False
        self._hold_release_candidate: Optional[Tuple[int, int]] = None
        self._hold_release_arm_start: float = 0.0
        self._hold_release_start: float = 0.0
        self._hold_release_progress: float = 0.0

        self.on_progress = None

    def _macos_double_click(self, x: int, y: int, interval_sec: float) -> bool:
        """Return True if we successfully emitted a macOS double-click via Quartz."""
        if not (_HAS_QUARTZ and sys.platform == "darwin"):
            return False

        try:
            pt = CGPoint(int(x), int(y))

            ev_down1 = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev_down1, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, ev_down1)

            ev_up1 = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev_up1, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, ev_up1)

            time.sleep(max(0.02, float(interval_sec)))

            ev_down2 = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev_down2, kCGMouseEventClickState, 2)
            CGEventPost(kCGHIDEventTap, ev_down2)

            ev_up2 = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev_up2, kCGMouseEventClickState, 2)
            CGEventPost(kCGHIDEventTap, ev_up2)

            return True
        except Exception:
            return False

    def _macos_mouse_down(self, x: int, y: int) -> bool:
        if not (_HAS_QUARTZ and sys.platform == "darwin"):
            return False
        try:
            pt = CGPoint(int(x), int(y))
            ev = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, ev)
            return True
        except Exception:
            return False

    def _macos_mouse_drag(self, x: int, y: int) -> bool:
        """Emit a left-mouse-dragged event at (x,y)."""
        if not (_HAS_QUARTZ and sys.platform == "darwin"):
            return False
        try:
            pt = CGPoint(int(x), int(y))
            ev = CGEventCreateMouseEvent(None, kCGEventLeftMouseDragged, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, ev)
            return True
        except Exception:
            return False

    def _macos_mouse_up(self, x: int, y: int) -> bool:
        if not (_HAS_QUARTZ and sys.platform == "darwin"):
            return False
        try:
            pt = CGPoint(int(x), int(y))
            ev = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, ev)
            return True
        except Exception:
            return False
    def _macos_mouse_down(self, x: int, y: int) -> bool:
        if not (_HAS_QUARTZ and sys.platform == "darwin"):
            return False
        try:
            pt = CGPoint(int(x), int(y))
            ev = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, ev)
            return True
        except Exception:
            return False

    def _macos_mouse_drag(self, x: int, y: int) -> bool:
        """Emit a left-mouse-dragged event at (x,y)."""
        if not (_HAS_QUARTZ and sys.platform == "darwin"):
            return False
        try:
            pt = CGPoint(int(x), int(y))
            ev = CGEventCreateMouseEvent(None, kCGEventLeftMouseDragged, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, ev)
            return True
        except Exception:
            return False

    def _macos_mouse_up(self, x: int, y: int) -> bool:
        if not (_HAS_QUARTZ and sys.platform == "darwin"):
            return False
        try:
            pt = CGPoint(int(x), int(y))
            ev = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, ev)
            return True
        except Exception:
            return False
        """Return True if we successfully emitted a macOS double-click via Quartz."""
        if not (_HAS_QUARTZ and sys.platform == "darwin"):
            return False

        try:
            pt = CGPoint(x, y)

            ev_down1 = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev_down1, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, ev_down1)

            ev_up1 = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev_up1, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, ev_up1)

            time.sleep(max(0.02, float(interval_sec)))

            ev_down2 = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev_down2, kCGMouseEventClickState, 2)
            CGEventPost(kCGHIDEventTap, ev_down2)

            ev_up2 = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, pt, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(ev_up2, kCGMouseEventClickState, 2)
            CGEventPost(kCGHIDEventTap, ev_up2)

            return True
        except Exception:
            return False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._tracking_active.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def set_tracking(self, enabled: bool) -> None:
        if enabled:
            self._tracking_active.set()
        else:
            self._tracking_active.clear()

    def toggle_tracking(self) -> bool:
        if self._tracking_active.is_set():
            self._tracking_active.clear()
            return False
        self._tracking_active.set()
        return True

    def attach_overlay(self, root: tk.Misc) -> None:
        """Attach the dwell progress bar overlay to a Tk root."""
        if not self.overlay_cfg.show:
            return
        if self._overlay is None:
            self._overlay = DwellBarOverlay(root, self.overlay_cfg)
            self._overlay.start()

    def arm_right_click_next(self) -> None:
        """Arm a one-shot right click for the next dwell click."""
        self._next_action = "right"

    def arm_double_click_next(self) -> None:
        """Arm a one-shot DOUBLE click for the next dwell click."""
        self._next_action = "double"

    def arm_hold_click_next(self) -> None:
        """Arm HOLD/DRAG mode: next dwell will press mouseDown at the target location."""
        self._hold_armed = True
        self._next_action = None
        self.reset()
        print("[HOLD MODE] ARMED (next dwell will mouseDown)")

    def release_hold(self) -> None:
        """Release an active hold (mouseUp)."""
        if not self._holding_active:
            return
        cfg = self.cfg
        if not self._macos_mouse_up(*pyautogui.position()):
            try:
                pyautogui.mouseUp(button=cfg.hold_button)
            except Exception:
                pyautogui.mouseUp()
        self._holding_active = False
        self._hold_armed = False
        self._next_action = None
        self._reset_hold_release()
        self.reset()
        print("[HOLD MODE] RELEASED (mouseUp)")

    def _bounds_for_point(self, x: int, y: int) -> Tuple[int, int, int, int]:
        """Return (x0, y0, w, h) bounds of the display containing (x,y). Fallback to main screen."""
        if _HAS_QUARTZ and sys.platform == "darwin":
            try:
                max_displays = 16
                active, count = CGGetActiveDisplayList(max_displays, None, None)
            except Exception:
                active = None
                count = 0

            try:
                if isinstance(active, tuple) and len(active) == 3:
                    _, displays, count = active
                else:
                    displays = active

                if displays:
                    for did in list(displays)[: int(count) if count else len(list(displays))]:
                        b = CGDisplayBounds(did)
                        x0, y0 = int(b.origin.x), int(b.origin.y)
                        w, h = int(b.size.width), int(b.size.height)
                        if x0 <= x < (x0 + w) and y0 <= y < (y0 + h):
                            return (x0, y0, w, h)
            except Exception:
                pass

        return (0, 0, int(self._screen_w), int(self._screen_h))
    def _handle_bottom_right_zone(self, x: int, y: int, now: float) -> bool:
        """Return True if we're in the BR zone (caller should suppress dwell)."""
        cfg = self.zone_cfg
        if not cfg.enabled:
            return False

        x0, y0, w, h = self._bounds_for_point(x, y)
        in_zone = (x >= (x0 + w - cfg.size_px)) and (y >= (y0 + h - cfg.size_px))

        if in_zone and not self._in_br_zone_prev:
            self._br_enter_time = now
            self._br_fired = False
        elif (not in_zone) and self._in_br_zone_prev:
            self._br_enter_time = 0.0
            self._br_fired = False

        self._in_br_zone_prev = in_zone

        if not in_zone:
            return False

        self.reset()

        if (now - self._br_last_fire) < cfg.cooldown_sec:
            return True

        held = now - self._br_enter_time if self._br_enter_time else 0.0
        if (not self._br_fired) and held >= cfg.hold_sec:
            self._br_fired = True
            self._br_last_fire = now
            if self._holding_active:
                self.release_hold()
                print("[ZONE BR] Release HOLD")
            else:
                self._hold_armed = not self._hold_armed
                self._next_action = None
                self.reset()
                state = "ARMED" if self._hold_armed else "DISARMED"
                print(f"[HOLD MODE] {state}")
                print("[ZONE BR] Toggle HOLD arm")

        return True

    def toggle_clicking_enabled(self) -> bool:
        """Toggle whether dwell clicks are allowed. Returns the new state."""
        self._clicking_enabled = not self._clicking_enabled
        self.reset()
        state = "ON" if self._clicking_enabled else "OFF"
        print(f"[CLICKING] {state}")
        return self._clicking_enabled

    def _handle_top_left_zone(self, x: int, y: int, now: float) -> bool:
        """Return True if we're in the TL zone (caller should suppress dwell)."""
        cfg = self.zone_cfg
        if not cfg.enabled:
            return False

        x0, y0, w, h = self._bounds_for_point(x, y)
        in_zone = (x <= (x0 + cfg.size_px)) and (y <= (y0 + cfg.size_px))

        if in_zone and not self._in_tl_zone_prev:
            self._tl_enter_time = now
            self._tl_fired = False
        elif (not in_zone) and self._in_tl_zone_prev:
            self._tl_enter_time = 0.0
            self._tl_fired = False

        self._in_tl_zone_prev = in_zone

        if not in_zone:
            return False

        self.reset()

        if (now - self._tl_last_fire) < cfg.cooldown_sec:
            return True

        held = now - self._tl_enter_time if self._tl_enter_time else 0.0
        if (not self._tl_fired) and held >= cfg.hold_sec:
            self._tl_fired = True
            self._tl_last_fire = now
            self.arm_double_click_next()
            print("[ZONE TL] Armed DOUBLE click (next dwell)")

        return True

    def _handle_top_right_zone(self, x: int, y: int, now: float) -> bool:
        """Return True if we're in the TR zone (caller should suppress dwell)."""
        cfg = self.zone_cfg
        if not cfg.enabled:
            return False

        x0, y0, w, h = self._bounds_for_point(x, y)
        in_zone = (x >= (x0 + w - cfg.size_px)) and (y <= (y0 + cfg.size_px))

        if in_zone and not self._in_tr_zone_prev:
            self._tr_enter_time = now
            self._tr_fired = False
        elif (not in_zone) and self._in_tr_zone_prev:
            self._tr_enter_time = 0.0
            self._tr_fired = False

        self._in_tr_zone_prev = in_zone

        if not in_zone:
            return False

        self.reset()

        if (now - self._tr_last_fire) < cfg.cooldown_sec:
            return True

        held = now - self._tr_enter_time if self._tr_enter_time else 0.0
        if (not self._tr_fired) and held >= cfg.hold_sec:
            self._tr_fired = True
            self._tr_last_fire = now
            self.arm_right_click_next()
            print("[ZONE TR] Armed RIGHT click (next dwell)")

        return True

    def _handle_bottom_left_zone(self, x: int, y: int, now: float) -> bool:
        """Return True if we're in the BL zone (caller should suppress dwell)."""
        cfg = self.zone_cfg
        if not cfg.enabled:
            return False

        x0, y0, w, h = self._bounds_for_point(x, y)
        in_zone = (x <= (x0 + cfg.size_px)) and (y >= (y0 + h - cfg.size_px))

        if in_zone and not self._in_bl_zone_prev:
            self._bl_enter_time = now
            self._bl_fired = False
        elif (not in_zone) and self._in_bl_zone_prev:
            self._bl_enter_time = 0.0
            self._bl_fired = False

        self._in_bl_zone_prev = in_zone

        if not in_zone:
            return False

        self.reset()

        if (now - self._bl_last_fire) < cfg.cooldown_sec:
            return True

        held = now - self._bl_enter_time if self._bl_enter_time else 0.0
        if (not self._bl_fired) and held >= cfg.hold_sec:
            self._bl_fired = True
            self._bl_last_fire = now
            self.toggle_clicking_enabled()
            print("[ZONE BL] Toggle CLICKING")

        return True

    @staticmethod
    def _dist2(a: Tuple[int, int], b: Tuple[int, int]) -> int:
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        return dx * dx + dy * dy

    def reset(self) -> None:
        self._candidate = None
        self._arm_start = 0.0
        self._dwell_start = 0.0
        self._progress = 0.0

    def _reset_hold_release(self) -> None:
        self._hold_release_candidate = None
        self._hold_release_arm_start = 0.0
        self._hold_release_start = 0.0
        self._hold_release_progress = 0.0

    def _update_hold_release(self, x: int, y: int, now: float) -> float:
        """While holding is active, dwell to release (mouseUp) at current location."""
        cfg = self.cfg
        cur = (int(x), int(y))

        if self._hold_release_candidate is None:
            self._hold_release_candidate = cur
            self._hold_release_arm_start = now
            self._hold_release_start = 0.0
            self._hold_release_progress = 0.0
            return 0.0

        if self._dist2(cur, self._hold_release_candidate) > (cfg.dwell_radius_px * cfg.dwell_radius_px):
            self._hold_release_candidate = cur
            self._hold_release_arm_start = now
            self._hold_release_start = 0.0
            self._hold_release_progress = 0.0
            return 0.0

        if self._hold_release_start == 0.0:
            if (now - self._hold_release_arm_start) >= cfg.arm_delay_sec:
                self._hold_release_start = now
                self._hold_release_progress = 0.0
            return self._hold_release_progress

        elapsed = now - self._hold_release_start
        self._hold_release_progress = max(0.0, min(1.0, elapsed / cfg.hold_release_dwell_sec))

        if elapsed >= cfg.hold_release_dwell_sec:
            if not self._macos_mouse_up(int(x), int(y)):
                try:
                    pyautogui.mouseUp(button=cfg.hold_button)
                except Exception:
                    pyautogui.mouseUp()

            self._holding_active = False
            self._cooldown_until = now + cfg.cooldown_sec
            self._reset_hold_release()
            self.reset()
            print("Hold → RELEASE (mouseUp)")
            return 0.0

        return self._hold_release_progress

    def update_and_maybe_click(self, x: int, y: int, now: float) -> float:
        cfg = self.cfg

        if now < self._cooldown_until:
            self._progress = 0.0
            return self._progress

        cur = (int(x), int(y))

        if self._candidate is None:
            self._candidate = cur
            self._arm_start = now
            self._dwell_start = 0.0
            self._progress = 0.0
            return self._progress

        if self._dist2(cur, self._candidate) > (cfg.dwell_radius_px * cfg.dwell_radius_px):
            self._candidate = cur
            self._arm_start = now
            self._dwell_start = 0.0
            self._progress = 0.0
            return self._progress

        if self._dwell_start == 0.0:
            if (now - self._arm_start) >= cfg.arm_delay_sec:
                self._dwell_start = now
                self._progress = 0.0
            return self._progress

        elapsed = now - self._dwell_start
        self._progress = max(0.0, min(1.0, elapsed / cfg.dwell_time_sec))

        if elapsed >= cfg.dwell_time_sec:
            if self._hold_armed:
                if not self._macos_mouse_down(int(x), int(y)):
                    try:
                        pyautogui.mouseDown(button=cfg.hold_button)
                    except Exception:
                        pyautogui.mouseDown()
                self._holding_active = True
                self._reset_hold_release()
                self._hold_armed = False
                self._next_action = None
                print("Dwell → HOLD DOWN (mouseDown)")

                self.reset()
                return 0.0
            if self._next_action == "right":
                pyautogui.click(button="right")
                print("Dwell → RIGHT CLICK")
            elif self._next_action == "double":
                ok = self._macos_double_click(int(x), int(y), cfg.double_click_interval_sec)
                if not ok:
                    pyautogui.click(
                        button=cfg.button,
                        clicks=2,
                        interval=max(0.02, float(cfg.double_click_interval_sec)),
                    )
                print(f"Dwell → DOUBLE CLICK (interval={cfg.double_click_interval_sec:.2f}s)")
            else:
                pyautogui.click(button=cfg.button)

            self._next_action = None

            if self._holding_active:
                self.reset()
            else:
                self._cooldown_until = now + cfg.cooldown_sec
                self.reset()

        return self._progress

    def _loop(self) -> None:
        cfg = self.cfg

        while not self._stop_event.is_set():
            if not self._tracking_active.is_set():
                time.sleep(0.05)
                continue

            now = time.time()
            x, y = pyautogui.position()
            xi, yi = int(x), int(y)

            if self._holding_active:
                _ = self._handle_top_left_zone(xi, yi, now)
                _ = self._handle_top_right_zone(xi, yi, now)
                _ = self._handle_bottom_left_zone(xi, yi, now)
                _ = self._handle_bottom_right_zone(xi, yi, now)

                self._macos_mouse_drag(xi, yi)

                p = self._update_hold_release(x, y, now)
                if self._overlay is not None:
                    active = (self._hold_release_candidate is not None) or (p > 0.0)
                    self._overlay.set_progress(p, active)
                if callable(self.on_progress):
                    try:
                        self.on_progress(float(p))
                    except Exception:
                        pass
                time.sleep(cfg.tick_sec)
                continue

            in_zone = self._handle_top_left_zone(xi, yi, now)
            if not in_zone:
                in_zone = self._handle_top_right_zone(xi, yi, now)
            if not in_zone:
                in_zone = self._handle_bottom_left_zone(xi, yi, now)
            if not in_zone:
                in_zone = self._handle_bottom_right_zone(xi, yi, now)

            if in_zone:
                p = 0.0
            else:
                if not self._clicking_enabled:
                    self.reset()
                    p = 0.0
                else:
                    if self._hold_armed:
                        p = self.update_and_maybe_click(x, y, now)
                    else:
                        p = self.update_and_maybe_click(x, y, now)

            if self._overlay is not None:
                active = (self._candidate is not None) or (p > 0.0)
                self._overlay.set_progress(p, active)

            if callable(self.on_progress):
                try:
                    self.on_progress(float(p))
                except Exception:
                    pass

            time.sleep(cfg.tick_sec)


if __name__ == "__main__":

    root = tk.Tk()
    root.title("gaze_click (minimal)")
    root.geometry("360x120")
    root.resizable(False, False)

    gaze = GazeClickService()
    gaze.start()
    gaze.set_tracking(True)
    gaze.attach_overlay(root)

    msg = (
        "Hold your mouse still to trigger an automatic click (works in Finder).\n"
        "Top-left hold (1s) arms a DOUBLE click for the next dwell.\n"
        "Top-right hold (1s) arms a RIGHT click for the next dwell.\n"
        "Bottom-left hold (1s) toggles clicking ON/OFF (pause).\n"
        "Bottom-right hold (1s) ARMS hold/drag (next dwell presses down). To release, stop and dwell anywhere.\n"
        "Close this window to stop."
    )
    tk.Label(root, text=msg, justify="left").pack(anchor="w", padx=12, pady=(12, 6))

    status = tk.StringVar(value="Running")

    def toggle() -> None:
        running = gaze.toggle_tracking()
        status.set("Running" if running else "Paused")

    row = tk.Frame(root)
    row.pack(fill="x", padx=12, pady=(0, 8))
    tk.Label(row, textvariable=status).pack(side="left")
    tk.Button(row, text="Start/Pause", command=toggle).pack(side="right")

    def on_close() -> None:
        try:
            gaze.stop()
        finally:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()