# Справочник шагов пайплайна ExcelForge

Файл в формате **Markdown**: каждый шаг описан в отдельном разделе с заголовком `## <тип_шага>`.  
Параметры шага задаются в YAML в поле `params` выбранного шага в **Builder** (вкладка «Builder (конструктор)»).

В Builder кнопка **«Документация по шагу»** открывает этот текст в отдельном окне (Markdown → HTML). Пользовательская документация: [docs/03_РУКОВОДСТВО_ПОЛЬЗОВАТЕЛЯ.md](../../docs/03_РУКОВОДСТВО_ПОЛЬЗОВАТЕЛЯ.md).

Общие правила:

- Имена датафреймов (`dataframe`, `source_df`, `target_df`, …) — строки; DF хранятся в контексте выполнения пайплайна.
- **Глобальный контекст (сессия приложения):** если имя DF начинается с префикса `glob_` (например `glob_raw`, `glob_lookup`), таблица сохраняется между запусками разных пайплайнов до закрытия ExcelForge или ручной очистки в «Общие настройки». При новом запуске пайплайна локальные имена (`df_main`, …) не переносятся, а `glob_*` подставляются автоматически. Запись в глобальный контекст выполняется только когда шаг сохраняет результат в имя с префиксом `glob_`.
- Пустая строка `""` в параметрах обычно означает «не задано» или значение по умолчанию шага.
- Числовые индексы строк/колонок в Excel в YAML задаются **с 1** (первая строка листа = `1`).

**Пример:** пайплайн A загружает данные в `glob_raw`; пайплайн B в отладке читает `glob_raw` как `source_df` без повторной загрузки Excel.

---

## load_excel

**Назначение:** загрузка одного или нескольких Excel-файлов в один `pandas.DataFrame` (конкатенация по строкам).

### Параметры (`params`)

| Параметр | Тип | Описание |
|----------|-----|----------|
| `input_mode` | строка | `file` — один файл (`file_path`); `mask` — все файлы по маске в `directory`; `latest` — **один** файл с максимальным **mtime** (время изменения) среди совпавших с маской. |
| `file_path` | строка | Полный путь к файлу при `input_mode: file`. |
| `directory` | строка | Каталог при `mask` / `latest`. |
| `pattern` | строка | Маска файлов, напр. `*.xlsx`. |
| `recursive` | bool | Искать файлы во вложенных папках (`mask` / `latest`). |
| `sheet` | строка или число | Имя листа или индекс листа (0 — первый). |
| `header_mode` | строка | `first_row` — первая строка данных = заголовки; `letters` — имена колонок `A,B,…`; `numbers` — `1,2,…`. |
| `start_row` | int | Первая строка **данных** на листе (1-based). Строки выше пропускаются как при `skiprows`. |
| `usecols` | строка | Диапазон колонок для `pandas` (например `A:Z`) или пусто = все. |
| `dataframe` | строка | Имя результирующего DF в контексте. |
| `dtype` | строка | По умолчанию `str` — все колонки как строки. |
| `include_service_columns` | `on` / `off` | Добавить служебные столбцы **`_from_file`** и **`_date_file`** в результат. |
| `from_file_mode` | строка | Что писать в `_from_file`: `basename` — только имя файла; `fullpath` — полный путь. |
| `date_file_mode` | строка | Что писать в `_date_file`: `modified` — дата изменения (mtime); `created` — дата создания (ctime; на Windows — creation time). |
| `file_open_dialog` | `on` / `off` | При выполнении шага показать диалог выбора **файла** (только при `input_mode: file`). Результат **перезаписывает** `file_path` из YAML. |
| `file_open_dialog_help` | строка | Заголовок окна диалога выбора файла (например: «Выбери файл загрузки»). |
| `filetypes` | Опционально: список пар для фильтра диалога, как в `globals_settings` — `[["Excel", "*.xlsx"], ["Все", "*.*"]]`. Если пусто — фильтр строится из **`pattern`** (та же маска, что для `input_mode: mask`). |
| `directory_open_dialog` | `on` / `off` | При выполнении показать диалог выбора **каталога** (при `input_mode: mask` или `latest`). Результат **перезаписывает** `directory`. |
| `directory_open_dialog_help` | строка | Заголовок диалога выбора каталога. |

Значения «включено» для флагов: `true`, `on`, `yes`, `1` (без учёта регистра).

Диалоги работают только при запуске из **GUI** (Builder / Runner): используются стандартные диалоги Qt (`QFileDialog`); в коде шагов имена хуков `tk_askopenfilename` / `tk_askdirectory` сохранены для совместимости.

### Поведение

- Режимы `mask` и `latest`: каталог сканируется **один раз** (при `recursive: true` — один `os.walk`; иначе `glob` в корне каталога) + один `os.stat` на каждый найденный файл; метаданные (mtime/ctime) в памяти. Для `latest` — только файл с максимальным **mtime**, без повторных обращений к диску.
- Несколько файлов: колонки всех частей должны совпасть по именам и порядку; иначе файл пропускается с записью в протокол.
- Итоговое число строк 0: предупреждение и запрос «продолжить / выйти» (в GUI).

### Пример

```yaml
type: load_excel
params:
  input_mode: file
  file_path: "C:/data/in.xlsx"
  sheet: "Sheet1"
  header_mode: first_row
  start_row: 1
  usecols: ""
  dataframe: df_main
  dtype: str
```

Пример со служебными столбцами **`_from_file`** и **`_date_file`**:

```yaml
type: load_excel
params:
  input_mode: mask
  directory: "C:/data/in"
  pattern: "*.xlsx"
  recursive: false
  sheet: "Sheet1"
  header_mode: first_row
  start_row: 1
  usecols: ""
  dataframe: df_main
  dtype: str
  include_service_columns: on
  from_file_mode: basename   # basename|fullpath
  date_file_mode: modified   # modified|created
```

---

## globals_settings

**Назначение:** задание глобальных переменных для всего пайплайна (внутренне — `ctx.variables`), которые можно использовать как подстановки в параметрах других шагов.

### Подстановка `@var`

Если в любом параметре шага указана строка вида **`@имя`** (без пробелов), то перед выполнением шага она заменяется на значение переменной `имя`, заданное ранее.  
Например, если шаг `globals_settings` задаёт `directory_n: "C:/target_catalog"`, то в `load_excel` можно написать `directory: "@directory_n"`.

Также поддерживается **встраивание** в строку: все вхождения вида `@имя` будут заменены на строковое представление значения переменной (если переменная задана). Например: `"C:/out/@directory_n/result.xlsx"`.

### Параметры (`params`)

