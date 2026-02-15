from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from typing import Callable

from pynput.keyboard import Controller, Key

SYSTEM = platform.system()


@dataclass(frozen=True)
class Command:
    name: str
    phrases: tuple[str, ...]
    action: Callable[[], None]


def build_commands(os_keyboard: Controller) -> list[Command]:
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
        ),
        Command(
            name="close_window",
            phrases=("close window", "close this", "close tab"),
            action=close_window,
        ),
        Command(
            name="open_whatsapp",
            phrases=("open whatsapp", "whatsapp", "launch whatsapp"),
            action=lambda: open_app("WhatsApp"),
        ),
        Command(
            name="open_mun",
            phrases=("open mun", "open online mun", "mun login"),
            action=lambda: open_url("https://online.mun.ca"),
        ),
        Command(
            name="stop_listening",
            phrases=("stop listening", "voice off", "disable commands"),
            action=noop,
        ),
    ]
