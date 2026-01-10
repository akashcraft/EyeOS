#!/usr/bin/env python3

from __future__ import annotations
import objc

from Cocoa import (
    NSApplication, NSPanel, NSButton,
    NSApplicationActivationPolicyRegular,
    NSMakeRect,
    NSWindowStyleMaskNonactivatingPanel, NSWindowStyleMaskTitled,
    NSBackingStoreBuffered, NSView,
)
from AppKit import (
    NSStatusWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSColor,
)
from PyObjCTools import AppHelper
from Quartz import (
    CGEventCreateKeyboardEvent, CGEventPost, CGEventKeyboardSetUnicodeString,
    kCGHIDEventTap
)

KEYCODES = {
    "A": 0, "S": 1, "D": 2, "F": 3, "H": 4, "G": 5, "Z": 6, "X": 7, "C": 8, "V": 9,
    "B": 11, "Q": 12, "W": 13, "E": 14, "R": 15, "Y": 16, "T": 17, "1": 18, "2": 19,
    "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28,
    "0": 29, "]": 30, "O": 31, "U": 32, "[": 33, "I": 34, "P": 35, "RETURN": 36,
    "L": 37, "J": 38, "'": 39, "K": 40, ";": 41, "\\": 42, ",": 43, "/": 44,
    "N": 45, "M": 46, ".": 47, "TAB": 48, "SPACE": 49, "DELETE": 51, "ESC": 53,
    "LEFT": 123, "RIGHT": 124, "DOWN": 125, "UP": 126,
}

SHIFTED = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
    "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\", ":": ";", "\"": "'", "<": ",", ">": ".", "?": "/",
}
SHIFTED_REV = {v: k for k, v in SHIFTED.items()}

def type_unicode(text: str):
    """Type unicode text by synthesizing key down/up with a unicode payload."""
    ev_down = CGEventCreateKeyboardEvent(None, 0, True)
    CGEventKeyboardSetUnicodeString(ev_down, len(text), text)
    CGEventPost(kCGHIDEventTap, ev_down)

    ev_up = CGEventCreateKeyboardEvent(None, 0, False)
    CGEventKeyboardSetUnicodeString(ev_up, len(text), text)
    CGEventPost(kCGHIDEventTap, ev_up)

def post_keycode(name: str):
    """Send non-text keys by keycode (return/tab/delete/esc/arrows/space)."""
    kc = KEYCODES.get(name)
    if kc is None:
        return
    CGEventPost(kCGHIDEventTap, CGEventCreateKeyboardEvent(None, kc, True))
    CGEventPost(kCGHIDEventTap, CGEventCreateKeyboardEvent(None, kc, False))

def make_button(title, x, y, w, h, parent_view, target):
    btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    btn.setTitle_(title)
    btn.setBezelStyle_(1)
    btn.setTarget_(target)
    btn.setAction_(b"clicked:")  
    parent_view.addSubview_(btn)
    return btn

class FlippedView(NSView):
    def isFlipped(self): return True
    def drawRect_(self, rect):
        self.setWantsLayer_(True)
        self.layer().setBackgroundColor_(NSColor.windowBackgroundColor().CGColor())

def key_width_for(label: str) -> int:
    if label in ("DELETE","RETURN","TAB"): return 80
    if label == "SPACE": return 240
    if label in ("LEFT","DOWN","UP","RIGHT","ESC"): return 60
    if label in ("Shift", "Shift On", "Shift On (LOCKED)","Minimize","Quit"): return 108
    if len(label) == 1 and label in '!@#$%^&*()_+{}|:"<>?': return 36
    return 40

def layout_row(content_view, handler, labels, x0, y, key_h=30, gap=6):
    x = x0
    for lbl in labels:
        w = key_width_for(lbl)
        make_button(lbl, x, y, w, key_h, content_view, handler)
        x += w + gap
    return x

