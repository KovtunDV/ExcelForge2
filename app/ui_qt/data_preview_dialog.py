from __future__ import annotations

import json
from typing import Any

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.pipeline.context import RunContext
from app.pipeline.global_context import get_df_for_preview, list_preview_df_names
from app.pipeline.user_variables import user_variables_for_display
from app.ui_qt.app_icon import apply_window_icon


def _format_variable_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, (list, dict, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError):
            return repr(value)
    return repr(value)


def _variable_type_name(value: Any) -> str:
    if value is None:
        return "null"
    return type(value).__name__


_VARIABLE_VALUE_PREVIEW_LIMIT = 200


def _preview_variable_value(value: str) -> str:
    if len(value) <= _VARIABLE_VALUE_PREVIEW_LIMIT:
        return value
    return value[:_VARIABLE_VALUE_PREVIEW_LIMIT] + "…"


class _DataFrameModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame | None = None) -> None:
        super().__init__()
        self._df = df if df is not None else pd.DataFrame()

    def set_dataframe(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self._df = df
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._df)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._df.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        val = self._df.iat[index.row(), index.column()]
        if pd.isna(val):
            return ""
        return str(val)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._df.columns[section])
        return str(section + 1)


class _VariablesModel(QAbstractTableModel):
    _COLUMNS = ("Имя", "Значение", "Тип")

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[tuple[str, str, str]] = []

    def set_variables(self, variables: dict[str, Any]) -> None:
        self.beginResetModel()
        rows: list[tuple[str, str, str]] = []
        for name in sorted(variables, key=lambda x: x.lower()):
            val = variables[name]
            rows.append((name, _format_variable_value(val), _variable_type_name(val)))
        self._rows = rows
        self.endResetModel()

    def variable_at(self, row: int) -> tuple[str, str, str] | None:
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid():
            return None
        name, value, vtype = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 1:
                return _preview_variable_value(value)
            return (name, value, vtype)[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole and index.column() == 1 and value:
            return value
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._COLUMNS[section]
        return str(section + 1)


class DataPreviewDialog(QDialog):
    def __init__(self, parent=None, title: str = "Просмотр DataFrame") -> None:
        super().__init__(parent)
        apply_window_icon(self)
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(600, 400)
        self.resize(900, 520)

        self._ctx: RunContext | None = None
        self._preview_row_limit = 10
        self._current_df_name = ""
        self._showing_variables = False

        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Доступные DF:"))
        self.df_list = QListWidget()
        self.df_list.currentRowChanged.connect(self._on_df_selected)
        left_layout.addWidget(self.df_list)
        self.btn_variables = QPushButton("Переменные (@var)")
        self.btn_variables.setCheckable(True)
        self.btn_variables.clicked.connect(self._toggle_variables_view)
        left_layout.addWidget(self.btn_variables)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.df_info = QLabel("Нет данных.")
        self.df_info.setWordWrap(True)
        right_layout.addWidget(self.df_info)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Фильтр:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Подстрока в ячейке или имени переменной…")
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_edit, stretch=1)
        btn_clear_filter = QPushButton("Сбросить")
        btn_clear_filter.clicked.connect(self._clear_filter)
        filter_row.addWidget(btn_clear_filter)
        right_layout.addLayout(filter_row)

        self.rows_label = QLabel("Первые 10 строк:")
        right_layout.addWidget(self.rows_label)

        self.table = QTableView()
        self._source_model = _DataFrameModel()
        self._variables_model = _VariablesModel()
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._source_model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)
        self.table.setModel(self._proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_: self._update_row_count_label())
        self.table.selectionModel().currentChanged.connect(self._on_table_selection_changed)
        right_layout.addWidget(self.table)

        self.var_detail_container = QWidget()
        var_detail_layout = QVBoxLayout(self.var_detail_container)
        var_detail_layout.setContentsMargins(0, 6, 0, 0)
        var_detail_header = QHBoxLayout()
        self.var_detail_label = QLabel("Полное значение:")
        var_detail_header.addWidget(self.var_detail_label, stretch=1)
        self.btn_copy_var_value = QPushButton("Копировать")
        self.btn_copy_var_value.clicked.connect(self._copy_selected_variable_value)
        var_detail_header.addWidget(self.btn_copy_var_value)
        var_detail_layout.addLayout(var_detail_header)
        self.var_value_edit = QTextEdit()
        self.var_value_edit.setReadOnly(True)
        self.var_value_edit.setPlaceholderText("Выберите переменную в таблице…")
        self.var_value_edit.setMinimumHeight(100)
        self.var_value_edit.setMaximumHeight(220)
        var_detail_layout.addWidget(self.var_value_edit)
        self.var_detail_container.setVisible(False)
        right_layout.addWidget(self.var_detail_container)

        splitter.addWidget(right)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter)

    def set_context(self, ctx: RunContext, subtitle: str = "", *, max_rows: int = 10) -> None:
        self._ctx = ctx
        try:
            self._preview_row_limit = max(1, min(int(max_rows), 5000))
        except (TypeError, ValueError):
            self._preview_row_limit = 10
        if subtitle:
            self.setWindowTitle(f"Просмотр DataFrame — {subtitle}")

        self.df_list.clear()
        sorted_names = list_preview_df_names(ctx.df_store)
        self.df_list.addItems(sorted_names)
        self._variables_model.set_variables(user_variables_for_display(ctx.variables))
        if self._showing_variables:
            self._render_variables()
        elif sorted_names:
            self.df_list.setCurrentRow(0)
        else:
            self.df_info.setText("Нет доступных датафреймов.")
            self._current_df_name = ""
            self._clear_filter(silent=True)
            self._source_model.set_dataframe(pd.DataFrame())
            self._update_row_count_label()

    def _on_df_selected(self, row: int) -> None:
        if self._showing_variables:
            self.btn_variables.blockSignals(True)
            self.btn_variables.setChecked(False)
            self.btn_variables.blockSignals(False)
            self._showing_variables = False
            self._proxy.setSourceModel(self._source_model)
            self._hide_variable_detail()
        self._render_preview(row)

    def _toggle_variables_view(self, checked: bool) -> None:
        self._showing_variables = checked
        if checked:
            self.df_list.blockSignals(True)
            self.df_list.clearSelection()
            self.df_list.blockSignals(False)
            self._proxy.setSourceModel(self._variables_model)
            self._render_variables()
        else:
            self._proxy.setSourceModel(self._source_model)
            self._hide_variable_detail()
            row = self.df_list.currentRow()
            if row >= 0:
                self._render_preview(row)
            else:
                self._update_row_count_label()

    def _hide_variable_detail(self) -> None:
        self.var_detail_container.setVisible(False)
        self.var_value_edit.clear()
        self.var_detail_label.setText("Полное значение:")

    def _on_table_selection_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not self._showing_variables:
            return
        self.var_detail_container.setVisible(True)
        if not current.isValid():
            self.var_value_edit.clear()
            self.var_detail_label.setText("Полное значение:")
            return
        src_index = self._proxy.mapToSource(current)
        item = self._variables_model.variable_at(src_index.row())
        if item is None:
            return
        name, value, vtype = item
        self.var_detail_label.setText(f"@{name} ({vtype}, {len(value)} симв.)")
        self.var_value_edit.setPlainText(value)

    def _copy_selected_variable_value(self) -> None:
        text = self.var_value_edit.toPlainText()
        if text:
            QGuiApplication.clipboard().setText(text)

    def _render_variables(self) -> None:
        if not self._ctx:
            return
        variables = user_variables_for_display(self._ctx.variables)
        self._variables_model.set_variables(variables)
        count = len(variables)
        if count:
            names = ", ".join(sorted(variables, key=lambda x: x.lower()))
            self.df_info.setText(
                f"Переменные пайплайна (пользовательские): {count}\n"
                f"Имена: {names}\n"
                "Используются в YAML как @имя_переменной. Служебные Qt/tk-хуки скрыты."
            )
        else:
            self.df_info.setText(
                "Пользовательские переменные: 0\n"
                "Задаются шагами globals_settings, диалогами (assign), file_ops (result_var), "
                "run_command и др. Служебные переменные Qt не показываются."
            )
        self._clear_filter(silent=True)
        self._proxy.sort(-1, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()
        self.var_detail_container.setVisible(True)
        if self._proxy.rowCount() > 0:
            self.table.selectRow(0)
        else:
            self.var_value_edit.clear()
            self.var_detail_label.setText("Полное значение:")
        self._update_row_count_label()

    def _clear_filter(self, *, silent: bool = False) -> None:
        if not silent:
            self.filter_edit.blockSignals(True)
        self.filter_edit.clear()
        if not silent:
            self.filter_edit.blockSignals(False)
        self._proxy.setFilterFixedString("")
        self._update_row_count_label()

    def _apply_filter(self, text: str) -> None:
        self._proxy.setFilterFixedString(text.strip())
        self._update_row_count_label()

    def _update_row_count_label(self) -> None:
        source = self._variables_model if self._showing_variables else self._source_model
        total = source.rowCount()
        shown = self._proxy.rowCount()
        if self._showing_variables:
            parts = ["Переменные (@var)"]
        else:
            parts = [f"До {self._preview_row_limit} строк из DF"]
        if self.filter_edit.text().strip():
            parts.append(f"после фильтра: {shown} из {total}")
        else:
            parts.append(f"строк: {total}")
        parts.append("сортировка — клик по заголовку столбца")
        if self._showing_variables:
            parts.append("полный текст — выбор строки ниже")
        self.rows_label.setText(" | ".join(parts))

    def _render_preview(self, row: int) -> None:
        if not self._ctx or row < 0:
            return
        item = self.df_list.item(row)
        if item is None:
            return
        name = item.text()
        df = get_df_for_preview(self._ctx.df_store, name)
        if df is None:
            return

        self._current_df_name = name
        cols = [str(c) for c in df.columns]
        self.df_info.setText(
            f"DF: {name} | rows={len(df)} cols={len(cols)}\nColumns: {', '.join(cols)}"
        )

        self._clear_filter(silent=True)
        self._proxy.sort(-1, Qt.SortOrder.AscendingOrder)
        head = df.head(self._preview_row_limit)
        self._source_model.set_dataframe(head)
        self.table.resizeColumnsToContents()
        self._update_row_count_label()