| Параметр | Описание |
|----------|----------|
| `values` | Словарь `{ "@var": value }` или `{ "var": value }`. Значения могут быть строками, числами, списками и т.д. Также допускается **системное значение** — вложенный словарь `{ system: date \| time \| datetime, format: "...", days_offset: N }`. |
| `system_values` | Список системных переменных: `{ var, type, format?, days_offset? }`. `type`: `date`, `time`, `datetime`. `format` — шаблон `strftime` (Python). `days_offset` — смещение даты на ±N дней (для `date` и `datetime`). |
| `directory_open_dialog` | `on/off`: показать диалог выбора каталога и сохранить результат в переменную `directory_var`. |
| `directory_var` | Имя переменной для каталога (например `directory_n` или `@directory_n`). |
| `directory_open_dialog_help` | Заголовок диалога выбора каталога. |
| `directory_initial` | Начальный каталог (опционально). |
| `file_open_dialog` | `on/off`: показать диалог выбора файла и сохранить результат в `file_var`. |
| `file_var` | Имя переменной для файла (например `file_path` или `@file_path`). |
| `file_open_dialog_help` | Заголовок диалога выбора файла. |
| `filetypes` | `filetypes` для Tk (опционально). |

### Системные дата и время

Текущие дата/время берутся из системы (локальное время ОС). Формат задаётся через `format` в нотации **`strftime`** (как в Python).

| `type` / `system` | По умолчанию `format` | `days_offset` |
|-------------------|----------------------|---------------|
| `date` | `%Y-%m-%d` | да |
| `time` | `%H:%M:%S` | нет |
| `datetime` | `%Y-%m-%d %H:%M:%S` | да |

Примеры форматов: `%d.%m.%Y` → `23.05.2025`, `%Y%m%d` → `20250523`, `%H:%M` → `14:30`.

### Пример

```yaml
type: globals_settings
params:
  values:
    directory_n: "C:/target_catalog"
    value1: "глобальное_значение1"
  system_values:
    - var: report_date
      type: date
      format: "%d.%m.%Y"
      days_offset: -1          # вчера
    - var: report_time
      type: time
      format: "%H:%M"
    - var: stamp
      type: datetime
      format: "%Y%m%d_%H%M%S"
  directory_open_dialog: off
  file_open_dialog: off
```

Системное значение можно задать и внутри `values`:

```yaml
values:
  tomorrow:
    system: date
    format: "%Y-%m-%d"
    days_offset: 1
```

Использование в других шагах:

```yaml
type: load_excel
params:
  input_mode: mask
  directory: "@directory_n"
  pattern: "*.xlsx"
  dataframe: df_main
```

---

## save_excel

**Назначение:** выгрузка выбранного DF в файл(ы) Excel.

### Параметры (`params`)

| Параметр | Описание |
|----------|----------|
| `export_mode` | **`single`** (по умолчанию) — один DF из `source_df`; **`mask_sheets`** — несколько DF в **один** файл, **каждый на свой лист** (без шаблона). Синонимы: `by_mask`, `multi_df`. |
| `source_df` | Имя DF для выгрузки (режим **`single`**). |
| `dataframes` | Список имён DF (режим **`mask_sheets`**): порядок листов в файле. Может быть пустым, если задан только `name_glob`. |
| `name_glob` | Маска имён (`fnmatch`, как в `concat_dfs`): `sheet_*`, `part_*`. Если `dataframes` пуст — все DF из контекста, совпавшие с маской; если оба заданы — фильтр списка `dataframes`. |
| `out_dir` | Каталог сохранения. |
| `filename` | Имя файла при записи **одного** файла (без split). |
| `file_open_dialog` | `on` / `off` | При выполнении — диалог **«Сохранить как»**: полный путь к файлу задаёт `out_dir` (каталог) и `filename` (имя файла), **переопределяя** значения из YAML. Если задан `split_by_column`, обновляется только `out_dir` (имена файлов по группам — по `split_filename_mask`). |
| `file_open_dialog_help` | строка | Заголовок диалога сохранения файла. |
| `directory_open_dialog` | `on` / `off` | Диалог выбора **каталога**; перезаписывает только `out_dir`. Имеет смысл, если `file_open_dialog` выключен. |
| `directory_open_dialog_help` | строка | Заголовок диалога каталога. |
| `columns` | Список имён колонок для выгрузки; `[]` — все колонки. |
| `sheet_name` | Имя листа (режим **`single`** / шаблон). В **`mask_sheets`** не используется — лист называется **как имя DF** (санитизация под Excel: до 31 символа, без `[]:*?/\\`). |
| `start_row`, `start_col` | Левый верх ячейки области записи (**1-based**): для шаблона и для простой записи без шаблона. |
| `template_path` | Путь к шаблону `.xlsx`; пусто — новый файл через `pandas.ExcelWriter`. |
| `writer_mode` | Только при **пустом** `template_path` (при шаблоне не используется). Режим `pandas.ExcelWriter(..., mode=...)`: **`w`** (по умолчанию) — как раньше: файл перезаписывается целиком; **`a`** — дописать в **существующий** `.xlsx` (аналог `mode='a'`). Если файла ещё нет, при `a` выполняется первая запись как **`w`** (создание файла). |
| `if_sheet_exists` | Только при **пустом** `template_path`, **`writer_mode: a`** и уже существующем файле. Поведение `ExcelWriter(..., if_sheet_exists=...)` (openpyxl), см. таблицу ниже. По умолчанию **`replace`**. При **`writer_mode: w`** параметр не используется. |
| `template_write_mode` | Режим записи при `template_path`: `overwrite` — создать/перезаписать `out_dir/filename` как **копию шаблона** и записать данные; `update` — открыть **существующий** файл `out_dir/filename` и дописать данные. |
| `template_column_map` | Словарь `{ "колонка_DF": номер_колонки_Excel }` — запись в **абсолютные** номера колонок листа (1=A, 2=B, …). Если пусто — блок данных подряд с `start_col`. |
| `split_by_column` | Непустое имя колонки — разбить выгрузку на несколько файлов по уникальным значениям. |
| `split_filename_mask` | Шаблон имени файла; подстановка `{group}` из значения группирующей колонки. |

Если одновременно включены `file_open_dialog` и `directory_open_dialog`, при выполнении вызывается **только** диалог сохранения файла (он задаёт и каталог, и имя).

### Запись без шаблона: `writer_mode` и `if_sheet_exists`

Поведение как в pandas:

| `if_sheet_exists` | Действие (при `writer_mode: a`, файл уже есть) |
|-------------------|-----------------------------------------------|
| `replace` | Заменить лист с тем же `sheet_name` новым содержимым DF. |
| `overlay` | Наложить данные поверх существующих ячеек (с учётом `start_row` / `start_col`). |
| `error` | Ошибка, если лист с таким именем уже есть. |
| `new` | Создать лист с автоматическим суффиксом (как в pandas). |

### Режим `mask_sheets` (несколько DF → один файл, лист = имя DF)

