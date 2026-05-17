# Публикация ExcelForge на GitHub

Репозиторий подготовлен локально: ветка **`main`**, первый коммит создан.

## Шаг 1. Авторизация GitHub CLI

В PowerShell (один раз):

```powershell
gh auth login
```

Выберите:

- GitHub.com
- HTTPS
- Login with a web browser (или token)

Проверка:

```powershell
gh auth status
```

## Шаг 2. Создать публичный репозиторий и отправить код

Из корня проекта:

```powershell
cd C:\Users\kovtu.CODER\ExcelForge

gh repo create ExcelForge --public --source=. --remote=origin --push
```

Если репозиторий с именем `ExcelForge` уже занят, укажите другое имя:

```powershell
gh repo create ExcelForge-app --public --source=. --remote=origin --push
```

## Шаг 3. Проверка

```powershell
gh repo view --web
```

В настройках репозитория на GitHub: **Settings → General → Danger Zone** — убедитесь, что репозиторий **Public**.

## Если репозиторий создан вручную на сайте

```powershell
git remote add origin https://github.com/ВАШ_ЛОГИН/ExcelForge.git
git push -u origin main
```

## Что не попало в git (`.gitignore`)

- `.venv/`
- `Демо_данные/`, `Демо_вывод/`, локальные рабочие папки
- `*.docx`, служебный файл `con` (артефакт Windows)

## Настройка имени автора коммитов (рекомендуется)

```powershell
git config --global user.name "Ваше Имя"
git config --global user.email "your@email.com"
```

Для следующих коммитов.
