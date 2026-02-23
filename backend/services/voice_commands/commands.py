from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

import json
import os
from pathlib import Path
from typing import Any

from pynput.keyboard import Controller, Key

SYSTEM = platform.system()


@dataclass(frozen=True)
class Command:
    name: str
    phrases: tuple[str, ...]
    action: Callable[[], None]
    description: str = ""

    @property
    def activation_phrase(self) -> str:
        return self.phrases[0] if self.phrases else ""

_KEY_ALIASES: dict[str, Key] = {
    "cmd": Key.cmd,
    "command": Key.cmd,
    "ctrl": Key.ctrl,
    "control": Key.ctrl,
    "alt": Key.alt,
    "option": Key.alt,
    "shift": Key.shift,
    "enter": Key.enter,
    "return": Key.enter,
    "tab": Key.tab,
    "space": Key.space,
    "esc": Key.esc,
    "escape": Key.esc,
    "backspace": Key.backspace,
    "delete": Key.delete,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
}

_KEY_LABELS: dict[str, str] = {
    "cmd": "Cmd",
    "command": "Cmd",
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "alt": "Alt",
    "option": "Alt",
    "shift": "Shift",
    "enter": "Enter",
    "return": "Enter",
    "tab": "Tab",
    "space": "Space",
    "esc": "Esc",
    "escape": "Esc",
    "backspace": "Backspace",
    "delete": "Delete",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
}


def _title_from_name(name: str) -> str:
    return (name or "").replace("_", " ").strip().title()


def _format_hotkey(keys: list[Any]) -> str:
    labels: list[str] = []
    for key in keys:
        token = str(key or "").strip().lower()
        if not token:
            continue
        if token in _KEY_LABELS:
            labels.append(_KEY_LABELS[token])
        elif len(token) == 1 and token.isalpha():
            labels.append(token.upper())
        else:
            labels.append(token.capitalize())
    return " + ".join(labels)


def _description_from_action(name: str, action_spec: dict[str, Any]) -> str:
    action_type = str(action_spec.get("type") or "").strip().lower()
    if action_type == "open_app":
        app = str(action_spec.get("app") or "").strip()
        return f"Open {app}" if app else f"Open {_title_from_name(name)}"
    if action_type == "open_url":
        url = str(action_spec.get("url") or "").strip()
        return f"Open {url}" if url else f"Open {_title_from_name(name)}"
    if action_type == "type_text":
        return f"Type text for {_title_from_name(name)}"
    if action_type == "hotkey":
        keys = action_spec.get("keys")
        if isinstance(keys, list):
            combo = _format_hotkey(keys)
            if combo:
                return f"Press {combo}"
        return f"Run {_title_from_name(name)}"
    return f"Run {_title_from_name(name)}"


def _as_key(k: str) -> Key | str:
    kk = (k or "").strip().lower()
    if kk in _KEY_ALIASES:
        return _KEY_ALIASES[kk]
    if len(kk) == 1:
        return kk
    if kk.startswith("f") and kk[1:].isdigit():
        n = int(kk[1:])
        try:
            return getattr(Key, f"f{n}")
        except Exception:
            pass
    return kk


def _action_from_spec(spec: dict[str, Any], os_keyboard: Controller) -> Callable[[], None]:
    t = (spec.get("type") or "").strip().lower()

    def open_app(app_name: str) -> None:
        if SYSTEM == "Darwin":
            subprocess.run(["open", "-a", app_name], capture_output=True, text=True)
        elif SYSTEM == "Windows":
            subprocess.run(["cmd", "/c", "start", "", app_name], capture_output=True, text=True)
        else:
            subprocess.run(["xdg-open", app_name], capture_output=True, text=True)

    def open_url(url: str) -> None:
        if SYSTEM == "Darwin":
            subprocess.run(["open", url], capture_output=True, text=True)
        elif SYSTEM == "Windows":
            subprocess.run(["cmd", "/c", "start", "", url], capture_output=True, text=True)
        else:
            subprocess.run(["xdg-open", url], capture_output=True, text=True)

    if t == "open_app":
        app = str(spec.get("app") or "").strip()
        return lambda: open_app(app)

    if t == "open_url":
        url = str(spec.get("url") or "").strip()
        return lambda: open_url(url)

    if t == "type_text":
        text = str(spec.get("text") or "")
        return lambda: os_keyboard.type(text)

    if t == "hotkey":
        keys = spec.get("keys")
        if not isinstance(keys, list):
            keys = []
        seq = [_as_key(str(k)) for k in keys]

        def _press_release() -> None:
            for k in seq:
                os_keyboard.press(k)
            for k in reversed(seq):
                os_keyboard.release(k)

        return _press_release

    return lambda: None


