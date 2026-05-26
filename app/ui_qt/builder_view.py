from __future__ import annotations

import os
from typing import Callable

import yaml
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.io.yaml_io import load_pipeline_yaml, save_pipeline_yaml
from app.pipeline.context import RunContext, create_run_context
from app.pipeline.global_context import list_global_names
from app.pipeline.registry import REGISTRY
from app.pipeline.schema import Pipeline, Step
from app import preview_settings
from app.ui_qt.data_preview_dialog import DataPreviewDialog
from app.ui_qt.log_bridge import LogBridge
from app.ui_qt.pipeline_qt_hooks import bind_qt_dialogs_to_context
from app.ui_qt.pipeline_worker import PipelineRunConfig, PipelineWorker, SingleStepWorker
from app.ui_qt.protocol_view import ProtocolView
from app.ui_qt.step_documentation_dialog import StepDocumentationDialog


class BuilderView(QWidget):
    def __init__(self, parent=None, *, pipelines_dir: str = "") -> None:
        super().__init__(parent)
        self.pipelines_dir = pipelines_dir
        self.pipeline = Pipeline(name="NewPipeline", description="", steps=[])
        self.current_file: str | None = None
        self._active_step_index: int | None = None
        self._dirty = False
        self._suppress_dirty = False
        self._step_editor_dirty = False
        self._df_preview: DataPreviewDialog | None = None
        self._doc_window: StepDocumentationDialog | None = None
        self._debug_ctx: RunContext | None = None
        self._worker: PipelineWorker | None = None
        self._single_worker: SingleStepWorker | None = None
        self._log_bridge = LogBridge(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("Файл конфигурации:"))
        self.lbl_file = QLineEdit()
        self.lbl_file.setReadOnly(True)
        file_row.addWidget(self.lbl_file, stretch=1)
        layout.addLayout(file_row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Описание:"))
        self.edit_desc = QLineEdit(self.pipeline.description)
        self.edit_desc.textChanged.connect(self._mark_dirty)
        row2.addWidget(self.edit_desc, stretch=1)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        for text, slot in (
            ("Новый", self._new),
            ("Открыть YAML…", self._open),
            ("Сохранить", self._save),
            ("Сохранить как…", self._save_as),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row3.addWidget(btn)
        row3.addStretch()
        layout.addLayout(row3)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Шаги пайплайна:"))
        self.steps_list = QListWidget()
        self.steps_list.currentRowChanged.connect(self._on_step_select)
        left_layout.addWidget(self.steps_list)

        tools = QHBoxLayout()
        self.cmb_new_type = QComboBox()
        step_defs = REGISTRY.list()
        self._step_type_titles = {d.title: d.type for d in step_defs}
        titles = [d.title for d in step_defs]
        self.cmb_new_type.addItems(titles)
        tools.addWidget(self.cmb_new_type, stretch=1)
        btn_add = QPushButton("Добавить")
        btn_add.clicked.connect(self._add_step)
        tools.addWidget(btn_add)
        left_layout.addLayout(tools)

        row2l = QHBoxLayout()
        for text, slot in (
            ("Удалить", self._delete_step),
            ("Вверх", lambda: self._move(-1)),
            ("Вниз", lambda: self._move(+1)),
            ("Клонировать", self._clone_step),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row2l.addWidget(btn)
        left_layout.addLayout(row2l)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        edit = QGroupBox("Параметры выбранного шага")
        edit_layout = QVBoxLayout(edit)

        id_type_row = QHBoxLayout()
        id_type_row.addWidget(QLabel("ID:"))
        self.edit_step_id = QLineEdit()
        self.edit_step_id.setMaxLength(64)
        self.edit_step_id.textChanged.connect(self._mark_step_editor_dirty)
        id_type_row.addWidget(self.edit_step_id)
        id_type_row.addSpacing(12)
        id_type_row.addWidget(QLabel("Type:"))
        self.edit_step_type = QLineEdit()
        self.edit_step_type.setReadOnly(True)
        id_type_row.addWidget(self.edit_step_type)
        id_type_row.addStretch()
        edit_layout.addLayout(id_type_row)
        field_w = QFontMetrics(self.edit_step_id.font()).horizontalAdvance("M" * 25) + 16
        self.edit_step_id.setFixedWidth(field_w)
        self.edit_step_type.setFixedWidth(field_w)

        comment_frame = QGroupBox("Комментарий к шагу (в YAML: comment)")
        comment_layout = QVBoxLayout(comment_frame)
        self.step_comment_text = QTextEdit()
        self.step_comment_text.setMaximumHeight(80)
        self.step_comment_text.textChanged.connect(self._mark_step_editor_dirty)
        comment_layout.addWidget(self.step_comment_text)
        edit_layout.addWidget(comment_frame)

        params_area = QWidget()
        params_area_layout = QVBoxLayout(params_area)
        params_area_layout.setContentsMargins(0, 0, 0, 0)
        params_area_layout.addWidget(QLabel("Params (YAML):"))
        self.params_text = QPlainTextEdit()
        self.params_text.setMinimumHeight(180)
        self.params_text.textChanged.connect(self._mark_step_editor_dirty)
        params_area_layout.addWidget(self.params_text, stretch=1)
        edit_layout.addWidget(params_area, stretch=1)

        tools_box = QGroupBox("Управление параметрами")
        tools_layout = QVBoxLayout(tools_box)
        tools_layout.setContentsMargins(8, 8, 8, 8)

        apply_row = QHBoxLayout()
        for text, slot in (
            ("Применить в шаг", self._apply_step_edits),
            ("Сбросить к default", self._reset_params_to_default),
            ("Документация по шагу", self._show_step_documentation),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            apply_row.addWidget(btn)
        apply_row.addStretch()
        tools_layout.addLayout(apply_row)

        self.step_path_tools = QWidget()
        path_layout = QHBoxLayout(self.step_path_tools)
        path_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_pick_in_file = QPushButton("Выбрать входной файл…")
        self.btn_pick_in_file.clicked.connect(self._pick_load_excel_file)
        path_layout.addWidget(self.btn_pick_in_file)
        self.btn_pick_in_dir = QPushButton("Выбрать входной каталог…")
        self.btn_pick_in_dir.clicked.connect(self._pick_load_excel_dir)
        path_layout.addWidget(self.btn_pick_in_dir)
        self.btn_pick_out_dir = QPushButton("Выбрать выходной каталог…")
        self.btn_pick_out_dir.clicked.connect(self._pick_save_excel_out_dir)
        path_layout.addWidget(self.btn_pick_out_dir)
        self.btn_pick_template = QPushButton("Выбрать Excel шаблон…")
        self.btn_pick_template.clicked.connect(self._pick_save_excel_template)
        path_layout.addWidget(self.btn_pick_template)
        self.btn_pick_globals_dir = QPushButton("Выбрать каталог (значение)…")
        self.btn_pick_globals_dir.clicked.connect(self._pick_globals_directory_value)
        path_layout.addWidget(self.btn_pick_globals_dir)
        self.btn_pick_globals_file = QPushButton("Выбрать файл (значение)…")
        self.btn_pick_globals_file.clicked.connect(self._pick_globals_file_value)
        path_layout.addWidget(self.btn_pick_globals_file)
        path_layout.addStretch()
        self.step_path_tools.hide()
        tools_layout.addWidget(self.step_path_tools)

        edit_layout.addWidget(tools_box, stretch=0)

        right_layout.addWidget(edit, stretch=1)

        run_box = QGroupBox("Тестовый запуск")
        run_row = QHBoxLayout(run_box)
        for text, slot in (
            ("Запустить пайплайн", self._run_pipeline),
            ("Просмотр данных", self._preview_data),
            ("Выполнить до текущего шага", self._run_through_current_step),
            ("Проверить шаг", self._verify_current_step),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            run_row.addWidget(btn)
        self.btn_cancel_run = QPushButton("Отмена")
        self.btn_cancel_run.setEnabled(False)
        self.btn_cancel_run.clicked.connect(self._cancel_run)
        run_row.addWidget(self.btn_cancel_run)
        run_row.addStretch()
        right_layout.addWidget(run_box)

        splitter.addWidget(right)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter, stretch=1)

        proto = QGroupBox("Протокол")
        proto_layout = QVBoxLayout(proto)
        self.protocol = ProtocolView(height_lines=5)
        proto_layout.addWidget(self.protocol)
        layout.addWidget(proto)

        self._log_bridge.event.connect(self.protocol.on_log_event)
        self._refresh_steps_list()
        self._select_step(0)
        self._update_file_label()
        self._dirty = False

    def _mark_dirty(self) -> None:
        if not self._suppress_dirty:
            self._dirty = True

    def _mark_step_editor_dirty(self) -> None:
        if not self._suppress_dirty:
            self._step_editor_dirty = True

    def _clear_dirty(self) -> None:
        self._dirty = False

    def _update_file_label(self) -> None:
        if self.current_file:
            self.lbl_file.setText(os.path.abspath(self.current_file))
        else:
            self.lbl_file.setText("(новый пайплайн, файл не сохранён)")

    def _maybe_save_dirty(self) -> bool:
        if not self._dirty:
            return True
        btn = QMessageBox.question(
            self,
            "ExcelForge",
            "Есть несохранённые изменения (описание или шаги).\n"
            "Сохранить текущий файл перед продолжением?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
        )
        if btn == QMessageBox.StandardButton.Cancel:
            return False
        if btn == QMessageBox.StandardButton.Yes:
            self._sync_pipeline_header()
            if self.current_file:
                try:
                    self._sync_pipeline_name_from_path(self.current_file)
                    save_pipeline_yaml(self.pipeline, self.current_file)
                    self._clear_dirty()
                    self._update_file_label()
                except Exception as e:  # noqa: BLE001
                    QMessageBox.critical(self, "ExcelForge", f"Ошибка сохранения:\n{e}")
                    return False
            else:
                if not self._save_as_internal(show_messages=True):
                    return False
        else:
            self._clear_dirty()
        return True

    def _reset_to_new_pipeline(self) -> None:
        self.pipeline = Pipeline(name="NewPipeline", description="", steps=[])
        self.current_file = None
        self._suppress_dirty = True
        self.edit_desc.setText(self.pipeline.description)
        self._suppress_dirty = False
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
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть YAML пайплайн",
            self.pipelines_dir,
            "YAML (*.yml *.yaml);;All files (*.*)",
        )
        if not path:
            return
        try:
            p = load_pipeline_yaml(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "ExcelForge", f"Ошибка загрузки YAML:\n{e}")
            return
        self.pipeline = p
        self.current_file = path
        self._suppress_dirty = True
        self.edit_desc.setText(p.description)
        self._suppress_dirty = False
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
            QMessageBox.information(self, "ExcelForge", f"Сохранено:\n{self.current_file}")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "ExcelForge", f"Ошибка сохранения:\n{e}")

    def _save_as(self) -> None:
        self._save_as_internal(show_messages=True)

    def _save_as_internal(self, *, show_messages: bool) -> bool:
        self._sync_pipeline_header()
        os.makedirs(self.pipelines_dir, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить пайплайн как",
            self.pipelines_dir,
            "YAML (*.yaml *.yml);;All files (*.*)",
        )
        if not path:
            return False
        if not path.lower().endswith((".yaml", ".yml")):
            path += ".yaml"
        self._sync_pipeline_name_from_path(path)
        try:
            save_pipeline_yaml(self.pipeline, path)
            self.current_file = path
            self._clear_dirty()
            self._update_file_label()
            if show_messages:
                QMessageBox.information(self, "ExcelForge", f"Сохранено:\n{path}")
            return True
        except Exception as e:  # noqa: BLE001
            if show_messages:
                QMessageBox.critical(self, "ExcelForge", f"Ошибка сохранения:\n{e}")
            return False

    def _sync_pipeline_header(self) -> None:
        self.pipeline.description = self.edit_desc.text().strip()

    @staticmethod
    def _name_from_yaml_path(path: str) -> str:
        base = os.path.splitext(os.path.basename(path))[0].strip()
        return base or "pipeline"

    def _sync_pipeline_name_from_path(self, path: str) -> None:
        self.pipeline.name = self._name_from_yaml_path(path)

    @staticmethod
    def _step_title_ru(step: Step) -> str:
        if REGISTRY.has(step.type):
            return REGISTRY.get(step.type).title
        return step.type

    def _refresh_steps_list(self) -> None:
        self.steps_list.clear()
        for i, s in enumerate(self.pipeline.steps, start=1):
            self.steps_list.addItem(f"{i}. {self._step_title_ru(s)}")

    def _select_step(self, idx: int) -> None:
        if not self.pipeline.steps:
            self.edit_step_id.clear()
            self.edit_step_type.clear()
            self.params_text.clear()
            self.step_comment_text.clear()
            self._active_step_index = None
            self._step_editor_dirty = False
            return
        idx = max(0, min(idx, len(self.pipeline.steps) - 1))
        self._active_step_index = idx
        self.steps_list.blockSignals(True)
        self.steps_list.setCurrentRow(idx)
        self.steps_list.blockSignals(False)
        self._load_selected_step()

    def _on_step_select(self, new_idx: int) -> None:
        if new_idx < 0:
            return
        cur_idx = self._active_step_index
        if cur_idx is not None and new_idx != cur_idx and self._step_editor_dirty:
            btn = QMessageBox.question(
                self,
                "ExcelForge",
                "Текущий шаг изменён, но изменения не применены.\n"
                "Применить изменения перед переходом на другой шаг?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if btn == QMessageBox.StandardButton.Cancel:
                self.steps_list.blockSignals(True)
                self.steps_list.setCurrentRow(cur_idx)
                self.steps_list.blockSignals(False)
                return
            if btn == QMessageBox.StandardButton.Yes:
                prev_idx = cur_idx
                self._apply_step_edits()
                if self._step_editor_dirty:
                    self.steps_list.blockSignals(True)
                    self.steps_list.setCurrentRow(prev_idx)
                    self.steps_list.blockSignals(False)
                    return
            else:
                self._step_editor_dirty = False
        self._active_step_index = new_idx
        self._load_selected_step()

    def _load_selected_step(self) -> None:
        idx = self._active_step_index
        if idx is None or idx < 0 or idx >= len(self.pipeline.steps):
            return
        step = self.pipeline.steps[idx]
        self._suppress_dirty = True
        self.edit_step_id.setText(step.id)
        self.edit_step_type.setText(step.type)
        self.params_text.setPlainText(
            yaml.safe_dump(step.params or {}, sort_keys=False, allow_unicode=True)
        )
        self.step_comment_text.setPlainText(step.comment or "")
        self._suppress_dirty = False
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
            w.hide()
        self.step_path_tools.hide()
        if step_type == "load_excel":
            self.step_path_tools.show()
            self.btn_pick_in_file.show()
            self.btn_pick_in_dir.show()
        elif step_type == "save_excel":
            self.step_path_tools.show()
            self.btn_pick_out_dir.show()
            self.btn_pick_template.show()
        elif step_type == "globals_settings":
            self.step_path_tools.show()
            self.btn_pick_globals_dir.show()
            self.btn_pick_globals_file.show()

    def _apply_step_edits(self) -> None:
        idx = self._active_step_index
        if idx is None:
            QMessageBox.warning(self, "ExcelForge", "Сначала выберите шаг.")
            return
        step = self.pipeline.steps[idx]
        step.id = self.edit_step_id.text().strip()
        try:
            params = yaml.safe_load(self.params_text.toPlainText()) or {}
            if not isinstance(params, dict):
                raise ValueError("Params YAML должен быть словарём (mapping).")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "ExcelForge", f"Ошибка params YAML:\n{e}")
            return
        step.params = params
        step.comment = self.step_comment_text.toPlainText().replace("\r\n", "\n").rstrip("\n")
        self._mark_dirty()
        self._refresh_steps_list()
        self._step_editor_dirty = False
        self._select_step(idx)

    def _current_step(self) -> Step | None:
        idx = self._active_step_index
        if idx is None or idx < 0 or idx >= len(self.pipeline.steps):
            return None
        return self.pipeline.steps[idx]

    def _read_params_text(self) -> dict:
        params = yaml.safe_load(self.params_text.toPlainText()) or {}
        if not isinstance(params, dict):
            raise ValueError("Params YAML должен быть словарём (mapping).")
        return params

    def _write_params_text(self, params: dict) -> None:
        self.params_text.setPlainText(yaml.safe_dump(params, sort_keys=False, allow_unicode=True))
        self._mark_step_editor_dirty()

    def _pick_load_excel_file(self) -> None:
        step = self._current_step()
        if not step or step.type != "load_excel":
            return
        try:
            params = self._read_params_text()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "ExcelForge", f"Ошибка params YAML:\n{e}")
            return
        initial = params.get("file_path") or os.getcwd()
        fp, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите Excel файл",
            os.path.dirname(str(initial)) if str(initial) else os.getcwd(),
            "Excel (*.xlsx *.xlsm *.xls);;All files (*.*)",
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
            QMessageBox.critical(self, "ExcelForge", f"Ошибка params YAML:\n{e}")
            return
        initial = params.get("directory") or os.getcwd()
        d = QFileDialog.getExistingDirectory(
            self,
            "Выберите каталог с Excel файлами",
            str(initial) if str(initial) else os.getcwd(),
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
            QMessageBox.critical(self, "ExcelForge", f"Ошибка params YAML:\n{e}")
            return
        initial = params.get("out_dir") or os.getcwd()
        d = QFileDialog.getExistingDirectory(
            self,
            "Выберите выходной каталог",
            str(initial) if str(initial) else os.getcwd(),
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
            QMessageBox.critical(self, "ExcelForge", f"Ошибка params YAML:\n{e}")
            return
        initial = params.get("template_path") or os.getcwd()
        fp, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите Excel шаблон",
            os.path.dirname(str(initial)) if str(initial) else os.getcwd(),
            "Excel (*.xlsx *.xlsm *.xls);;All files (*.*)",
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
            QMessageBox.critical(self, "ExcelForge", f"Ошибка params YAML:\n{e}")
            return
        values = params.get("values") or {}
        if not isinstance(values, dict):
            QMessageBox.critical(self, "ExcelForge", "globals_settings: params.values должен быть словарём.")
            return
        var = self._norm_global_var_name(params.get("directory_var"), "directory")
        current = values.get(var)
        initial = str(current or params.get("directory_initial") or os.getcwd())
        title = str(params.get("directory_open_dialog_help") or "Выберите каталог")
        d = QFileDialog.getExistingDirectory(self, title, initial if initial else os.getcwd())
        if not d:
            return
        values[var] = d
        params["values"] = values
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
            QMessageBox.critical(self, "ExcelForge", f"Ошибка params YAML:\n{e}")
            return
        values = params.get("values") or {}
        if not isinstance(values, dict):
            QMessageBox.critical(self, "ExcelForge", "globals_settings: params.values должен быть словарём.")
            return
        var = self._norm_global_var_name(params.get("file_var"), "file_path")
        current = values.get(var)
        initial_dir = os.path.dirname(str(current)) if current else os.getcwd()
        title = str(params.get("file_open_dialog_help") or "Выберите файл")
        fp, _ = QFileDialog.getOpenFileName(
            self,
            title,
            initial_dir if initial_dir else os.getcwd(),
            "All files (*.*)",
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
            QMessageBox.warning(self, "ExcelForge", "Выберите шаг в списке.")
            return
        step = self.pipeline.steps[idx]
        step_title = REGISTRY.get(step.type).title if REGISTRY.has(step.type) else ""
        if self._doc_window is None:
            self._doc_window = StepDocumentationDialog(self.window())
        self._doc_window.show_documentation(step.type, step_title)

    def _add_step(self) -> None:
        title = self.cmb_new_type.currentText()
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
        row = self.steps_list.currentRow()
        if row < 0:
            return
        del self.pipeline.steps[row]
        self._mark_dirty()
        self._refresh_steps_list()
        self._select_step(min(row, len(self.pipeline.steps) - 1))

    def _move(self, delta: int) -> None:
        row = self.steps_list.currentRow()
        if row < 0:
            return
        j = row + delta
        if j < 0 or j >= len(self.pipeline.steps):
            return
        self.pipeline.steps[row], self.pipeline.steps[j] = self.pipeline.steps[j], self.pipeline.steps[row]
        self._mark_dirty()
        self._refresh_steps_list()
        self._select_step(j)

    def _clone_step(self) -> None:
        row = self.steps_list.currentRow()
        if row < 0:
            return
        s = self.pipeline.steps[row]
        new_id = self._next_step_id(s.type)
        self.pipeline.steps.insert(
            row + 1,
            Step(id=new_id, type=s.type, params=dict(s.params), comment=str(s.comment or "")),
        )
        self._mark_dirty()
        self._refresh_steps_list()
        self._select_step(row + 1)

    def _attach_run_context_ui(self, ctx: RunContext) -> None:
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

    def _set_run_buttons_running(self, running: bool) -> None:
        self.btn_cancel_run.setEnabled(running)

    def _cancel_run(self) -> None:
        if self._worker and self._worker.isRunning():
            ctx = self._worker._ctx  # noqa: SLF001
            ctx.cancel()
        if self._single_worker and self._single_worker.isRunning():
            pass

    def _start_pipeline_worker(
        self,
        ctx: RunContext,
        *,
        stop_after_index: int | None = None,
        on_ok: Callable[[RunContext], None],
    ) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(self, "ExcelForge", "Уже выполняется пайплайн.")
            return
        self._sync_pipeline_header()
        try:
            self.pipeline.validate()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "ExcelForge", f"Пайплайн невалиден:\n{e}")
            return

        self.protocol.clear()
        self._log_bridge.connect_logger(ctx.logger)
        self._set_run_buttons_running(True)

        config = PipelineRunConfig(pipeline=self.pipeline, stop_after_index=stop_after_index)
        self._worker = PipelineWorker(ctx, config, self)
        self._worker.finished_ok.connect(lambda c: self._on_worker_ok(c, on_ok))
        self._worker.finished_error.connect(self._on_worker_error)
        self._worker.cancelled.connect(self._on_worker_cancelled)
        self._worker.start()

    def _on_worker_ok(self, ctx: RunContext, on_ok: Callable[[RunContext], None]) -> None:
        self._set_run_buttons_running(False)
        if self._worker:
            self._worker.wait(3000)
            self._worker = None
        self._debug_ctx = ctx
        on_ok(ctx)

    def _on_worker_error(self, err: str) -> None:
        self._set_run_buttons_running(False)
        if self._worker:
            self._worker.wait(3000)
            self._worker = None
        QMessageBox.critical(self, "ExcelForge", f"Ошибка выполнения:\n{err}")

    def _on_worker_cancelled(self) -> None:
        self._set_run_buttons_running(False)
        if self._worker:
            self._worker.wait(3000)
            self._worker = None
        QMessageBox.critical(self, "ExcelForge", "Выполнение отменено.")

    def _run_pipeline(self) -> None:
        ctx = create_run_context()
        self._attach_run_context_ui(ctx)

        def _ok(_c: RunContext) -> None:
            QMessageBox.information(self, "ExcelForge", "Выполнено успешно.")

        self._start_pipeline_worker(ctx, on_ok=_ok)

    def _open_df_preview_window(self, ctx: RunContext, subtitle: str) -> None:
        if self._df_preview is None:
            self._df_preview = DataPreviewDialog(self.window(), title="Просмотр DataFrame")
        self._df_preview.set_context(
            ctx,
            subtitle=subtitle,
            max_rows=preview_settings.get_preview_rows(),
        )
        self._df_preview.show()
        self._df_preview.raise_()
        self._df_preview.activateWindow()

    def _preview_data(self) -> None:
        if self._debug_ctx is not None:
            ctx = self._debug_ctx
            subtitle = "текущий контекст выполнения"
            try:
                ctx.logger.info("Open DataFrame preview (current execution context).")
            except Exception:
                pass
        elif list_global_names():
            ctx = create_run_context()
            subtitle = "глобальный контекст сессии"
            try:
                ctx.logger.info(
                    "Open DataFrame preview (global session context, "
                    f"{len(list_global_names())} DF)."
                )
            except Exception:
                pass
        else:
            QMessageBox.warning(
                self,
                "ExcelForge",
                "Нет данных для просмотра.\n\n"
                "Выполните пайплайн в Runner или Builder (с glob_* в имени DF), "
                "либо «Выполнить до текущего шага» / «Проверить шаг» в Builder.",
            )
            return
        self._open_df_preview_window(ctx, subtitle=subtitle)

    def _run_through_current_step(self) -> None:
        idx0 = self._active_step_index
        if idx0 is None:
            QMessageBox.warning(self, "ExcelForge", "Сначала выберите шаг.")
            return
        step = self.pipeline.steps[idx0]
        ctx = create_run_context()
        self._attach_run_context_ui(ctx)

        def _ok(c: RunContext) -> None:
            self._open_df_preview_window(c, subtitle=f"после шага «{step.id}»")
            QMessageBox.information(self, "ExcelForge", "Выполнение до текущего шага завершено успешно.")

        self._start_pipeline_worker(ctx, stop_after_index=idx0 + 1, on_ok=_ok)

    def _verify_current_step(self) -> None:
        idx0 = self._active_step_index
        if idx0 is None:
            QMessageBox.warning(self, "ExcelForge", "Сначала выберите шаг.")
            return
        step = self.pipeline.steps[idx0]
        if not REGISTRY.has(step.type):
            QMessageBox.critical(self, "ExcelForge", f"Неизвестный тип шага: {step.type}")
            return
        base = self._debug_ctx
        if base is None:
            QMessageBox.warning(
                self,
                "ExcelForge",
                "Нет подготовленного контекста для быстрой проверки.\n\n"
                "Сначала выполните «Просмотр данных на шаге» или «Выполнить до текущего шага», "
                "чтобы загрузить/подготовить датафреймы.",
            )
            return
        if self._single_worker and self._single_worker.isRunning():
            return

        ctx = create_run_context(df_store=base.df_store, variables=dict(base.variables))
        self._attach_run_context_ui(ctx)
        self.protocol.clear()
        self._log_bridge.connect_logger(ctx.logger)
        self._set_run_buttons_running(True)

        self._single_worker = SingleStepWorker(ctx, step, self)
        self._single_worker.finished_ok.connect(self._on_verify_ok)
        self._single_worker.finished_error.connect(self._on_verify_error)
        self._single_worker.start()

    def _on_verify_ok(self, ctx: RunContext) -> None:
        self._set_run_buttons_running(False)
        if self._single_worker:
            self._single_worker.wait(3000)
            self._single_worker = None
        idx0 = self._active_step_index
        step = self.pipeline.steps[idx0] if idx0 is not None else None
        self._debug_ctx = ctx
        sid = step.id if step else ""
        self._open_df_preview_window(ctx, subtitle=f"проверка шага «{sid}»")
        QMessageBox.information(
            self,
            "ExcelForge",
            "Проверка шага завершена (предыдущие шаги НЕ запускались; использован подготовленный контекст).",
        )

    def _on_verify_error(self, err: str) -> None:
        self._set_run_buttons_running(False)
        if self._single_worker:
            self._single_worker.wait(3000)
            self._single_worker = None
        QMessageBox.critical(self, "ExcelForge", f"Ошибка при проверке шага:\n{err}")
