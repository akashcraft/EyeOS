"""
EyeOS Voice-to-Text Service (Cross-Platform)

Goal:
- Press a global hotkey to START listening.
- Press the hotkey again to STOP.
- Transcribe speech locally (offline) using Vosk.
- Type the recognized text into whatever app currently has focus.

Dependencies:
  pip install vosk sounddevice pynput
  # Windows (for better focus restore):
  pip install pywin32 psutil
  # Optional macOS overlay:
  pip install pyobjc

Model:
- Download a Vosk model (e.g., vosk-model-small-en-us-0.15)
- Set env var VOSK_MODEL_PATH to the model directory OR place it at:
    <repo_root>/backend/models/vosk-model-small-en-us-0.15

macOS notes:
- For "type into other apps" to work, your Python process/app will need
  Accessibility permission: System Settings -> Privacy & Security -> Accessibility.
- Global hotkeys may also require Input Monitoring permission.
- For microphone: Privacy & Security -> Microphone.

Hotkey:
- Default: F8 (toggle start/stop)
- F9: type a test string into the focused app
- Run with --overlay for a non-activating macOS overlay button (no focus stealing).
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any
import queue

import sounddevice as sd
from pynput import keyboard
from pynput.keyboard import Controller
from vosk import KaldiRecognizer, Model

SYSTEM = platform.system()


# ----------------------------
# Optional Windows imports (lazy)
# ----------------------------
_WIN_OK = False
if SYSTEM == "Windows":
    try:
        import psutil
        import win32gui
        import win32process

        _WIN_OK = True
    except Exception:
        _WIN_OK = False


def _is_our_process_windows(pid: int) -> bool:
    """Best-effort: ignore windows that belong to our current python process, plus common dev shells."""
    if not _WIN_OK:
        return False
    try:
        me = psutil.Process().pid
        if pid == me:
            return True
        name = psutil.Process(pid).name().lower()
        return name in {
            "python.exe",
            "pythonw.exe",
            "cmd.exe",
            "powershell.exe",
            "windowsterminal.exe",
            "code.exe",
            "code - insiders.exe",
        }
    except Exception:
        return False


# ----------------------------
# GUI (Tkinter) — cross-platform
# ----------------------------
def run_gui(service: "VoiceToTextService") -> None:
    """Run a minimal start/stop GUI (non-blocking hotkeys still work)."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as e:
        print(f"[VoiceToText] GUI unavailable (tkinter import failed): {e}")
        service.start_hotkey_listener()
        return

    root = tk.Tk()
    root.title("EyeOS Voice-to-Text")
    root.resizable(False, False)

    status_var = tk.StringVar(value="Idle")

    def refresh_status() -> None:
        service._update_last_external_target()
        status_var.set("Listening" if service._is_recording else "Idle")
        toggle_btn.configure(text="Stop" if service._is_recording else "Start")
        root.after(150, refresh_status)

    def on_toggle() -> None:
        service.toggle()
        if service.config.restore_focus_to_target_app:
            target = service._target_token or service._last_external_token
            if target is not None:
                service._activate_target(target)

    def on_quit() -> None:
        try:
            service.stop()
        finally:
            try:
                service._hotkeys.stop()
            except Exception:
                pass
            root.destroy()

    try:
        service._hotkeys.start()
    except Exception:
        pass

    frame = ttk.Frame(root, padding=14)
    frame.grid(row=0, column=0)

    title = ttk.Label(frame, text="Voice-to-Text", font=("TkDefaultFont", 16, "bold"))
    title.grid(row=0, column=0, columnspan=2, sticky="w")

    status_lbl = ttk.Label(frame, textvariable=status_var)
    status_lbl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 10))

    toggle_btn = ttk.Button(frame, text="Start", command=on_toggle)
    toggle_btn.grid(row=2, column=0, sticky="ew", padx=(0, 8))

    quit_btn = ttk.Button(frame, text="Quit", command=on_quit)
    quit_btn.grid(row=2, column=1, sticky="ew")

    hint = ttk.Label(
        frame,
        text="Hotkeys: F8 toggle listen | F9 type test",
        foreground="#666666",
    )
    hint.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    root.protocol("WM_DELETE_WINDOW", on_quit)
    refresh_status()
    root.mainloop()


