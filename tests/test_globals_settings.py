from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from app.pipeline.context import RunContext
from app.pipeline.schema import Step
from app.steps.globals_settings import (
    _parse_days_offset,
    _resolve_system_value,
    run_globals_settings,
)


class GlobalsSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = RunContext()
        self.frozen = datetime(2025, 5, 23, 14, 30, 45)

    def test_resolve_date_default_format(self) -> None:
        with patch("app.steps.globals_settings._now", return_value=self.frozen):
            self.assertEqual(_resolve_system_value({"type": "date"}), "2025-05-23")

    def test_resolve_date_with_offset_and_format(self) -> None:
        with patch("app.steps.globals_settings._now", return_value=self.frozen):
            val = _resolve_system_value(
                {"system": "date", "format": "%d.%m.%Y", "days_offset": -2},
            )
            self.assertEqual(val, "21.05.2025")

    def test_resolve_time(self) -> None:
        with patch("app.steps.globals_settings._now", return_value=self.frozen):
            self.assertEqual(_resolve_system_value({"type": "time"}), "14:30:45")
            self.assertEqual(
                _resolve_system_value({"type": "time", "format": "%H:%M"}),
                "14:30",
            )

    def test_resolve_datetime_with_offset(self) -> None:
        with patch("app.steps.globals_settings._now", return_value=self.frozen):
            val = _resolve_system_value(
                {"type": "datetime", "format": "%Y%m%d", "days_offset": 7},
            )
            self.assertEqual(val, "20250530")

    def test_parse_days_offset_aliases(self) -> None:
        self.assertEqual(_parse_days_offset({"offset": 3}), 3)
        self.assertEqual(_parse_days_offset({"offset_days": -1}), -1)

    def test_run_system_values_list(self) -> None:
        with patch("app.steps.globals_settings._now", return_value=self.frozen):
            step = Step(
                id="g1",
                type="globals_settings",
                params={
                    "system_values": [
                        {"var": "today", "type": "date", "format": "%d.%m.%Y"},
                        {"var": "yesterday", "type": "date", "days_offset": -1, "format": "%d.%m.%Y"},
                        {"var": "now_time", "type": "time", "format": "%H:%M"},
                    ],
                },
            )
            run_globals_settings(self.ctx, step)
        self.assertEqual(self.ctx.variables["today"], "23.05.2025")
        self.assertEqual(self.ctx.variables["yesterday"], "22.05.2025")
        self.assertEqual(self.ctx.variables["now_time"], "14:30")

    def test_run_values_inline_system(self) -> None:
        with patch("app.steps.globals_settings._now", return_value=self.frozen):
            step = Step(
                id="g1",
                type="globals_settings",
                params={
                    "values": {
                        "report_dt": {
                            "system": "datetime",
                            "format": "%Y-%m-%d %H:%M",
                            "days_offset": 1,
                        },
                        "plain": "hello",
                    },
                },
            )
            run_globals_settings(self.ctx, step)
        self.assertEqual(self.ctx.variables["report_dt"], "2025-05-24 14:30")
        self.assertEqual(self.ctx.variables["plain"], "hello")


if __name__ == "__main__":
    unittest.main()
