# Архитектура CallGuard AI

Заказчик кейса: ПАО КБ «Центр-инвест». Источник требований: `PROJECT_PLAN_CallGuard_AI.md`. Всего файлов в каркасе: 188 (+ `ARCHITECTURE.md`, `TEAM_PLAN.md`).

## 1. Принципы
- Offline-first: аудио, тексты и AI-оценки обрабатываются только локально, модели скачиваются заранее.
- Доказуемость: у каждого замечания критерий, цитата и таймкод либо «недостаточно данных».
- Human-in-the-loop: руководитель может скорректировать оценку, исходный результат сохраняется.
- Безопасность по умолчанию: права проверяются на сервере, аудио вне статики, аудит, срок хранения.
- Redis не источник истины: статусы задач хранятся в PostgreSQL.

## 2. Схема
```
Browser (React) ──► nginx ──► FastAPI ── PostgreSQL (users, calls, segments, evaluations, audit)
                                 │  \── защищённое хранилище (audio, exports)
                                 ▼
                           Redis / RQ ──► AI Worker ──► FFmpeg ──► faster-whisper (CPU int8)
                                                   ├──► rules engine / Ollama (опционально)
                                                   └──► PostgreSQL (результаты, статусы)
```

## 3. Стек
| Слой | Технология |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic, PostgreSQL |
| Очередь | Redis + RQ, один AI-worker по умолчанию |
| AI | FFmpeg, faster-whisper CPU int8, rule-based оценка, Ollama/Qwen опционально |
| Frontend | React, TypeScript, Vite, Tailwind, Recharts |
| Инфраструктура | Docker Compose, nginx, GitHub Actions |
| Тесты | pytest, httpx, Playwright, Ruff, ESLint |

## 4. Конвейер обработки звонка
1. `POST /calls` — проверка прав и файла (`services/storage.py`, `services/audio.py`), запись в `calls`, постановка задачи (`workers/queue.py`).
2. Worker (`workers/tasks.py`) ставит статус `processing`, вызывает `services/pipeline.py`.
3. `audio.py` нормализует файл → `transcription.py` даёт сегменты → `evaluation.py` (rules или Ollama) даёт оценку.
4. `result_repository.py` сохраняет результат, `metrics.py` считает KPI, статус `completed` или `failed` с ошибкой.
5. `recovery.py` после перезапуска сверяет зависшие задачи.

## 5. Контракты между модулями
- **AI-контракт** (`services/ai_types.py`, участник 2): `process_audio(path) -> TranscriptResult`, `evaluate(transcript, profile) -> EvaluationResult`.
- **API-контракт** (`schemas/`, участник 1): UUID, даты ISO 8601 UTC, ошибки `{detail, request_id}`, пагинация.
- **Статусы звонка:** `queued → processing → completed | failed`.
- **KPI** (`docs/kpi-spec.md`, участник 5): формулы и значения `null` при недостатке данных.

## 6. Описание файлов
Колонки: владелец (см. `TEAM_PLAN.md`), приоритет (P0 обязательно, P1 желательно, P2 после MVP).


### `(корень)/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `.dockerignore` | P4 | P0 | Исключения для сборки образов. |
| `.env.example` | P4 | P0 | Пример настроек без секретов: БД, Redis, лимиты, модели, срок хранения. |
| `.gitignore` | P4 | P0 | Исключает секреты, аудио, модели, тома, node_modules. |
| `AGENTS.md` | P5 | P0 | Правила для Codex/агентов: приоритеты, запреты, порядок работы. |
| `PROJECT_PLAN_CallGuard_AI.md` | P5 | P0 | Исходное ТЗ и план. |
| `README.md` | P5 | P0 | Запуск по шагам, структура, ссылки на документацию. |

### `.github/workflows/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `ci.yml` | P4 | P0 | CI: Ruff, ESLint, pytest, сборка фронтенда, проверка миграций. |

