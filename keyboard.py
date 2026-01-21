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
    "LEFT": 123, "RIGHT": 124, "DOWN": 125, "UP": 126,
}

class ClickHandler(NSView):
    def init(self):
        self = objc.super(ClickHandler, self).init()
        self.shift_active = False
        return self

    def clicked_(self, sender):
        label = str(sender.title())

        if label == "Quit":
            NSApplication.sharedApplication().terminate_(None)
            return
        if label == "Min":
            self.window().miniaturize_(None)
            return

        if len(label) == 1 and label.isalpha():
            post_text(label)
            return

        return

class KeyView(NSView):
    def isFlipped(self): return True

def get_key_width(key):
    """Calculates specific widths to ensure text fits and rows align."""
    if key in ["RETURN", "DELETE", "TAB", "Shift"]: return STD_W * 1.8
    if key == "SPACE": return STD_W * 4
    if len(key) > 3: return STD_W * 1.3 # Handles LEFT, DOWN, RIGHT
    return STD_W

def main():
    app = NSApplication.sharedApplication()
    
    # Organized rows
    rows = [
        ["ESC", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "DELETE"],
        ["TAB", "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "[", "]", "\\"],
        ["Shift", "A", "S", "D", "F", "G", "H", "J", "K", "L", ";", "'", "RETURN"],
        ["Z", "X", "C", "V", "B", "N", "M", ",", ".", "/", "UP", "SPACE"],
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
            btn.setBezelStyle_(NSBezelStyleRounded)
            btn.setFont_(NSFont.systemFontOfSize_(12))
            btn.setTarget_(handler)
            btn.setAction_(b"clicked:")
            container.addSubview_(btn)
            x += w + GAP
        y += KEY_H + GAP

    panel.setTitle_("Keypad")
    panel.setLevel_(NSStatusWindowLevel)
    panel.orderFront_(None)
    AppHelper.runEventLoop()

if __name__ == "__main__":
    main()