Только **без шаблона** (`template_path` пустой). Один файл `out_dir/filename`, внутри — по листу на каждый DF из маски. Параметры **`writer_mode`** / **`if_sheet_exists`** работают так же, как для простой записи (для `a` — поведение на **каждый** лист при записи в существующую книгу).

```yaml
type: save_excel
params:
  export_mode: mask_sheets
  out_dir: "C:/out"
  filename: "all_sheets.xlsx"
  template_path: ""
  name_glob: "df_*"
  dataframes: []
  writer_mode: w
  columns: []
  start_row: 1
  start_col: 1
```

Список «активных» таблиц + маска (порядок как в `dataframes`):

```yaml
type: save_excel
params:
  export_mode: mask_sheets
  out_dir: "C:/out"
  filename: "report.xlsx"
  template_path: ""
  dataframes:
    - df_main
    - df_lookup
    - df_summary
  name_glob: "df_*"
  writer_mode: a
  if_sheet_exists: replace
```

### Пример (простая выгрузка)

```yaml
type: save_excel
params:
  export_mode: single
  source_df: df_main
  out_dir: "C:/out"
  filename: "result.xlsx"
  columns: []
  template_path: ""
  writer_mode: w
  if_sheet_exists: replace
  sheet_name: "Sheet1"
  start_row: 1
  start_col: 1
  split_by_column: ""
  split_filename_mask: "{group}.xlsx"
```

### Пример (новый лист / замена листа в существующей книге, без шаблона)

Эквивалент идеи:

```python
with pd.ExcelWriter("file.xlsx", mode="a", engine="openpyxl", if_sheet_exists="replace") as writer:
    df.to_excel(writer, sheet_name="НовыйЛист", index=False)
```

```yaml
type: save_excel
params:
  source_df: df_main
  out_dir: "C:/out"
  filename: "file.xlsx"
  template_path: ""
  writer_mode: a
  if_sheet_exists: replace
  sheet_name: НовыйЛист
  start_row: 1
  start_col: 1
  columns: []
```

### Пример (шаблон, режим `update` — дописать в существующий файл)

Режим **`template_write_mode: update`** открывает файл **`out_dir/filename`** и пишет данные в него.  
Файл **должен существовать** (обычно его создают один раз в режиме `overwrite` или вручную кладут в каталог).

```yaml
type: save_excel
params:
  source_df: df_main
  out_dir: "C:/out"
  filename: "result.xlsx"              # файл должен уже существовать
  template_path: "C:/templates/tpl.xlsx"
  template_write_mode: update          # открыть out_dir/filename и дописать
  sheet_name: "Sheet1"
  start_row: 50                        # куда дописать
  start_col: 1
  columns: []                          # все колонки
  split_by_column: ""
  split_filename_mask: "{group}.xlsx"
```

---

## group_template_export

**Назначение:** групповой вывод DataFrame в **отдельные Excel-файлы по шаблону**. Для каждой группы по столбцу(ам) `group_by` создаётся копия шаблона с подстановкой значений группы, строк таблицы (с **вставкой строк** при нескольких позициях), агрегатов и глобальных переменных `@var`.

**Однострочный режим формы:** если не заданы `table_start_row` и `table_columns` (или `single_row_mode: true`), шаблон заполняется для **каждой строки** DF отдельным файлом. Плейсхолдеры `{{row.ИмяКолонки}}` подставляются в **любых ячейках** листа (как `{{group.*}}`). К имени файла по умолчанию добавляется номер `{inc}` в **начале** (`filename_inc: prefix`); можно указать `suffix` или отключить (`false`).

Отличие от `save_excel` + `split_by_column`: поддержка плейсхолдеров в ячейках, динамическая таблица, именованные агрегаты с выражениями.

### Плейсхолдеры в шаблоне

| Маркер | Источник |
|--------|----------|
| `{{group.ИмяКолонки}}` | Значение столбца группировки |
| `{{row.ИмяКолонки}}` | Значение в строке таблицы |
| `{{agg.имя}}` | Результат из `aggregations` |
| `{{@var}}` | Глобальная переменная из `globals_settings` |
| `{{inc}}` / `{{inc:1}}` | Порядковый номер строки (в таблице — в строке таблицы; в однострочном режиме — по строке DF) |

### Режимы работы

| Режим | Условие | Результат |
|-------|---------|-----------|
| **Таблица** | Заданы `table_start_row` и/или `table_columns` | Один файл на группу; строки вставляются в таблицу шаблона |
| **Форма (одна строка)** | Пустые `table_start_row` и `table_columns`, либо `single_row_mode: true` | Один файл на **каждую строку**; `{{row.*}}` по всему листу |

### Параметры (`params`)

| Параметр | Описание |
|----------|----------|
| `source_df` | Исходный DataFrame. |
| `group_by` | Строка или список столбцов группировки. |
| `group_separator` | Разделитель частей имени группы в имени файла (несколько `group_by`). |
| `out_dir` | Каталог для выходных файлов. |
| `template_path` | Путь к `.xlsx` шаблону. |
| `filename` | Словарь `{prefix, suffix, extension, group_separator}` или строка-маска с `{group}`. |
| `filename_mask` | Альтернатива: `"Report_{group}.xlsx"`. |
| `prefix`, `suffix`, `extension` | Можно задать на верхнем уровне `params`. |
| `sheet_name` | Лист шаблона; пусто — активный. |
| `table_start_row` | Первая строка **вывода** данных (1-based). Пусто — однострочный режим формы. |
| `table_template_row` | Строка-**образец** в шаблоне: откуда копируются шрифт, границы, заливка, `number_format` и высота строки на каждую строку группы. Может совпадать с `table_start_row` или быть отдельной (например скрытая строка-макет выше таблицы). |
| `table_columns` | Список `{df_col, excel_col}` — запись колонок DF в номера колонок Excel. Пусто — однострочный режим формы. |
| `single_row_mode` | `true` — принудительно однострочный режим (даже если заданы параметры таблицы). |
| `filename_inc` | В однострочном режиме: размещение номера строки в имени файла. `prefix` (по умолчанию) — `{inc}_` в начале; `suffix` — `_{inc}` в конце (перед расширением); `false` — не добавлять. Словарь `{enabled, position}` с `position`: `prefix` \| `suffix`. В маске `filename_mask` доступен `{inc}`. |
| `static_fields` | Список `{cell: "B2", value: "..."}` с плейсхолдерами. |
| `aggregations` | Список `{name, op, column?, expression?, format?}`; `op`: `sum`, `count`, `min`, `max`, `avg`, `expr`. Числа в колонках распознаются и с точкой (`34.55`), и с запятой (`34,55`). |
| `row_increment` | `{enabled, excel_col, start}` — номер п/п в колонку (или маркер `{{inc}}`). |
| `row_filter` | Выражение фильтрации (как в `filtration`) перед группировкой. |
| `sort_within_group` | `{column, ascending}` — сортировка строк внутри группы. |
| `skip_empty_groups` | `true` — не создавать файл для пустых групп. |
| `directory_open_dialog` | Диалог выбора `out_dir` (GUI). |
| `template_open_dialog` | Диалог выбора `template_path` (GUI). |

