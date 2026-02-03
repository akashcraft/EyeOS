"""EyeOS Voice-to-Text Service

Goal:
- Press a global hotkey to START listening.
- Press the hotkey again to STOP.
- Transcribe speech locally (offline) using Vosk.
- Type the recognized text into whatever app currently has focus.

Dependencies:
  pip install vosk sounddevice pynput
  # Optional UI overlay on macOS:
  # pip install pyobjc

Model:
- Download a Vosk model (e.g., vosk-model-small-en-us-0.15)
- Set env var VOSK_MODEL_PATH to the model directory OR place it at:
    <repo_root>/backend/models/vosk-model-small-en-us-0.15

macOS notes:
- For "type into other apps" to work, your Python process/app will need
  Accessibility permission: System Settings -> Privacy & Security -> Accessibility.
- Global hotkeys may also require Input Monitoring permission (Privacy & Security -> Input Monitoring) for the app you run this from (Terminal/Python/VSCodium).
- For microphone: Privacy & Security -> Microphone.

Hotkey:
- Default: F8 (toggle start/stop)
- F9: type a test string into the focused app
- Run with --overlay for a non-activating macOS overlay button (no focus stealing).
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import queue

import sounddevice as sd
from pynput import keyboard
from pynput.keyboard import Controller
from vosk import KaldiRecognizer, Model

# GUI is optional. We import lazily in `run_gui()` to avoid hard failures on systems
# without Tkinter.


def run_gui(service: "VoiceToTextService") -> None:
    """Run a minimal start/stop GUI (non-blocking hotkeys still work)."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as e:
        print(f"[VoiceToText] GUI unavailable (tkinter import failed): {e}")
        print("[VoiceToText] Tip: On macOS, make sure you're using a Python build with Tk support.")
        # Fall back to hotkey-only mode
        service.start_hotkey_listener()
        return

    root = tk.Tk()
    root.title("EyeOS Voice-to-Text")
    root.resizable(False, False)

    status_var = tk.StringVar(value="Idle")

    def refresh_status() -> None:
        # Track the last non-GUI frontmost app so clicking the GUI doesn't break typing target.
        service._update_last_external_app()
        status_var.set("Listening" if service._is_recording else "Idle")
        toggle_btn.configure(text="Stop" if service._is_recording else "Start")
        root.after(150, refresh_status)

    def on_toggle() -> None:
        # Toggle start/stop. If the GUI stole focus, we restore focus to the last external app.
        service.toggle()
        if service.config.restore_focus_to_target_app:
            target = service._target_app_name or service._last_external_app_name
            if target:
                service._activate_app(target)

    def on_quit() -> None:
        try:
            service.stop()
        finally:
            try:
                service._hotkeys.stop()
            except Exception:
                pass
            root.destroy()

    # Start global hotkeys so F8/F9 work even with the GUI.
    service._hotkeys.start()

    frame = ttk.Frame(root, padding=14)
    frame.grid(row=0, column=0)

    title = ttk.Label(frame, text="Voice-to-Text", font=("-apple-system", 16, "bold"))
    title.grid(row=0, column=0, columnspan=2, sticky="w")

    status_lbl = ttk.Label(frame, textvariable=status_var)
    status_lbl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 10))

    toggle_btn = ttk.Button(frame, text="Start", command=on_toggle)
    toggle_btn.grid(row=2, column=0, sticky="ew", padx=(0, 8))

    quit_btn = ttk.Button(frame, text="Quit", command=on_quit)
    quit_btn.grid(row=2, column=1, sticky="ew")

    hint = ttk.Label(
        frame,
        text=f"Hotkeys: F8 toggle listen | F9 type test\nGUI won’t steal focus: it restores to your last app (WhatsApp/Word/etc.)",
        foreground="#666666",
    )
    hint.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    root.protocol("WM_DELETE_WINDOW", on_quit)
    refresh_status()
    root.mainloop()