### `backend/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `alembic.ini` | P1 | P0 | Конфигурация Alembic. |
| `pyproject.toml` | P4 | P0 | Настройки Ruff и pytest. |
| `requirements-dev.txt` | P1 | P0 | Зависимости для тестов и линтеров. |
| `requirements.txt` | P1 | P0 | Зависимости backend (остальные участники добавляют через PR). |

### `backend/alembic/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `env.py` | P1 | P0 | Окружение миграций (подключение к БД, metadata). |
| `script.py.mako` | P1 | P0 | Шаблон файла миграции. |

### `backend/alembic/versions/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `0001_initial.py` | P1 | P0 | Первая миграция: все таблицы, внешние ключи, индексы по датам/операторам/статусам. |

### `backend/app/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `__init__.py` | P1 | P0 | Пакет приложения. |
| `main.py` | P1 | P0 | Точка входа FastAPI: фабрика приложения, подключение роутеров /api/v1, middleware, обработчики ошибок, OpenAPI. |

### `backend/app/api/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `__init__.py` | P1 | P0 | Пакет HTTP-слоя. |
| `analytics.py` | P1 | P0 | GET /analytics/overview и /analytics/trends; тонкий слой над services/analytics_service.py. |
| `auth.py` | P1 | P0 | POST /auth/login, GET /auth/me, смена пароля. |
| `calls.py` | P1 | P0 | POST /calls (загрузка, постановка в очередь), GET /calls, /calls/{id}, /audio, /transcript, /evaluation, POST /calls/{id}/retry. |
| `deps.py` | P1 | P0 | Зависимости FastAPI: сессия БД, текущий пользователь, проверка роли и владения ресурсом. |
| `health.py` | P1 | P0 | GET /health: API, БД, Redis, доступность моделей. |
| `operators.py` | P1 | P0 | GET /operators с учётом прав (руководитель — своя группа). |
| `reports.py` | P1 | P0 | GET /reports/export?format=csv или json; тонкий слой над services/reports.py. |
| `router.py` | P1 | P0 | Сборка всех роутеров под префикс /api/v1. |
| `settings.py` | P1 | P1 | GET/PUT /settings/evaluation-profile (запись только админ). |

### `backend/app/core/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `__init__.py` | P1 | P0 | Пакет ядра. |
| `config.py` | P4 | P0 | Настройки из .env (pydantic-settings), без секретов в коде. |
| `exceptions.py` | P1 | P0 | Исключения домена и единый контракт ошибки (код, detail, request_id). |
| `logging.py` | P4 | P0 | Логи без содержимого звонков, с request_id. |
| `middleware.py` | P4 | P0 | request_id и базовые security headers. |
| `permissions.py` | P1 | P0 | Матрица ролей admin/manager/operator и функции проверки доступа к звонку, аудио, отчёту. |
| `security.py` | P1 | P0 | Хеширование паролей (argon2), выпуск и проверка токенов/сессий. |

### `backend/app/db/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `__init__.py` | P1 | P0 | Пакет БД. |
| `base.py` | P1 | P0 | Declarative Base, UUID-ключи, общие поля created_at. |
| `seed.py` | P1 | P0 | Начальные данные: администратор, демо-руководитель/оператор, профиль оценки по умолчанию. |
| `session.py` | P1 | P0 | Engine и фабрика сессий SQLAlchemy 2 к PostgreSQL. |

### `backend/app/db/models/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `__init__.py` | P1 | P0 | Экспорт моделей для Alembic. |
| `audit_event.py` | P1 | P0 | Таблица audit_events: кто, действие, ресурс, время, metadata_json. |
| `call.py` | P1 | P0 | Таблица calls: оператор, загрузил, время, длительность, формат, storage_key, статус, ошибка. |
| `criterion_score.py` | P1 | P0 | Таблица criterion_scores: критерий, балл, evidence_json. |
| `evaluation.py` | P1 | P0 | Таблица evaluations: звонок, профиль, версия модели, балл, резюме, reviewed_by; хранится история оценок. |
| `evaluation_profile.py` | P1 | P0 | Таблица evaluation_profiles: версия, веса и правила в JSON, признак active. |
| `operator.py` | P1 | P0 | Таблица operators: имя, команда, связь с пользователем. |
| `transcript_segment.py` | P1 | P0 | Таблица transcript_segments: start/end, speaker, текст, confidence (nullable). |
| `user.py` | P1 | P0 | Таблица users: логин, password_hash, роль, active. |
| `violation.py` | P1 | P0 | Таблица violations: критерий, серьёзность, таймкоды, объяснение, рекомендация. |

