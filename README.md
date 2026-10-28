# ФинПарус

**ФинПарус** — Django-приложение с публичной витриной предложений микрофинансовых организаций, внутренней панелью управления и интеграцией с API Leads.su.

Приложение получает активные офферы из Leads.su, нормализует их, сохраняет в локальную базу данных и формирует ограниченную витрину предложений с сортировкой по приоритету и EPC.

Проект использует server-side rendering через Django Templates, обычный CSS и небольшой объём vanilla JavaScript. Отдельный frontend framework и Node.js toolchain не требуются.

---

## Возможности

### Публичная витрина

Публичная страница показывает активные финансовые предложения и позволяет фильтровать их на клиенте по категориям:

- все предложения;
- предложения для новых клиентов;
- займы сроком до 30 дней;
- займы на длительный срок.

Количество карточек на витрине ограничено `MAX_SHOWCASE_OFFERS`.

Офферы сортируются в следующем порядке:

1. приоритетные предложения;
2. более высокий EPC;
3. `sort_order`;
4. более новые карточки;
5. `id` как стабильный tie-breaker.

Неактивные предложения на публичную витрину не попадают.

В нижней части страницы выводится юридическая информация об организациях, если она была получена при синхронизации.

### Панель управления

Проект содержит отдельную staff-панель для управления витриной.

Доступ к ней разрешён только пользователям с `is_staff=True`.

Панель позволяет:

- просматривать все офферы;
- видеть, какие предложения фактически входят в публичную витрину;
- фильтровать предложения по состоянию;
- включать и скрывать предложения;
- назначать и снимать приоритет;
- редактировать данные карточек;
- удалять предложения;
- выполнять групповые действия;
- запускать синхронизацию с Leads.su.

Изменяющие состояние операции выполняются через `POST` и защищаются Django CSRF middleware.

Дополнительно модель `Product` доступна через стандартный Django Admin.

---

## Интеграция с Leads.su

Основная интеграция находится в:

```text
project/showcase/integrations/leads_su.py
```

Management command синхронизации:

```text
project/showcase/management/commands/sync_leads_offers.py
```

Общий процесс:

```text
Leads.su API
    ↓
получение всех страниц активных офферов
    ↓
валидация и нормализация
    ↓
Product.objects.update_or_create(...)
    ↓
деактивация исчезнувших офферов
    ↓
публичная витрина
```

### Автоматическая синхронизация

В production витрина автоматически синхронизируется с Leads.su.

Интервал задается в переменной окружения:

```dotenv
SHOWCASE_SYNC_INTERVAL_SECONDS=600
```

Значение указывается в секундах.

Например:

```text
300 = 5 минут
900 = 15 минут
1800 = 30 минут
3600 = 1 час
```

Если переменная не указана, используется интервал:

```text
600 секунд
```

Автоматическая синхронизация выполняется отдельным Docker Compose сервисом:

```text
sync
```

Он запускает management command:

```bash
python manage.py run_offer_sync_scheduler
```

При запуске scheduler сразу выполняет синхронизацию, после чего ожидает заданный интервал перед следующим запуском.

Ошибка отдельной синхронизации не останавливает scheduler. Следующая попытка будет выполнена через установленный интервал.

### Основные правила синхронизации

Импортированные предложения идентифицируются комбинацией:

```text
source + external_id
```

На уровне базы данных действует уникальное ограничение для ненулевых `external_id`.

Ручные карточки имеют:

```text
source = "manual"
```

Карточки Leads.su:

```text
source = "leads_su"
```

Синхронизация Leads.su не деактивирует ручные карточки.

### Обновление существующих предложений

Если оффер с тем же `source` и `external_id` уже существует, его данные обновляются.

Если оффер новый — создаётся новая запись.

### Исчезнувшие предложения

После полностью успешного получения данных из API импортированные активные карточки, которых больше нет в ответе Leads.su, автоматически переводятся в неактивное состояние.

Они не удаляются из базы данных.

### Ошибки API

Изменения базы выполняются только после успешного получения полного набора данных из API.

Если получение данных завершается ошибкой, существующие предложения не деактивируются.

### Невалидные офферы

