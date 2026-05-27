from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget

from app.settings import effective_pipelines_dir, load_settings
from app.ui_qt.builder_view import BuilderView
from app.ui_qt.font_utils import apply_font_to_application
from app.ui_qt.runner_view import RunnerView
from app.ui_qt.settings_view import SettingsView


class AppWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ExcelForge")
        self.resize(1200, 750)
        self.setMinimumSize(1000, 650)

        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        pipelines_dir = effective_pipelines_dir()

        self.runner = RunnerView(pipelines_dir=pipelines_dir)
        self.builder = BuilderView(pipelines_dir=pipelines_dir)
        self.settings = SettingsView(
            apply_font=self._apply_font,
            on_pipelines_dir=self._apply_pipelines_dir,
        )

        tabs.addTab(self.runner, "Runner (выполнение)")
        tabs.addTab(self.builder, "Builder (конструктор)")
        tabs.addTab(self.settings, "Общие настройки")

        self._apply_saved_font()

    def _apply_saved_font(self) -> None:
        s = load_settings()
        self._apply_font(str(s.font_family or ""), int(s.font_size or 10))

    def _apply_font(self, family: str, size: int) -> None:
        apply_font_to_application(family, size)

    def _apply_pipelines_dir(self, path: str) -> None:
        self.runner.set_pipelines_dir(path)
        self.builder.set_pipelines_dir(path)