# ---- macOS Overlay Panel (HUD) ----
def run_overlay(service: "VoiceToTextService") -> None:
    """Run a macOS non-activating floating Start/Stop button.

    This is the same trick used in `keyboard.py`: an `NSPanel` with
    `NSWindowStyleMaskNonactivatingPanel` can be clicked without stealing focus
    from the active app (WhatsApp/Word/etc.).

    Hotkeys (F8/F9) still work while the overlay is up.

    Requires: `pip install pyobjc` (macOS only). If PyObjC isn't available, we
    fall back to `run_gui()`.
    """
    try:
        import objc
        from Cocoa import (
            NSApplication,
            NSPanel,
            NSButton,
            NSMakeRect,
            NSWindowStyleMaskTitled,
            NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            NSStatusWindowLevel,
            NSTextAlignmentCenter,
            NSVisualEffectView,
            NSVisualEffectMaterialHUDWindow,
            NSVisualEffectBlendingModeBehindWindow,
            NSFont,
            NSObject,
        )
        from PyObjCTools import AppHelper
        import Foundation
    except Exception as e:
        print(f"[VoiceToText] Overlay unavailable (PyObjC import failed): {e}")
        print("[VoiceToText] Falling back to Tk GUI...")
        run_gui(service)
        return

    # Start global hotkeys so F8/F9 work even with the overlay.
    try:
        service._hotkeys.start()
    except Exception:
        pass

    _app = NSApplication.sharedApplication()

    # Small HUD-style non-activating panel.
    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(40, 80, 360, 118),
        NSWindowStyleMaskTitled | NSWindowStyleMaskNonactivatingPanel,
        NSBackingStoreBuffered,
        False,
    )

    # Key bits: don't steal focus.
    panel.setBecomesKeyOnlyIfNeeded_(True)
    panel.setHidesOnDeactivate_(False)
    panel.setFloatingPanel_(True)
    panel.setLevel_(NSStatusWindowLevel)
    panel.setTitle_("Voice")

    # Modern macOS HUD look (similar to keyboard.py).
    effect_view = NSVisualEffectView.alloc().initWithFrame_(panel.contentView().bounds())
    effect_view.setMaterial_(NSVisualEffectMaterialHUDWindow)
    effect_view.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
    effect_view.setState_(1)
    panel.setContentView_(effect_view)

    class OverlayController(NSObject):
        def init(self):
            self = objc.super(OverlayController, self).init()
            self._btn = None
            self._status = None
            self._partial = None
            return self

        def clicked_(self, _sender):
            # Toggle start/stop. Panel should not take focus.
            service.toggle()
            self._refresh()

        def _refresh(self):
            if self._btn is not None:
                self._btn.setTitle_("Stop" if service._is_recording else "Start")
            if self._status is not None:
                self._status.setStringValue_("Listening" if service._is_recording else "Idle")
            if self._partial is not None:
                self._partial.setStringValue_(service.get_partial())

        def tick_(self, _timer):
            # Keep UI synced if toggled via hotkey.
            self._refresh()

    controller = OverlayController.alloc().init()

    # Button
    btn = NSButton.alloc().initWithFrame_(NSMakeRect(14, 62, 120, 36))
    btn.setTitle_("Start")
    btn.setBezelStyle_(10)  # rounded
    btn.setAlignment_(NSTextAlignmentCenter)
    btn.setFont_(NSFont.boldSystemFontOfSize_(14))
    btn.setTarget_(controller)
    btn.setAction_(b"clicked:")

    # Status label (NSTextField)
    from Cocoa import NSTextField

    status = NSTextField.alloc().initWithFrame_(NSMakeRect(154, 26, 70, 22))
    status.setBezeled_(False)
    status.setDrawsBackground_(False)
    status.setEditable_(False)
    status.setSelectable_(False)
    status.setAlignment_(NSTextAlignmentCenter)
    status.setStringValue_("Idle")

    partial = NSTextField.alloc().initWithFrame_(NSMakeRect(14, 18, 332, 34))
    partial.setBezeled_(False)
    partial.setDrawsBackground_(False)
    partial.setEditable_(False)
    partial.setSelectable_(False)
    partial.setStringValue_("")
    partial.setUsesSingleLineMode_(False)
    partial.setLineBreakMode_(0)

    controller._partial = partial
    effect_view.addSubview_(partial)

    controller._btn = btn
    controller._status = status

    effect_view.addSubview_(btn)
    effect_view.addSubview_(status)

    # Timer to refresh title/status.
    Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        0.2, controller, b"tick:", None, True
    )

    panel.orderFrontRegardless()
    print("[VoiceToText] Overlay running (non-activating panel).")
    AppHelper.runEventLoop()


