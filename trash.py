#!/usr/bin/env python3
# osk_panel.py — macOS Non-Activating On-Screen Keyboard (always-on-top, all spaces, minimizable)
# Requires: pip install pyobjc

from __future__ import annotations
import objc
from Cocoa import (
    NSApplication, NSPanel, NSButton,
    NSApplicationActivationPolicyAccessory, NSApplicationActivationPolicyRegular,
    NSMakeRect,
    NSWindowStyleMaskNonactivatingPanel, NSWindowStyleMaskTitled,
    NSBackingStoreBuffered, NSView,
)
from PyObjCTools import AppHelper
from Quartz import CGEventCreateKeyboardEvent, CGEventPost, kCGHIDEventTap
from AppKit import (
    NSStatusWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskMiniaturizable,
)

# ---------- Key mapping (US ANSI) ----------
KEYCODES = {
    "A": 0, "S": 1, "D": 2, "F": 3, "H": 4, "G": 5, "Z": 6, "X": 7, "C": 8, "V": 9,
    "B": 11, "Q": 12, "W": 13, "E": 14, "R": 15, "Y": 16, "T": 17, "1": 18, "2": 19,
    "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28,
    "0": 29, "]": 30, "O": 31, "U": 32, "[": 33, "I": 34, "P": 35, "RETURN": 36,
    "L": 37, "J": 38, "'": 39, "K": 40, ";": 41, "\\": 42, ",": 43, "/": 44,
    "N": 45, "M": 46, ".": 47, "TAB": 48, "SPACE": 49, "DELETE": 51, "ESC": 53,
    "LEFT": 123, "RIGHT": 124, "DOWN": 125, "UP": 126,
}
SHIFT_KC = 56
SHIFTED = {
    "!":"1","@":"2","#":"3","$":"4","%":"5","^":"6","&":"7","*":"8","(":"9",")":"0",
    "_":"-","+":"=","{":"[","}":"]","|":"\\",":":";","\"":"'", "<":",",">":".","?":"/",
}

def post_key(keycode: int, use_shift: bool = False):
    if use_shift:
        CGEventPost(kCGHIDEventTap, CGEventCreateKeyboardEvent(None, SHIFT_KC, True))
    CGEventPost(kCGHIDEventTap, CGEventCreateKeyboardEvent(None, keycode, True))
    CGEventPost(kCGHIDEventTap, CGEventCreateKeyboardEvent(None, keycode, False))
    if use_shift:
        CGEventPost(kCGHIDEventTap, CGEventCreateKeyboardEvent(None, SHIFT_KC, False))

def make_button(title, x, y, w, h, parent_view, target):
    btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    btn.setTitle_(title)
    btn.setBezelStyle_(1)
    btn.setTarget_(target)
    btn.setAction_(b"clicked:")
    parent_view.addSubview_(btn)
    return btn

class ClickHandler(NSView):
    def init(self):
        self = objc.super(ClickHandler, self).init()
        if self is None: return None
        self.shift_next = False
        self.panel = None  # filled in after creation
        return self

    def clicked_(self, sender):
        label = str(sender.title())

        # Window controls
        if label == "Minimize":
            # Miniaturize to Dock
            if self.panel is not None:
                self.panel.miniaturize_(None)
            return
        if label == "Quit":
            from AppKit import NSApp
            NSApp.terminate_(None)
            return

        # Shift logic
        if label == "Shift":
            self.shift_next = True
            sender.setTitle_("Shift (ON)")
            return

        up = label.upper()
        if up in ("RETURN","TAB","SPACE","DELETE","ESC","LEFT","RIGHT","UP","DOWN"):
            post_key(KEYCODES[up], self.shift_next); self._reset_shift(sender); return

        if label in SHIFTED:
            base = SHIFTED[label]; kc = KEYCODES.get(base.upper())
            if kc: post_key(kc, True); self._reset_shift(sender); return

        if len(label) == 1:
            kc = KEYCODES.get(up)
            if kc: post_key(kc, label.isalpha() or self.shift_next); self._reset_shift(sender); return

        kc = KEYCODES.get(up)
        if kc: post_key(kc, self.shift_next); self._reset_shift(sender)

    def _reset_shift(self, last_sender):
        if self.shift_next:
            self.shift_next = False
            parent = last_sender.superview()
            for v in parent.subviews():
                try:
                    if str(v.title()) in ("Shift (ON)", "Shift"):
                        v.setTitle_("Shift")
                except Exception:
                    pass

def main():
    app = NSApplication.sharedApplication()

    # To support *real* minimization (to the Dock), we need a Dock icon:
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    # If you prefer to hide from Dock and skip true minimize, set Accessory policy instead.
    # app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    style = (NSWindowStyleMaskNonactivatingPanel
             | NSWindowStyleMaskTitled
             | NSWindowStyleMaskMiniaturizable)  # allow miniaturize

    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(200, 600, 880, 190),
        style, NSBackingStoreBuffered, False
    )

    # Always on top + all Spaces + alongside fullscreen apps
    panel.setLevel_(NSStatusWindowLevel)
    panel.setHidesOnDeactivate_(False)
    panel.setBecomesKeyOnlyIfNeeded_(True)
    panel.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces
        | NSWindowCollectionBehaviorFullScreenAuxiliary
        | NSWindowCollectionBehaviorStationary
    )
    panel.setTitle_("On-Screen Keyboard")

    content = panel.contentView()
    handler = ClickHandler.alloc().init()
    handler.panel = panel  # so the handler can call panel.miniaturize_(None)

    def row(chars, x0, y, key_w=40, key_h=30, gap=6):
        x = x0
        for ch in chars:
            w = 40
            if ch in ("DELETE","RETURN","TAB","SPACE"):
                w = 80 if ch != "SPACE" else 240
            elif ch in ("LEFT","DOWN","UP","RIGHT","ESC"):
                w = 56
            make_button(ch, x, y, w, key_h, content, handler)
            x += w + gap

    # Rows
    row(list("1234567890-=")+["DELETE"],10,130)
    row(list("QWERTYUIOP")+["[","]","\\"],10,94)
    row(list("ASDFGHJKL")+[";","'","RETURN"],10,58)
    row(["TAB"]+["Z","X","C","V","B","N","M",",",".","/","SPACE","LEFT","DOWN","UP","RIGHT","ESC"],10,22)

    # Bottom controls
    make_button("Shift",10,-14,80,30,content,handler)
    row(list("!@#$%^&*()_+{}|:\"<>?"),100,-14,36)
    make_button("Minimize", 740, -14, 80, 30, content, handler)
    make_button("Quit", 830, -14, 40, 30, content, handler)

    panel.makeKeyAndOrderFront_(None)
    AppHelper.runEventLoop()

if __name__ == "__main__":
    main()
