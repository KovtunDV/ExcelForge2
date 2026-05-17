from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

from app.io.yaml_io import load_pipeline_yaml
from app.pipeline.context import RunContext
from app.pipeline.registry import REGISTRY
from app.pipeline.schema import Pipeline
from app.steps.util import param_is_on
from app.ui.pipeline_tk_hooks import bind_tk_dialogs_to_context
from app.ui.protocol_view import ProtocolView
from app.pipeline.runner import _resolve_step_params


class RunnerView(ttk.Frame):
    def __init__(self, master: tk.Misc, pipelines_dir: str):
        super().__init__(master)

        self.pipelines_dir = tk.StringVar(value=pipelines_dir)
        self.selected_yaml = tk.StringVar(value="")
        self._running = False
        self._ctx: RunContext | None = None

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Label(top, text="Каталог пайплайнов:").pack(side="left")
        ttk.Entry(top, textvariable=self.pipelines_dir, width=60).pack(side="left", padx=(8, 8))
        ttk.Button(top, text="Выбрать…", command=self._pick_dir).pack(side="left")
        ttk.Button(top, text="Обновить список", command=self.refresh_list).pack(side="left", padx=(8, 0))

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(main)
        right = ttk.Frame(main)
        main.add(left, weight=1)
        main.add(right, weight=3)

        ttk.Label(left, text="Пайплайны (*.yml, *.yaml):").pack(anchor="w")
        self.listbox = tk.Listbox(left, height=25)
        self.listbox.pack(fill="both", expand=True, pady=(6, 8))
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._on_select())

        btns = ttk.Frame(left)
        btns.pack(fill="x")
        self.btn_run = ttk.Button(btns, text="Запустить", command=self._run_selected)
        self.btn_run.pack(side="left")
        self.btn_cancel = ttk.Button(btns, text="Отмена", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(left, mode="determinate")
        self.progress.pack(fill="x", pady=(10, 0))

        info = ttk.LabelFrame(right, text="Информация")
        info.pack(fill="x")
        self.lbl_info = ttk.Label(info, text="Выберите YAML пайплайн слева.")
        self.lbl_info.pack(anchor="w", padx=10, pady=10)

        proto = ttk.LabelFrame(right, text="Протокол")
        proto.pack(fill="both", expand=True, pady=(10, 0))
        self.protocol = ProtocolView(proto)
        self.protocol.pack(fill="both", expand=True, padx=10, pady=10)

        self.refresh_list()

    def _pick_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=self.pipelines_dir.get() or os.getcwd())
        if d:
            self.pipelines_dir.set(d)
            self.refresh_list()

    def refresh_list(self) -> None:
        d = self.pipelines_dir.get()
        os.makedirs(d, exist_ok=True)
        files = [
            f
            for f in os.listdir(d)
            if f.lower().endswith((".yaml", ".yml")) and os.path.isfile(os.path.join(d, f))
        ]
        files.sort(key=lambda s: s.lower())
        self.listbox.delete(0, "end")
        for f in files:
            self.listbox.insert("end", f)
        self.selected_yaml.set("")
        self.lbl_info.configure(text="Выберите YAML пайплайн слева.")

    def _on_select(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        fname = self.listbox.get(sel[0])
        self.selected_yaml.set(fname)
        try:
            path = os.path.join(self.pipelines_dir.get(), fname)
            p = load_pipeline_yaml(path)
            self.lbl_info.configure(
                text=f"Имя: {p.name}\nШагов: {len(p.steps)}\nОписание: {p.description}"
            )
        except Exception as e:  # noqa: BLE001
            self.lbl_info.configure(text=f"Ошибка загрузки: {e}")

    def _prepare_pipeline(self, p: Pipeline) -> Pipeline:
        # Дозапрос путей только если в шаге не включены runtime-диалоги и путь пустой.
        for step in p.steps:
            if step.type != "load_excel":
                continue
            params = dict(step.params)
            input_mode = str(params.get("input_mode", "mask"))
            if input_mode == "file":
                if param_is_on(params.get("file_open_dialog")):
                    continue
                if not str(params.get("file_path", "")).strip():
                    fp = filedialog.askopenfilename(
                        title="Выберите Excel файл",
                        filetypes=[("Excel", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")],
                    )
                    if not fp:
                        raise RuntimeError("Не выбран входной файл для load_excel.")
                    params["file_path"] = fp
            if input_mode in ("mask", "latest"):
                if param_is_on(params.get("directory_open_dialog")):
                    continue
                if not str(params.get("directory", "")).strip():
                    d = filedialog.askdirectory(title="Выберите каталог с Excel файлами")
                    if not d:
                        raise RuntimeError("Не выбран каталог для load_excel.")
                    params["directory"] = d
            step.params = params
        return p

    def _run_selected(self) -> None:
        if self._running:
            return
        sel = self.selected_yaml.get()
        if not sel:
            messagebox.showwarning("ExcelForge", "Сначала выберите YAML пайплайн.")
            return

        path = os.path.join(self.pipelines_dir.get(), sel)
        try:
            pipeline = load_pipeline_yaml(path)
            pipeline = self._prepare_pipeline(pipeline)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("ExcelForge", f"Не удалось загрузить пайплайн:\n{e}")
            return

        ctx = RunContext()
        bind_tk_dialogs_to_context(ctx, self)
        ctx.variables["confirm_continue_on_zero_rows"] = lambda df_name: messagebox.askyesno(
            "ExcelForge",
            f"Загружено 0 строк в датафрейм '{df_name}'. Продолжить выполнение?",
        )
        self._ctx = ctx
        self.protocol.clear()
        self.protocol.bind_logger(ctx.logger)

        self._running = True
        self.btn_run.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.progress.configure(value=0, maximum=max(1, len(pipeline.steps)))

        # Пошаговое выполнение в главном потоке Tk, чтобы UI/протокол обновлялись
        # в процессе выполнения, а диалоги оставались рабочими.
        total = len(pipeline.steps)
        pipeline.validate()
        ctx.logger.info(f"Start pipeline: {pipeline.name} (steps={total})")

        i = 0

        def _progress() -> None:
            self.progress.configure(maximum=max(1, total), value=i)

        def _run_next() -> None:
            nonlocal i
            if ctx.cancelled:
                ctx.logger.warn("Pipeline cancelled by user.")
                self._on_done(False, "cancelled")
                return
            if i >= total:
                ctx.logger.info("Pipeline finished successfully.")
                self._on_done(True, None)
                return

            step = pipeline.steps[i]
            idx1 = i + 1
            _progress()
            ctx.logger.info(f"[{idx1}/{total}] Step {step.id}: {step.type}")

            if not REGISTRY.has(step.type):
                msg = f"Unknown step type: {step.type}"
                ctx.logger.error(msg)
                self._on_done(False, msg)
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
                self._on_done(False, msg)
                return

            i += 1
            # Yield to Tk so protocol/progress repaint between steps.
            self.after(0, _run_next)

        self.after(0, _run_next)

    def _on_done(self, ok: bool, err: str | None) -> None:
        self._running = False
        self.btn_run.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.progress.configure(value=self.progress["maximum"])
        if ok:
            messagebox.showinfo("ExcelForge", "Пайплайн выполнен успешно.")
        else:
            messagebox.showerror("ExcelForge", f"Ошибка выполнения:\n{err or 'unknown error'}")

    def _cancel(self) -> None:
        if self._ctx:
            self._ctx.cancel()

