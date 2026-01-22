#!/usr/bin/env python3
import objc
from Cocoa import (
    NSApplication, NSPanel, NSButton, NSView, NSMakeRect,
    NSWindowStyleMaskTitled, NSWindowStyleMaskNonactivatingPanel,
    NSBackingStoreBuffered, NSStatusWindowLevel, NSVisualEffectView,
    NSVisualEffectMaterialHUDWindow, NSVisualEffectBlendingModeBehindWindow,
    NSBezelStyleRounded, NSFont, NSColor
)
from PyObjCTools import AppHelper
from Quartz import (
    CGEventCreateKeyboardEvent, CGEventPost, CGEventKeyboardSetUnicodeString,
    CGEventSetFlags,
    kCGHIDEventTap,
    kCGEventFlagMaskCommand, kCGEventFlagMaskAlternate, kCGEventFlagMaskControl,
    kCGEventFlagMaskShift,
)

def post_text(text: str) -> None:
    if not text:
        return

    for ch in text:
        ev_down = CGEventCreateKeyboardEvent(None, 0, True)
        if ev_down is None:
            continue
        CGEventKeyboardSetUnicodeString(ev_down, 1, ch)
        CGEventPost(kCGHIDEventTap, ev_down)

        ev_up = CGEventCreateKeyboardEvent(None, 0, False)
        if ev_up is None:
            continue
        CGEventKeyboardSetUnicodeString(ev_up, 1, ch)
        CGEventPost(kCGHIDEventTap, ev_up)

# Standardized Layout Constants
# Bigger keys (easier gaze/eye-click targets), tighter spacing between keys.
GAP = 3
MARGIN = 10
KEY_H = 40
STD_W = 50  # Slightly wider to prevent text clipping + adds perceived "padding"

KEYCODES = {
    "RETURN": 36, "TAB": 48, "SPACE": 49, "DELETE": 51, "ESC": 53,
    "CAPS": 57,
    "CMD": 55,
    "Shift": 56,
    "OPT": 58,
    "CTRL": 59,
    "LEFT": 123, "RIGHT": 124, "DOWN": 125, "UP": 126,
}

KEYCODES_CHAR = {
    "A": 0, "S": 1, "D": 2, "F": 3, "H": 4, "G": 5,
    "Z": 6, "X": 7, "C": 8, "V": 9, "B": 11,
    "Q": 12, "W": 13, "E": 14, "R": 15, "Y": 16, "T": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23,
    "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
    "]": 30, "O": 31, "U": 32, "[": 33, "I": 34, "P": 35,
    "L": 37, "J": 38, "'": 39, "K": 40, ";": 41, "\\": 42,
    ",": 43, "/": 44, "N": 45, "M": 46, ".": 47,
    "`": 50,
}