Если Leads.su вернул оффер с известным `external_id`, но его данные не прошли локальную нормализацию, существующая карточка с этим ID не деактивируется.

Это сделано намеренно: временно повреждённые или неполные данные внешнего API не должны автоматически убирать ранее корректный оффер с витрины.

Новый невалидный оффер при этом не создаётся.

### Транзакционность

Запись нормализованных данных и деактивация исчезнувших предложений выполняются внутри `transaction.atomic()`.

Таким образом, изменения базы применяются как одна транзакция.

---

## Ручной запуск синхронизации

Из каталога `project`:

```bash
python manage.py sync_leads_offers
```

При успешном выполнении команда выводит статистику:

```text
получено=N,
создано=N,
обновлено=N,
деактивировано=N,
пропущено=N
```

### Dry run

Для проверки ответа API и нормализации без изменения базы данных:

```bash
python manage.py sync_leads_offers --dry-run
```

В этом режиме приложение:

- обращается к Leads.su;
- получает офферы;
- выполняет нормализацию и валидацию;
- выводит статистику;
- не создаёт записи;
- не обновляет существующие записи;
- не деактивирует отсутствующие предложения.

Dry run полезно выполнять перед изменениями интеграции или правил нормализации.

---

## Модель `Product`

Основная модель находится в:

```text
project/showcase/models.py
```

`Product` содержит пользовательские данные карточки, служебные данные интеграции и параметры публикации.

### Идентификация внешнего источника

```text
source
external_id
external_modified_at
```

### Содержимое карточки

```text
provider_name
title
logo_url
category
is_for_new_clients
amount_text
term_text
rate_text
psk_text
description
product_url
legal_info
```

### Управление витриной

```text
is_active
is_priority_offer
other_epc
sort_order
```

### Служебные даты

```text
created_at
updated_at
```

`other_epc` используется при сортировке витрины и импортируется из Leads.su.

`sort_order` используется как дополнительный ручной приоритет внутри соответствующей группы предложений.

---

## Структура проекта

```text
.
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
├── Dockerfile
├── compose.prod.yaml
├── requirements.txt
├── README.md
└── project/
    ├── manage.py
    ├── project/
    │   ├── settings.py
    │   ├── test_settings.py
    │   ├── urls.py
    │   ├── asgi.py
    │   └── wsgi.py
    └── showcase/
        ├── admin.py
        ├── apps.py
        ├── dashboard_views.py
        ├── error_views.py
        ├── forms.py
        ├── middleware.py
        ├── models.py
        ├── urls.py
        ├── views.py
        ├── integrations/
        │   └── leads_su.py
        ├── management/
        │   └── commands/
        │       └── sync_leads_offers.py
        ├── migrations/
        ├── static/
        │   └── showcase/
        │       ├── css/
        │       └── js/
        ├── templates/
        │   ├── admin/
        │   ├── dashboard/
        │   ├── errors/
        │   └── showcase/
        └── tests/
            ├── test_dashboard.py
            ├── test_forms.py
            ├── test_import_to_showcase.py
            ├── test_leads_su.py
            ├── test_leads_su_extended.py
            ├── test_models.py
            ├── test_security.py
            ├── test_showcase.py
            └── test_sync_leads_offers.py
```

---

## Технологии

Основной стек:

- Python 3.14;
- Django;
- PostgreSQL;
- Gunicorn;
- Nginx для production static files;
- Requests;
- python-dotenv;
- Docker / Docker Compose;
- GitHub Actions;
- GitHub Container Registry.

Frontend:

- Django Templates;
- CSS;
- vanilla JavaScript.

Отдельная frontend-сборка не требуется.

---

## Локальная разработка

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd showcase
```

### 2. Создание виртуального окружения

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Установка зависимостей

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## Переменные окружения

Настройки приложения загружаются из переменных окружения.

При локальной разработке `python-dotenv` также позволяет использовать файл `.env`.

Пример:

```dotenv
SECRET_KEY=change-me

DJANGO_ENV=development
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=showcase
DB_USER=showcase
DB_PASSWORD=change-me
DB_HOST=localhost
DB_PORT=5432

LEADS_API_TOKEN=
LEADS_PLATFORM_ID=1315391