### Пример

```yaml
type: group_template_export
params:
  source_df: df_lines
  group_by: "Отдел"
  out_dir: "@output_dir"
  template_path: "C:/templates/act.xlsx"
  filename:
    prefix: "Акт_"
    suffix: "_@period"
  sheet_name: "Sheet1"
  table_start_row: 9
  table_columns:
    - { df_col: "Товар", excel_col: 2 }
    - { df_col: "Количество", excel_col: 3 }
  row_increment:
    enabled: true
    excel_col: 1
    start: 1
  aggregations:
    - { name: total_qty, op: sum, column: "Количество" }
    - { name: total_sum, op: expr, expression: "total_qty * 50" }
    - { name: lines_count, op: count }
```

### Пример (однострочный режим формы)

```yaml
type: group_template_export
params:
  source_df: df_lines
  group_by: "Отдел"
  out_dir: "@output_dir"
  template_path: "C:/templates/form.xlsx"
  filename:
    prefix: "Акт_"
  filename_inc: prefix   # 1_Акт_Sales.xlsx; suffix → Акт_Sales_1.xlsx; false — без номера
  # table_start_row и table_columns не заданы — режим формы
  aggregations:
    - { name: qty, op: sum, column: "Количество" }
```

Демо-пайплайн: `pipelines/Демо групповой вывод по шаблону.yaml`, шаблон: `pipelines/Demo_data/Templates/group_export_template.xlsx`.

---

## cast_column_type

**Назначение:** приведение одной или нескольких колонок к типу `datetime`, `int`, `decimal` или `str`.

### Параметры

| Параметр | Описание |
|----------|----------|
| `source_df` | DF. |
| `column` | Имя колонки (обратная совместимость, если `columns` не задан). |
| `columns` | Список колонок (или строка `"A,B,C"`). Если задан непустым — используется он вместо `column`. |
| `target_type` | `datetime` \| `int` \| `decimal` \| `str`. |
| `errors_to_zero` | Для чисел: `true` — нечисловые и пустые заменить на 0. |
| `use_decimal_objects` | Только для `decimal`: писать объекты `Decimal` в ячейки (обычно `false`). |

Колонка изменяется **на месте** в указанном DF.

---

## text_transform

**Назначение:** текстовые операции над одной колонкой (на месте в `source_df`).

### Параметры

| Параметр | Описание |
|----------|----------|
| `source_df`, `column` | Цель. |
| `trim` | Обрезка пробелов по краям. |
| `upper` / `lower` | Регистр (не оба сразу осмысленно). |
| `replace_map` | Словарь `{ "что": "на_что" }` или список `{from, to}` для замены подстрок/значений. |

---

## transpose_df

**Назначение:** транспонирование таблицы (`pandas.DataFrame.transpose`), строки и столбцы меняются местами. Результат записывается в **`target_df`** (если не указан — в **`source_df`**, перезапись по имени в хранилище).

| Параметр | Описание |
|----------|----------|
| `source_df` | Исходный датафрейм. |
| `target_df` | Куда положить результат (по умолчанию то же имя, что `source_df`). |
| `copy` | Явное копирование данных при транспонировании. По умолчанию **`true`** — вызов `transpose(copy=True)`. При **`false`** передаётся `transpose(copy=False)` (поведение pandas: по возможности без лишнего копирования). |

Индекс и имена столбцов после операции соответствуют правилам pandas: бывшие имена столбцов становятся индексом новой таблицы (и наоборот), типы столбцов могут стать `object`, если исходные типы различались.

### Пример

```yaml
type: transpose_df
params:
  source_df: df_main
  target_df: df_transposed
  copy: true
```

---

## filtration

**Назначение:** отбор строк по условию; результат в `target_df` (может совпадать с `source_df` — перезапись).

Это «визуальный» шаг с тем же форматом `expression`, что используется в `drop_rows` (`mode: by_filter`).

Поддерживаются строковые сравнения в `cmp`: `contains`, `startswith`, `endswith` (реализованы через `Series.astype("string").str...`).

### Выражение `expression`

- `op`: `and` или `or`.
- `items`: список условий `{ col, cmp, value }`.

**Операторы `cmp`:** `==`, `!=`, `>`, `>=`, `<`, `<=`, `contains`, `startswith`, `endswith`, `in`, `not_in`, `is_na`, `not_na`, `str_len`, а также сокращения `len_eq` … `len_le`.

- Для `in` / `not_in` в `value` — строка `"a,b,c"` или YAML-массив значений.
- Для `is_na` / `not_na` поле `value` не используется.

### Длина текста в ячейке (`str_len` и `len_*`)

Идея одна и та же: берётся длина **строкового** представления значения ячейки; `NaN` / пропуск pandas обрабатываются как пустая строка (**длина 0**). Дальше эта длина сравнивается с целым числом **n**.

**Рекомендуемый вариант — `str_len`:** в `value` передаётся словарь с полем **`op`** (вид сравнения) и **`n`** (целое):

| `op` (можно писать и коротко) | Смысл |
|-------------------------------|--------|
| `==` или `eq` | длина **равна** n |
| `!=` или `ne` | длина **не равна** n |
| `>` или `gt` | длина **строго больше** n |
| `>=` или `ge` | длина **больше или равна** n |
| `<` или `lt` | длина **строго меньше** n |
| `<=` или `le` | длина **меньше или равна** n |

Пример: строки, у которых в колонке `Текст` не короче 3 символов:

```yaml
- { col: "Текст", cmp: "str_len", value: { op: ">=", n: 3 } }
```

**Сокращения `len_*`** — то же самое, только вид сравнения зашит в имя оператора, а в `value` указывается **одно число** n (без словаря):

| `cmp` | Эквивалент `str_len` |
|-------|----------------------|
| `len_eq` | `{ op: "==", n: … }` |
| `len_ne` | `{ op: "!=", n: … }` |
| `len_gt` | `{ op: ">", n: … }` |
| `len_ge` | `{ op: ">=", n: … }` |
| `len_lt` | `{ op: "<", n: … }` |
| `len_le` | `{ op: "<=", n: … }` |

### Пример

```yaml
type: filtration
params:
  source_df: df_main
  target_df: df_filtered
  expression:
    op: and
    items:
      - { col: "Status", cmp: "==", value: "OK" }
      - { col: "City", cmp: "contains", value: "Екб" }
```

**Совместимость:** старый `type: filter` работает так же, как `type: filtration`.

---

## query

