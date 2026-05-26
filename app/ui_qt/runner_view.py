from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.io.yaml_io import load_pipeline_yaml
from app.pipeline.context import RunContext, create_run_context
from app.pipeline.schema import Pipeline
from app.steps.util import param_is_on
from app.ui_qt.log_bridge import LogBridge
from app.ui_qt.pipeline_qt_hooks import bind_qt_dialogs_to_context
from app.ui_qt.pipeline_worker import PipelineRunConfig, PipelineWorker
from app.ui_qt.protocol_view import ProtocolView


class RunnerView(QWidget):
    def __init__(self, parent=None, *, pipelines_dir: str = "") -> None:
        super().__init__(parent)
        self._pipelines_dir = pipelines_dir
        self._running = False
        self._ctx: RunContext | None = None
        self._worker: PipelineWorker | None = None
        self._log_bridge = LogBridge(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        top = QHBoxLayout()
        top.addWidget(QLabel("Каталог пайплайнов:"))
        self.edit_dir = QLineEdit(self._pipelines_dir)
        top.addWidget(self.edit_dir, stretch=1)
        btn_pick = QPushButton("Выбрать…")
        btn_pick.clicked.connect(self._pick_dir)
        top.addWidget(btn_pick)
        btn_refresh = QPushButton("Обновить список")
        btn_refresh.clicked.connect(self.refresh_list)
        top.addWidget(btn_refresh)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Пайплайны (*.yml, *.yaml):"))
        self.listbox = QListWidget()
        self.listbox.currentRowChanged.connect(self._on_select)
        left_layout.addWidget(self.listbox)
        # Ширина списка пайплайнов: базовая + 15 символов для длинных имён YAML.
        _list_chars = 45
        left.setMinimumWidth(QFontMetrics(self.listbox.font()).horizontalAdvance("M" * _list_chars))

        btns = QHBoxLayout()
        self.btn_run = QPushButton("Запустить")
        self.btn_run.clicked.connect(self._run_selected)
        btns.addWidget(self.btn_run)
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        btns.addWidget(self.btn_cancel)
        btns.addStretch()
        left_layout.addLayout(btns)

        self.progress = QProgressBar()
        left_layout.addWidget(self.progress)
        splitter.addWidget(left)

        right_splitter = QSplitter(Qt.Orientation.Vertical)

        info = QGroupBox("Информация")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(8, 8, 8, 8)
        self.info_text = QPlainTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setPlaceholderText("Выберите YAML пайплайн слева.")
        self.info_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        info_layout.addWidget(self.info_text)
        right_splitter.addWidget(info)

        proto = QGroupBox("Протокол")
        proto_layout = QVBoxLayout(proto)
        proto_layout.setContentsMargins(8, 8, 8, 8)
        self.protocol = ProtocolView(height_lines=None)
        proto_layout.addWidget(self.protocol, stretch=1)
        right_splitter.addWidget(proto)

        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 1)
        splitter.addWidget(right_splitter)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 4)
        splitter.setChildrenCollapsible(False)

        layout.addWidget(splitter, stretch=1)
        self._h_splitter = splitter
        self._splitter_sized = False
        self._log_bridge.event.connect(self.protocol.on_log_event)
        self.refresh_list()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        if not self._splitter_sized:
            self._apply_pipeline_splitter_sizes()
            self._splitter_sized = True

    def _apply_pipeline_splitter_sizes(self) -> None:
        splitter = getattr(self, "_h_splitter", None)
        if splitter is None:
            return
        total = splitter.width()
        if total < 200:
            return
        char_w = max(8, QFontMetrics(self.listbox.font()).horizontalAdvance("M"))
        left_w = min(total - 180, max(splitter.widget(0).minimumWidth(), int(total * 0.32) + char_w * 15))
        splitter.setSizes([left_w, max(180, total - left_w)])

    def _pipelines_path(self) -> str:
        return self.edit_dir.text().strip() or os.getcwd()

    def _pick_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Каталог пайплайнов", self._pipelines_path())
        if d:
            self.edit_dir.setText(d)
            self.refresh_list()

    def refresh_list(self) -> None:
        d = self._pipelines_path()
        os.makedirs(d, exist_ok=True)
        files = [
            f
            for f in os.listdir(d)
            if f.lower().endswith((".yaml", ".yml")) and os.path.isfile(os.path.join(d, f))
        ]
        files.sort(key=str.lower)
        self.listbox.clear()
        self.listbox.addItems(files)
        self.info_text.setPlainText("")

    def _on_select(self, row: int) -> None:
        if row < 0:
            return
        item = self.listbox.item(row)
        if item is None:
            return
        fname = item.text()
        try:
            path = os.path.join(self._pipelines_path(), fname)
            p = load_pipeline_yaml(path)
            self.info_text.setPlainText(
                f"Имя: {p.name}\nШагов: {len(p.steps)}\nОписание: {p.description}"
            )
        except Exception as e:  # noqa: BLE001
            self.info_text.setPlainText(f"Ошибка загрузки: {e}")

    def _prepare_pipeline(self, p: Pipeline) -> Pipeline:
        for step in p.steps:
            if step.type != "load_excel":
                continue
            params = dict(step.params)
            input_mode = str(params.get("input_mode", "mask"))
            if input_mode == "file":
                if param_is_on(params.get("file_open_dialog")):
                    continue
                if not str(params.get("file_path", "")).strip():
                    fp, _ = QFileDialog.getOpenFileName(
                        self,
                        "Выберите Excel файл",
                        "",
                        "Excel (*.xlsx *.xlsm *.xls);;All files (*.*)",
                    )
                    if not fp:
                        raise RuntimeError("Не выбран входной файл для load_excel.")
                    params["file_path"] = fp
            if input_mode in ("mask", "latest"):
                if param_is_on(params.get("directory_open_dialog")):
                    continue
                if not str(params.get("directory", "")).strip():
                    d = QFileDialog.getExistingDirectory(self, "Выберите каталог с Excel файлами")
                    if not d:
                        raise RuntimeError("Не выбран каталог для load_excel.")
                    params["directory"] = d
            step.params = params
        return p

    def _run_selected(self) -> None:
        if self._running:
            return
        row = self.listbox.currentRow()
        if row < 0:
            QMessageBox.warning(self, "ExcelForge", "Сначала выберите YAML пайплайн.")
            return
        item = self.listbox.item(row)
        if item is None:
            return
        sel = item.text()
        path = os.path.join(self._pipelines_path(), sel)
        try:
            pipeline = load_pipeline_yaml(path)
            pipeline = self._prepare_pipeline(pipeline)
            pipeline.validate()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "ExcelForge", f"Не удалось загрузить пайплайн:\n{e}")
            return

        ctx = create_run_context()
        host = bind_qt_dialogs_to_context(ctx, self)

        def _confirm_zero_rows(df_name: str) -> bool:
            def _ask() -> bool:
                return (
                    QMessageBox.question(
                        self,
                        "ExcelForge",
                        f"Загружено 0 строк в датафрейм '{df_name}'. Продолжить выполнение?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    == QMessageBox.StandardButton.Yes
                )

            return bool(host.invoke(_ask))

        ctx.variables["confirm_continue_on_zero_rows"] = _confirm_zero_rows
        self._ctx = ctx
        self.protocol.clear()
        self._log_bridge.connect_logger(ctx.logger)

        self._running = True
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        total = max(1, len(pipeline.steps))
        self.progress.setMaximum(total)
        self.progress.setValue(0)

        config = PipelineRunConfig(pipeline=pipeline)
        self._worker = PipelineWorker(ctx, config, self)
        self._worker.step_finished.connect(self._on_step_finished)
        self._worker.finished_ok.connect(self._on_finished_ok)
        self._worker.finished_error.connect(self._on_finished_error)
        self._worker.cancelled.connect(self._on_finished_cancelled)
        self._worker.start()

    def _on_step_finished(self, done: int, total: int) -> None:
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(done)

    def _on_finished_ok(self, _ctx: object) -> None:
        self._on_done(True, None)

    def _on_finished_error(self, err: str) -> None:
        self._on_done(False, err)

    def _on_finished_cancelled(self) -> None:
        self._on_done(False, "cancelled")

    def _on_done(self, ok: bool, err: str | None) -> None:
        self._running = False
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        if self._worker:
            self._worker.wait(3000)
            self._worker = None
        if ok:
            QMessageBox.information(self, "ExcelForge", "Пайплайн выполнен успешно.")
        else:
            QMessageBox.critical(self, "ExcelForge", f"Ошибка выполнения:\n{err or 'unknown error'}")

    def _cancel(self) -> None:
        if self._ctx:
            self._ctx.cancel()