DJANGO_CSRF_TRUSTED_ORIGINS=
DJANGO_HSTS_SECONDS=0
```

> **Важно:** `.env` содержит секреты и не должен добавляться в Git.

### `SECRET_KEY`

Обязательная переменная:

```dotenv
SECRET_KEY=...
```

Без неё Django settings не загружаются.

### `DJANGO_ENV`

Production security settings активируются при:

```dotenv
DJANGO_ENV=production
```

В production включаются:

- `SESSION_COOKIE_SECURE`;
- `CSRF_COOKIE_SECURE`;
- `SECURE_SSL_REDIRECT`;
- `SECURE_PROXY_SSL_HEADER`.

HSTS управляется через `DJANGO_HSTS_SECONDS`.

### PostgreSQL

Основные переменные подключения:

```dotenv
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
DB_HOST=localhost
DB_PORT=5432
```

### Leads.su

Для реальной синхронизации необходим API token:

```dotenv
LEADS_API_TOKEN=...
```

ID площадки:

```dotenv
LEADS_PLATFORM_ID=1315391
```

---

## База данных

Основная конфигурация приложения использует PostgreSQL.

После настройки базы данных перейдите в каталог Django-проекта:

```bash
cd project
```

Примените миграции:

```bash
python manage.py migrate
```

Создайте администратора:

```bash
python manage.py createsuperuser
```

Запустите development server:

```bash
python manage.py runserver
```

По умолчанию Django development server будет доступен по адресу:

```text
http://127.0.0.1:8000/
```

---

## Тестирование

Для тестов предусмотрен отдельный settings module:

```text
project.test_settings
```

Он использует SQLite in-memory database, поэтому для запуска автоматических тестов локальный PostgreSQL не требуется.

### Linux/macOS

Из каталога `project`:

```bash
SECRET_KEY=test-secret-key \
python manage.py test showcase \
  --settings=project.test_settings
```

### Windows PowerShell

```powershell
$env:SECRET_KEY="test-secret-key"
python manage.py test showcase --settings=project.test_settings
```

### Что проверяют тесты

#### Модель

Проверяются:

- значения по умолчанию;
- категории;
- URL validation;
- `sort_order`;
- timestamps;
- строковое представление;
- database constraint для `source + external_id`.

#### Публичная витрина

Проверяются:

- публичная доступность;
- исключение неактивных карточек;
- максимальное количество предложений;
- приоритет предложений;
- сортировка по EPC.

#### Dashboard

Проверяются:

- authentication;
- ограничение доступа только staff-пользователям;
- наличие карточек в dashboard;
- POST-only mutations;
- включение и выключение карточек;
- изменение приоритета;
- удаление;
- bulk actions;
- logout;
- CSRF protection.

#### Leads.su

Проверяются:

- нормализация данных API;
- создание новых предложений;
- обновление существующих;
- отсутствие дубликатов;
- деактивация исчезнувших офферов;
- сохранение ручных карточек;
- поведение при ошибке API;
- поведение при невалидных данных;
- dry run;
- статистика синхронизации.

#### End-to-end импорт

Отдельные тесты проверяют полную цепочку:

```text
сырой Leads.su offer
    ↓
sync_leads_offers
    ↓
Product
    ↓
public showcase
    ↓
HTML response
```

В том числе проверяются tracking URLs, категории, EPC, повторная синхронизация и исчезновение деактивированного оффера с публичной страницы.

#### Security regression tests

Есть отдельные проверки:

- экранирования потенциально опасного пользовательского содержимого;
- CSRF-защиты изменяющих состояние операций.

---

## Django system check

Для проверки конфигурации:

```bash
SECRET_KEY=test-secret-key \
python manage.py check \
  --settings=project.test_settings