### `backend/app/schemas/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `__init__.py` | P1 | P0 | Пакет DTO. |
| `analytics.py` | P1 | P0 | Схемы overview и trends. |
| `auth.py` | P1 | P0 | Схемы логина, токена, смены пароля. |
| `call.py` | P1 | P0 | Схемы звонка: создание, список, детали, статус. |
| `common.py` | P1 | P0 | Пагинация, ErrorResponse (detail, request_id), общие типы. |
| `evaluation.py` | P1 | P0 | Схемы оценки, критериев, нарушений, рекомендаций. |
| `operator.py` | P1 | P0 | Схемы оператора. |
| `report.py` | P1 | P0 | Схема строки экспорта (call_id, operator_id, started_at, duration_sec, score, violation_rate, response_time_sec, sentiment, status, criteria, violations). |
| `settings.py` | P1 | P1 | Схемы профиля оценки (веса, правила). |
| `transcript.py` | P1 | P0 | Схемы сегментов расшифровки. |
| `user.py` | P1 | P0 | Схемы пользователя и роли. |

### `backend/app/services/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `ai_types.py` | P2 | P0 | Контракт AI-модулей: TranscriptResult, Segment, EvaluationResult, CriterionResult, ViolationResult. Фиксируется в первый день. |
| `analytics_service.py` | P5 | P0 | Агрегаты для дашборда с фильтрами и учётом прав. |
| `audio.py` | P2 | P0 | FFmpeg: определение реального типа файла, длительность, нормализация WAV/MP3/OGG в 16 кГц mono. |
| `audit.py` | P4 | P1 | Запись audit_events без секретов. |
| `auth_service.py` | P1 | P0 | Проверка учётных данных, выдача токенов, смена пароля. |
| `call_service.py` | P1 | P0 | Создание звонка, смена статусов, фильтрация списка по правам, повторная обработка. |
| `evaluation.py` | P2 | P0 | evaluate(transcript, profile): выбор движка, резервный rule-based, версия правил/модели. |
| `fakes.py` | P2 | P0 | Заглушки STT и оценщика для тестов и независимой работы frontend/backend. |
| `llm_ollama.py` | P2 | P1 | Клиент локальной Ollama/Qwen: JSON-валидация, таймауты, ретраи, откат на правила. |
| `metrics.py` | P5 | P0 | Формулы KPI: итоговый балл, violation_rate, response_time_sec только при корректных метках, sentiment nullable. |
| `pipeline.py` | P2 | P0 | process_call(call_id): аудио → STT → оценка → сохранение результата; вызывается задачей worker. |
| `prompts.py` | P2 | P1 | Промпты оценки и рекомендаций на русском. |
| `reports.py` | P5 | P0 | Экспорт CSV/JSON с null вместо выдуманных значений; PDF позже. |
| `result_repository.py` | P1 | P0 | Сохранение результатов AI (сегменты, оценка, критерии, нарушения) в БД, история оценок, ручная проверка руководителем. |
| `retention.py` | P4 | P1 | Очистка аудио, транскриптов и отчётов по сроку хранения. |
| `rules_engine.py` | P2 | P0 | Rule-based оценка по критериям с цитатой, таймкодом или статусом «недостаточно данных». |
| `speakers.py` | P2 | P1 | Стратегия меток говорящих: роли только для двухканальной записи, иначе «говорящий 1/2» или «не определён». |
| `storage.py` | P4 | P0 | Защищённое хранилище вне статики: безопасные имена, лимиты, временные файлы, выдача по storage_key. |
| `transcription.py` | P2 | P0 | faster-whisper (CPU int8): process_audio(path) возвращает сегменты с start/end и confidence. |