@dataclass
class VoiceToTextConfig:
    hotkey: str = "<f8>"  # pynput GlobalHotKeys format
    test_hotkey: str = "<f9>"  # types a test string into the focused app
    samplerate: int = 16000
    channels: int = 1
    blocksize: int = 8000  # ~0.5s at 16kHz (bytes depend on dtype)
    dtype: str = "int16"   # Vosk expects 16-bit PCM
    model_path: Optional[str] = None  # if None, auto-detect
    type_trailing_space: bool = True
    restore_focus_to_target_app: bool = True
    live_typing: bool = True  # type words as they become stable (using partial results)
    live_flush_interval_s: float = 0.12  # how often we flush queued text to the OS


class VoiceToTextService:
    """Global-hotkey voice-to-text -> types into the active application."""

    def __init__(self, config: Optional[VoiceToTextConfig] = None) -> None:
        self.config = config or VoiceToTextConfig()

        self._keyboard = Controller()
        self._stop_event = threading.Event()
        self._is_recording = False
        self._worker_thread: Optional[threading.Thread] = None
        self._target_app_name: Optional[str] = None
        self._last_external_app_name: Optional[str] = None
        self._gui_app_names = {"Python", "Wish", "Terminal", "iTerm2", "VSCodium", "Visual Studio Code"}
        self._ui_lock = threading.Lock()
        self._latest_partial = ""

        self._model = Model(self._resolve_model_path())
        self._hotkeys = keyboard.GlobalHotKeys(
            {
                self.config.hotkey: self.toggle,
                self.config.test_hotkey: self.type_test,
            }
        )

    # ----------------------------
    # Public API
    # ----------------------------

    def start_hotkey_listener(self) -> None:
        """Start listening for the hotkey (blocking)."""
        print(
            f"[VoiceToText] Hotkey listener started. Toggle listen: {self.config.hotkey} | "
            f"Type test: {self.config.test_hotkey}"
        )
        self._hotkeys.start()
        try:
            while True:
                time.sleep(0.25)
        except KeyboardInterrupt:
            print("\n[VoiceToText] Exiting...")
        finally:
            self.stop()
            self._hotkeys.stop()

    def toggle(self) -> None:
        """Toggle recording on/off."""
        if self._is_recording:
            self.stop()
        else:
            # Prefer the last external app (e.g., WhatsApp/Word) if we have one.
            if self.config.restore_focus_to_target_app and self._last_external_app_name:
                self.start(target_app_override=self._last_external_app_name)
            else:
                self.start()

    def type_test(self) -> None:
        """Type a known string into the currently focused app (permission/debug check)."""
        app_name = None
        if self.config.restore_focus_to_target_app:
            app_name = self._last_external_app_name or self._get_frontmost_app_name()
        if app_name:
            self._activate_app(app_name)
            time.sleep(0.08)
        test_text = "[VoiceToText TEST] "
        print(f"[VoiceToText] Typing test -> {test_text!r}")
        try:
            self._keyboard.type(test_text)
        except Exception as e:
            print(f"[VoiceToText] ERROR typing test: {e}")

    def start(self, target_app_override: Optional[str] = None) -> None:
        if self._is_recording:
            return

        self._stop_event.clear()
        if self.config.restore_focus_to_target_app:
            # If the GUI stole focus, use the last external app we tracked.
            self._target_app_name = target_app_override or self._get_frontmost_app_name()
            if self._target_app_name:
                print(f"[VoiceToText] Target app captured: {self._target_app_name}")
        self._is_recording = True

        self._worker_thread = threading.Thread(target=self._record_transcribe_type, daemon=True)
        self._worker_thread.start()
        print("[VoiceToText] Listening... (press hotkey again to stop)")

    def stop(self) -> None:
        if not self._is_recording:
            return

        self._stop_event.set()
        self._is_recording = False
        print("[VoiceToText] Stopping...")

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)

    # ----------------------------
    # Internals
    # ----------------------------

    def _resolve_model_path(self) -> str:
        """Resolve Vosk model path from config/env/default."""
        # 1) Explicit config
        if self.config.model_path:
            return self.config.model_path

        # 2) Environment variable
        env_path = os.getenv("VOSK_MODEL_PATH")
        if env_path:
            return env_path

        # 3) Repo default: backend/models/<vosk-model-small-en-us-0.15>
        # This file lives at: EyeOS/backend/services/voice_to_text.py
        backend_dir = Path(__file__).resolve().parents[1]
        models_dir = backend_dir / "models"
        candidate = models_dir / "vosk-model-small-en-us-0.15"
        if candidate.exists():
            return str(candidate)

        # 4) Fallback: models_dir/<any vosk-model-*>
        if models_dir.exists():
            for p in sorted(models_dir.glob("vosk-model-*/")):
                return str(p)

        raise FileNotFoundError(
            "Vosk model not found. Set VOSK_MODEL_PATH to your model folder, "
            "or place a model under backend/models/ (e.g., vosk-model-small-en-us-0.15)."
        )

    def _get_frontmost_app_name(self) -> Optional[str]:
        """Return the frontmost macOS application name (best-effort)."""
        if os.name != "posix":
            return None
        try:
            proc = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            name = (proc.stdout or "").strip()
            return name or None
        except Exception:
            return None

    def _activate_app(self, app_name: str) -> None:
        """Bring a macOS app to the front (best-effort)."""
        if os.name != "posix":
            return
        try:
            subprocess.run(
                ["osascript", "-e", f'tell application "{app_name}" to activate'],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            pass

    def _update_last_external_app(self) -> None:
        """Track the most recent frontmost app that is NOT this script/GUI."""
        name = self._get_frontmost_app_name()
        if not name:
            return
        if name in self._gui_app_names:
            return
        # Record as last known external target
        self._last_external_app_name = name

    def _ui_set_partial(self, text: str) -> None:
        with self._ui_lock:
            self._latest_partial = text

    def get_partial(self) -> str:
        with self._ui_lock:
            return self._latest_partial

    def _record_transcribe_type(self) -> None:
        """Record until stop, transcribe with Vosk, and type into active app."""
        recognizer = KaldiRecognizer(self._model, self.config.samplerate)
        recognizer.SetWords(True)

        # We collect final segments to produce a clean final string.
        segments: list[str] = []
        out_q: "queue.Queue[str]" = queue.Queue()
        committed_words: list[str] = []  # words already typed in live mode
        activated_once = False

        def _enqueue_words(text: str) -> None:
            # Enqueue a string of words to type (adds trailing space).
            t = (text or "").strip()
            if not t:
                return
            out_q.put(t + " ")

        def _starts_with_prefix(full: list[str], prefix: list[str]) -> bool:
            if len(prefix) > len(full):
                return False
            return full[: len(prefix)] == prefix

        def on_audio(indata: bytes, frames: int, time_info, status) -> None:
            if status:
                # Non-fatal warnings (over/under-runs) can happen.
                print(f"[VoiceToText] Audio status: {status}")

            if self._stop_event.is_set():
                return

            data = bytes(indata)  # cffi buffer -> bytes for Vosk
            if recognizer.AcceptWaveform(data):
                # A finalized segment (more stable than partial).
                try:
                    result = json.loads(recognizer.Result())
                    text = (result.get("text") or "").strip()
                    if text:
                        segments.append(text)
                        self._ui_set_partial("")
                        if self.config.live_typing:
                            # Only type words we haven't already typed.
                            seg_words = text.split()
                            if _starts_with_prefix(seg_words, committed_words):
                                new_words = seg_words[len(committed_words) :]
                                if new_words:
                                    _enqueue_words(" ".join(new_words))
                                    committed_words.extend(new_words)
                            else:
                                # If alignment is off, just enqueue the whole segment.
                                _enqueue_words(text)
                                committed_words[:] = seg_words
                except Exception:
                    pass
            else:
                # Partial (intermediate) hypothesis.
                if not self.config.live_typing:
                    return
                try:
                    part = json.loads(recognizer.PartialResult())
                    ptxt = (part.get("partial") or "").strip()
                    self._ui_set_partial(ptxt)
                    if not ptxt:
                        return
                    pwords = ptxt.split()
                    # Only type forward when Vosk's partial is a clean prefix extension.
                    if _starts_with_prefix(pwords, committed_words):
                        new_words = pwords[len(committed_words) :]
                        if new_words:
                            _enqueue_words(" ".join(new_words))
                            committed_words.extend(new_words)
                except Exception:
                    pass

        try:
            with sd.RawInputStream(
                samplerate=self.config.samplerate,
                channels=self.config.channels,
                dtype=self.config.dtype,
                callback=on_audio,
                blocksize=0,  # let sounddevice pick a good block size
            ):
                # Poll until stop pressed.
                while not self._stop_event.is_set():
                    # Flush any live text queued by the audio callback.
                    if self.config.live_typing:
                        to_type: list[str] = []
                        try:
                            while True:
                                to_type.append(out_q.get_nowait())
                        except queue.Empty:
                            pass

                        if to_type:
                            if self.config.restore_focus_to_target_app and self._target_app_name and not activated_once:
                                self._activate_app(self._target_app_name)
                                time.sleep(0.10)
                                activated_once = True
                            self._keyboard.type("".join(to_type))

                    time.sleep(self.config.live_flush_interval_s)

            # After recording stops, flush any remaining queued partial text.
            if self.config.live_typing:
                # Flush any remaining queued partial text.
                to_type: list[str] = []
                try:
                    while True:
                        to_type.append(out_q.get_nowait())
                except queue.Empty:
                    pass
                if to_type:
                    if self.config.restore_focus_to_target_app and self._target_app_name and not activated_once:
                        self._activate_app(self._target_app_name)
                        time.sleep(0.10)
                        activated_once = True
                    self._keyboard.type("".join(to_type))

            # Pull any remaining text.
            try:
                final_res = json.loads(recognizer.FinalResult())
                final_text = (final_res.get("text") or "").strip()
                if final_text:
                    segments.append(final_text)
            except Exception:
                pass

            transcript = " ".join(s for s in segments if s).strip()
            if not transcript and not self.config.live_typing:
                print("[VoiceToText] (no speech recognized)")
                return

            # If live typing is enabled, only type any final words we didn't already type.
            final_to_type = ""
            if transcript:
                if self.config.live_typing:
                    words = transcript.split()
                    if _starts_with_prefix(words, committed_words):
                        remaining = words[len(committed_words) :]
                        if remaining:
                            final_to_type = " ".join(remaining)
                    else:
                        # Alignment broke; fall back to typing the whole transcript.
                        final_to_type = transcript
                else:
                    final_to_type = transcript

            if final_to_type:
                if self.config.restore_focus_to_target_app and self._target_app_name:
                    self._activate_app(self._target_app_name)
                    time.sleep(0.12)

                if self.config.type_trailing_space:
                    final_to_type += " "

                print(f"[VoiceToText] -> {final_to_type!r}")
                self._keyboard.type(final_to_type)
            else:
                print("[VoiceToText] (no additional final text)")

        except Exception as e:
            print(f"[VoiceToText] ERROR: {e}")
        finally:
            self._is_recording = False
            self._stop_event.set()




if __name__ == "__main__":
    # Run directly for quick testing:
    #   python -m backend.services.voice_to_text
    #   python -m backend.services.voice_to_text --gui
    #   python -m backend.services.voice_to_text --overlay
    import argparse

    parser = argparse.ArgumentParser(description="EyeOS voice-to-text service")
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch a small Start/Stop window (hotkeys still work)",
    )
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="Launch a macOS non-activating floating Start/Stop overlay",
    )
    args = parser.parse_args()

    service = VoiceToTextService()

    if args.overlay:
        run_overlay(service)
    elif args.gui:
        run_gui(service)
    else:
        service.start_hotkey_listener()