```

---

## Maintenance mode

Проект содержит middleware:

```text
showcase.middleware.MaintenanceModeMiddleware
```

При включённом:

```python
MAINTENANCE_MODE = True
```

приложение возвращает страницу `503 Service Unavailable` для обычных запросов.

Разрешённые IP задаются через:

```python
MAINTENANCE_ALLOWED_IPS = [
    "127.0.0.1",
    "::1",
]
```

Ответ maintenance mode содержит заголовок:

```http
Retry-After: 3600
```

По умолчанию maintenance mode выключен.

---

## Static files

В production static files собираются командой:

```bash
python manage.py collectstatic --noinput
```

`STATIC_ROOT`:

```text
project/staticfiles
```

В Docker Compose static files находятся в общем volume:

```text
static_data
```

Gunicorn и контейнер, обслуживающий static files, используют этот volume совместно.

---

## Docker

Production image собирается из корневого `Dockerfile`.

Сборка:

```bash
docker build -t showcase .
```

Контейнер запускает приложение через Gunicorn:

```text
project.wsgi:application
```

Gunicorn слушает:

```text
0.0.0.0:8000
```

Приложение внутри контейнера запускается от непривилегированного пользователя `django`.

---

## Production Docker Compose

Production-конфигурация находится в:

```text
compose.prod.yaml
```

Она содержит четыре сервиса:

```text
web
sync
db
nginx-static
```

### `web`

Django + Gunicorn.

Образ передаётся через переменную:

```dotenv
APP_IMAGE=...
```

Контейнер читает production environment из `.env`.

### `sync`

Отдельный процесс автоматической синхронизации витрины с Leads.su.

Scheduler запускает:

```bash
python manage.py sync_leads_offers
```

с интервалом, заданным через:

```dotenv
SHOWCASE_SYNC_INTERVAL_SECONDS=600
```

Scheduler использует тот же Docker image и `.env`, что и основной Django-сервис.

### `db`

PostgreSQL с persistent volume:

```text
postgres_data
```

Для базы настроен healthcheck через `pg_isready`.

`web` ожидает успешный healthcheck базы перед запуском.

### `nginx-static`

Отдельный Nginx-контейнер обслуживает собранные Django static files из read-only volume.

Снаружи он привязан к:

```text
127.0.0.1:8080
```

Django/Gunicorn:

```text
127.0.0.1:8000
```

Предполагается, что внешний reverse proxy принимает публичный HTTP/HTTPS traffic и проксирует динамические запросы в Gunicorn, а static requests — в Nginx static container.

---

## CI

Workflow:

```text
.github/workflows/ci.yml
```

запускается при:

- push в `main`;
- создании или обновлении pull request.

Pipeline выполняет:

```text
Checkout
    ↓
Python
    ↓
pip install
    ↓
Django system check
    ↓
Django tests
    ↓
Docker build
```

Изменение должно пройти тесты и успешно собраться в Docker image.

---

## Production deployment

Production workflow:

```text
.github/workflows/deploy.yml
```

запускается при push в `main`.

Deployment состоит из трёх последовательных jobs:

```text
test
 ↓
build
 ↓
deploy
```

### Test

Перед deployment запускается Django test suite.

Если тесты завершаются ошибкой, Docker image не собирается и deployment не выполняется.

### Build

После успешных тестов GitHub Actions:

1. авторизуется в GitHub Container Registry;
2. собирает Docker image;
3. публикует image в GHCR.

Создаются теги:

```text
:<git-sha>
:latest
```

Для непосредственного deployment используется immutable SHA tag.

### Deploy

Deployment выполняется по SSH.

Workflow:

1. копирует актуальный `compose.prod.yaml` на сервер;
2. скачивает новый Docker image;
3. запускает PostgreSQL;
4. выполняет migrations;
5. выполняет `collectstatic`;
6. запускает или обновляет production services;
7. выводит состояние Docker Compose services.

Production directory на сервере:

```text
/opt/finparus
```

---

## GitHub Actions secrets

Deployment ожидает следующие repository/environment secrets:

```text
SSH_PRIVATE_KEY
SSH_KNOWN_HOSTS
SERVER_HOST
SERVER_USER
```

`GITHUB_TOKEN` предоставляется GitHub Actions автоматически и используется для публикации image в GHCR.

Секреты приложения и базы данных не должны передаваться через Docker image. Они хранятся в production `.env` на сервере.

---

## Production environment

Пример минимальной конфигурации `/opt/finparus/.env`:

```dotenv
SECRET_KEY=replace-with-secure-random-value

DJANGO_ENV=production
DJANGO_ALLOWED_HOSTS=finparus.ru,www.finparus.ru
DJANGO_CSRF_TRUSTED_ORIGINS=https://finparus.ru,https://www.finparus.ru
DJANGO_HSTS_SECONDS=31536000