### `backend/app/workers/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `__init__.py` | P4 | P0 | Пакет worker. |
| `queue.py` | P4 | P0 | Подключение Redis/RQ, постановка задач. |
| `recovery.py` | P4 | P0 | Сверка зависших задач после перезапуска. |
| `tasks.py` | P4 | P0 | Задача обработки звонка: статусы в PostgreSQL, вызов pipeline, таймаут, ошибки. |
| `worker.py` | P4 | P0 | Запуск worker, по умолчанию один процесс. |

### `backend/tests/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `__init__.py` | P1 | P0 | Пакет тестов. |
| `conftest.py` | P1 | P0 | Фикстуры: тестовая БД, клиент httpx, пользователи по ролям. |
| `test_analytics.py` | P5 | P0 | Агрегаты на тестовых данных. |
| `test_audio.py` | P2 | P0 | Форматы WAV/MP3/OGG, подмена расширения, битые файлы. |
| `test_audit.py` | P4 | P1 | Аудит без чувствительных данных. |
| `test_auth.py` | P1 | P0 | Вход, неверный пароль, смена пароля, хеширование. |
| `test_calls_api.py` | P1 | P0 | Загрузка, список, детали, фильтры, пагинация, ошибки. |
| `test_llm_ollama.py` | P2 | P1 | Тесты клиента с моком: невалидный JSON, таймаут, откат. |
| `test_metrics.py` | P5 | P0 | Проверка формул и граничных случаев. |
| `test_migrations.py` | P1 | P0 | Миграции применяются на чистой БД. |
| `test_permissions.py` | P1 | P0 | Оператор не видит чужие звонки и аудио; руководитель — только свою группу. |
| `test_pipeline.py` | P2 | P0 | Конвейер целиком на заглушках, обработка ошибок. |
| `test_queue.py` | P4 | P0 | Постановка, порядок, статусы, retry. |
| `test_recovery.py` | P4 | P0 | Восстановление после падения. |
| `test_reports.py` | P5 | P0 | Поля CSV/JSON и null. |
| `test_rules_engine.py` | P2 | P0 | Критерии, доказательства, статус «недостаточно данных». |
| `test_security_headers.py` | P4 | P1 | Заголовки безопасности и request_id. |
| `test_storage.py` | P4 | P0 | Безопасные имена, лимиты, очистка временных файлов. |
| `test_transcription.py` | P2 | P0 | Структура сегментов, таймкоды; тест на реальной модели помечен slow. |

### `backend/tests/integration/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `__init__.py` | P5 | P0 | Пакет интеграционных тестов. |
| `conftest.py` | P5 | P0 | Окружение интеграционных тестов. |
| `test_access_control.py` | P5 | P0 | Сквозная проверка прав. |
| `test_offline_mode.py` | P5 | P0 | Проверка отсутствия внешних вызовов. |
| `test_pipeline_e2e.py` | P5 | P0 | Загрузка, очередь, STT, оценка, экспорт. |

### `docs/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `ai-design.md` | P2 | P1 | Описание AI-модуля: выбор моделей, диаризация, ограничения, как не выдавать вероятность за факт. |
| `api.md` | P1 | P1 | Описание API-контрактов, формат ошибок, примеры. |
| `benchmark.md` | P2 | P0 | Результаты замеров на i5-1235U относительно цели 3–5 минут. |
| `data-model.md` | P1 | P1 | ER-схема и описание таблиц. |
| `demo-scenario.md` | P5 | P0 | Сценарий демонстрации и метрики скорости. |
| `deployment.md` | P4 | P0 | Запуск на Windows и Linux, офлайн-установка, восстановление. |
| `kpi-spec.md` | P5 | P0 | Формулы, веса, критерии, обработка «недостаточно данных». |
| `limitations.md` | P5 | P0 | Известные ограничения продукта. |
| `pilot-readiness.md` | P4 | P2 | Чек-лист банковского пилота: ИБ, ПДн, TLS, ключи, SSO, резервирование. |
| `security.md` | P4 | P0 | Модель безопасности, роли, хранение, логи. |
| `testing.md` | P5 | P0 | Стратегия тестов и запуск. |

