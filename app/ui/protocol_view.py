from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.pipeline.log import LogEvent, MemoryLogger


class ProtocolView(ttk.Frame):
    def __init__(self, master: tk.Misc, *, height_lines: int = 12):
        super().__init__(master)

        self.text = tk.Text(self, wrap="none", height=height_lines)
        self.text.configure(state="disabled")
        yscroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=yscroll.set)

        self.text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def append_event(self, ev: LogEvent) -> None:
        line = f"{ev.ts:%Y-%m-%d %H:%M:%S} [{ev.level}] {ev.message}\n"
        self.text.configure(state="normal")
        self.text.insert("end", line)
        self.text.see("end")
        self.text.configure(state="disabled")

    def bind_logger(self, logger: MemoryLogger) -> None:
        def _listener(ev: LogEvent) -> None:
            # В ExcelForge шаги выполняются в Tk-потоке; чтобы протокол обновлялся
            # во время долгих операций, рисуем сразу и принудительно обновляем idle-задачи.
            self.append_event(ev)
            try:
                self.update_idletasks()
            except tk.TclError:
                pass

        logger.add_listener(_listener)