**Назначение:** отбор строк через **`pandas.DataFrame.query()`**: текстовое условие в параметре **`query`** (как первый аргумент метода `df.query(...)`). Результат записывается в **`target_df`** (может совпадать с **`source_df`** — перезапись). Индекс строк сохраняется так же, как возвращает pandas после `query`.

### Режим обращения к столбцам — `column_reference`

| Значение | Смысл |
|----------|--------|
| `names` | Условие пишется по **именам** столбцов (`Qty > 0`, имя с пробелами — в обратных кавычках pandas: `` `Имя колонки` == 'x' ``). |
| `positions` | Перед запросом столбцы временно переименованы в **`col_1`**, **`col_2`**, … (**номер с 1**, слева направо, как порядок колонок в DF). В строке **`query`** используйте только эти имена; после выполнения имена восстанавливаются. |

Допустимые синонимы для режима имён: `name`, `columns`; для режима позиций: `position`, `indices`, `index`.

Условие задаётся синтаксисом **`pandas.eval`** / **`query`** (операторы сравнения, `and` / `or`, скобки и т.д.). При ошибке в тексте запроса шаг завершится с сообщением об ошибке.

**Строковые фильтры** (`str.contains`, `startswith`, `endswith`, regex) в самом тексте `query` выразить надёжно нельзя, поэтому они задаются отдельным списком **`string_filters`**. Для каждого условия строится булева маска по столбцу, маски передаются в `DataFrame.query(..., local_dict=…, engine='python')` через префикс **`@`** (например `@__sf_all` — все условия из списка объединены по **AND**).

### Параметры (`params`)

| Параметр | Описание |
|----------|----------|
| `source_df` | DF, к которому применяется запрос. |
| `target_df` | DF для записи результата (отфильтрованные строки). |
| `query` | Строка условия для `DataFrame.query`. Можно **не указывать** (или оставить пустой), если задан только **`string_filters`** — тогда выполняется `@__sf_all`. |
| `column_reference` | `names` или `positions` (см. таблицу выше); влияет только на текст **`query`**, не на имена столбцов в **`string_filters`**. |
| `string_filters` | Список условий по строкам (см. ниже). Опционально. |
| `query_variables` | Словарь переменных для `query`, доступных через `@name`. Удобно для `isin`/`~isin` по спискам. |

### Строковые фильтры — элементы `string_filters`

Каждый элемент — словарь:

| Поле | Описание |
|------|----------|
| `column` | Столбец: **имя** в `source_df` или **целое число** — позиция столбца **с 1** (первая колонка = `1`). |
| `mode` | `contains` (подстрока, без regex), `regex`, `startswith`, `endswith`. По умолчанию `contains`. |
| `pattern` | Строка поиска; для `regex` — шаблон **regex**. |
| `case_insensitive` | `true` — без учёта регистра (для regex добавляется `re.IGNORECASE`). По умолчанию `false`. |
| `na` | Передаётся в pandas как **`na`** у `.str.contains` / `startswith` / `endswith`: считать ли отсутствие значения совпадением. По умолчанию `false`. |

Несколько элементов списка объединяются по **AND** в переменную **`@__sf_all`**. Отдельные маски доступны как **`@__sf0`**, **`@__sf1`**, … по порядку в списке.

Если **`query` непустой** и в нём **нет** подстроки **`__sf`**, к условию автоматически добавляется **`& (@__sf_all)`**. Если нужно своё объединение масок (**OR** и т.д.), напишите выражение явно с **`@__sf0`**, **`@__sf1`** и т.д. (или **`@__sf_all`**) — автодобавление не выполняется.

### Пример (по именам столбцов)

```yaml
type: query
params:
  source_df: df_main
  target_df: df_filtered
  column_reference: names
  query: "Status == 'OK' and Qty > 0"
```

### Пример (`isin` через переменную)

```yaml
type: query
params:
  source_df: df_main
  target_df: df_filtered
  query_variables:
    values: ["A", "C", "E"]
  query: "category.isin(@values)"
```

Исключить значения (аналог `~isin`):

```yaml
type: query
params:
  source_df: df_main
  target_df: df_filtered
  query_variables:
    values: ["A", "C", "E"]
  query: "~category.isin(@values)"
```

### Пример (подстрока «Екб» в названии города + условие в query)

Подстрока в режиме **`contains`** должна **буквально** входить в текст ячейки (например, значение «Екатеринбург» **не** содержит последовательность символов «Екб»). Для сложных правил используйте **`mode: regex`**.

```yaml
type: query
params:
  source_df: df_main
  target_df: df_filtered
  column_reference: names
  query: "Qty > 0"
  string_filters:
    - column: Город
      mode: contains
      pattern: "Екб"
      case_insensitive: true
```

Только строковые условия (эквивалент `@__sf_all`):

```yaml
type: query
params:
  source_df: df_main
  target_df: df_filtered
  query: ""
  string_filters:
    - column: Город
      mode: contains
      pattern: "Екб"
      case_insensitive: true
```

### Пример (regex по столбцу)

```yaml
type: query
params:
  source_df: df_main
  target_df: df_filtered
  string_filters:
    - column: Код
      mode: regex
      pattern: "^[A-Z]{2}\\d+$"
```

### Пример (по индексу столбца, 1 — первая колонка)

```yaml
type: query
params:
  source_df: df_main
  target_df: df_filtered
  column_reference: positions
  query: "col_1 > 0 and col_3 == 'x'"
```

---

## drop_rows

**Назначение:** удаление строк из DF.

### Параметр `mode`

| Значение | Смысл |
|----------|--------|
| `empty` | `dropna`; при непустом `subset_columns` — только по этим колонкам. |
| `duplicates` | `drop_duplicates`; `subset_columns` — по каким колонкам считать дубль; `keep`: `first` / `last` / `false`. |
| `by_filter` | Удалить строки, **удовлетворяющие** `expression` (тот же формат `op` / `items` / `cmp`, что раньше у шага `filter`). |
| `by_list` | Удалить строки, где `column` входит в список `values`. |

`target_df` по умолчанию = `source_df` (перезапись).

### Сложный фильтр для `mode: by_filter` (строкой `query`)

Помимо `expression`, для `by_filter` можно задать строку **`query`** (вычисляется через `pandas.DataFrame.eval(..., engine='python')`).  
Поддерживаются выражения вида `Остаток.isna() & (Контроль == 0)`. Для удобства допускается запись `and/or/not` (они будут преобразованы в `&/|/~`) и алиас `isnan()` (как `isna()`).

Пример: удалить строки, где `Остаток` пустой (NaN/Null) **и** `Контроль == 0`:

```yaml
type: drop_rows
params:
  source_df: df_main
  target_df: df_main
  mode: by_filter
  query: "Остаток.isna() and Контроль == 0"
```

### Пример (mode: by_filter, удаление строк с NaN/Null)

В `by_filter` удаляются строки, которые **удовлетворяют** `expression`. Поэтому, чтобы убрать пропуски в колонке, используйте `cmp: is_na`.

