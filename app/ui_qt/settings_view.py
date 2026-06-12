from __future__ import annotations

import os
from typing import Callable

from PySide6.QtWidgets import (
    QFileDialog,
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
from app.settings import (
    AppSettings,
    bundled_pipelines_dir,
    effective_pipelines_dir,
    load_settings,
    normalize_pipelines_dir,
    save_settings,
)
from app.ui_qt.font_utils import list_font_families, make_app_font
from app.version import __version__


class SettingsView(QWidget):
    def __init__(
        self,
        parent=None,
        *,
        apply_font: Callable[[str, int], None] | None = None,
        on_pipelines_dir: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._apply_font = apply_font or (lambda _f, _s: None)
        self._on_pipelines_dir = on_pipelines_dir or (lambda _p: None)
        self._s = load_settings()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        root.addWidget(QLabel(f"ExcelForge — версия {__version__}"))

        lf_pipelines = QGroupBox("Каталог пайплайнов")
        pipelines_layout = QVBoxLayout(lf_pipelines)
        pipelines_layout.addWidget(
            QLabel(
                "Папка с YAML-сценариями для Runner и Builder. "
                "Пустое поле — каталог pipelines в папке запуска программы."
            )
        )
        pipelines_row = QHBoxLayout()
        self.edit_pipelines_dir = QLineEdit()
        self.edit_pipelines_dir.setPlaceholderText(bundled_pipelines_dir())
        saved_dir = normalize_pipelines_dir(self._s.pipelines_dir)
        if saved_dir:
            self.edit_pipelines_dir.setText(saved_dir)
        pipelines_row.addWidget(self.edit_pipelines_dir, stretch=1)
        btn_browse_pipelines = QPushButton("Обзор…")
        btn_browse_pipelines.clicked.connect(self._pick_pipelines_dir)
        pipelines_row.addWidget(btn_browse_pipelines)
        btn_default_pipelines = QPushButton("По умолчанию")
        btn_default_pipelines.clicked.connect(self._reset_pipelines_dir_field)
        pipelines_row.addWidget(btn_default_pipelines)
        pipelines_layout.addLayout(pipelines_row)
        root.addWidget(lf_pipelines)

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

    def _pick_pipelines_dir(self) -> None:
        start = self.edit_pipelines_dir.text().strip() or effective_pipelines_dir()
        path = QFileDialog.getExistingDirectory(self, "Каталог пайплайнов", start)
        if path:
            self.edit_pipelines_dir.setText(os.path.abspath(path))

    def _reset_pipelines_dir_field(self) -> None:
        self.edit_pipelines_dir.clear()

    def _resolve_pipelines_dir_for_ui(self) -> tuple[str, str]:
        """(путь для Runner/Builder, значение для сохранения в settings.json)."""
        raw = self.edit_pipelines_dir.text().strip()
        if not raw:
            return bundled_pipelines_dir(), ""
        path = normalize_pipelines_dir(raw)
        return path, path

    def _apply_pipelines_dir(self) -> bool:
        path, _ = self._resolve_pipelines_dir_for_ui()
        if not os.path.isdir(path):
            btn = QMessageBox.question(
                self,
                "ExcelForge",
                f"Каталог не существует:\n{path}\n\nСоздать?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if btn != QMessageBox.StandardButton.Yes:
                return False
            try:
                os.makedirs(path, exist_ok=True)
            except OSError as e:
                QMessageBox.warning(self, "ExcelForge", f"Не удалось создать каталог:\n{e}")
                return False
        self._on_pipelines_dir(path)
        return True

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
        if not self._apply_pipelines_dir():
            return
        fam, size = self._current_font_settings()
        self._refresh_sample_font()
        self._apply_font(fam, size)
        try:
            preview_settings.set_preview_rows(self.spin_preview.value())
        except Exception:
            preview_settings.set_preview_rows(10)
            self.spin_preview.setValue(preview_settings.get_preview_rows())

    def _save(self) -> None:
        fam, size = self._current_font_settings()
        self._refresh_sample_font()
        self._apply_font(fam, size)
        try:
            preview_settings.set_preview_rows(self.spin_preview.value())
        except Exception:
            preview_settings.set_preview_rows(10)
            self.spin_preview.setValue(preview_settings.get_preview_rows())
        if not self._apply_pipelines_dir():
            return
        _, stored_pipelines = self._resolve_pipelines_dir_for_ui()
        s = AppSettings(
            preview_rows=preview_settings.get_preview_rows(),
            font_family=fam,
            font_size=size,
            pipelines_dir=stored_pipelines,
        )
        save_settings(s)
        self._s = s
        QMessageBox.information(self, "ExcelForge", "Настройки сохранены.")

    def _reset(self) -> None:
        self.spin_preview.setValue(10)
        self.cmb_font.setCurrentIndex(0)
        self.spin_font_size.setValue(10)
        self._reset_pipelines_dir_field()
        self._save()