class ClickHandler(NSView):
    def init(self):
        self = objc.super(ClickHandler, self).init()
        self.shift_active = False
        self.caps_active = False

        self._buttons = []
        self._base_label = {}

        self.hotkeys_active = False
        self.hotkey_mods = set()  
        self.hotkey_seq = []    
        self._hk_display_btn = None
        return self

    def register_button(self, btn, base_label: str) -> None:
        self._buttons.append(btn)
        self._base_label[btn] = base_label
        if base_label == "HK_DISPLAY":
            self._hk_display_btn = btn

    def update_key_labels(self) -> None:
        shifted = {
            "`": "~",
            "1": "!", "2": "@", "3": "#", "4": "$", "5": "%", "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
            "-": "_", "=": "+",
            "[": "{", "]": "}", "\\": "|",
            ";": ":", "'": '"',
            ",": "<", ".": ">", "/": "?",
        }

        for btn in self._buttons:
            base = self._base_label.get(btn, str(btn.title()))

            if base == "HotKeys":
                btn.setTitle_("HotKeys*" if self.hotkeys_active else "HotKeys")
                continue
            if base == "HK_RUN":
                btn.setTitle_("Run")
                continue
            if base == "HK_CLEAR":
                btn.setTitle_("Clear")
                continue
            if base == "HK_DISPLAY":
                continue

            if base == "Shift":
                if self.hotkeys_active:
                    btn.setTitle_("Shift*" if "Shift" in self.hotkey_mods else "Shift")
                else:
                    btn.setTitle_("Shift*" if self.shift_active else "Shift")
                continue
            if base == "CAPS":
                btn.setTitle_("CAPS*" if self.caps_active else "CAPS")
                continue

            if base in ["CMD", "OPT", "CTRL"]:
                btn.setTitle_(f"{base}*" if (self.hotkeys_active and base in self.hotkey_mods) else base)
                continue

            if base in ["ESC", "TAB", "RETURN", "DELETE", "SPACE", "Min", "Quit", "LEFT", "RIGHT", "UP", "DOWN"]:
                btn.setTitle_(base)
                continue

            if len(base) == 1:
                if base.isalpha():
                    make_upper = (self.caps_active ^ self.shift_active)
                    btn.setTitle_(base.upper() if make_upper else base.lower())
                else:
                    if self.shift_active and base in shifted:
                        btn.setTitle_(shifted[base])
                    else:
                        btn.setTitle_(base)
                continue

            btn.setTitle_(base)

    def _hk_flags(self) -> int:
        flags = 0
        if "CMD" in self.hotkey_mods:
            flags |= kCGEventFlagMaskCommand
        if "OPT" in self.hotkey_mods:
            flags |= kCGEventFlagMaskAlternate
        if "CTRL" in self.hotkey_mods:
            flags |= kCGEventFlagMaskControl
        if "Shift" in self.hotkey_mods:
            flags |= kCGEventFlagMaskShift
        return flags

    def _update_hotkeys_display(self) -> None:
        if not self._hk_display_btn:
            return
        if not self.hotkeys_active:
            self._hk_display_btn.setTitle_("HK: off")
            return

        order = ["CTRL", "OPT", "CMD", "Shift"]
        mods = [m for m in order if m in self.hotkey_mods]
        keys = [k for k in self.hotkey_seq]

        left = "+".join(mods) if mods else "(mods)"
        right = " ".join(keys) if keys else "(keys)"
        self._hk_display_btn.setTitle_(f"HK: {left} | {right}")

    def _send_keycode(self, keycode: int, flags: int = 0) -> None:
        ev_down = CGEventCreateKeyboardEvent(None, keycode, True)
        if ev_down is not None:
            if flags:
                CGEventSetFlags(ev_down, flags)
            CGEventPost(kCGHIDEventTap, ev_down)

        ev_up = CGEventCreateKeyboardEvent(None, keycode, False)
        if ev_up is not None:
            if flags:
                CGEventSetFlags(ev_up, flags)
            CGEventPost(kCGHIDEventTap, ev_up)

    def _run_hotkeys(self) -> None:
        flags = self._hk_flags()

        for k in self.hotkey_seq:
            if k in KEYCODES:
                self._send_keycode(KEYCODES[k], flags)
                continue

            if len(k) == 1:
                kc = KEYCODES_CHAR.get(k.upper())
                if kc is not None:
                    self._send_keycode(kc, flags)

        self.hotkeys_active = False
        self.hotkey_mods.clear()
        self.hotkey_seq.clear()
        self.update_key_labels()
        self._update_hotkeys_display()

    def clicked_(self, sender):
        label = str(sender.title())
        base_label = self._base_label.get(sender, label.rstrip("*"))

        if base_label == "Quit":
            NSApplication.sharedApplication().terminate_(None)
            return
        if base_label == "Min":
            self.window().miniaturize_(None)
            return

        if base_label == "HotKeys":
            self.hotkeys_active = not self.hotkeys_active
            self.hotkey_mods.clear()
            self.hotkey_seq.clear()
            self.update_key_labels()
            self._update_hotkeys_display()
            return

        if base_label == "HK_RUN":
            if self.hotkeys_active:
                self._run_hotkeys()
            return

        if base_label == "HK_CLEAR":
            if self.hotkeys_active:
                self.hotkey_mods.clear()
                self.hotkey_seq.clear()
                self.update_key_labels()
                self._update_hotkeys_display()
            return

        if self.hotkeys_active:
            if base_label in ["CMD", "OPT", "CTRL", "Shift"]:
                if base_label in self.hotkey_mods:
                    self.hotkey_mods.remove(base_label)
                else:
                    self.hotkey_mods.add(base_label)
                self.update_key_labels()
                self._update_hotkeys_display()
                return

            if base_label == "HK_DISPLAY":
                return

            self.hotkey_seq.append(base_label)
            self._update_hotkeys_display()
            return

        if base_label == "ESC":
            self._send_keycode(KEYCODES["ESC"], 0)
            return

        if base_label == "TAB":
            self._send_keycode(KEYCODES["TAB"], 0)
            return

        if base_label == "RETURN":
            self._send_keycode(KEYCODES["RETURN"], 0)
            return

        if base_label == "DELETE":
            self._send_keycode(KEYCODES["DELETE"], 0)
            return

        if base_label in ["LEFT", "RIGHT", "UP", "DOWN"]:
            self._send_keycode(KEYCODES[base_label], 0)
            return

        if base_label == "Shift":
            self.shift_active = not self.shift_active
            self.update_key_labels()
            return

        if base_label == "CAPS":
            self.caps_active = not self.caps_active
            self.update_key_labels()
            return

        if base_label == "SPACE":
            post_text(" ")
            return

        if len(base_label) == 1:
            shifted = {
                "`": "~",
                "1": "!", "2": "@", "3": "#", "4": "$", "5": "%", "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
                "-": "_", "=": "+",
                "[": "{", "]": "}", "\\": "|",
                ";": ":", "'": '"',
                ",": "<", ".": ">", "/": "?",
            }

            out = base_label
            if base_label.isalpha():
                make_upper = (self.caps_active ^ self.shift_active)
                out = base_label.upper() if make_upper else base_label.lower()
            else:
                if self.shift_active and base_label in shifted:
                    out = shifted[base_label]

            post_text(out)
            return

        return

