from __future__ import annotations

import argparse
import difflib
import platform
import subprocess
import threading
import time
from typing import Callable, Optional

from pynput import keyboard
from pynput.keyboard import Controller, Key

from backend.services.voice_to_text import VoiceToTextConfig, VoiceToTextService
from backend.services.voice_commands.commands import Command, build_commands, load_command_pack

SYSTEM = platform.system()


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    for ch in ["!", "?", ".", ",", ":", ";", "\"", "'", "(", ")"]:
        s = s.replace(ch, " ")
    return " ".join(s.split())


def _best_score(cmd: Command, utterance: str) -> float:
    u = _norm(utterance)
    if not u:
        return 0.0
    best = 0.0
    for p in cmd.phrases:
        pn = _norm(p)
        if not pn:
            continue
        if u == pn:
            return 1.0
        best = max(best, difflib.SequenceMatcher(None, u, pn).ratio())
    return best


class _CaptureKeyboard:
    def __init__(self, on_text: Callable[[str], None]) -> None:
        self._on_text = on_text

    def type(self, text: str) -> None:
        self._on_text(text)


class VoiceCommandService:
    def __init__(
        self,
        toggle_hotkey: str = "<f10>",
        execute_threshold: float = 0.82,
        maybe_threshold: float = 0.75,
        cooldown_s: float = 0.6,
        pack_path: str | None = None,
        reload_pack_s: float = 1.0,
    ) -> None:
        self.toggle_hotkey = toggle_hotkey
        self.execute_threshold = execute_threshold
        self.maybe_threshold = maybe_threshold
        self.cooldown_s = cooldown_s

        self.pack_path = pack_path
        self.reload_pack_s = reload_pack_s

        self._pack_last_mtime: float | None = None
        self._pack_last_checked_at: float = 0.0

        self._active = False
        self._lock = threading.Lock()
        self._last_executed_at = 0.0

        self._os_keyboard = Controller()

        self._commands = self._load_all_commands()

        cfg = VoiceToTextConfig(
            restore_focus_to_target_app=False,
            live_typing=True,
        )
        self._vtt = VoiceToTextService(cfg)

        self._vtt._keyboard = _CaptureKeyboard(self._on_vtt_text)

        self._hotkeys = keyboard.GlobalHotKeys({self.toggle_hotkey: self.toggle})

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def start_hotkey_listener(self) -> None:
        print(f"[VoiceCommands] Hotkey listener started. Toggle: {self.toggle_hotkey}")
        self._hotkeys.start()
        try:
            while True:
                time.sleep(0.25)
        except KeyboardInterrupt:
            print("\n[VoiceCommands] Exiting...")
        finally:
            self.stop()
            try:
                self._hotkeys.stop()
            except Exception:
                pass

    def toggle(self) -> None:
        if self.is_active:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        with self._lock:
            if self._active:
                return
            self._active = True
        print("[VoiceCommands] Command Mode ON")
        self._vtt.start()

    def stop(self) -> None:
        with self._lock:
            if not self._active:
                return
            self._active = False
        print("[VoiceCommands] Command Mode OFF")
        self._vtt.stop()

    def _load_all_commands(self) -> list[Command]:
        builtins = build_commands(self._os_keyboard)
        extras: list[Command] = []
        if self.pack_path:
            extras = load_command_pack(self.pack_path, self._os_keyboard)
            if extras:
                print(f"[VoiceCommands] Loaded {len(extras)} commands from pack: {self.pack_path}")
        return builtins + extras

    def _maybe_reload_pack(self) -> None:
        if not self.pack_path:
            return
        now = time.time()
        if now - self._pack_last_checked_at < self.reload_pack_s:
            return
        self._pack_last_checked_at = now

        try:
            import os
            p = os.path.expanduser(self.pack_path)
            mtime = os.path.getmtime(p)
        except Exception:
            return

        if self._pack_last_mtime is None:
            self._pack_last_mtime = mtime
            return

        if mtime != self._pack_last_mtime:
            self._pack_last_mtime = mtime
            self._commands = self._load_all_commands()
            print("[VoiceCommands] Command pack reloaded")

    def _on_vtt_text(self, text: str) -> None:
        if not self.is_active:
            return

        self._maybe_reload_pack()

        t = _norm(text)
        if not t:
            return

        now = time.time()
        if now - self._last_executed_at < self.cooldown_s:
            return

        best_cmd: Optional[Command] = None
        best_score = 0.0
        for cmd in self._commands:
            s = _best_score(cmd, t)
            if s > best_score:
                best_score = s
                best_cmd = cmd

        if best_cmd is None:
            return

        if best_score >= self.execute_threshold:
            print(f"[VoiceCommands] Matched: {best_cmd.name} (score={best_score:.2f}) <- {t!r}")
            try:
                if best_cmd.name == "stop_listening":
                    self.stop()
                else:
                    best_cmd.action()
                self._last_executed_at = now
            except Exception as e:
                print(f"[VoiceCommands] ERROR executing {best_cmd.name}: {e}")
        elif best_score >= self.maybe_threshold:
            print(f"[VoiceCommands] Maybe: {best_cmd.name} (score={best_score:.2f}) <- {t!r}")

    def dry_run(self, text: str) -> None:
        self._commands = self._load_all_commands()
        t = _norm(text)
        if not t:
            print("[VoiceCommands] Dry-run: empty text")
            return

        best_cmd: Optional[Command] = None
        best_score = 0.0
        for cmd in self._commands:
            s = _best_score(cmd, t)
            if s > best_score:
                best_score = s
                best_cmd = cmd

        if best_cmd is None:
            print(f"[VoiceCommands] Dry-run: no match <- {t!r}")
            return

        verdict = (
            "EXECUTE" if best_score >= self.execute_threshold else
            "MAYBE" if best_score >= self.maybe_threshold else
            "NO"
        )
        print(f"[VoiceCommands] Dry-run: {verdict}: {best_cmd.name} (score={best_score:.2f}) <- {t!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="EyeOS voice command PoC (no edits to voice_to_text.py)")
    parser.add_argument("--hotkey", default="<f10>", help="Global hotkey to toggle command mode")
    parser.add_argument("--exec", dest="execute_threshold", type=float, default=0.82, help="Execute threshold")
    parser.add_argument("--maybe", dest="maybe_threshold", type=float, default=0.75, help="Maybe threshold")
    parser.add_argument("--cooldown", dest="cooldown_s", type=float, default=0.6, help="Cooldown seconds")
    parser.add_argument("--pack", default=None, help="Path to a JSON command pack file")
    parser.add_argument("--reload", dest="reload_pack_s", type=float, default=1.0, help="Pack reload polling seconds")
    parser.add_argument("--dry-run", dest="dry_run_text", default=None, help="Test matching with provided text and exit")
    args = parser.parse_args()

    svc = VoiceCommandService(
        toggle_hotkey=args.hotkey,
        execute_threshold=args.execute_threshold,
        maybe_threshold=args.maybe_threshold,
        cooldown_s=args.cooldown_s,
        pack_path=args.pack,
        reload_pack_s=args.reload_pack_s,
    )

    if args.dry_run_text is not None:
        svc.dry_run(args.dry_run_text)
        return

    svc.start_hotkey_listener()


if __name__ == "__main__":
    main()