# ----------------------------
# macOS Overlay Panel (HUD) — macOS only
# ----------------------------
def run_overlay(service: "VoiceToTextService") -> None:
    """
    Run a macOS non-activating floating Start/Stop button.

    Requires: `pip install pyobjc` (macOS only). If PyObjC isn't available,
    fall back to Tk GUI.
    """
    if SYSTEM != "Darwin":
        print("[VoiceToText] Overlay is macOS-only. Falling back to Tk GUI...")
        run_gui(service)
        return

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
            NSTextField,
        )
        from PyObjCTools import AppHelper
        import Foundation
    except Exception as e:
        print(f"[VoiceToText] Overlay unavailable (PyObjC import failed): {e}")
        print("[VoiceToText] Falling back to Tk GUI...")
        run_gui(service)
        return

    try:
        service._hotkeys.start()
    except Exception:
        pass

    _app = NSApplication.sharedApplication()

    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(40, 80, 360, 118),
        NSWindowStyleMaskTitled | NSWindowStyleMaskNonactivatingPanel,
        NSBackingStoreBuffered,
        False,
    )

    panel.setBecomesKeyOnlyIfNeeded_(True)
    panel.setHidesOnDeactivate_(False)
    panel.setFloatingPanel_(True)
    panel.setLevel_(NSStatusWindowLevel)
    panel.setTitle_("Voice")

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
            self._refresh()

    controller = OverlayController.alloc().init()

    btn = NSButton.alloc().initWithFrame_(NSMakeRect(14, 62, 120, 36))
    btn.setTitle_("Start")
    btn.setBezelStyle_(10)
    btn.setAlignment_(NSTextAlignmentCenter)
    btn.setFont_(NSFont.boldSystemFontOfSize_(14))
    btn.setTarget_(controller)
    btn.setAction_(b"clicked:")

    status = NSTextField.alloc().initWithFrame_(NSMakeRect(154, 62, 190, 22))
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
    controller._btn = btn
    controller._status = status

    effect_view.addSubview_(btn)
    effect_view.addSubview_(status)
    effect_view.addSubview_(partial)

    Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        0.2, controller, b"tick:", None, True
    )

    panel.orderFrontRegardless()
    print("[VoiceToText] Overlay running (non-activating panel).")
    AppHelper.runEventLoop()


# ----------------------------
# Service
# ----------------------------
@dataclass
class VoiceToTextConfig:
    hotkey: str = "<f8>"
    test_hotkey: str = "<f9>"
    samplerate: int = 16000
    channels: int = 1
    dtype: str = "int16"
    model_path: Optional[str] = None
    type_trailing_space: bool = True

    restore_focus_to_target_app: bool = True

    live_typing: bool = True
    live_flush_interval_s: float = 0.12