class KeyView(NSView):
    def isFlipped(self): return True

def get_key_width(key):
    """Calculates specific widths to ensure text fits and rows align."""
    if key in ["RETURN", "DELETE", "TAB", "Shift", "CAPS", "CMD", "OPT", "CTRL", "HotKeys", "Run", "Clear"]: return STD_W * 1.8
    if key == "HK_DISPLAY": return STD_W * 6
    if key == "SPACE": return STD_W * 4
    if len(key) > 3: return STD_W * 1.3 # Handles LEFT, DOWN, RIGHT
    return STD_W

def main():
    app = NSApplication.sharedApplication()
    
    # Organized rows
    rows = [
        ["ESC", "`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "DELETE"],
        ["TAB", "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "[", "]", "\\"],
        ["CAPS", "A", "S", "D", "F", "G", "H", "J", "K", "L", ";", "'", "RETURN"],
        ["Shift", "Z", "X", "C", "V", "B", "N", "M", ",", ".", "/", "SPACE"],
        ["HotKeys", "Run", "Clear", "CMD", "OPT", "CTRL", "HK_DISPLAY"],
        ["Min", "Quit", "LEFT", "DOWN", "RIGHT", "UP"]
    ]

    # Calculate exact window size based on the longest row
    row_widths = [sum(get_key_width(k) for k in r) + (len(r)-1)*GAP for r in rows]
    win_w = max(row_widths) + (MARGIN * 2)
    win_h = (len(rows) * (KEY_H + GAP)) + (MARGIN * 2) - GAP

    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(300, 300, win_w, win_h),
        NSWindowStyleMaskTitled | NSWindowStyleMaskNonactivatingPanel,
        NSBackingStoreBuffered, False
    )
    panel.setBecomesKeyOnlyIfNeeded_(True)
    
    # Modern macOS "HUD" look
    effect_view = NSVisualEffectView.alloc().initWithFrame_(panel.contentView().bounds())
    effect_view.setMaterial_(NSVisualEffectMaterialHUDWindow)
    effect_view.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
    effect_view.setState_(1)
    panel.setContentView_(effect_view)

    container = KeyView.alloc().initWithFrame_(effect_view.bounds())
    effect_view.addSubview_(container)
    handler = ClickHandler.alloc().init()

    # Build rows with consistent alignment
    y = MARGIN
    for row in rows:
        x = MARGIN
        for key in row:
            w = get_key_width(key)
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, KEY_H))
            btn.setTitle_(key)
            base_key = key
            if key == "Run":
                base_key = "HK_RUN"
            elif key == "Clear":
                base_key = "HK_CLEAR"
            handler.register_button(btn, base_key)
            if key == "HK_DISPLAY":
                btn.setEnabled_(False)
            btn.setBezelStyle_(NSBezelStyleRounded)
            btn.setFont_(NSFont.systemFontOfSize_(12))
            btn.setTarget_(handler)
            btn.setAction_(b"clicked:")
            container.addSubview_(btn)
            x += w + GAP
        y += KEY_H + GAP

    handler.update_key_labels()
    handler._update_hotkeys_display()
    panel.setTitle_("Keypad")
    panel.setLevel_(NSStatusWindowLevel)
    panel.orderFront_(None)
    AppHelper.runEventLoop()

if __name__ == "__main__":
    main()