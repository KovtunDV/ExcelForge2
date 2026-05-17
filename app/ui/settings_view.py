from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from tkinter import font as tkfont

from app.settings import AppSettings, load_settings, save_settings
from app.ui import preview_settings


class SettingsView(ttk.Frame):
    def __init__(self, master: tk.Misc, *, apply_font: callable[[str, int], None]):
        super().__init__(master)
        self._apply_font = apply_font
        self._s = load_settings()

        self.var_preview_rows = tk.IntVar(value=preview_settings.get_preview_rows())
        self.var_font_family = tk.StringVar(value=self._s.font_family or "")
        self.var_font_size = tk.IntVar(value=int(self._s.font_size or 10))

        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=12, pady=12)

        lf_preview = ttk.LabelFrame(root, text="Предпросмотр DataFrame")
        lf_preview.pack(fill="x")
        rowp = ttk.Frame(lf_preview)
        rowp.pack(fill="x", padx=10, pady=10)
        ttk.Label(rowp, text="Строк предпросмотра:").pack(side="left")
        ttk.Spinbox(rowp, from_=1, to=5000, width=6, textvariable=self.var_preview_rows).pack(
            side="left", padx=(8, 0)
        )

        lf_font = ttk.LabelFrame(root, text="Шрифт интерфейса")
        lf_font.pack(fill="x", pady=(12, 0))

        rowf = ttk.Frame(lf_font)
        rowf.pack(fill="x", padx=10, pady=10)
        ttk.Label(rowf, text="Шрифт:").pack(side="left")
        families = sorted(tkfont.families(), key=lambda x: x.lower())
        self.cmb_font = ttk.Combobox(rowf, values=families, textvariable=self.var_font_family, state="readonly")
        self.cmb_font.pack(side="left", padx=(8, 0), fill="x", expand=True)

        ttk.Label(rowf, text="Размер:").pack(side="left", padx=(12, 0))
        ttk.Spinbox(rowf, from_=6, to=48, width=4, textvariable=self.var_font_size).pack(
            side="left", padx=(8, 0)
        )

        row_btn = ttk.Frame(root)
        row_btn.pack(fill="x", pady=(12, 0))
        ttk.Button(row_btn, text="Применить", command=self._apply).pack(side="left")
        ttk.Button(row_btn, text="Сохранить", command=self._save).pack(side="left", padx=(8, 0))
        ttk.Button(row_btn, text="Сбросить настройки", command=self._reset).pack(
            side="left", padx=(8, 0)
        )

        sample = ttk.LabelFrame(root, text="Пример")
        sample.pack(fill="both", expand=True, pady=(12, 0))
        sroot = ttk.Frame(sample)
        sroot.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Label(sroot, text="Label: пример текста").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(sroot, width=30).grid(row=0, column=1, sticky="we")
        ttk.Button(sroot, text="Кнопка").grid(row=0, column=2, sticky="w", padx=(12, 0))

        self._var_chk = tk.BooleanVar(value=True)
        ttk.Checkbutton(sroot, text="Checkbutton", variable=self._var_chk).grid(
            row=1, column=0, sticky="w", pady=(10, 0)
        )
        ttk.Combobox(sroot, values=["Option A", "Option B", "Option C"], state="readonly").grid(
            row=1, column=1, sticky="we", pady=(10, 0)
        )
        ttk.Spinbox(sroot, from_=0, to=100, width=6).grid(
            row=1, column=2, sticky="w", padx=(12, 0), pady=(10, 0)
        )

        ttk.Label(sroot, text="Text widget:").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self._txt = tk.Text(sroot, height=3, wrap="word")
        self._txt.insert("1.0", "Пример многострочного текста.\nКод/логи/документация.")
        self._txt.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(6, 0))

        sroot.columnconfigure(1, weight=1)
        sroot.rowconfigure(3, weight=1)

    def _apply(self) -> None:
        fam = str(self.var_font_family.get() or "").strip()
        size = int(self.var_font_size.get() or 10)
        size = max(6, min(size, 48))
        # Apply even when family is empty (restore defaults).
        self._apply_font(fam, size)
        try:
            preview_settings.set_preview_rows(self.var_preview_rows.get())
        except Exception:
            preview_settings.set_preview_rows(10)
            self.var_preview_rows.set(preview_settings.get_preview_rows())

    def _save(self) -> None:
        self._apply()
        s = AppSettings(
            preview_rows=preview_settings.get_preview_rows(),
            font_family=str(self.var_font_family.get() or "").strip(),
            font_size=int(self.var_font_size.get() or 10),
        )
        save_settings(s)
        messagebox.showinfo("ExcelForge", "Настройки сохранены.")

    def _reset(self) -> None:
        # Reset to defaults
        self.var_preview_rows.set(10)
        self.var_font_family.set("")
        self.var_font_size.set(10)
        self._save()