### `e2e/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `package.json` | P5 | P1 | Зависимости Playwright. |
| `playwright.config.ts` | P5 | P1 | Настройки Playwright. |

### `e2e/tests/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `access.spec.ts` | P5 | P1 | Оператор не видит чужое. |
| `full_scenario.spec.ts` | P5 | P1 | Вход, загрузка, очередь, транскрипт, оценка, дашборд, экспорт. |

### `frontend/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `eslint.config.js` | P3 | P0 | Правила ESLint. |
| `index.html` | P3 | P0 | HTML-оболочка. |
| `package.json` | P3 | P0 | Зависимости и скрипты: React, TypeScript, Vite, Tailwind, Recharts, ESLint. |
| `postcss.config.js` | P3 | P0 | PostCSS для Tailwind. |
| `tailwind.config.ts` | P3 | P0 | Тема и токены Tailwind. |
| `tsconfig.json` | P3 | P0 | Настройки TypeScript (strict). |
| `tsconfig.node.json` | P3 | P0 | Настройки TypeScript для Vite. |
| `vite.config.ts` | P3 | P0 | Сборка и прокси /api на backend. |

### `frontend/src/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `App.tsx` | P3 | P0 | Маршрутизация и защищённые маршруты. |
| `index.css` | P3 | P0 | Подключение Tailwind и глобальные стили. |
| `main.tsx` | P3 | P0 | Точка входа React. |
| `vite-env.d.ts` | P3 | P0 | Типы окружения Vite. |