```yaml
type: drop_rows
params:
  source_df: df_main
  target_df: df_main
  mode: by_filter
  expression:
    op: and
    items:
      - { col: "Цена", cmp: "is_na" }
```

### Пример (оставить только строки с NaN/Null в колонке)

`drop_rows` удаляет совпавшие строки, поэтому чтобы **оставить только NaN**, удаляем все **не-NaN**:

```yaml
type: drop_rows
params:
  source_df: df_main
  target_df: df_only_nulls
  mode: by_filter
  expression:
    op: and
    items:
      - { col: "Цена", cmp: "not_na" }
```

---

## merge

**Назначение:** объединение двух DF (`pandas.merge`).

### Параметры

| Параметр | Описание |
|----------|----------|
| `left_df`, `right_df` | Имена DF. |
| `how` | `inner`, `left`, `right`, `outer`, `cross`. |
| `on` | Список общих колонок-ключей (или пусто, если заданы `left_on` / `right_on`). |
| `left_on`, `right_on` | Списки колонок для разных имён ключей. |
| `indicator` | Добавить колонку `_merge`. |
| `suffixes` | Суффиксы при конфликте имён, напр. `["_x", "_y"]` или строка `"_x,_y"`. |
| `result_df` | Имя результата. |

---

## concat_dfs

**Назначение:** склейка нескольких датафреймов через **`pandas.concat`**: по строкам (**`axis: 0`**) или по столбцам (**`axis: 1`**). Результат записывается в **`target_df`**.

### Источники DF

- **`dataframes`** — список имён DF **в нужном порядке** склейки. Каждое имя должно быть в контексте.
- **`name_glob`** — маска имён в стиле **shell** (`fnmatch`): например `sheet_*`, `part_??`. Если **`dataframes` пуст**, в склейку попадают **все** DF из контекста, чьи имена совпали с маской, **в порядке сортировки имён** (без учёта регистра).
- Если заданы **и** список **`dataframes`**, **и** **`name_glob`**, используются **только те имена из списка**, которые **совпали с маской** (порядок как в **`dataframes`**). Так можно отфильтровать «активные» таблицы без лишних ключей.

Нужно указать либо непустой **`dataframes`**, либо непустой **`name_glob`** (или оба вместе для фильтрации списка).

### Параметры (`params`)

| Параметр | Описание |
|----------|----------|
| `target_df` | Имя результирующего DF. |
| `dataframes` | Список имён DF по порядку (может быть пустым, если задан только `name_glob`). |
| `name_glob` | Маска имён (`*`, `?`, `[seq]`); опционально фильтрует список `dataframes`. |
| `axis` | `0`, `rows`, `index` — склейка **по строкам**; `1`, `columns`, `cols` — **по столбцам**. |
| `ignore_index` | `true` (по умолчанию) — после `concat` строится новый индекс `0..n-1` по оси склейки; `false` — сохраняются исходные метки индекса. |
| `join` | `outer` (по умолчанию) или `inner` — как выравнивать несовпадающие метки по **несклеиваемой** оси (см. документацию pandas `concat`). |

### Пример (список по строкам)

```yaml
type: concat_dfs
params:
  target_df: df_all
  dataframes:
    - df_jan
    - df_feb
  axis: 0
  ignore_index: true
  join: outer
```

### Пример (только маска имён)

```yaml
type: concat_dfs
params:
  target_df: df_merged_parts
  name_glob: "part_*"
  axis: 0
  ignore_index: true
```

### Пример (склейка по столбцам)

```yaml
type: concat_dfs
params:
  target_df: df_wide
  dataframes:
    - df_keys
    - df_attrs
  axis: 1
  ignore_index: false
  join: outer
```

---

## rename_columns

**Назначение:** переименование колонок.

### Параметр `mapping`

- Словарь `{ "старое_имя": "новое_имя" }`, или
- Список `{ from: "...", to: "..." }`.

`target_df` по умолчанию = `source_df` (иначе — копия под новым именем).

Если после `load_excel` с `header_mode: first_row` в файле **числовые** заголовки (`1`, `2`, `3`), в DataFrame они приводятся к строкам `"1"`, `"2"`, …; в `mapping` указывайте то же имя (`"1": test` или `from: 1`). При несовпадении шаг завершится с перечислением доступных столбцов.

---

## groupby_aggregate

**Назначение:** группировка и агрегаты (`groupby` + `agg`).

### Параметры

| Параметр | Описание |
|----------|----------|
| `source_df` | Входной DF. |
| `target_df` | Выходной DF. |
| `group_keys` | Список колонок группировки (или строка через запятую). |
| `aggregations` | Классический режим: словарь `{ "колонка": "sum" }` или `{ "колонка": ["sum", "mean"] }`. |
| `named_aggregations` | Именованный режим pandas: как `df.groupby(...).agg(имя=(колонка, функция), ...)`. См. ниже. |

Задайте **либо** `aggregations`, **либо** `named_aggregations` (не оба сразу). Пустой `named_aggregations: {}` или отсутствие ключа означает использование `aggregations`.

Имена колонок в `group_keys` и в источниках агрегаций должны **существовать** в `source_df`. В классическом режиме имена результирующих колонок могут стать составными (через `__`). В именованном режиме имена столбцов результата — это ключи из `named_aggregations` плюс колонки группировки.

### Именованная агрегация (`named_aggregations`)

Эквивалент вызова:

`grouped.agg(количество_записей=('серийный_номер', 'size'), последняя_дата=('дата', 'max'))` с последующим `reset_index()`.

**Вариант 1 — словарь:** ключ — имя **новой** колонки; значение — либо список из двух элементов `[колонка, функция]`, либо словарь `{ column: ..., func: ... }` (допускаются также ключи `col`, `source` и `agg`, `aggregation`).

**Вариант 2 — список словарей:** у каждого элемента поля `name` / `output` / `as` (имя результата), `column` / `col` (источник), `func` / `agg` (строка: `size`, `count`, `sum`, `max`, `min`, `mean`, `first`, `last`, `nunique` и др., как в pandas).

### Пример (классический режим)

```yaml
type: groupby_aggregate
params:
  source_df: df_main
  target_df: df_grouped
  group_keys:
    - Тип оборудования
  aggregations:
    "Остаточная стоимость": sum
```

### Пример (именованные колонки: число строк и max даты)

```yaml
type: groupby_aggregate
params:
  source_df: df_main
  target_df: df_grouped
  group_keys:
    - серийный_номер
  aggregations: {}
  named_aggregations:
    количество_записей:
      column: серийный_номер
      func: size
    последняя_дата:
      column: дата
      func: max
```

Компактная запись с парами `[колонка, функция]`:

```yaml
  named_aggregations:
    количество_записей: [серийный_номер, size]
    последняя_дата: [дата, max]
```

---