DB_NAME=showcase
DB_USER=showcase
DB_PASSWORD=replace-with-secure-password
DB_HOST=db
DB_PORT=5432

LEADS_API_TOKEN=replace-with-real-token
LEADS_PLATFORM_ID=1315391

SHOWCASE_SYNC_INTERVAL_SECONDS=600
```

Для Docker Compose `DB_HOST` должен соответствовать имени database service:

```dotenv
DB_HOST=db
```

---

## Ручные команды в production

### Синхронизация Leads.su

```bash
docker compose \
  -f compose.prod.yaml \
  run --rm web \
  python manage.py sync_leads_offers
```

### Dry run

```bash
docker compose \
  -f compose.prod.yaml \
  run --rm web \
  python manage.py sync_leads_offers --dry-run
```

### Migrations

```bash
docker compose \
  -f compose.prod.yaml \
  run --rm web \
  python manage.py migrate
```

### Django shell

```bash
docker compose \
  -f compose.prod.yaml \
  run --rm web \
  python manage.py shell
```

---

## Безопасность

Проект следует базовым правилам безопасности Django.

Production secret key не хранится в исходном коде:

```python
SECRET_KEY = os.environ["SECRET_KEY"]
```

В production включаются secure cookies и HTTPS redirect.

Изменяющие состояние dashboard actions используют `POST`.

Формы защищаются CSRF middleware.

Django Templates автоматически экранируют выводимые значения.

Внешние ссылки на продукты открываются с:

```html
rel="nofollow sponsored noopener"
```

Приложение запускается внутри Docker container от непривилегированного пользователя.

Секреты deployment и приложения не должны добавляться в Git или Docker image.

---

## Принципы архитектуры

Проект намеренно сохраняет простую Django-архитектуру.

### Django ORM остаётся основным слоем доступа к данным

Дополнительный repository layer не используется.

### Интеграция с внешним API изолирована

HTTP-взаимодействие и нормализация Leads.su находятся за пределами views и templates.

### Management command управляет синхронизацией

HTTP views не содержат реализацию импорта, а используют существующую management command.

### Backend является источником бизнес-состояния

JavaScript отвечает за локальное UI-поведение, но не определяет серверные правила сортировки и формирования публичной витрины.

### Frontend остаётся server-rendered

Проект не требует React, Vue или другого SPA framework.

Основной UI строится на Django Templates, CSS и небольшом количестве vanilla JavaScript.

### Абстракции добавляются только при реальной необходимости

Предпочтение отдаётся явному и простому коду вместо дополнительных service/repository/use-case слоёв без практической необходимости.

---

## Основные бизнес-инварианты

При изменении проекта важно сохранять следующие свойства:

1. На публичной витрине показываются только активные предложения.
2. Количество предложений не превышает `MAX_SHOWCASE_OFFERS`.
3. Приоритетное предложение располагается выше обычного независимо от EPC.
4. Внутри одной priority-группы более высокий EPC имеет преимущество.
5. Ручные предложения не деактивируются синхронизацией Leads.su.
6. Ошибка API не должна приводить к массовой деактивации существующих предложений.
7. Полученный, но временно невалидный оффер не должен автоматически деактивировать существующую карточку с тем же `external_id`.
8. Новый невалидный оффер не должен публиковаться.
9. Комбинация ненулевых `source + external_id` должна быть уникальной.
10. Изменяющие состояние HTTP endpoints должны требовать `POST` и CSRF protection.

Большая часть этих правил закреплена автоматическими тестами.

---

## Рекомендуемый workflow разработки

Перед началом изменений:

```bash
git pull
```

После изменения backend-кода:

```bash
cd project

SECRET_KEY=test-secret-key \
python manage.py check \
  --settings=project.test_settings

SECRET_KEY=test-secret-key \
python manage.py test showcase \
  --settings=project.test_settings
```

При изменениях интеграции Leads.su дополнительно рекомендуется выполнить:

```bash
python manage.py sync_leads_offers --dry-run
```

Перед merge необходимо убедиться, что GitHub Actions CI завершился успешно.
