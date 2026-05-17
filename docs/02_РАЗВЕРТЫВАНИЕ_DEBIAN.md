# ExcelForge — развёртывание на Debian (Python 3.9)

## 1. Назначение документа

Инструкция по установке и запуску ExcelForge на **Debian GNU/Linux** с интерпретатором **Python 3.9**.

Документ дополняет [02_РАЗВЕРТЫВАНИЕ.md](02_РАЗВЕРТЫВАНИЕ.md) (Windows) и не заменяет [руководство пользователя](03_РУКОВОДСТВО_ПОЛЬЗОВАТЕЛЯ.md).

---

## 2. Системные требования

| Параметр | Значение |
|----------|----------|
| ОС | Debian 11 (Bullseye) — **рекомендуется** (системный Python 3.9) |
| ОС | Debian 12 (Bookworm) — возможна установка Python 3.9 отдельно (см. §4.2) |
| Python | **3.9.x** (обязательно) |
| RAM | от 4 ГБ |
| GUI | X11 или Wayland с доступом к дисплею (для Tkinter) |
| Excel | не требуется; работа с `.xlsx` через openpyxl |

### Совместимость кода с Python 3.9

Проект использует аннотации типов с синтаксисом `list[str]`, `str | None` и файл `from __future__ import annotations` — на **3.9** это поддерживается. Отдельная сборка под 3.10+ не требуется.

---

## 3. Подготовка каталога приложения

Скопируйте проект на сервер или рабочую станцию, например:

```text
/opt/excelforge/ExcelForge/
```

или в домашний каталог:

```text
/home/user/ExcelForge/
```

Минимальный состав:

```text
ExcelForge/
  app/
  pipelines/
  requirements.txt
  docs/
```

Иконка окна (необязательно): `app/1-var.png` или `app/1 var.png` (на Linux `.ico` может не использоваться — предпочтителен PNG).

---

## 4. Установка Python 3.9 и зависимостей ОС

### 4.1. Debian 11 (Bullseye)

Обновите индекс пакетов и установите Python 3.9, venv и **Tkinter** (без `python3-tk` GUI не запустится):

```bash
sudo apt update
sudo apt install -y \
  python3.9 \
  python3.9-venv \
  python3.9-dev \
  python3-tk \
  tk-dev \
  libtk8.6
```

Проверка:

```bash
python3.9 --version
# Ожидается: Python 3.9.x

python3.9 -c "import tkinter; print('tkinter OK')"
```

### 4.2. Debian 12 (Bookworm) и новее

В репозитории Bookworm по умолчанию **Python 3.11**. Пакет `python3.9` может отсутствовать.

Варианты:

1. **Рекомендуется для продакшена:** развернуть на **Debian 11** или в контейнере `debian:bullseye`.
2. **На Bookworm:** собрать 3.9 через [pyenv](https://github.com/pyenv/pyenv) или использовать отдельный хост с Bullseye.

Пример установки системных библиотек для Tkinter на Bookworm (при наличии своего `python3.9`):

```bash
sudo apt update
sudo apt install -y python3-tk tk-dev libtk8.6 build-essential \
  libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
  libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
```

---

## 5. Виртуальное окружение и pip

Перейдите в корень проекта:

```bash
cd /opt/excelforge/ExcelForge
```

Создайте venv **именно на Python 3.9**:

```bash
python3.9 -m venv .venv
source .venv/bin/activate
```

Обновите pip и установите зависимости:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

Проверка версии внутри venv:

```bash
python --version
# Python 3.9.x

python -c "import pandas, openpyxl, yaml, markdown2; print('deps OK')"
```

### Если `pip install` падает на pandas

На старых системах иногда помогает явное ограничение версии, совместимой с 3.9:

```bash
python -m pip install "pandas>=2.0,<2.3" openpyxl PyYAML markdown2
```

При необходимости зафиксируйте версии в отдельном файле `requirements-debian39.txt` в корне проекта.

---

## 6. Первый запуск (графический режим)

### 6.1. Локальная машина с монитором

```bash
cd /opt/excelforge/ExcelForge
source .venv/bin/activate
python -m app.main
```

Должно открыться окно **ExcelForge** (вкладки Runner, Builder, Общие настройки).

### 6.2. SSH с X11-пробросом

На **клиенте** (с X-сервером):

```bash
ssh -X user@debian-host
```

На **сервере**:

```bash
cd ~/ExcelForge
source .venv/bin/activate
python -m app.main
```

Если окно не появляется, проверьте `echo $DISPLAY` (должно быть не пусто).

### 6.3. Запуск без GUI (только пайплайны)

Штатного CLI-режима «без Tkinter» в поставке нет: точка входа `app.main` создаёт окно. Для серверной автоматизации можно вызывать исполнитель пайплайна из Python (кастомный скрипт) — это выходит за рамки базовой установки. Для интерактивной работы нужен дисплей.

---

## 7. Скрипт запуска

Создайте файл `run-excelforge.sh` в корне проекта:

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
exec python -m app.main
```

Права:

```bash
chmod +x run-excelforge.sh
./run-excelforge.sh
```

Опционально — ярлык в меню или симлинк в `~/bin`.

---

## 8. Пути и настройки на Linux

| Объект | Расположение |
|--------|----------------|
| Пайплайны по умолчанию | `ExcelForge/pipelines/` |
| Настройки UI | `~/.excelforge/settings.json` |
| Рабочие данные | задаются в YAML (`directory`, `out_dir`, `file_path`) |

В YAML используйте **прямые слэши** или экранированные пути Linux, например:

```yaml
file_path: "/home/user/data/in.xlsx"
out_dir: "/home/user/data/out"
```

---

## 9. Права доступа

- Пользователь, от которого запускается приложение, должен иметь **чтение** входных Excel и **запись** в `out_dir`.
- При записи в `/opt/...` не запускайте GUI от root без необходимости; лучше выделить каталог ` /var/lib/excelforge` с владельцем `excelforge:excelforge`.

Пример:

```bash
sudo useradd -r -m -s /bin/bash excelforge || true
sudo chown -R excelforge:excelforge /opt/excelforge/ExcelForge
sudo -u excelforge bash -c 'cd /opt/excelforge/ExcelForge && source .venv/bin/activate && python -m app.main'
```

---

## 10. Обновление

```bash
cd /opt/excelforge/ExcelForge
# сохраните свои pipelines/ и данные
source .venv/bin/activate
git pull   # если используется git
python -m pip install -r requirements.txt
```

Проверьте запуск тестового YAML из `pipelines/`.

---

## 11. Устранение неполадок

### `ModuleNotFoundError: No module named 'tkinter'`

```bash
sudo apt install python3-tk
# для venv на 3.9 иногда нужен системный tk, привязанный к той же версии:
sudo apt install python3.9-tk   # если пакет есть в репозитории
```

### `python3.9: command not found`

На Debian 12 установите Bullseye-контейнер, pyenv или перенесите хост на Debian 11.

### Ошибка дисплея / `_tkinter.TclError: couldn't connect to display`

Нет графической сессии или не задан `DISPLAY`. Запускайте локально, через `ssh -X`, или VNC.

### `Permission denied` при сохранении Excel

Проверьте права на `out_dir`; закройте файл, если он открыт в LibreOffice Calc на другой машине (SMB/NFS).

### Шрифт интерфейса «ломается»

Вкладка **Общие настройки** → выберите шрифт, доступный в системе (например `DejaVu Sans`, `Liberation Sans`).

### Иконка окна не отображается

На Linux используется в основном **PNG** в `app/`; `.ico` может игнорироваться — это нормально.

---

## 12. Контрольный чек-лист

- [ ] `python3.9 --version` → 3.9.x
- [ ] Установлен `python3-tk`, импорт `tkinter` успешен
- [ ] Создан venv: `python3.9 -m venv .venv`
- [ ] `pip install -r requirements.txt` без ошибок
- [ ] `python -m app.main` открывает окно (при наличии DISPLAY)
- [ ] В Runner выбран каталог `pipelines/`, тестовый YAML выполняется
- [ ] Настроены пути к данным в YAML или `globals_settings`

---

## 13. Связанные документы

| Документ | Содержание |
|----------|------------|
| [03_РУКОВОДСТВО_ПОЛЬЗОВАТЕЛЯ.md](03_РУКОВОДСТВО_ПОЛЬЗОВАТЕЛЯ.md) | Работа с Runner и Builder |
| [00_ОПИСАНИЕ_ПРОГРАММЫ.md](00_ОПИСАНИЕ_ПРОГРАММЫ.md) | Описание продукта |
| [../app/docs/pipeline_steps.md](../app/docs/pipeline_steps.md) | Справочник шагов |

---

*Версия инструкции: Debian, Python 3.9.*