## sort_list_output

**Назначение:** упорядочить строки, при необходимости отфильтровать по списку значений из другого датафрейма и оставить уникальные значения в выбранном столбце (с сохранением первой встреченной строки). Результат в **`target_df`** (можно совпасть с **`source_df`**).

**Порядок применения (фиксированный):**

1. **Сортировка** — если задан блок **`sort`**.
2. **Фильтр по списку** — если задан непустой **`list_filter`** (и не отключён `enabled: false`).
3. **Уникальность** — если задан непустой **`unique_by_column`** (или **`unique_by_columns`**): `drop_duplicates` по **одному столбцу** или по **списку столбцов** (совпадение по комбинации значений).

### Параметры (`params`)

| Параметр | Описание |
|----------|----------|
| `source_df` | Исходный DF. |
| `target_df` | Результат. |
| `sort` | Правила сортировки. Можно задать **списком** правил (рекомендуется) или **одним** правилом-словарём. Элемент — имя столбца (строка) или словарь: `{ column: "…", ascending: true/false }` **или** `{ columns: ["A","B"], ascending: false }` (на несколько колонок). Для `ascending` принимаются значения `true/on/yes/1` и `false/off/no/0`. Если `columns` — список, то `ascending` может быть **одним значением** (применится ко всем) или **списком той же длины** (по каждой колонке). Несколько правил задают ключи сортировки слева направо. Пусто/`[]` — не сортировать. |
| `ascending` | Опционально: общий флаг сортировки **для всего списка `sort`**, если там указаны только имена колонок. Может быть `true/false` (применится ко всем) или списком `[...]` той же длины, что и `sort`. Если в элементах `sort` явно задано `ascending`, используйте его (приоритетнее и понятнее). |
| `list_filter` | Опционально. Фильтрация строк по принадлежности значения столбца множеству из другого DF. |
| `unique_by_column` | Один столбец, **список** имён столбцов или строка **`"Кол1, Кол2"`**; `drop_duplicates(subset=…)` после предыдущих шагов (см. `duplicate_keep`). Пусто — не удалять дубли. Если задано **`unique_by_columns`**, оно используется только когда `unique_by_column` пуст. |
| `unique_by_columns` | Альтернатива списку в `unique_by_column`: массив имён столбцов, например `[Тип, Норма]`. |
| `duplicate_keep` | `first` (по умолчанию), `last` или `false` — как в `pandas.drop_duplicates(..., keep=...)`. |

### Поля `list_filter`

| Поле | Описание |
|------|----------|
| `values_df` | Имя DF, из которого берётся список (синонимы: `reference_df`, `list_df`, `list_source_df`). |
| `values_column` | Столбец этого DF; берутся **уникальные ненулевые** значения как множество для проверки (синонимы: `list_column`, `column`). |
| `match_column` | Столбец в **`source_df`** (в текущих данных после сортировки), значение строки сравнивается со списком (синонимы: `filter_column`, `target_column`). |
| `mode` | `in` — оставить строки, где значение **входит** в список; `not_in` — где **не входит**. |
| `enabled` | `false` — не применять фильтр по списку (остальные поля можно не заполнять). |

Строки, где в `match_column` стоит пропуск (`NaN`), для режима `in` обычно **не попадают** в список (`isin`); для `not_in` такие строки **остаются**.

### Пример

```yaml
type: sort_list_output
params:
  source_df: df_main
  target_df: df_main
  sort:
    - column: дата
      ascending: false
    - серийный_номер
  list_filter:
    values_df: df_allowed_codes
    values_column: Код
    match_column: Код
    mode: in
  unique_by_column: серийный_номер
  duplicate_keep: first
```

Уникальность по **нескольким** столбцам (одинаковые пары `Тип` + `Норма` схлопываются, остаётся первая строка по текущему порядку):

```yaml
type: sort_list_output
params:
  source_df: df_main
  target_df: df_main
  unique_by_column:
    - Тип
    - Норма
  duplicate_keep: first
```

Эквивалентно: `unique_by_column: "Тип, Норма"` или `unique_by_columns: [Тип, Норма]`.

---

## df_assign

**Назначение:** операции над датафреймом без Excel: новый столбец как текстовая склейка, выбор подмножества столбцов (по именам или позициям), подстановка значений из другого DF по совпадению ключа, удаление строк с пустыми ячейками, заполнение пустых ячеек.

Поле **`operation`**: `concat_column` \| `calc_column` \| `apply_transform` \| `select_columns` \| `map_lookup` \| `drop_empty` \| `fill_empty`.

Общие поля: `source_df`, `target_df` (пусто или совпадает с `source_df` — изменение на месте; иначе результат копируется в новое имя DF).

### concat_column

Текстовая склейка в **`target_column`**: **`prefix`** + значения столбцов подряд (каждое через **`astype(string)`**, пропуски **`NaN`** / **`NA`** → пустая строка) + **`suffix`**.

Можно указать **один** столбец через **`source_column`** или **несколько** — через **`source_columns`** (YAML-массив имён в нужном порядке). Если задан непустой **`source_columns`**, он имеет приоритет; одну колонку можно задать и строкой в **`source_columns`**. Пустые элементы в списке имён отбрасываются.

Если **`source_column`** и **`source_columns`** не заданы (или пустые), то в `target_column` записывается:

- `prefix + suffix`, если хотя бы один из них непустой;
- `NaN`, если и `prefix`, и `suffix` пустые.

| Параметр | Описание |
|----------|----------|
| `target_column` | Имя нового (или перезаписываемого) столбца. |
| `source_column` | Один исходный столбец (если **`source_columns`** не задан или пуст). |
| `source_columns` | Список имён столбцов; их текстовые значения склеиваются **подряд** в этом порядке. |
| `prefix` | Строка слева от всей склейки столбцов (может быть пустой). |
| `suffix` | Строка справа (может быть пустой). |

### calc_column

Арифметическое вычисление значения в **`target_column`** по выражению **`expression`** с использованием чисел и других столбцов.

Правила:

- `value_type`: `int` или `decimal`
- Любые `null/NaN` и нечисловые значения в используемых столбцах приводятся к **0**.
- Если столбец имеет “не тот” тип, выполняется попытка `to_numeric`; при неудаче значения становятся 0.

Параметры:

| Параметр | Описание |
|----------|----------|
| `target_column` | Имя столбца результата (создать/перезаписать). |
| `expression` | Выражение, например `"A + B*2 - 10"`. |
| `value_type` | `int` или `decimal`. |
| `calc_columns` | Опционально: список/строка через запятую — какие столбцы заранее приводить к числам. Если не задано — приводятся все столбцы DF. |

Пример:

```yaml
type: df_assign
params:
  operation: calc_column
  source_df: df_main
  target_df: df_main
  target_column: Итог
  value_type: decimal
  calc_columns: [Цена, Количество]
  expression: "Цена * Количество"
```