def load_command_pack(pack_path: str | os.PathLike[str], os_keyboard: Controller) -> list[Command]:
    if not pack_path:
        return []

    p = Path(pack_path).expanduser()
    if not p.exists() or not p.is_file():
        return []

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[VoiceCommands] WARNING: failed to parse command pack {p}: {e}")
        return []

    if not isinstance(raw, list):
        print(f"[VoiceCommands] WARNING: command pack {p} must be a JSON list")
        return []

    cmds: list[Command] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        phrases = item.get("phrases")
        action_spec = item.get("action")
        if not name or not isinstance(phrases, list) or not isinstance(action_spec, dict):
            continue
        ph = tuple(str(x) for x in phrases if str(x).strip())
        if not ph:
            continue
        action = _action_from_spec(action_spec, os_keyboard)
        description = str(item.get("description") or "").strip()
        if not description:
            description = _description_from_action(name, action_spec)
        cmds.append(Command(name=name, phrases=ph, action=action, description=description))

    return cmds


def _platform_pack_path() -> Optional[Path]:
    packs_dir = Path(__file__).resolve().parent / "packs"

    sys_name = platform.system()
    if sys_name == "Darwin":
        return packs_dir / "mac.json"
    if sys_name == "Windows":
        return packs_dir / "windows.json"

    return None


def load_platform_command_pack(os_keyboard: Controller) -> list[Command]:
    p = _platform_pack_path()
    if p is None:
        return []
    return load_command_pack(p, os_keyboard)


def build_commands(os_keyboard: Controller) -> list[Command]:
    platform_cmds = load_platform_command_pack(os_keyboard)
    if platform_cmds:
        return platform_cmds

    def open_app(app_name: str) -> None:
        if SYSTEM == "Darwin":
            subprocess.run(["open", "-a", app_name], capture_output=True, text=True)
        elif SYSTEM == "Windows":
            subprocess.run(["cmd", "/c", "start", "", app_name], capture_output=True, text=True)
        else:
            subprocess.run(["xdg-open", app_name], capture_output=True, text=True)

    def open_url(url: str) -> None:
        if SYSTEM == "Darwin":
            subprocess.run(["open", url], capture_output=True, text=True)
        elif SYSTEM == "Windows":
            subprocess.run(["cmd", "/c", "start", "", url], capture_output=True, text=True)
        else:
            subprocess.run(["xdg-open", url], capture_output=True, text=True)

    def close_window() -> None:
        os_keyboard.press(Key.cmd)
        os_keyboard.press("w")
        os_keyboard.release("w")
        os_keyboard.release(Key.cmd)

    def noop() -> None:
        return

    return [
        Command(
            name="open_safari",
            phrases=("open safari", "safari", "launch safari"),
            action=lambda: open_app("Safari"),
            description="Open Safari",
        ),
        Command(
            name="close_window",
            phrases=("close window", "close this", "close tab"),
            action=close_window,
            description="Close the current window or tab",
        ),
        Command(
            name="open_whatsapp",
            phrases=("open whatsapp", "whatsapp", "launch whatsapp"),
            action=lambda: open_app("WhatsApp"),
            description="Open WhatsApp",
        ),
        Command(
            name="open_mun",
            phrases=("open mun", "open online mun", "mun login"),
            action=lambda: open_url("https://online.mun.ca"),
            description="Open the MUN login page",
        ),
        Command(
            name="stop_listening",
            phrases=("stop listening", "voice off", "disable commands"),
            action=noop,
            description="Disable command mode",
        ),
    ]
