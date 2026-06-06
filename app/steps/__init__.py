from __future__ import annotations

from app.steps.cast_column_type import register_cast_column_type
from app.steps.concat_dfs import register_concat_dfs
from app.steps.df_assign import register_df_assign
from app.steps.drop_rows import register_drop_rows
from app.steps.file_ops import register_file_ops
from app.steps.filtration_rows import register_filtration_rows
from app.steps.transpose_df import register_transpose_df
from app.steps.groupby_aggregate import register_groupby_aggregate
from app.steps.group_template_export import register_group_template_export
from app.steps.globals_settings import register_globals_settings
from app.steps.load_excel import register_load_excel
from app.steps.merge_dfs import register_merge
from app.steps.query_df import register_query_df
from app.steps.rename_columns import register_rename_columns
from app.steps.save_excel import register_save_excel
from app.steps.sort_list_output import register_sort_list_output
from app.steps.text_transform import register_text_transform


def register_all_steps() -> None:
    register_globals_settings()
    register_load_excel()
    register_save_excel()
    register_cast_column_type()
    register_text_transform()
    register_filtration_rows()
    register_transpose_df()
    register_query_df()
    register_drop_rows()
    register_merge()
    register_concat_dfs()
    register_rename_columns()
    register_groupby_aggregate()
    register_group_template_export()
    register_sort_list_output()
    register_df_assign()
    register_file_ops()

