from __future__ import annotations

import unittest

import pandas as pd

from app.steps.group_template_export import _compute_aggregations
from app.steps.numeric_parse import coerce_to_float, normalize_value_for_excel
from app.steps.excel_template import resolve_cell_value


class NumericParseTests(unittest.TestCase):
    def test_coerce_comma_decimal(self) -> None:
        self.assertAlmostEqual(coerce_to_float("34,55"), 34.55)
        self.assertAlmostEqual(coerce_to_float("1 234,56"), 1234.56)
        self.assertAlmostEqual(coerce_to_float("1.234,56"), 1234.56)
        self.assertAlmostEqual(coerce_to_float("1,234.56"), 1234.56)

    def test_normalize_for_excel(self) -> None:
        self.assertEqual(normalize_value_for_excel("34,55"), 34.55)
        self.assertIsInstance(normalize_value_for_excel("34,55"), float)

    def test_aggregation_with_comma_strings(self) -> None:
        gdf = pd.DataFrame({"Qty": ["10,5", "20,25"], "Price": ["3,2", "4,8"]})
        specs = [
            {"name": "total_qty", "op": "sum", "column": "Qty"},
            {"name": "doubled", "op": "expr", "expression": "total_qty * 2"},
        ]
        res = _compute_aggregations(gdf, specs, {})
        self.assertAlmostEqual(res["total_qty"], 30.75)
        self.assertAlmostEqual(res["doubled"], 61.5)

    def test_resolve_agg_placeholder_as_number(self) -> None:
        val = resolve_cell_value(
            "{{agg.total_sum}}",
            group_values={},
            agg_values={"total_sum": 34.55},
            var_values={},
        )
        self.assertEqual(val, 34.55)
        self.assertIsInstance(val, float)

    def test_resolve_row_placeholder_as_number(self) -> None:
        val = resolve_cell_value(
            "{{row.Amount}}",
            group_values={},
            agg_values={},
            var_values={},
            row_values={"Amount": "12,34"},
        )
        self.assertAlmostEqual(val, 12.34)


if __name__ == "__main__":
    unittest.main()