class ClickHandler(NSView):
    def init(self):
        self = objc.super(ClickHandler, self).init()
        if self is None: return None
        self.shift_next = False    
        self.shift_lock = False    
        self.panel = None
        return self

    def clicked_(self, sender):
        label = str(sender.title())

        if label == "Minimize":
            if self.panel is not None: self.panel.miniaturize_(None)
            return
        if label == "Quit":
            from AppKit import NSApp
            NSApp.terminate_(None)
            return

        if label.startswith("Shift On"):
            self.shift_lock = not self.shift_lock
            sender.setTitle_("Shift On (LOCKED)" if self.shift_lock else "Shift On")
            return
        if label.startswith("Shift"):  
            self.shift_next = True
            sender.setTitle_("Shift (ON)")
            return

        shift_active = self.shift_lock or self.shift_next

        up = label.upper()
        if up in ("RETURN","TAB","DELETE","ESC","LEFT","RIGHT","UP","DOWN"):
            post_keycode(up)
            self._reset_shift_visuals(sender)
            return
        if up == "SPACE":
            type_unicode(" ")
            self._reset_shift_visuals(sender)
            return

        if len(label) == 1 and label in SHIFTED:
            type_unicode(label)
            self._reset_shift_visuals(sender)
            return

        if len(label) == 1:
            base = label
            if base.isalpha():
                ch = base.upper() if shift_active else base.lower()
            else:
                ch = (SHIFTED_REV.get(base, base) if shift_active else base)
            type_unicode(ch)
            self._reset_shift_visuals(sender)
            return

        if up in KEYCODES:
            post_keycode(up)
            self._reset_shift_visuals(sender)

    def _reset_shift_visuals(self, last_sender):
        if self.shift_next:
            self.shift_next = False
            parent = last_sender.superview()
            if parent is None: return
            for v in parent.subviews():
                try:
                    if str(v.title()) == "Shift (ON)":
                        v.setTitle_("Shift")
                except Exception:
                    pass

def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    style = (NSWindowStyleMaskNonactivatingPanel
             | NSWindowStyleMaskTitled
             | NSWindowStyleMaskMiniaturizable
             | NSWindowStyleMaskResizable)

    row1 = list("1234567890-=") + ["DELETE"]
    row2 = list("QWERTYUIOP") + ["[", "]", "\\"]
    row3 = list("ASDFGHJKL") + [";", "'", "RETURN"]
    row4 = ["TAB","Z","X","C","V","B","N","M",",",".","/","SPACE","LEFT","DOWN","UP","RIGHT","ESC"]

    bottom_left = ["Shift", "Shift On"]
    shifted_row = list("!@#$%^&*()_+{}|:\"<>?")
    bottom_right = ["Minimize", "Quit"]

    GAP_X, GAP_Y, MARGIN, KEY_H = 6, 8, 10, 30

    def row_width(labels):
        return 0 if not labels else sum(key_width_for(l) for l in labels) + GAP_X * (len(labels) - 1)

    widths = [
        row_width(row1), row_width(row2), row_width(row3), row_width(row4),
        row_width(bottom_left + shifted_row + bottom_right),
    ]
    content_width = max(widths) + 2 * MARGIN
    rows_count = 5
    content_height = (rows_count * KEY_H) + ((rows_count - 1) * GAP_Y) + 2 * MARGIN

    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(200, 600, content_width, content_height),
        style, NSBackingStoreBuffered, False
    )
    panel.setTitle_("On-Screen Keyboard")
    panel.setLevel_(NSStatusWindowLevel)
    panel.setHidesOnDeactivate_(False)
    panel.setBecomesKeyOnlyIfNeeded_(True)
    panel.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces
        | NSWindowCollectionBehaviorFullScreenAuxiliary
        | NSWindowCollectionBehaviorStationary
    )
    panel.setContentMinSize_((content_width, content_height))

    flipped = FlippedView.alloc().initWithFrame_(panel.contentView().frame())
    panel.setContentView_(flipped)

    handler = ClickHandler.alloc().init()
    handler.panel = panel

    y = MARGIN
    layout_row(flipped, handler, row1, MARGIN, y, key_h=KEY_H, gap=GAP_X); y += KEY_H + GAP_Y
    layout_row(flipped, handler, row2, MARGIN, y, key_h=KEY_H, gap=GAP_X); y += KEY_H + GAP_Y
    layout_row(flipped, handler, row3, MARGIN, y, key_h=KEY_H, gap=GAP_X); y += KEY_H + GAP_Y
    layout_row(flipped, handler, row4, MARGIN, y, key_h=KEY_H, gap=GAP_X); y += KEY_H + GAP_Y

    x = MARGIN
    x = layout_row(flipped, handler, bottom_left, x, y, key_h=KEY_H, gap=GAP_X); x += GAP_X
    layout_row(flipped, handler, shifted_row, x, y, key_h=KEY_H, gap=GAP_X)

    right_w = row_width(bottom_right)
    rx = max(MARGIN, content_width - MARGIN - right_w)
    layout_row(flipped, handler, bottom_right, rx, y, key_h=KEY_H, gap=GAP_X)

    panel.makeKeyAndOrderFront_(None)
    AppHelper.runEventLoop()

if __name__ == "__main__":
    main()
