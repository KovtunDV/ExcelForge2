from __future__ import annotations

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.pipeline.context import RunContext
from app.pipeline.global_context import get_df_for_preview, list_preview_df_names
from app.ui_qt.app_icon import apply_window_icon


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

        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Доступные DF:"))
        self.df_list = QListWidget()
        self.df_list.currentRowChanged.connect(self._render_preview)
        left_layout.addWidget(self.df_list)
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
        self.filter_edit.setPlaceholderText("Подстрока в любой ячейке…")
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
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._source_model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)
        self.table.setModel(self._proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_: self._update_row_count_label())
        right_layout.addWidget(self.table)
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
        if sorted_names:
            self.df_list.setCurrentRow(0)
        else:
            self.df_info.setText("Нет доступных датафреймов.")
            self._current_df_name = ""
            self._clear_filter(silent=True)
            self._source_model.set_dataframe(pd.DataFrame())
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
        total = self._source_model.rowCount()
        shown = self._proxy.rowCount()
        parts = [f"До {self._preview_row_limit} строк из DF"]
        if self.filter_edit.text().strip():
            parts.append(f"после фильтра: {shown} из {total}")
        else:
            parts.append(f"строк: {total}")
        parts.append("сортировка — клик по заголовку столбца")
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
