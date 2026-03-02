# Публикация пакета: установка через uvx и npx

## Установка через uvx (рекомендуется для Python)

**uvx** — способ запуска Python-приложений из PyPI без глобальной установки (аналог npx для Python).

### Шаги для публикации

1. **Аккаунт на PyPI**
   - Зарегистрируйтесь на [pypi.org](https://pypi.org/account/register/).
   - Для тестовой публикации: [test.pypi.org](https://test.pypi.org/account/register/).

2. **Токен API PyPI**
   - PyPI → Account settings → API tokens → Add API token.
   - Сохраните токен (username: `__token__`, password: значение токена).

3. **Сборка и публикация**
   Из корня репозитория (где лежит `pyproject.toml`):

   ```bash
   # Установить uv (если ещё нет): https://docs.astral.sh/uv/
   uv build
   uv publish
   ```

   При первом `uv publish` будет запрошен токен PyPI (или укажите через переменные окружения/конфиг uv).

4. **Использование после публикации**
   Пользователи смогут запускать без установки пакета:

   ```bash
   uvx mcp-atlassian
   ```

   Или установить в изолированное окружение и вызывать команду:

   ```bash
   uv tool install mcp-atlassian
   mcp-atlassian
   ```

---

## Установка через npx (опционально)

**npx** работает с npm-пакетами. Ваш проект — Python, поэтому «напрямую» в npx его не опубликовать. Варианты:

### Вариант A: Только uvx

Официально распространять пакет как Python-инструмент и в документации указывать только `uvx mcp-atlassian`. Для Python-аудитории этого достаточно.

### Вариант B: npm-обёртка для npx

Создать отдельный репозиторий/пакет на npm с именем, например, `mcp-atlassian` или `mcp-atlassian-cli`, который при запуске через npx:

- проверяет наличие Python и `uv`/`pip`;
- при необходимости устанавливает пакет `mcp-atlassian` из PyPI (например, через `uv tool install mcp-atlassian` или `pipx install mcp-atlassian`);
- запускает `mcp-atlassian`.

Такой пакет будет маленьким (один `package.json` + скрипт на Node.js или shell). Публикация: обычная публикация в npm (`npm publish`).

---

## Чек-лист перед публикацией на PyPI

- [ ] Версия задаётся через `uv-dynamic-versioning` (из git) или задана в `pyproject.toml`.
- [ ] В `pyproject.toml`: `name`, `description`, `readme`, зависимости, `[project.scripts]` с точкой входа `mcp-atlassian = "mcp_atlassian:main"`.
- [ ] В корне есть `README.md`.
- [ ] Репозиторий в git (для динамической версии нужен хотя бы один тег, например `v0.1.0`).
- [ ] Проверка сборки: `uv build` выполняется без ошибок, в `dist/` появляются wheel и sdist.

После выполнения этих шагов публикация через `uv publish` и установка через `uvx mcp-atlassian` будут работать.