### apply_transform

Условное присваивание в столбец по маске (как `df.loc[mask, target] = ...`), с безопасными преобразованиями строк из **`source_column`**. Маска задаётся выражением **`condition`** в стиле **`DataFrame.eval()`** (имена столбцов, сравнения, `and` / `or` и т.д.). Если **`condition`** не задано или пустая строка, преобразование применяется ко **всем** строкам.

| Параметр | Описание |
|----------|----------|
| `target_column` | Столбец результата (создать или обновить только отфильтрованные строки). |
| `source_column` | Столбец-источник значений. Для всех типов **`transform`**, кроме **`static_value`**, обязателен явно или по умолчанию совпадает с **`target_column`** (тогда столбец уже должен существовать). |
| `condition` | Выражение для булевой маски, например `` `_merge == 'right_only' ``, `Кол1 > 0 and Кол2 == 'Да'`. |
| `transform` | Строка (только тип) или объект `{ type, params }` — см. ниже. |
| `fill_unmatched_rows_with` | Опционально: значение для строк, где маска **ложна** (имеет смысл только при непустом **`condition`**). |
| `coerce_to_numeric_on_error` | Если `true`, после операции столбец **`target_column`** приводится к числу (`to_numeric`, ошибки и пропуски → **0**). |

**Типы `transform.type`:**

| `type` | Назначение | `params` |
|--------|------------|----------|
| `split_first_word` | Первый фрагмент после разбиения (как `str.split(...)[0]`) | `delimiter` — по умолчанию пробел |
| `split_last_word` | Последний фрагмент | `delimiter` — по умолчанию пробел |
| `regex_extract` | `Series.str.extract(pattern)` | `pattern` (или `regex`) — шаблон с **одной** захватывающей группой или без группы |
| `replace_map` | Последовательная замена подстрок | `map` — объект «что заменить → на что» |
| `static_value` | Константа для строк с истинной маской | `value` |
| `as_string` | Приведение к строке (`astype(string)`) | — |

Эквивалент примера:

```python
mask = analiz['_merge'] == 'right_only'
analiz.loc[mask, 'ГОСБ'] = analiz.loc[mask, 'Город'].apply(lambda x: x.split()[0])
```

— в YAML:

```yaml
type: df_assign
params:
  operation: apply_transform
  source_df: analiz
  target_df: analiz
  target_column: ГОСБ
  source_column: Город
  condition: "_merge == 'right_only'"
  transform:
    type: split_first_word
    params:
      delimiter: " "
```

Алиас операции: `conditional_assign`.

### select_columns

Подмножество столбцов в новый вид DF (как `DF = DF[["A","B"]]` или по номерам).

| Параметр | Описание |
|----------|----------|
| `column_mode` | `names` — список имён; `positions` — список номеров столбцов **с 1** (первая колонка = `1`, как в привычной нумерации слева направо). |
| `columns` | Список имён или чисел (не пустой). |

### map_lookup

Для каждой строки `source_df`: по значению `source_key` ищется строка в `lookup_df` с тем же значением в `lookup_key`, в целевой столбец (или столбцы) записывается значение из соответствующей колонки справочника. При нескольких совпадениях в справочнике берётся **последняя** строка после `drop_duplicates`. Несовпадения дают `NaN`.

Параметры **`lookup_value_column`** и **`target_column`** можно задать **одной строкой** (одна пара столбцов) или **списками одинаковой длины**: i-й столбец из справочника подставляется в i-й целевой столбец.

| Параметр | Описание |
|----------|----------|
| `lookup_df` | Имя DF-справочника. |
| `source_key` | Колонка ключа в основном DF. |
| `lookup_key` | Колонка ключа в справочнике. |
| `lookup_value_column` | Имя столбца в справочнике, значение которого подставляется; или **список** имён столбцов справочника. |
| `target_column` | Имя столбца в результате (создать или перезаписать); или **список** имён **в том же порядке**, что и `lookup_value_column`. |

Если указаны списки, их длины должны совпадать; пустые элементы в списках недопустимы.

### drop_empty

Удаление строк, где в указанных столбцах «пусто»: `NaN` / `NA`; для текстовых — при `treat_whitespace_as_empty: true` также строка из одних пробелов.

| Параметр | Описание |
|----------|----------|
| `subset` или `columns` | Список имён столбцов (достаточно одного из ключей). |
| `how` | `any` — удалить строку, если **хотя бы один** из столбцов пуст; `all` — если **все** перечисленные столбцы пусты. |
| `treat_whitespace_as_empty` | Учитывать пробельные строки как пустые (по умолчанию `true`). |

### fill_empty

Подстановка **`fill_value`** вместо пустых ячеек (те же правила пустоты, что у `drop_empty`).

| Параметр | Описание |
|----------|----------|
| `fill_value` | Значение для подстановки (строка, число и т.д.). |
| `scope` | `listed` — только столбцы из `columns`; `all_columns` — все столбцы DF. |
| `columns` | Список имён (при `scope: listed`). |
| `treat_whitespace_as_empty` | Как у `drop_empty`. |

### Примеры

```yaml
type: df_assign
params:
  operation: concat_column
  source_df: df_main
  target_df: df_main
  target_column: new_col
  source_column: OLD
  prefix: ""
  suffix: "ДопЗначение"
```

Склейка нескольких столбцов (результат: `prefix` + `Код` + `Наименование` + `suffix`):

```yaml
type: df_assign
params:
  operation: concat_column
  source_df: df_main
  target_df: df_main
  target_column: composite_key
  source_columns:
    - Код
    - Наименование
  prefix: ""
  suffix: ""
```

```yaml
type: df_assign
params:
  operation: select_columns
  source_df: df_main
  target_df: df_narrow
  column_mode: positions
  columns: [1, 2, 5, 7]
```

```yaml
type: df_assign
params:
  operation: map_lookup
  source_df: df_main
  target_df: df_main
  lookup_df: df_dict
  source_key: Код
  lookup_key: Код
  lookup_value_column: Название
  target_column: Название_из_справочника
```

Несколько столбцов за один проход (порядок списков совпадает по позициям):

```yaml
type: df_assign
params:
  operation: map_lookup
  source_df: df_main
  target_df: df_main
  lookup_df: df_dict
  source_key: Код
  lookup_key: Код
  lookup_value_column:
    - Название
    - Единица
  target_column:
    - Название_из_справочника
    - Единица_из_справочника
```

```yaml
type: df_assign
params:
  operation: drop_empty
  source_df: df_main
  target_df: df_main
  subset: [Кол1, Кол2]
  how: any
  treat_whitespace_as_empty: true
```

```yaml
type: df_assign
params:
  operation: fill_empty
  source_df: df_main
  target_df: df_main
  fill_value: "—"
  scope: all_columns
  treat_whitespace_as_empty: true
```
