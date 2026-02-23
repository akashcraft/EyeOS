from __future__ import annotations

import argparse
import platform
import tkinter as tk
from tkinter import ttk

try:
    from backend.services.voice_commands.commands import Command, build_commands
except ModuleNotFoundError:
    from commands import Command, build_commands


class _NoopKeyboardController:
    """Keyboard stub so command actions can be built without executing anything."""

    def press(self, _key) -> None:
        return

    def release(self, _key) -> None:
        return

    def type(self, _text: str) -> None:
        return


class TextCommandMenu:
    def __init__(self) -> None:
        self._keyboard = _NoopKeyboardController()
        self._commands: list[Command] = []
        self._by_name: dict[str, Command] = {}

        self._root = tk.Tk()
        self._root.title("EyeOS Voice Command Help")
        self._root.resizable(False, False)

        self._selected_name = tk.StringVar()
        self._phrases_var = tk.StringVar(value="All phrases: -")
        self._description_var = tk.StringVar(value="Description: -")
        self._status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self._selected_name.trace_add("write", self._on_selected_change)
        self._load_commands()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self._root, padding=14)
        frame.grid(row=0, column=0, sticky="nsew")

        title = ttk.Label(frame, text="Voice Command Help", font=("TkDefaultFont", 14, "bold"))
        title.grid(row=0, column=0, columnspan=3, sticky="w")

        os_label = ttk.Label(frame, text=f"OS: {platform.system()}")
        os_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 8))

        columns = ("name", "activation", "description")
        self._table = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        self._table.heading("name", text="Command")
        self._table.heading("activation", text="Activation Phrase")
        self._table.heading("description", text="Description")
        self._table.column("name", width=180, anchor="w")
        self._table.column("activation", width=200, anchor="w")
        self._table.column("description", width=280, anchor="w")
        self._table.grid(row=2, column=0, columnspan=3, sticky="nsew")
        self._table.bind("<<TreeviewSelect>>", self._on_table_selected)

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self._table.yview)
        scrollbar.grid(row=2, column=3, sticky="ns")
        self._table.configure(yscrollcommand=scrollbar.set)

        phrases = ttk.Label(frame, textvariable=self._phrases_var, wraplength=680, justify="left")
        phrases.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 2))

        description = ttk.Label(frame, textvariable=self._description_var, wraplength=680, justify="left")
        description.grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 10))

        refresh_btn = ttk.Button(frame, text="Refresh", command=self._load_commands)
        refresh_btn.grid(row=5, column=0, sticky="w")

        status = ttk.Label(frame, textvariable=self._status_var, foreground="#666666")
        status.grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)

    def _load_commands(self) -> None:
        self._commands = build_commands(self._keyboard)
        self._by_name = {c.name: c for c in self._commands}

        names = sorted(self._by_name.keys())
        self._table.delete(*self._table.get_children())
        for name in names:
            cmd = self._by_name[name]
            self._table.insert(
                "",
                "end",
                iid=name,
                values=(name, cmd.activation_phrase, cmd.description or "-"),
            )

        if not names:
            self._selected_name.set("")
            self._phrases_var.set("All phrases: -")
            self._description_var.set("Description: -")
            self._status_var.set("No commands found")
            return

        current = self._selected_name.get()
        if current not in self._by_name:
            self._selected_name.set(names[0])
        if self._selected_name.get():
            self._table.selection_set(self._selected_name.get())
            self._table.focus(self._selected_name.get())
        self._update_phrases()
        self._status_var.set(f"Loaded {len(names)} command(s)")

    def _on_selected_change(self, *_args) -> None:
        self._update_phrases()

    def _update_phrases(self) -> None:
        cmd = self._by_name.get(self._selected_name.get())
        if not cmd:
            self._phrases_var.set("All phrases: -")
            self._description_var.set("Description: -")
            return
        self._phrases_var.set(f"All phrases: {', '.join(cmd.phrases)}")
        self._description_var.set(f"Description: {cmd.description or '-'}")

    def _on_table_selected(self, _event) -> None:
        selection = self._table.selection()
        if not selection:
            return
        self._selected_name.set(selection[0])

    def run(self) -> None:
        self._root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="EyeOS text command menu")
    parser.parse_args()
    TextCommandMenu().run()


if __name__ == "__main__":
    main()