### `frontend/src/api/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `analytics.ts` | P3 | P0 | Вызовы /analytics/*. |
| `auth.ts` | P3 | P0 | Вызовы /auth/*. |
| `calls.ts` | P3 | P0 | Вызовы /calls*: загрузка, список, детали, транскрипт, оценка, retry, URL аудио. |
| `client.ts` | P3 | P0 | HTTP-клиент: токен, разбор ошибки (detail, request_id). |
| `operators.ts` | P3 | P1 | Вызов /operators. |
| `reports.ts` | P3 | P0 | Скачивание экспорта CSV/JSON. |
| `settings.ts` | P3 | P1 | Вызовы профиля оценки. |

### `frontend/src/components/auth/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `ProtectedRoute.tsx` | P3 | P0 | Защита маршрутов по авторизации и роли. |

### `frontend/src/components/calls/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `AudioPlayer.tsx` | P3 | P0 | Плеер с переходом по таймкоду. |
| `CallFilters.tsx` | P3 | P0 | Фильтры: период, оператор, статус, диапазон оценки, критерий. |
| `CallsTable.tsx` | P3 | P0 | Таблица звонков с сортировкой и пагинацией. |
| `EvaluationPanel.tsx` | P3 | P0 | Итоговый балл, критерии, основания, пометка «недостаточно данных». |
| `QueueStatus.tsx` | P3 | P0 | Список файлов в очереди и их статусы. |
| `StatusBadge.tsx` | P3 | P0 | Метки queued/processing/completed/failed. |
| `TranscriptView.tsx` | P3 | P0 | Сегменты с подсветкой текущего, говорящие, поиск. |
| `UploadDropzone.tsx` | P3 | P0 | Drag-and-drop, пакетная загрузка, проверка формата и размера, прогресс. |
| `ViolationList.tsx` | P3 | P0 | Нарушения с цитатой, таймкодом и рекомендацией. |

### `frontend/src/components/charts/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `CriteriaChart.tsx` | P3 | P0 | Распределение по критериям. |
| `KpiCards.tsx` | P3 | P0 | Карточки показателей. |
| `TrendChart.tsx` | P3 | P0 | Динамика качества по датам. |

### `frontend/src/components/common/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `EmptyState.tsx` | P3 | P0 | Пустые состояния. |
| `ErrorState.tsx` | P3 | P0 | Ошибки с request_id. |
| `Pagination.tsx` | P3 | P0 | Пагинация. |
| `Spinner.tsx` | P3 | P0 | Индикатор загрузки. |

### `frontend/src/components/layout/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `AppLayout.tsx` | P3 | P0 | Каркас: меню по роли, шапка, выход. |

### `frontend/src/components/settings/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `ProfileEditor.tsx` | P3 | P1 | Форма весов и правил. |

### `frontend/src/hooks/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `useAuth.tsx` | P3 | P0 | Контекст авторизации и роль пользователя. |
| `useCalls.ts` | P3 | P0 | Загрузка списка звонков с фильтрами. |
| `usePolling.ts` | P3 | P0 | Периодический опрос статусов очереди без блокировки интерфейса. |

### `frontend/src/pages/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `CallDetailsPage.tsx` | P3 | P0 | Плеер, транскрипт, поиск по тексту, оценка, нарушения с таймкодами, retry. |
| `CallsPage.tsx` | P3 | P0 | Загрузка файлов, очередь и список звонков с фильтрами. |
| `DashboardPage.tsx` | P3 | P0 | Дашборд: число звонков, средний балл, доля нарушений, критерии, динамика, проблемные звонки. |
| `LoginPage.tsx` | P3 | P0 | Страница входа. |
| `OperatorsPage.tsx` | P3 | P1 | Рейтинг операторов с числом проанализированных звонков. |
| `SettingsPage.tsx` | P3 | P1 | Редактор весов и правил (админ), очередь и ошибки. |

### `frontend/src/types/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `api.ts` | P3 | P0 | Типы DTO, повторяющие OpenAPI backend. |
| `index.ts` | P3 | P0 | Реэкспорт типов. |

### `frontend/src/utils/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `format.ts` | P3 | P0 | Форматирование дат, длительности, баллов, null как «недоступно». |

### `infrastructure/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `docker-compose.yml` | P4 | P0 | PostgreSQL, Redis, backend, worker, frontend, опционально Ollama; volume, healthcheck, внутренняя сеть. |

### `infrastructure/docker/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `backend.Dockerfile` | P4 | P0 | Образ backend с ffmpeg. |
| `frontend.Dockerfile` | P4 | P0 | Сборка фронтенда и раздача через nginx. |
| `worker.Dockerfile` | P4 | P0 | Образ AI-worker с faster-whisper. |

### `infrastructure/nginx/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `nginx.conf` | P4 | P1 | Прокси, security headers, подготовка к TLS, лимит тела запроса. |

### `infrastructure/scripts/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `backup.sh` | P4 | P1 | Резервная копия БД и хранилища. |
| `benchmark_stt.py` | P2 | P0 | Замер времени и качества на записях 1/5/10 минут. |
| `download_models.ps1` | P4 | P0 | Предзагрузка моделей на Windows (дальше работа офлайн). |
| `download_models.sh` | P4 | P1 | То же для Linux-сервера. |
| `offline_check.sh` | P4 | P0 | Проверка работы при отключённом интернете. |
| `restore.sh` | P4 | P1 | Восстановление из копии и проверка. |

### `test_data/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `README.md` | P5 | P0 | Правила тестовых данных: синтетические записи, согласия, запрет реальных клиентов. |
| `manifest.json` | P5 | P0 | Список тестовых записей и ожидания. |

### `test_data/audio/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `.gitkeep` | P5 | P0 | Каталог для синтетических WAV/MP3/OGG. |

### `test_data/expected/`

| Файл | Владелец | Прио | Назначение |
|---|---|---|---|
| `call_ok.json` | P5 | P0 | Ожидаемый результат: корректный звонок. |
| `call_rude.json` | P5 | P0 | Ожидаемый результат: нарушение вежливости. |
| `call_unresolved.json` | P5 | P0 | Ожидаемый результат: вопрос не решён. |
