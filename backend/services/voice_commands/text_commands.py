from __future__ import annotations

import argparse
import platform
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

try:
    from backend.services.voice_commands.commands import Command, build_commands
except ModuleNotFoundError:
    from commands import Command, build_commands

class _NoopKeyboardController:
    def press(self, _key) -> None:
        return

    def release(self, _key) -> None:
        return

    def type(self, _text: str) -> None:
        return

class TextCommandMenu:
    def __init__(self, theme: str = "dark") -> None:
        self._keyboard = _NoopKeyboardController()
        self._commands: list[Command] = []
        self._by_name: dict[str, Command] = {}

        ctk.set_appearance_mode(theme)
        
        self._root = ctk.CTk()
        self._root.title("EyeOS Voice Command Help")
        self._root.resizable(False, False)
        self._root.attributes("-topmost", True)
        self._root.lift()

        self._selected_name = tk.StringVar()
        self._phrases_var = tk.StringVar(value="All phrases: -")
        self._description_var = tk.StringVar(value="Description: -")
        self._status_var = tk.StringVar(value="Ready")

        self._apply_treeview_style(theme)
        self._build_ui()
        self._selected_name.trace_add("write", self._on_selected_change)
        self._load_commands()

    def _apply_treeview_style(self, theme: str) -> None:
        style = ttk.Style(self._root)
        style.theme_use("default")
        
        if theme.lower() == "dark":
            bg_color = "#2b2b2b"
            fg_color = "white"
            head_bg = "#565b5e"
            sel_bg = "#1f538d"
        else:
            bg_color = "#ebebeb"
            fg_color = "black"
            head_bg = "#d9d9d9"
            sel_bg = "#3a7ebf"

        style.configure("Treeview", background=bg_color, foreground=fg_color, fieldbackground=bg_color, borderwidth=0)
        style.configure("Treeview.Heading", background=head_bg, foreground=fg_color, borderwidth=0)
        style.map("Treeview", background=[("selected", sel_bg)])

    def _build_ui(self) -> None:
        frame = ctk.CTkFrame(self._root, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)

        title = ctk.CTkLabel(frame, text="Voice Command Help", font=("Arial", 16, "bold"))
        title.grid(row=0, column=0, columnspan=3, sticky="w")

        os_label = ctk.CTkLabel(frame, text=f"OS: {platform.system()}")
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

        scrollbar = ctk.CTkScrollbar(frame, orientation="vertical", command=self._table.yview)
        scrollbar.grid(row=2, column=3, sticky="ns", padx=(5, 0))
        self._table.configure(yscrollcommand=scrollbar.set)

        phrases = ctk.CTkLabel(frame, textvariable=self._phrases_var, wraplength=680, justify="left")
        phrases.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 2))

        description = ctk.CTkLabel(frame, textvariable=self._description_var, wraplength=680, justify="left")
        description.grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 10))

        refresh_btn = ctk.CTkButton(frame, text="Refresh", command=self._load_commands)
        refresh_btn.grid(row=5, column=0, sticky="w")

        status = ctk.CTkLabel(frame, textvariable=self._status_var, text_color="gray")
        status.grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))

    def _load_commands(self) -> None:
        self._commands = build_commands(self._keyboard) # type: ignore
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
    parser.add_argument("--theme", default="dark")
    args = parser.parse_args()
    TextCommandMenu(theme=args.theme).run()

if __name__ == "__main__":
    main()