class VoiceToTextService:
    """Global-hotkey voice-to-text -> types into the active application."""

    def __init__(self, config: Optional[VoiceToTextConfig] = None) -> None:
        self.config = config or VoiceToTextConfig()

        self._keyboard = Controller()
        self._stop_event = threading.Event()
        self._is_recording = False
        self._worker_thread: Optional[threading.Thread] = None

        # Cross-platform focus tokens:
        # - macOS: app name (str)
        # - Windows: hwnd (int)
        # - Others: None
        self._target_token: Optional[Any] = None
        self._last_external_token: Optional[Any] = None

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
        print(
            f"[VoiceToText] Hotkey listener started. Toggle: {self.config.hotkey} | "
            f"Test type: {self.config.test_hotkey}"
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
        if self._is_recording:
            self.stop()
        else:
            if self.config.restore_focus_to_target_app and self._last_external_token is not None:
                self.start(target_override=self._last_external_token)
            else:
                self.start()

    def type_test(self) -> None:
        token = None
        if self.config.restore_focus_to_target_app:
            token = self._last_external_token or self._get_frontmost_target()

        if token is not None:
            self._activate_target(token)
            time.sleep(0.08)

        test_text = "[VoiceToText TEST] "
        print(f"[VoiceToText] Typing test -> {test_text!r}")
        try:
            self._keyboard.type(test_text)
        except Exception as e:
            print(f"[VoiceToText] ERROR typing test: {e}")

    def start(self, target_override: Optional[Any] = None) -> None:
        if self._is_recording:
            return

        self._stop_event.clear()

        if self.config.restore_focus_to_target_app:
            self._target_token = target_override or self._get_frontmost_target()
            if self._target_token is not None:
                print(f"[VoiceToText] Target captured: {self._target_token!r}")

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
    # Focus capture/restore
    # ----------------------------
    def _get_frontmost_target(self) -> Optional[Any]:
        """Return platform-specific 'focus token'."""
        if SYSTEM == "Darwin":
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

        if SYSTEM == "Windows" and _WIN_OK:
            try:
                hwnd = win32gui.GetForegroundWindow()
                return int(hwnd) if hwnd else None
            except Exception:
                return None

        return None

    def _activate_target(self, token: Any) -> None:
        """Bring the captured target back to the front (best-effort)."""
        if token is None:
            return

        if SYSTEM == "Darwin":
            try:
                subprocess.run(
                    ["osascript", "-e", f'tell application "{token}" to activate'],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except Exception:
                pass
            return

        if SYSTEM == "Windows" and _WIN_OK:
            try:
                hwnd = int(token)
                if not win32gui.IsWindow(hwnd):
                    return
                win32gui.ShowWindow(hwnd, 9)
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            return

    def _update_last_external_target(self) -> None:
        """Track last frontmost target that is NOT our own process/dev shells (Windows) or GUI-like apps (macOS)."""
        token = self._get_frontmost_target()
        if token is None:
            return

        if SYSTEM == "Darwin":
            name = token
            if name in {"Python", "Wish", "Terminal", "iTerm2", "VSCodium", "Visual Studio Code"}:
                return
            self._last_external_token = name
            return

        if SYSTEM == "Windows" and _WIN_OK:
            hwnd = int(token)
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if _is_our_process_windows(pid):
                    return
            except Exception:
                return
            self._last_external_token = hwnd
            return

    # ----------------------------
    # Model path + UI partial
    # ----------------------------
    def _resolve_model_path(self) -> str:
        if self.config.model_path:
            return self.config.model_path

        env_path = os.getenv("VOSK_MODEL_PATH")
        if env_path:
            return env_path

        backend_dir = Path(__file__).resolve().parents[1]
        models_dir = backend_dir / "models"
        candidate = models_dir / "vosk-model-small-en-us-0.15"
        if candidate.exists():
            return str(candidate)

        if models_dir.exists():
            for p in sorted(models_dir.glob("vosk-model-*/")):
                return str(p)

        raise FileNotFoundError(
            "Vosk model not found. Set VOSK_MODEL_PATH to your model folder, "
            "or place a model under backend/models/ (e.g., vosk-model-small-en-us-0.15)."
        )

    def _ui_set_partial(self, text: str) -> None:
        with self._ui_lock:
            self._latest_partial = text

    def get_partial(self) -> str:
        with self._ui_lock:
            return self._latest_partial

    # ----------------------------
    # Audio + Vosk + typing
    # ----------------------------
    def _record_transcribe_type(self) -> None:
        recognizer = KaldiRecognizer(self._model, self.config.samplerate)
        recognizer.SetWords(True)

        segments: list[str] = []
        out_q: "queue.Queue[str]" = queue.Queue()
        committed_words: list[str] = []
        activated_once = False

        def _enqueue_words(text: str) -> None:
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
                print(f"[VoiceToText] Audio status: {status}")

            if self._stop_event.is_set():
                return

            data = bytes(indata)
            if recognizer.AcceptWaveform(data):
                try:
                    result = json.loads(recognizer.Result())
                    text = (result.get("text") or "").strip()
                    if text:
                        segments.append(text)
                        self._ui_set_partial("")
                        if self.config.live_typing:
                            seg_words = text.split()
                            if _starts_with_prefix(seg_words, committed_words):
                                new_words = seg_words[len(committed_words) :]
                                if new_words:
                                    _enqueue_words(" ".join(new_words))
                                    committed_words.extend(new_words)
                            else:
                                _enqueue_words(text)
                                committed_words[:] = seg_words
                except Exception:
                    pass
            else:
                if not self.config.live_typing:
                    return
                try:
                    part = json.loads(recognizer.PartialResult())
                    ptxt = (part.get("partial") or "").strip()
                    self._ui_set_partial(ptxt)
                    if not ptxt:
                        return
                    pwords = ptxt.split()
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
                blocksize=0,
            ):
                while not self._stop_event.is_set():
                    if self.config.live_typing:
                        to_type: list[str] = []
                        try:
                            while True:
                                to_type.append(out_q.get_nowait())
                        except queue.Empty:
                            pass

                        if to_type:
                            if (
                                self.config.restore_focus_to_target_app
                                and self._target_token is not None
                                and not activated_once
                            ):
                                self._activate_target(self._target_token)
                                time.sleep(0.10)
                                activated_once = True
                            self._keyboard.type("".join(to_type))

                    time.sleep(self.config.live_flush_interval_s)

            if self.config.live_typing:
                to_type: list[str] = []
                try:
                    while True:
                        to_type.append(out_q.get_nowait())
                except queue.Empty:
                    pass
                if to_type:
                    if self.config.restore_focus_to_target_app and self._target_token is not None and not activated_once:
                        self._activate_target(self._target_token)
                        time.sleep(0.10)
                        activated_once = True
                    self._keyboard.type("".join(to_type))

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

            final_to_type = ""
            if transcript:
                if self.config.live_typing:
                    words = transcript.split()
                    if _starts_with_prefix(words, committed_words):
                        remaining = words[len(committed_words) :]
                        if remaining:
                            final_to_type = " ".join(remaining)
                    else:
                        final_to_type = transcript
                else:
                    final_to_type = transcript

            if final_to_type:
                if self.config.restore_focus_to_target_app and self._target_token is not None:
                    self._activate_target(self._target_token)
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


# ----------------------------
# Entrypoint
# ----------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="EyeOS voice-to-text service")
    parser.add_argument("--gui", action="store_true", help="Launch a small Start/Stop window (hotkeys still work)")
    parser.add_argument("--overlay", action="store_true", help="Launch a macOS non-activating overlay (macOS only)")
    args = parser.parse_args()

    service = VoiceToTextService()

    if args.overlay:
        run_overlay(service)
    elif args.gui:
        run_gui(service)
    else:
        service.start_hotkey_listener()
