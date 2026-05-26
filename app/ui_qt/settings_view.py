from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import preview_settings
from app.pipeline.global_context import (
    clear_global_store,
    global_df_summary,
    reconcile_globals_from_sessions,
)
from app.settings import AppSettings, load_settings, save_settings
from app.ui_qt.font_utils import list_font_families, make_app_font


class SettingsView(QWidget):
    def __init__(self, parent=None, *, apply_font: Callable[[str, int], None] | None = None) -> None:
        super().__init__(parent)
        self._apply_font = apply_font or (lambda _f, _s: None)
        self._s = load_settings()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        lf_preview = QGroupBox("Предпросмотр DataFrame")
        form_p = QFormLayout(lf_preview)
        self.spin_preview = QSpinBox()
        self.spin_preview.setRange(1, 5000)
        self.spin_preview.setValue(preview_settings.get_preview_rows())
        form_p.addRow("Строк предпросмотра:", self.spin_preview)
        root.addWidget(lf_preview)

        lf_font = QGroupBox("Шрифт интерфейса")
        form_f = QFormLayout(lf_font)
        self.cmb_font = QComboBox()
        self.cmb_font.setEditable(False)
        self.cmb_font.setMinimumWidth(280)
        self.cmb_font.addItem("(по умолчанию системы)", "")
        for fam in list_font_families():
            self.cmb_font.addItem(fam, fam)
        idx = self.cmb_font.findData(self._s.font_family or "")
        if idx >= 0:
            self.cmb_font.setCurrentIndex(idx)
        else:
            self.cmb_font.setCurrentIndex(0)
        form_f.addRow("Шрифт:", self.cmb_font)

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(6, 48)
        self.spin_font_size.setValue(int(self._s.font_size or 10))
        form_f.addRow("Размер:", self.spin_font_size)
        root.addWidget(lf_font)

        lf_global = QGroupBox("Глобальный контекст (glob_*)")
        global_layout = QVBoxLayout(lf_global)
        global_layout.addWidget(
            QLabel(
                "Датафреймы с именем glob_* сохраняются между запусками пайплайнов "
                "до закрытия программы или очистки вручную."
            )
        )
        self.global_info = QPlainTextEdit()
        self.global_info.setReadOnly(True)
        self.global_info.setMaximumHeight(120)
        global_layout.addWidget(self.global_info)
        global_btns = QHBoxLayout()
        btn_refresh_global = QPushButton("Обновить список")
        btn_refresh_global.clicked.connect(self._refresh_global_list)
        global_btns.addWidget(btn_refresh_global)
        btn_clear_global = QPushButton("Очистить глобальный контекст")
        btn_clear_global.clicked.connect(self._clear_global_context)
        global_btns.addWidget(btn_clear_global)
        global_btns.addStretch()
        global_layout.addLayout(global_btns)
        root.addWidget(lf_global)

        row_btn = QHBoxLayout()
        btn_apply = QPushButton("Применить")
        btn_apply.clicked.connect(self._apply)
        btn_save = QPushButton("Сохранить")
        btn_save.clicked.connect(self._save)
        btn_reset = QPushButton("Сбросить настройки")
        btn_reset.clicked.connect(self._reset)
        row_btn.addWidget(btn_apply)
        row_btn.addWidget(btn_save)
        row_btn.addWidget(btn_reset)
        row_btn.addStretch()
        root.addLayout(row_btn)

        sample = QGroupBox("Пример")
        sample_layout = QVBoxLayout(sample)
        self._sample_label = QLabel("Label: пример текста")
        self._sample_entry = QLineEdit()
        self._sample_entry.setPlaceholderText("Entry")
        self._sample_button = QPushButton("Кнопка")
        self._sample_check = QCheckBox("Checkbutton")
        self._sample_check.setChecked(True)
        self._sample_combo = QComboBox()
        self._sample_combo.addItems(["Option A", "Option B", "Option C"])
        self._sample_txt = QTextEdit()
        self._sample_txt.setPlainText("Пример многострочного текста.\nКод/логи/документация.")
        self._sample_txt.setMaximumHeight(80)
        for w in (
            self._sample_label,
            self._sample_entry,
            self._sample_button,
            self._sample_check,
            self._sample_combo,
            self._sample_txt,
        ):
            sample_layout.addWidget(w)
        root.addWidget(sample, stretch=1)

        self.cmb_font.currentIndexChanged.connect(self._refresh_sample_font)
        self.spin_font_size.valueChanged.connect(self._refresh_sample_font)
        self._refresh_sample_font()
        self._refresh_global_list()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self._refresh_global_list()

    def _refresh_global_list(self) -> None:
        reconcile_globals_from_sessions()
        rows = global_df_summary()
        if not rows:
            self.global_info.setPlainText("(нет глобальных датафреймов)")
            return
        lines = [f"{name} — rows={nrows}, cols={ncols}" for name, nrows, ncols in rows]
        self.global_info.setPlainText("\n".join(lines))

    def _clear_global_context(self) -> None:
        rows = global_df_summary()
        if not rows:
            QMessageBox.information(self, "ExcelForge", "Глобальный контекст уже пуст.")
            return
        btn = QMessageBox.question(
            self,
            "ExcelForge",
            f"Удалить {len(rows)} глобальных датафрейм(ов) из сессии?\n\n"
            "Пайплайны больше не смогут читать эти glob_* до повторного формирования.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if btn != QMessageBox.StandardButton.Yes:
            return
        n = clear_global_store()
        self._refresh_global_list()
        QMessageBox.information(
            self,
            "ExcelForge",
            f"Удалено глобальных DF: {n}.\n\n"
            "Копии glob_* убраны из активных контекстов выполнения; "
            "«Просмотр данных» больше не покажет очищенные таблицы.",
        )

    def _current_font_settings(self) -> tuple[str, int]:
        fam = str(self.cmb_font.currentData() or "").strip()
        size = max(6, min(int(self.spin_font_size.value()), 48))
        return fam, size

    def _refresh_sample_font(self) -> None:
        fam, size = self._current_font_settings()
        font = make_app_font(fam, size)
        for w in (
            self._sample_label,
            self._sample_entry,
            self._sample_button,
            self._sample_check,
            self._sample_combo,
            self._sample_txt,
        ):
            w.setFont(font)

    def _apply(self) -> None:
        fam, size = self._current_font_settings()
        self._refresh_sample_font()
        self._apply_font(fam, size)
        try:
            preview_settings.set_preview_rows(self.spin_preview.value())
        except Exception:
            preview_settings.set_preview_rows(10)
            self.spin_preview.setValue(preview_settings.get_preview_rows())

    def _save(self) -> None:
        self._apply()
        fam, size = self._current_font_settings()
        s = AppSettings(
            preview_rows=preview_settings.get_preview_rows(),
            font_family=fam,
            font_size=size,
        )
        save_settings(s)
        QMessageBox.information(self, "ExcelForge", "Настройки сохранены.")

    def _reset(self) -> None:
        self.spin_preview.setValue(10)
        self.cmb_font.setCurrentIndex(0)
        self.spin_font_size.setValue(10)
        self._save()
