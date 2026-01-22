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
    kCGHIDEventTap
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
GAP = 6
MARGIN = 15
KEY_H = 34
STD_W = 45 # Slightly wider to prevent text clipping

KEYCODES = {
    "RETURN": 36, "TAB": 48, "SPACE": 49, "DELETE": 51, "ESC": 53,
    "CAPS": 57,
    "LEFT": 123, "RIGHT": 124, "DOWN": 125, "UP": 126,
}

class ClickHandler(NSView):
    def init(self):
        self = objc.super(ClickHandler, self).init()
        self.shift_active = False
        self.caps_active = False

        self._buttons = []
        self._base_label = {}
        return self

    def register_button(self, btn, base_label: str) -> None:
        self._buttons.append(btn)
        self._base_label[btn] = base_label

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

            if base == "Shift":
                btn.setTitle_("Shift*" if self.shift_active else "Shift")
                continue
            if base == "CAPS":
                btn.setTitle_("CAPS*" if self.caps_active else "CAPS")
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

    def clicked_(self, sender):
        label = str(sender.title())
        base_label = self._base_label.get(sender, label.rstrip("*"))

        if base_label == "Quit":
            NSApplication.sharedApplication().terminate_(None)
            return
        if base_label == "Min":
            self.window().miniaturize_(None)
            return

        if base_label == "ESC":
            ev_down = CGEventCreateKeyboardEvent(None, KEYCODES["ESC"], True)
            CGEventPost(kCGHIDEventTap, ev_down)
            ev_up = CGEventCreateKeyboardEvent(None, KEYCODES["ESC"], False)
            CGEventPost(kCGHIDEventTap, ev_up)
            return

        if base_label == "TAB":
            ev_down = CGEventCreateKeyboardEvent(None, KEYCODES["TAB"], True)
            CGEventPost(kCGHIDEventTap, ev_down)
            ev_up = CGEventCreateKeyboardEvent(None, KEYCODES["TAB"], False)
            CGEventPost(kCGHIDEventTap, ev_up)
            return

        if base_label == "RETURN":
            ev_down = CGEventCreateKeyboardEvent(None, KEYCODES["RETURN"], True)
            CGEventPost(kCGHIDEventTap, ev_down)
            ev_up = CGEventCreateKeyboardEvent(None, KEYCODES["RETURN"], False)
            CGEventPost(kCGHIDEventTap, ev_up)
            return

        if base_label == "DELETE":
            ev_down = CGEventCreateKeyboardEvent(None, KEYCODES["DELETE"], True)
            CGEventPost(kCGHIDEventTap, ev_down)
            ev_up = CGEventCreateKeyboardEvent(None, KEYCODES["DELETE"], False)
            CGEventPost(kCGHIDEventTap, ev_up)
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
    if key in ["RETURN", "DELETE", "TAB", "Shift", "CAPS"]: return STD_W * 1.8
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
        ["Shift", "Z", "X", "C", "V", "B", "N", "M", ",", ".", "/", "UP", "SPACE"],
        ["Min", "Quit", "LEFT", "DOWN", "RIGHT"]
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
            handler.register_button(btn, key)
            btn.setBezelStyle_(NSBezelStyleRounded)
            btn.setFont_(NSFont.systemFontOfSize_(12))
            btn.setTarget_(handler)
            btn.setAction_(b"clicked:")
            container.addSubview_(btn)
            x += w + GAP
        y += KEY_H + GAP

    handler.update_key_labels()
    panel.setTitle_("Keypad")
    panel.setLevel_(NSStatusWindowLevel)
    panel.orderFront_(None)
    AppHelper.runEventLoop()

if __name__ == "__main__":
    main()