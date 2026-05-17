from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

import yaml

from app.io.yaml_io import load_pipeline_yaml, save_pipeline_yaml
from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY
from app.pipeline.runner import _resolve_step_params, run_pipeline
from app.pipeline.schema import Pipeline, Step
from app.ui import preview_settings
from app.ui.data_preview_window import DataPreviewWindow
from app.ui.pipeline_tk_hooks import bind_tk_dialogs_to_context
from app.ui.protocol_view import ProtocolView
from app.ui.step_documentation_window import StepDocumentationWindow


class BuilderView(ttk.Frame):
    def __init__(self, master: tk.Misc, pipelines_dir: str):
        super().__init__(master)

        self.pipelines_dir = pipelines_dir
        self.pipeline = Pipeline(name="NewPipeline", description="", steps=[])
        self.current_file: str | None = None
        self._active_step_index: int | None = None
        self._dirty = False
        self._suppress_dirty_trace = False
        self._step_editor_dirty = False
        self._df_preview_win: DataPreviewWindow | None = None
        # Контекст для быстрой отладки шагов (сохраняется после preview/выполнений).
        # df_store может быть большим — храним ссылку, не копируем.
        self._debug_ctx: RunContext | None = None

        self.var_desc = tk.StringVar(value=self.pipeline.description)
        self.var_file = tk.StringVar(value="(новый пайплайн, файл не сохранён)")

        self.var_desc.trace_add("write", lambda *_: self._mark_dirty())

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(10, 6))

        file_row = ttk.Frame(top)
        file_row.pack(fill="x")
        ttk.Label(file_row, text="Файл конфигурации:").pack(side="left")
        ttk.Entry(file_row, textvariable=self.var_file, width=80, state="readonly").pack(
            side="left", padx=(8, 0), fill="x", expand=True
        )

        row2 = ttk.Frame(top)
        row2.pack(fill="x", pady=(8, 0))
        ttk.Label(row2, text="Описание:").pack(side="left")
        ttk.Entry(row2, textvariable=self.var_desc, width=70).pack(side="left", padx=(6, 0), fill="x", expand=True)

        row3 = ttk.Frame(top)
        row3.pack(fill="x", pady=(8, 0))
        ttk.Button(row3, text="Новый", command=self._new).pack(side="left")
        ttk.Button(row3, text="Открыть YAML…", command=self._open).pack(side="left", padx=(6, 0))
        ttk.Button(row3, text="Сохранить", command=self._save).pack(side="left", padx=(6, 0))
        ttk.Button(row3, text="Сохранить как…", command=self._save_as).pack(side="left", padx=(6, 0))

        proto = ttk.LabelFrame(self, text="Протокол")
        proto.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        self.protocol = ProtocolView(proto, height_lines=4)
        self.protocol.pack(fill="x", padx=10, pady=10)

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        left = ttk.Frame(main)
        right = ttk.Frame(main)
        main.add(left, weight=1)
        main.add(right, weight=3)

        ttk.Label(left, text="Шаги пайплайна:").pack(anchor="w")
        self.steps_list = tk.Listbox(left, height=20, exportselection=False)
        self.steps_list.pack(fill="both", expand=True, pady=(6, 8))
        self.steps_list.bind("<<ListboxSelect>>", self._on_step_select)

        tools = ttk.Frame(left)
        tools.pack(fill="x")

        self.var_new_step_type = tk.StringVar(value="")
        step_defs = REGISTRY.list()
        self._step_type_titles = {d.title: d.type for d in step_defs}
        titles = [d.title for d in step_defs]
        self.cmb_new_type = ttk.Combobox(tools, values=titles, textvariable=self.var_new_step_type, state="readonly")
        self.cmb_new_type.pack(side="left", fill="x", expand=True)
        if titles:
            self.var_new_step_type.set(titles[0])
        ttk.Button(tools, text="Добавить", command=self._add_step).pack(side="left", padx=(8, 0))

        row2l = ttk.Frame(left)
        row2l.pack(fill="x", pady=(6, 0))
        ttk.Button(row2l, text="Удалить", command=self._delete_step).pack(side="left")
        ttk.Button(row2l, text="Вверх", command=lambda: self._move(-1)).pack(side="left", padx=(6, 0))
        ttk.Button(row2l, text="Вниз", command=lambda: self._move(+1)).pack(side="left", padx=(6, 0))
        ttk.Button(row2l, text="Клонировать", command=self._clone_step).pack(side="left", padx=(6, 0))

        run_box = ttk.LabelFrame(right, text="Тестовый запуск")
        run_box.pack(side="bottom", fill="x", pady=(10, 0))

        run_row = ttk.Frame(run_box)
        run_row.pack(fill="x", padx=10, pady=(10, 10))
        ttk.Button(run_row, text="Запустить пайплайн", command=self._run_pipeline).pack(side="left")
        ttk.Button(run_row, text="Просмотр данных", command=self._preview_data).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(run_row, text="Выполнить до текущего шага", command=self._run_through_current_step).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(run_row, text="Проверить шаг", command=self._verify_current_step).pack(
            side="left", padx=(8, 0)
        )

        edit = ttk.LabelFrame(right, text="Параметры выбранного шага")
        edit.pack(fill="both", expand=True)

        form = ttk.Frame(edit)
        form.pack(fill="x", padx=10, pady=10)

        self.var_step_id = tk.StringVar(value="")
        self.var_step_type = tk.StringVar(value="")
        self.var_step_id.trace_add("write", lambda *_: self._mark_step_editor_dirty())

        ttk.Label(form, text="ID:").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.var_step_id, width=15).grid(row=0, column=1, sticky="we", padx=(6, 10))
        ttk.Label(form, text="Type:").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.var_step_type, width=15, state="readonly").grid(
            row=0, column=3, sticky="we", padx=(6, 10)
        )

        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        comment_frame = ttk.LabelFrame(edit, text="Комментарий к шагу (в YAML: comment)")
        comment_frame.pack(fill="x", padx=10, pady=(10, 0))
        self.step_comment_text = tk.Text(comment_frame, height=3, wrap="word")
        self.step_comment_text.pack(fill="x", padx=8, pady=8)
        self.step_comment_text.bind("<KeyRelease>", lambda _e: self._mark_step_editor_dirty())

        ttk.Label(edit, text="Params (YAML):").pack(anchor="w", padx=10, pady=(10, 0))

        bottom_tools = ttk.Frame(edit)
        apply_row = ttk.Frame(bottom_tools)
        apply_row.pack(fill="x")
        ttk.Button(apply_row, text="Применить в шаг", command=self._apply_step_edits).pack(side="left")
        ttk.Button(apply_row, text="Сбросить к default", command=self._reset_params_to_default).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(apply_row, text="Документация по шагу", command=self._show_step_documentation).pack(
            side="left", padx=(8, 0)
        )

        self.step_path_tools = ttk.Frame(bottom_tools)
        self.step_path_tools.pack(fill="x", pady=(8, 0))

        self.btn_pick_in_file = ttk.Button(
            self.step_path_tools, text="Выбрать входной файл…", command=self._pick_load_excel_file
        )
        self.btn_pick_in_dir = ttk.Button(
            self.step_path_tools, text="Выбрать входной каталог…", command=self._pick_load_excel_dir
        )
        self.btn_pick_out_dir = ttk.Button(
            self.step_path_tools, text="Выбрать выходной каталог…", command=self._pick_save_excel_out_dir
        )
        self.btn_pick_template = ttk.Button(
            self.step_path_tools, text="Выбрать Excel шаблон…", command=self._pick_save_excel_template
        )
        self.btn_pick_globals_dir = ttk.Button(
            self.step_path_tools, text="Выбрать каталог (значение)…", command=self._pick_globals_directory_value
        )
        self.btn_pick_globals_file = ttk.Button(
            self.step_path_tools, text="Выбрать файл (значение)…", command=self._pick_globals_file_value
        )

        for w in (
            self.btn_pick_in_file,
            self.btn_pick_in_dir,
            self.btn_pick_out_dir,
            self.btn_pick_template,
            self.btn_pick_globals_dir,
            self.btn_pick_globals_file,
        ):
            w.pack_forget()

        # Сначала закрепляем нижний блок кнопок (иначе растягивающийся Params выталкивает их за край фрейма).
        bottom_tools.pack(side="bottom", fill="x", padx=10, pady=(8, 10))

        self.params_text = tk.Text(edit, height=14, wrap="none")
        self.params_text.pack(fill="both", expand=True, padx=10, pady=(6, 0))
        self.params_text.bind("<KeyRelease>", lambda _e: self._mark_step_editor_dirty())

        self._refresh_steps_list()
        self._select_step(0)
        self._update_file_label()
        self._dirty = False

    def _mark_dirty(self, *_args) -> None:
        if self._suppress_dirty_trace:
            return
        self._dirty = True

    def _mark_step_editor_dirty(self) -> None:
        if self._suppress_dirty_trace:
            return
        self._step_editor_dirty = True

    def _clear_dirty(self) -> None:
        self._dirty = False

    def _update_file_label(self) -> None:
        if self.current_file:
            self.var_file.set(os.path.abspath(self.current_file))
        else:
            self.var_file.set("(новый пайплайн, файл не сохранён)")

    def _maybe_save_dirty(self) -> bool:
        """True — можно продолжать (Новый/Открыть). False — отмена."""
        if not self._dirty:
            return True
        r = messagebox.askyesnocancel(
            "ExcelForge",
            "Есть несохранённые изменения (описание или шаги).\n"
            "Сохранить текущий файл перед продолжением?",
        )
        if r is None:
            return False
        if r:
            self._sync_pipeline_header()
            if self.current_file:
                try:
                    self._sync_pipeline_name_from_path(self.current_file)
                    save_pipeline_yaml(self.pipeline, self.current_file)
                    self._clear_dirty()
                    self._update_file_label()
                except Exception as e:  # noqa: BLE001
                    messagebox.showerror("ExcelForge", f"Ошибка сохранения:\n{e}")
                    return False
            else:
                ok = self._save_as_internal(show_messages=True)
                if not ok:
                    return False
        else:
            self._clear_dirty()
        return True

    def _reset_to_new_pipeline(self) -> None:
        self.pipeline = Pipeline(name="NewPipeline", description="", steps=[])
        self.current_file = None
        self._suppress_dirty_trace = True
        try:
            self.var_desc.set(self.pipeline.description)
        finally:
            self._suppress_dirty_trace = False
        self._update_file_label()
        self._refresh_steps_list()
        self._select_step(0)
        self.protocol.clear()
        self._clear_dirty()

    def _new(self) -> None:
        if not self._maybe_save_dirty():
            return
        self._reset_to_new_pipeline()

    def _open(self) -> None:
        if not self._maybe_save_dirty():
            return
        path = filedialog.askopenfilename(
            initialdir=self.pipelines_dir,
            title="Открыть YAML пайплайн",
            filetypes=[("YAML", "*.yml *.yaml"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            p = load_pipeline_yaml(path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("ExcelForge", f"Ошибка загрузки YAML:\n{e}")
            return
        self.pipeline = p
        self.current_file = path
        self._suppress_dirty_trace = True
        try:
            self.var_desc.set(p.description)
        finally:
            self._suppress_dirty_trace = False
        self._update_file_label()
        self._refresh_steps_list()
        self._select_step(0)
        self._clear_dirty()

    def _save(self) -> None:
        self._sync_pipeline_header()
        if not self.current_file:
            self._save_as()
            return
        self._sync_pipeline_name_from_path(self.current_file)
        try:
            save_pipeline_yaml(self.pipeline, self.current_file)
            self._clear_dirty()
            self._update_file_label()
            messagebox.showinfo("ExcelForge", f"Сохранено:\n{self.current_file}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("ExcelForge", f"Ошибка сохранения:\n{e}")

    def _save_as(self) -> None:
        self._save_as_internal(show_messages=True)

    def _save_as_internal(self, *, show_messages: bool) -> bool:
        self._sync_pipeline_header()
        os.makedirs(self.pipelines_dir, exist_ok=True)
        path = filedialog.asksaveasfilename(
            initialdir=self.pipelines_dir,
            defaultextension=".yaml",
            filetypes=[("YAML", "*.yaml"), ("YAML", "*.yml"), ("All files", "*.*")],
            title="Сохранить пайплайн как",
        )
        if not path:
            return False
        self._sync_pipeline_name_from_path(path)
        try:
            save_pipeline_yaml(self.pipeline, path)
            self.current_file = path
            self._clear_dirty()
            self._update_file_label()
            if show_messages:
                messagebox.showinfo("ExcelForge", f"Сохранено:\n{path}")
            return True
        except Exception as e:  # noqa: BLE001
            if show_messages:
                messagebox.showerror("ExcelForge", f"Ошибка сохранения:\n{e}")
            return False

    def _sync_pipeline_header(self) -> None:
        self.pipeline.description = self.var_desc.get().strip()

    @staticmethod
    def _name_from_yaml_path(path: str) -> str:
        base = os.path.splitext(os.path.basename(path))[0].strip()
        return base or "pipeline"

    def _sync_pipeline_name_from_path(self, path: str) -> None:
        """Имя пайплайна в YAML совпадает с именем файла (без расширения)."""
        self.pipeline.name = self._name_from_yaml_path(path)

    @staticmethod
    def _step_title_ru(step: Step) -> str:
        if REGISTRY.has(step.type):
            return REGISTRY.get(step.type).title
        return step.type

    def _refresh_steps_list(self) -> None:
        self.steps_list.delete(0, "end")
        for i, s in enumerate(self.pipeline.steps, start=1):
            self.steps_list.insert("end", f"{i}. {self._step_title_ru(s)}")

    def _select_step(self, idx: int) -> None:
        if not self.pipeline.steps:
            self.var_step_id.set("")
            self.var_step_type.set("")
            self.params_text.delete("1.0", "end")
            self.step_comment_text.delete("1.0", "end")
            self._active_step_index = None
            self._step_editor_dirty = False
            return
        idx = max(0, min(idx, len(self.pipeline.steps) - 1))
        self._active_step_index = idx
        self.steps_list.selection_clear(0, "end")
        self.steps_list.selection_set(idx)
        self.steps_list.activate(idx)
        self._load_selected_step()

    def _on_step_select(self, _e: tk.Event) -> None:
        sel = self.steps_list.curselection()
        if not sel:
            return
        new_idx = sel[0]
        cur_idx = self._active_step_index

        if cur_idx is not None and new_idx != cur_idx and self._step_editor_dirty:
            r = messagebox.askyesnocancel(
                "ExcelForge",
                "Текущий шаг изменён, но изменения не применены.\n"
                "Применить изменения перед переходом на другой шаг?",
            )
            if r is None:
                self.steps_list.selection_clear(0, "end")
                self.steps_list.selection_set(cur_idx)
                self.steps_list.activate(cur_idx)
                return
            if r:
                prev_idx = cur_idx
                self._apply_step_edits()
                # если применить не удалось (ошибка YAML и т.п.) — остаёмся на текущем шаге
                if self._step_editor_dirty:
                    self.steps_list.selection_clear(0, "end")
                    self.steps_list.selection_set(prev_idx)
                    self.steps_list.activate(prev_idx)
                    return
            else:
                # discard edits
                self._step_editor_dirty = False

        self._active_step_index = new_idx
        self._load_selected_step()

    def _load_selected_step(self) -> None:
        sel = self.steps_list.curselection()
        if not sel:
            return
        idx = sel[0]
        self._active_step_index = idx
        step = self.pipeline.steps[idx]
        self._suppress_dirty_trace = True
        try:
            self.var_step_id.set(step.id)
            self.var_step_type.set(step.type)
            self.params_text.delete("1.0", "end")
            self.params_text.insert(
                "1.0",
                yaml.safe_dump(step.params or {}, sort_keys=False, allow_unicode=True),
            )
            self.step_comment_text.delete("1.0", "end")
            self.step_comment_text.insert("1.0", step.comment or "")
        finally:
            self._suppress_dirty_trace = False
        self._step_editor_dirty = False
        self._update_step_path_tools(step.type)

    def _update_step_path_tools(self, step_type: str) -> None:
        for w in (
            self.btn_pick_in_file,
            self.btn_pick_in_dir,
            self.btn_pick_out_dir,
            self.btn_pick_template,
            self.btn_pick_globals_dir,
            self.btn_pick_globals_file,
        ):
            w.pack_forget()

        if step_type == "load_excel":
            self.btn_pick_in_file.pack(side="left")
            self.btn_pick_in_dir.pack(side="left", padx=(8, 0))
        elif step_type == "save_excel":
            self.btn_pick_out_dir.pack(side="left")
            self.btn_pick_template.pack(side="left", padx=(8, 0))
        elif step_type == "globals_settings":
            self.btn_pick_globals_dir.pack(side="left")
            self.btn_pick_globals_file.pack(side="left", padx=(8, 0))

    def _apply_step_edits(self) -> None:
        idx = self._active_step_index
        if idx is None:
            messagebox.showwarning("ExcelForge", "Сначала выберите шаг.")
            return
        step = self.pipeline.steps[idx]
        step.id = self.var_step_id.get().strip()

        try:
            params = yaml.safe_load(self.params_text.get("1.0", "end")) or {}
            if not isinstance(params, dict):
                raise ValueError("Params YAML должен быть словарём (mapping).")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("ExcelForge", f"Ошибка params YAML:\n{e}")
            return

        step.params = params
        step.comment = self.step_comment_text.get("1.0", "end").replace("\r\n", "\n").rstrip("\n")
        self._mark_dirty()
        self._refresh_steps_list()
        self._step_editor_dirty = False
        self._select_step(idx)

    def _current_step(self) -> Step | None:
        idx = self._active_step_index
        if idx is None:
            return None
        if idx < 0 or idx >= len(self.pipeline.steps):
            return None
        return self.pipeline.steps[idx]

    def _read_params_text(self) -> dict:
        params = yaml.safe_load(self.params_text.get("1.0", "end")) or {}
        if not isinstance(params, dict):
            raise ValueError("Params YAML должен быть словарём (mapping).")
        return params

    def _write_params_text(self, params: dict) -> None:
        self.params_text.delete("1.0", "end")
        self.params_text.insert("1.0", yaml.safe_dump(params, sort_keys=False, allow_unicode=True))
        self._mark_step_editor_dirty()

    def _pick_load_excel_file(self) -> None:
        step = self._current_step()
        if not step or step.type != "load_excel":
            return
        try:
            params = self._read_params_text()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("ExcelForge", f"Ошибка params YAML:\n{e}")
            return
        initial = params.get("file_path") or os.getcwd()
        fp = filedialog.askopenfilename(
            title="Выберите Excel файл",
            initialdir=os.path.dirname(str(initial)) if str(initial) else os.getcwd(),
            filetypes=[("Excel", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")],
        )
        if not fp:
            return
        params["file_path"] = fp
        params["input_mode"] = "file"
        self._write_params_text(params)
        self._mark_dirty()

    def _pick_load_excel_dir(self) -> None:
        step = self._current_step()
        if not step or step.type != "load_excel":
            return
        try:
            params = self._read_params_text()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("ExcelForge", f"Ошибка params YAML:\n{e}")
            return
        initial = params.get("directory") or os.getcwd()
        d = filedialog.askdirectory(
            title="Выберите каталог с Excel файлами",
            initialdir=str(initial) if str(initial) else os.getcwd(),
        )
        if not d:
            return
        params["directory"] = d
        if str(params.get("input_mode", "mask")) == "file":
            params["input_mode"] = "mask"
        self._write_params_text(params)
        self._mark_dirty()

    def _pick_save_excel_out_dir(self) -> None:
        step = self._current_step()
        if not step or step.type != "save_excel":
            return
        try:
            params = self._read_params_text()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("ExcelForge", f"Ошибка params YAML:\n{e}")
            return
        initial = params.get("out_dir") or os.getcwd()
        d = filedialog.askdirectory(
            title="Выберите выходной каталог",
            initialdir=str(initial) if str(initial) else os.getcwd(),
        )
        if not d:
            return
        params["out_dir"] = d
        self._write_params_text(params)
        self._mark_dirty()

    def _pick_save_excel_template(self) -> None:
        step = self._current_step()
        if not step or step.type != "save_excel":
            return
        try:
            params = self._read_params_text()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("ExcelForge", f"Ошибка params YAML:\n{e}")
            return
        initial = params.get("template_path") or os.getcwd()
        fp = filedialog.askopenfilename(
            title="Выберите Excel шаблон",
            initialdir=os.path.dirname(str(initial)) if str(initial) else os.getcwd(),
            filetypes=[("Excel", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")],
        )
        if not fp:
            return
        params["template_path"] = fp
        self._write_params_text(params)
        self._mark_dirty()

    @staticmethod
    def _norm_global_var_name(raw: object, default: str) -> str:
        s = str(raw or default).strip()
        if s.startswith("@"):
            s = s[1:].strip()
        return s or default

    def _pick_globals_directory_value(self) -> None:
        step = self._current_step()
        if not step or step.type != "globals_settings":
            return
        try:
            params = self._read_params_text()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("ExcelForge", f"Ошибка params YAML:\n{e}")
            return

        values = params.get("values") or {}
        if not isinstance(values, dict):
            messagebox.showerror("ExcelForge", "globals_settings: params.values должен быть словарём.")
            return

        var = self._norm_global_var_name(params.get("directory_var"), "directory")
        current = values.get(var)
        initial = str(current or params.get("directory_initial") or os.getcwd())

        title = str(params.get("directory_open_dialog_help") or "Выберите каталог")
        d = filedialog.askdirectory(title=title, initialdir=initial if initial else os.getcwd())
        if not d:
            return

        values[var] = d
        params["values"] = values
        # Чтобы при запуске не всплывал runtime-диалог, если он был включён.
        params["directory_open_dialog"] = False
        params["directory_initial"] = d
        self._write_params_text(params)
        self._mark_dirty()

    def _pick_globals_file_value(self) -> None:
        step = self._current_step()
        if not step or step.type != "globals_settings":
            return
        try:
            params = self._read_params_text()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("ExcelForge", f"Ошибка params YAML:\n{e}")
            return

        values = params.get("values") or {}
        if not isinstance(values, dict):
            messagebox.showerror("ExcelForge", "globals_settings: params.values должен быть словарём.")
            return

        var = self._norm_global_var_name(params.get("file_var"), "file_path")
        current = values.get(var)
        initial_dir = os.path.dirname(str(current)) if current else os.getcwd()
        title = str(params.get("file_open_dialog_help") or "Выберите файл")
        fp = filedialog.askopenfilename(
            title=title,
            initialdir=initial_dir if initial_dir else os.getcwd(),
            filetypes=[("All files", "*.*")],
        )
        if not fp:
            return

        values[var] = fp
        params["values"] = values
        params["file_open_dialog"] = False
        self._write_params_text(params)
        self._mark_dirty()

    def _reset_params_to_default(self) -> None:
        idx = self._active_step_index
        if idx is None:
            return
        step = self.pipeline.steps[idx]
        try:
            default = dict(REGISTRY.get(step.type).default_params)
        except KeyError:
            return
        step.params = default
        step.comment = ""
        self._mark_dirty()
        self._step_editor_dirty = False
        self._load_selected_step()

    def _show_step_documentation(self) -> None:
        idx = self._active_step_index
        if idx is None or not self.pipeline.steps:
            messagebox.showwarning("ExcelForge", "Выберите шаг в списке.")
            return
        step = self.pipeline.steps[idx]
        step_title = REGISTRY.get(step.type).title if REGISTRY.has(step.type) else ""
        StepDocumentationWindow(self.winfo_toplevel(), step_type=step.type, step_title=step_title)

    def _add_step(self) -> None:
        title = self.var_new_step_type.get()
        step_type = self._step_type_titles.get(title)
        if not step_type:
            return
        d = REGISTRY.get(step_type)
        new_id = self._next_step_id(step_type)
        self.pipeline.steps.append(Step(id=new_id, type=step_type, params=dict(d.default_params)))
        self._mark_dirty()
        self._refresh_steps_list()
        self._select_step(len(self.pipeline.steps) - 1)

    def _next_step_id(self, step_type: str) -> str:
        base = step_type.replace("-", "_")
        i = 1
        ids = {s.id for s in self.pipeline.steps}
        while f"{base}_{i}" in ids:
            i += 1
        return f"{base}_{i}"

    def _delete_step(self) -> None:
        sel = self.steps_list.curselection()
        if not sel:
            return
        idx = sel[0]
        del self.pipeline.steps[idx]
        self._mark_dirty()
        self._refresh_steps_list()
        self._select_step(min(idx, len(self.pipeline.steps) - 1))

    def _move(self, delta: int) -> None:
        sel = self.steps_list.curselection()
        if not sel:
            return
        idx = sel[0]
        j = idx + delta
        if j < 0 or j >= len(self.pipeline.steps):
            return
        self.pipeline.steps[idx], self.pipeline.steps[j] = self.pipeline.steps[j], self.pipeline.steps[idx]
        self._mark_dirty()
        self._refresh_steps_list()
        self._select_step(j)

    def _attach_run_context_ui(self, ctx: RunContext) -> None:
        bind_tk_dialogs_to_context(ctx, self)
        ctx.variables["confirm_continue_on_zero_rows"] = lambda df_name: messagebox.askyesno(
            "ExcelForge",
            f"Загружено 0 строк в датафрейм '{df_name}'. Продолжить выполнение?",
        )

    def _clone_step(self) -> None:
        sel = self.steps_list.curselection()
        if not sel:
            return
        idx = sel[0]
        s = self.pipeline.steps[idx]
        new_id = self._next_step_id(s.type)
        self.pipeline.steps.insert(
            idx + 1,
            Step(id=new_id, type=s.type, params=dict(s.params), comment=str(s.comment or "")),
        )
        self._mark_dirty()
        self._refresh_steps_list()
        self._select_step(idx + 1)

    def _run_pipeline(self) -> None:
        self._sync_pipeline_header()
        try:
            self.pipeline.validate()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("ExcelForge", f"Пайплайн невалиден:\n{e}")
            return

        ctx = RunContext()
        self._attach_run_context_ui(ctx)
        self.protocol.clear()
        self.protocol.bind_logger(ctx.logger)

        total = len(self.pipeline.steps)
        ctx.logger.info(f"Start pipeline: {self.pipeline.name} (steps={total})")
        i = 0

        def _run_next() -> None:
            nonlocal i
            if ctx.cancelled:
                ctx.logger.warn("Pipeline cancelled by user.")
                messagebox.showerror("ExcelForge", "Выполнение отменено.")
                return
            if i >= total:
                ctx.logger.info("Pipeline finished successfully.")
                # Сохраняем контекст выполнения для «Просмотр данных» / быстрой проверки шагов.
                self._debug_ctx = ctx
                messagebox.showinfo("ExcelForge", "Выполнено успешно.")
                return

            step = self.pipeline.steps[i]
            idx1 = i + 1
            ctx.logger.info(f"[{idx1}/{total}] Step {step.id}: {step.type}")
            if not REGISTRY.has(step.type):
                msg = f"Unknown step type: {step.type}"
                ctx.logger.error(msg)
                messagebox.showerror("ExcelForge", f"Ошибка выполнения:\n{msg}")
                return
            try:
                orig_params = step.params
                try:
                    step.params = _resolve_step_params(orig_params, ctx.variables)
                    REGISTRY.get(step.type).runner(ctx, step)
                finally:
                    step.params = orig_params
            except Exception as e:  # noqa: BLE001
                msg = f"Step {step.id} failed: {e}"
                ctx.logger.error(msg)
                messagebox.showerror("ExcelForge", f"Ошибка выполнения:\n{msg}")
                return

            i += 1
            self.after(0, _run_next)

        self.after(0, _run_next)

    def _open_df_preview_window(self, ctx: RunContext, subtitle: str) -> None:
        parent = self.winfo_toplevel()
        if self._df_preview_win is not None:
            try:
                if self._df_preview_win.winfo_exists():
                    self._df_preview_win.destroy()
            except tk.TclError:
                pass
        self._df_preview_win = DataPreviewWindow(parent, title="Просмотр DataFrame")
        self._df_preview_win.set_context(
            ctx,
            subtitle=subtitle,
            max_rows=preview_settings.get_preview_rows(),
        )

    def _preview_data(self) -> None:
        """Показать DataFrame из текущего сохранённого контекста выполнения."""
        if self._debug_ctx is None:
            messagebox.showwarning(
                "ExcelForge",
                "Нет текущего контекста выполнения.\n\n"
                "Сначала выполните пайплайн или «Выполнить до текущего шага», "
                "либо «Проверить шаг» (если контекст уже подготовлен).",
            )
            return
        try:
            self._debug_ctx.logger.info("Open DataFrame preview (current execution context).")
        except Exception:
            pass
        self._open_df_preview_window(self._debug_ctx, subtitle="текущий контекст выполнения")

    def _run_through_current_step(self) -> None:
        """Выполнить все шаги до текущего включительно; превью — состояние после текущего."""
        self._sync_pipeline_header()
        try:
            self.pipeline.validate()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("ExcelForge", f"Пайплайн невалиден:\n{e}")
            return

        idx0 = self._active_step_index
        if idx0 is None:
            messagebox.showwarning("ExcelForge", "Сначала выберите шаг.")
            return
        step = self.pipeline.steps[idx0]

        ctx = RunContext()
        self._attach_run_context_ui(ctx)
        self.protocol.clear()
        self.protocol.bind_logger(ctx.logger)
        stop_idx = idx0 + 1
        total = len(self.pipeline.steps)
        ctx.logger.info(f"Start pipeline: {self.pipeline.name} (steps={total})")
        i = 0

        def _run_next() -> None:
            nonlocal i
            if ctx.cancelled:
                ctx.logger.warn("Pipeline cancelled by user.")
                messagebox.showerror("ExcelForge", "Выполнение отменено.")
                return
            if i >= stop_idx:
                ctx.logger.info(
                    f"Pipeline preview stop requested at step {stop_idx}/{total}."
                )
                # Сохраняем контекст для быстрой проверки следующих шагов.
                self._debug_ctx = ctx
                self._open_df_preview_window(ctx, subtitle=f"после шага «{step.id}»")
                messagebox.showinfo("ExcelForge", "Выполнение до текущего шага завершено успешно.")
                return

            cur = self.pipeline.steps[i]
            idx1 = i + 1
            ctx.logger.info(f"[{idx1}/{total}] Step {cur.id}: {cur.type}")
            if not REGISTRY.has(cur.type):
                msg = f"Unknown step type: {cur.type}"
                ctx.logger.error(msg)
                messagebox.showerror("ExcelForge", f"Ошибка выполнения:\n{msg}")
                return
            try:
                orig_params = cur.params
                try:
                    cur.params = _resolve_step_params(orig_params, ctx.variables)
                    REGISTRY.get(cur.type).runner(ctx, cur)
                finally:
                    cur.params = orig_params
            except Exception as e:  # noqa: BLE001
                msg = f"Step {cur.id} failed: {e}"
                ctx.logger.error(msg)
                messagebox.showerror("ExcelForge", f"Ошибка шага:\n{msg}")
                return

            i += 1
            self.after(0, _run_next)

        self.after(0, _run_next)

    def _verify_current_step(self) -> None:
        """
        Быстро проверить выбранный шаг, НЕ запуская предыдущие шаги повторно.

        Используется сохранённый контекст `self._debug_ctx` (обычно появляется после
        «Просмотр данных на шаге» или «Выполнить до текущего шага»).
        Риск: шаг может изменить/перезаписать DF в контексте — это допустимо для быстрой отладки.
        """
        self._sync_pipeline_header()
        try:
            self.pipeline.validate()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("ExcelForge", f"Пайплайн невалиден:\n{e}")
            return

        idx0 = self._active_step_index
        if idx0 is None:
            messagebox.showwarning("ExcelForge", "Сначала выберите шаг.")
            return
        step = self.pipeline.steps[idx0]

        if not REGISTRY.has(step.type):
            messagebox.showerror("ExcelForge", f"Неизвестный тип шага: {step.type}")
            return

        base = self._debug_ctx
        if base is None:
            messagebox.showwarning(
                "ExcelForge",
                "Нет подготовленного контекста для быстрой проверки.\n\n"
                "Сначала выполните «Просмотр данных на шаге» или «Выполнить до текущего шага», "
                "чтобы загрузить/подготовить датафреймы.",
            )
            return

        # Используем общий df_store (без копирования), чтобы не переигрывать тяжёлые шаги.
        # logger новый, чтобы протокол не дублировал старые события.
        ctx = RunContext(df_store=base.df_store, variables=dict(base.variables))
        self._attach_run_context_ui(ctx)
        self.protocol.clear()
        self.protocol.bind_logger(ctx.logger)

        try:
            ctx.logger.info(f"Verify step: {step.id} ({step.type})")
            orig_params = step.params
            try:
                step.params = _resolve_step_params(orig_params, ctx.variables)
                REGISTRY.get(step.type).runner(ctx, step)
            finally:
                step.params = orig_params
        except Exception as e:  # noqa: BLE001
            ctx.logger.error(f"Verify step failed: {e}")
            messagebox.showerror("ExcelForge", f"Ошибка при проверке шага:\n{e}")
            return

        ctx.logger.info("Verify step finished successfully.")
        # Обновляем debug-контекст (df_store общий, но variables могли обновиться).
        self._debug_ctx = ctx
        self._open_df_preview_window(
            ctx,
            subtitle=f"проверка шага «{step.id}»",
        )
        messagebox.showinfo(
            "ExcelForge",
            "Проверка шага завершена (предыдущие шаги НЕ запускались; использован подготовленный контекст).",
        )
