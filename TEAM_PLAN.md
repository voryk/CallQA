# План работ на 5 человек — CallGuard AI

Основа: раздел 10–13 `PROJECT_PLAN_CallGuard_AI.md`. Срок MVP — 4 дня. Файлов в каркасе: 188. Каждый файл назначен одному владельцу; в общих файлах (например `requirements.txt`) остальные участники правят через PR.

## Сводка

| № | Роль | Файлов | из них P0 |
|---|---|---|---|
| 1 | Backend Lead / PostgreSQL / Auth | 58 | 54 |
| 2 | AI Lead / Speech-to-Text / NLP | 18 | 13 |
| 3 | Frontend Lead / UX / Dashboard | 50 | 45 |
| 4 | Infrastructure / Queues / Security | 34 | 25 |
| 5 | Product / KPI / QA / Integration | 28 | 24 |

## Контрольные точки
- **Конец дня 1:** сервисы запускаются, зафиксированы API-контракт (участник 1) и AI-контракт `ai_types.py` (участник 2).
- **День 2:** один звонок проходит весь backend-конвейер.
- **День 3:** весь сценарий доступен через UI.
- **День 4:** повторяемая демонстрация и измеренные показатели.

## Порядок интеграции
1. Ветки `feature/<module>`, PR с ревью, `main` всегда запускается.
2. Схема БД меняется только через Alembic; контракты согласуются до интеграции.
3. До готовности моделей все работают с заглушками `services/fakes.py`; результат заглушек маркируется «демо».
4. Ежедневная интеграция, утром стендап, вечером демонстрация.

## Приоритеты
- **P0:** offline, форматы, очередь, STT, транскрипт с таймкодами, объяснимая оценка, дашборд, CSV/JSON, ошибки, тест полного цикла.
- **P1:** роли и защищённая выдача аудио, массовая загрузка, настройка KPI, динамика, retry, аудит, ручная проверка.
- **P2:** продвинутая диаризация, интеграции, SSO/MFA, PDF, высокая доступность.
- Правило: не жертвовать P0 ради P2.

## Критерии приёмки и ответственные

| Критерий | Ответственный | Где реализуется |
|---|---|---|
| Запуск по README без внешних AI API | П4 + П5 | infrastructure/docker-compose.yml, README.md |
| WAV/MP3/OGG принимаются и расшифровываются | П2 | services/audio.py, transcription.py |
| 5 файлов в очереди, интерфейс не блокируется | П4 + П3 | workers/*, QueueStatus.tsx, usePolling.ts |
| Сегменты расшифровки с таймкодами | П2 + П1 | transcription.py, result_repository.py |
| Оценка: критерии, балл, объяснения, рекомендации | П2 | evaluation.py, rules_engine.py |
| Сомнительные выводы помечены | П2 + П3 | rules_engine.py, EvaluationPanel.tsx |
| Дашборд на реальных данных | П5 + П3 | analytics_service.py, DashboardPage.tsx |
| CSV/JSON с нужными полями и null | П5 + П1 | reports.py, schemas/report.py |
| Права проверяются на сервере | П1 | core/permissions.py, api/deps.py |
| Данные переживают перезапуск, ошибки видны | П4 + П1 | workers/recovery.py, db/* |
| Замер 10-минутной записи | П2 | benchmark_stt.py, docs/benchmark.md |
| Тест без интернета | П4 + П5 | offline_check.sh, test_offline_mode.py |
| Автотесты, инструкции, ограничения | П5 | docs/testing.md, docs/limitations.md |

---

## Участник 1 — Backend Lead / PostgreSQL / Auth

**Зона владения:** `backend/app/api`, `backend/app/db`, `backend/app/schemas`, Alembic; плюс `core/security.py`, `permissions.py`, `exceptions.py`.

**Задачи:**

1. Поднять FastAPI, SQLAlchemy, PostgreSQL, миграции.
2. Реализовать модели пользователей, операторов, звонков, сегментов, оценок.
3. Реализовать авторизацию, хеширование паролей, роли и проверки прав.
4. Реализовать API загрузки, списков, деталей и выдачи аудио.
5. Согласовать DTO и OpenAPI с frontend и AI-командой.
6. Добавить тесты API и разграничения доступа.

**План по дням:**

| День 1 | День 2 | День 3 | День 4 |
|---|---|---|---|
| БД, миграции, API-контракт | Загрузка, auth, calls API | RBAC, API оценок, исправления | Исправления, стабилизация |

**Готово, когда:** API работает с реальной БД; запрещён доступ к чужим данным; Swagger соответствует контрактам; миграции применяются на чистой БД.

**Зависимости:** Участник 2 (ai_types для хранения результатов), участник 3 (DTO), участник 4 (storage и очередь для POST /calls), участник 5 (services/metrics и reports для эндпоинтов аналитики).

**Файлы для заполнения (58, из них P0: 54):**

| Файл | Прио | Что нужно сделать |
|---|---|---|
| `backend/app/__init__.py` | P0 | Пакет приложения. |
| `backend/app/main.py` | P0 | Точка входа FastAPI: фабрика приложения, подключение роутеров /api/v1, middleware, обработчики ошибок, OpenAPI. |
| `backend/app/api/__init__.py` | P0 | Пакет HTTP-слоя. |
| `backend/app/api/deps.py` | P0 | Зависимости FastAPI: сессия БД, текущий пользователь, проверка роли и владения ресурсом. |
| `backend/app/api/router.py` | P0 | Сборка всех роутеров под префикс /api/v1. |
| `backend/app/api/auth.py` | P0 | POST /auth/login, GET /auth/me, смена пароля. |
| `backend/app/api/calls.py` | P0 | POST /calls (загрузка, постановка в очередь), GET /calls, /calls/{id}, /audio, /transcript, /evaluation, POST /calls/{id}/retry. |
| `backend/app/api/operators.py` | P0 | GET /operators с учётом прав (руководитель — своя группа). |
| `backend/app/api/analytics.py` | P0 | GET /analytics/overview и /analytics/trends; тонкий слой над services/analytics_service.py. |
| `backend/app/api/reports.py` | P0 | GET /reports/export?format=csv или json; тонкий слой над services/reports.py. |
| `backend/app/api/settings.py` | P1 | GET/PUT /settings/evaluation-profile (запись только админ). |
| `backend/app/api/health.py` | P0 | GET /health: API, БД, Redis, доступность моделей. |
| `backend/app/core/__init__.py` | P0 | Пакет ядра. |
| `backend/app/core/security.py` | P0 | Хеширование паролей (argon2), выпуск и проверка токенов/сессий. |
| `backend/app/core/permissions.py` | P0 | Матрица ролей admin/manager/operator и функции проверки доступа к звонку, аудио, отчёту. |
| `backend/app/core/exceptions.py` | P0 | Исключения домена и единый контракт ошибки (код, detail, request_id). |
| `backend/app/db/__init__.py` | P0 | Пакет БД. |
| `backend/app/db/base.py` | P0 | Declarative Base, UUID-ключи, общие поля created_at. |
| `backend/app/db/session.py` | P0 | Engine и фабрика сессий SQLAlchemy 2 к PostgreSQL. |
| `backend/app/db/seed.py` | P0 | Начальные данные: администратор, демо-руководитель/оператор, профиль оценки по умолчанию. |
| `backend/app/db/models/__init__.py` | P0 | Экспорт моделей для Alembic. |
| `backend/app/db/models/user.py` | P0 | Таблица users: логин, password_hash, роль, active. |
| `backend/app/db/models/operator.py` | P0 | Таблица operators: имя, команда, связь с пользователем. |
| `backend/app/db/models/call.py` | P0 | Таблица calls: оператор, загрузил, время, длительность, формат, storage_key, статус, ошибка. |
| `backend/app/db/models/transcript_segment.py` | P0 | Таблица transcript_segments: start/end, speaker, текст, confidence (nullable). |
| `backend/app/db/models/evaluation_profile.py` | P0 | Таблица evaluation_profiles: версия, веса и правила в JSON, признак active. |
| `backend/app/db/models/evaluation.py` | P0 | Таблица evaluations: звонок, профиль, версия модели, балл, резюме, reviewed_by; хранится история оценок. |
| `backend/app/db/models/criterion_score.py` | P0 | Таблица criterion_scores: критерий, балл, evidence_json. |
| `backend/app/db/models/violation.py` | P0 | Таблица violations: критерий, серьёзность, таймкоды, объяснение, рекомендация. |
| `backend/app/db/models/audit_event.py` | P0 | Таблица audit_events: кто, действие, ресурс, время, metadata_json. |
| `backend/app/schemas/__init__.py` | P0 | Пакет DTO. |
| `backend/app/schemas/common.py` | P0 | Пагинация, ErrorResponse (detail, request_id), общие типы. |
| `backend/app/schemas/auth.py` | P0 | Схемы логина, токена, смены пароля. |
| `backend/app/schemas/user.py` | P0 | Схемы пользователя и роли. |
| `backend/app/schemas/operator.py` | P0 | Схемы оператора. |
| `backend/app/schemas/call.py` | P0 | Схемы звонка: создание, список, детали, статус. |
| `backend/app/schemas/transcript.py` | P0 | Схемы сегментов расшифровки. |
| `backend/app/schemas/evaluation.py` | P0 | Схемы оценки, критериев, нарушений, рекомендаций. |
| `backend/app/schemas/analytics.py` | P0 | Схемы overview и trends. |
| `backend/app/schemas/report.py` | P0 | Схема строки экспорта (call_id, operator_id, started_at, duration_sec, score, violation_rate, response_time_sec, sentiment, status, criteria, violations). |
| `backend/app/schemas/settings.py` | P1 | Схемы профиля оценки (веса, правила). |
| `backend/app/services/call_service.py` | P0 | Создание звонка, смена статусов, фильтрация списка по правам, повторная обработка. |
| `backend/app/services/auth_service.py` | P0 | Проверка учётных данных, выдача токенов, смена пароля. |
| `backend/app/services/result_repository.py` | P0 | Сохранение результатов AI (сегменты, оценка, критерии, нарушения) в БД, история оценок, ручная проверка руководителем. |
| `backend/alembic.ini` | P0 | Конфигурация Alembic. |
| `backend/alembic/env.py` | P0 | Окружение миграций (подключение к БД, metadata). |
| `backend/alembic/script.py.mako` | P0 | Шаблон файла миграции. |
| `backend/alembic/versions/0001_initial.py` | P0 | Первая миграция: все таблицы, внешние ключи, индексы по датам/операторам/статусам. |
| `backend/requirements.txt` | P0 | Зависимости backend (остальные участники добавляют через PR). |
| `backend/requirements-dev.txt` | P0 | Зависимости для тестов и линтеров. |
| `backend/tests/__init__.py` | P0 | Пакет тестов. |
| `backend/tests/conftest.py` | P0 | Фикстуры: тестовая БД, клиент httpx, пользователи по ролям. |
| `backend/tests/test_auth.py` | P0 | Вход, неверный пароль, смена пароля, хеширование. |
| `backend/tests/test_permissions.py` | P0 | Оператор не видит чужие звонки и аудио; руководитель — только свою группу. |
| `backend/tests/test_calls_api.py` | P0 | Загрузка, список, детали, фильтры, пагинация, ошибки. |
| `backend/tests/test_migrations.py` | P0 | Миграции применяются на чистой БД. |
| `docs/api.md` | P1 | Описание API-контрактов, формат ошибок, примеры. |
| `docs/data-model.md` | P1 | ER-схема и описание таблиц. |

---

## Участник 2 — AI Lead / Speech-to-Text / NLP

**Зона владения:** `services/transcription.py`, `evaluation.py`, `audio.py` и связанные модули AI.

**Задачи:**

1. Подключить FFmpeg и faster-whisper CPU int8.
2. Обеспечить распознавание WAV/MP3/OGG, сегменты с таймкодами.
3. Подготовить базовый движок KPI с объяснениями и статусом «неизвестно».
4. Подключить Ollama/Qwen как опциональный локальный анализатор с JSON-валидацией и таймаутами.
5. Отдельно оценить качество распознавания и время обработки 1/5/10 минут.
6. Подготовить безопасную стратегию speaker labels; не обещать точную диаризацию без проверки.

**План по дням:**

| День 1 | День 2 | День 3 | День 4 |
|---|---|---|---|
| FFmpeg, STT прототип | STT + rule-based оценка | LLM опционально, замеры | Оптимизация, тест 10 мин |

**Готово, когда:** `process_audio(path)` выдаёт валидные сегменты; `evaluate(transcript, profile)` выдаёт структурированный результат; тесты работают без внешних сервисов.

**Зависимости:** Участник 1 (сохранение результатов), участник 4 (вызов pipeline из задачи worker), участник 5 (критерии и формулы).

**Файлы для заполнения (18, из них P0: 13):**

| Файл | Прио | Что нужно сделать |
|---|---|---|
| `backend/app/services/ai_types.py` | P0 | Контракт AI-модулей: TranscriptResult, Segment, EvaluationResult, CriterionResult, ViolationResult. Фиксируется в первый день. |
| `backend/app/services/audio.py` | P0 | FFmpeg: определение реального типа файла, длительность, нормализация WAV/MP3/OGG в 16 кГц mono. |
| `backend/app/services/transcription.py` | P0 | faster-whisper (CPU int8): process_audio(path) возвращает сегменты с start/end и confidence. |
| `backend/app/services/speakers.py` | P1 | Стратегия меток говорящих: роли только для двухканальной записи, иначе «говорящий 1/2» или «не определён». |
| `backend/app/services/evaluation.py` | P0 | evaluate(transcript, profile): выбор движка, резервный rule-based, версия правил/модели. |
| `backend/app/services/rules_engine.py` | P0 | Rule-based оценка по критериям с цитатой, таймкодом или статусом «недостаточно данных». |
| `backend/app/services/llm_ollama.py` | P1 | Клиент локальной Ollama/Qwen: JSON-валидация, таймауты, ретраи, откат на правила. |
| `backend/app/services/prompts.py` | P1 | Промпты оценки и рекомендаций на русском. |
| `backend/app/services/pipeline.py` | P0 | process_call(call_id): аудио → STT → оценка → сохранение результата; вызывается задачей worker. |
| `backend/app/services/fakes.py` | P0 | Заглушки STT и оценщика для тестов и независимой работы frontend/backend. |
| `backend/tests/test_audio.py` | P0 | Форматы WAV/MP3/OGG, подмена расширения, битые файлы. |
| `backend/tests/test_transcription.py` | P0 | Структура сегментов, таймкоды; тест на реальной модели помечен slow. |
| `backend/tests/test_rules_engine.py` | P0 | Критерии, доказательства, статус «недостаточно данных». |
| `backend/tests/test_llm_ollama.py` | P1 | Тесты клиента с моком: невалидный JSON, таймаут, откат. |
| `backend/tests/test_pipeline.py` | P0 | Конвейер целиком на заглушках, обработка ошибок. |
| `infrastructure/scripts/benchmark_stt.py` | P0 | Замер времени и качества на записях 1/5/10 минут. |
| `docs/benchmark.md` | P0 | Результаты замеров на i5-1235U относительно цели 3–5 минут. |
| `docs/ai-design.md` | P1 | Описание AI-модуля: выбор моделей, диаризация, ограничения, как не выдавать вероятность за факт. |

---

## Участник 3 — Frontend Lead / UX / Dashboard

**Зона владения:** `frontend/`.

**Задачи:**

1. Создать React + TypeScript + Tailwind, маршрутизацию, API-клиент.
2. Сделать Login, Dashboard, Calls, CallDetails, Operators, Settings.
3. Реализовать drag-and-drop загрузку, прогресс, очередь и статусы.
4. Сделать аудиоплеер с таймкодами, подсветку сегментов, оценки и нарушения.
5. Реализовать фильтры, графики, адаптивность, обработку пустых/ошибочных состояний.
6. Подключить реальные API, не оставлять фиктивные данные в итоговом режиме.

**План по дням:**

| День 1 | День 2 | День 3 | День 4 |
|---|---|---|---|
| Макет экранов, React scaffold | Загрузка, список, детали | Дашборд, плеер, интеграция | Полировка UX, ошибки |

**Готово, когда:** Пользователь проходит весь сценарий без Swagger; UI корректно отображает загрузку, ошибки и завершённые задания.

**Зависимости:** Участник 1 (OpenAPI и DTO; до готовности API работать на моках, помеченных «демо»), участник 5 (data-testid для e2e).

**Файлы для заполнения (50, из них P0: 45):**

| Файл | Прио | Что нужно сделать |
|---|---|---|
| `frontend/package.json` | P0 | Зависимости и скрипты: React, TypeScript, Vite, Tailwind, Recharts, ESLint. |
| `frontend/tsconfig.json` | P0 | Настройки TypeScript (strict). |
| `frontend/tsconfig.node.json` | P0 | Настройки TypeScript для Vite. |
| `frontend/vite.config.ts` | P0 | Сборка и прокси /api на backend. |
| `frontend/tailwind.config.ts` | P0 | Тема и токены Tailwind. |
| `frontend/postcss.config.js` | P0 | PostCSS для Tailwind. |
| `frontend/eslint.config.js` | P0 | Правила ESLint. |
| `frontend/index.html` | P0 | HTML-оболочка. |
| `frontend/src/main.tsx` | P0 | Точка входа React. |
| `frontend/src/App.tsx` | P0 | Маршрутизация и защищённые маршруты. |
| `frontend/src/index.css` | P0 | Подключение Tailwind и глобальные стили. |
| `frontend/src/vite-env.d.ts` | P0 | Типы окружения Vite. |
| `frontend/src/types/api.ts` | P0 | Типы DTO, повторяющие OpenAPI backend. |
| `frontend/src/types/index.ts` | P0 | Реэкспорт типов. |
| `frontend/src/api/client.ts` | P0 | HTTP-клиент: токен, разбор ошибки (detail, request_id). |
| `frontend/src/api/auth.ts` | P0 | Вызовы /auth/*. |
| `frontend/src/api/calls.ts` | P0 | Вызовы /calls*: загрузка, список, детали, транскрипт, оценка, retry, URL аудио. |
| `frontend/src/api/operators.ts` | P1 | Вызов /operators. |
| `frontend/src/api/analytics.ts` | P0 | Вызовы /analytics/*. |
| `frontend/src/api/reports.ts` | P0 | Скачивание экспорта CSV/JSON. |
| `frontend/src/api/settings.ts` | P1 | Вызовы профиля оценки. |
| `frontend/src/hooks/useAuth.tsx` | P0 | Контекст авторизации и роль пользователя. |
| `frontend/src/hooks/usePolling.ts` | P0 | Периодический опрос статусов очереди без блокировки интерфейса. |
| `frontend/src/hooks/useCalls.ts` | P0 | Загрузка списка звонков с фильтрами. |
| `frontend/src/utils/format.ts` | P0 | Форматирование дат, длительности, баллов, null как «недоступно». |
| `frontend/src/pages/LoginPage.tsx` | P0 | Страница входа. |
| `frontend/src/pages/DashboardPage.tsx` | P0 | Дашборд: число звонков, средний балл, доля нарушений, критерии, динамика, проблемные звонки. |
| `frontend/src/pages/CallsPage.tsx` | P0 | Загрузка файлов, очередь и список звонков с фильтрами. |
| `frontend/src/pages/CallDetailsPage.tsx` | P0 | Плеер, транскрипт, поиск по тексту, оценка, нарушения с таймкодами, retry. |
| `frontend/src/pages/OperatorsPage.tsx` | P1 | Рейтинг операторов с числом проанализированных звонков. |
| `frontend/src/pages/SettingsPage.tsx` | P1 | Редактор весов и правил (админ), очередь и ошибки. |
| `frontend/src/components/layout/AppLayout.tsx` | P0 | Каркас: меню по роли, шапка, выход. |
| `frontend/src/components/auth/ProtectedRoute.tsx` | P0 | Защита маршрутов по авторизации и роли. |
| `frontend/src/components/calls/UploadDropzone.tsx` | P0 | Drag-and-drop, пакетная загрузка, проверка формата и размера, прогресс. |
| `frontend/src/components/calls/QueueStatus.tsx` | P0 | Список файлов в очереди и их статусы. |
| `frontend/src/components/calls/StatusBadge.tsx` | P0 | Метки queued/processing/completed/failed. |
| `frontend/src/components/calls/CallsTable.tsx` | P0 | Таблица звонков с сортировкой и пагинацией. |
| `frontend/src/components/calls/CallFilters.tsx` | P0 | Фильтры: период, оператор, статус, диапазон оценки, критерий. |
| `frontend/src/components/calls/AudioPlayer.tsx` | P0 | Плеер с переходом по таймкоду. |
| `frontend/src/components/calls/TranscriptView.tsx` | P0 | Сегменты с подсветкой текущего, говорящие, поиск. |
| `frontend/src/components/calls/EvaluationPanel.tsx` | P0 | Итоговый балл, критерии, основания, пометка «недостаточно данных». |
| `frontend/src/components/calls/ViolationList.tsx` | P0 | Нарушения с цитатой, таймкодом и рекомендацией. |
| `frontend/src/components/charts/KpiCards.tsx` | P0 | Карточки показателей. |
| `frontend/src/components/charts/CriteriaChart.tsx` | P0 | Распределение по критериям. |
| `frontend/src/components/charts/TrendChart.tsx` | P0 | Динамика качества по датам. |
| `frontend/src/components/settings/ProfileEditor.tsx` | P1 | Форма весов и правил. |
| `frontend/src/components/common/EmptyState.tsx` | P0 | Пустые состояния. |
| `frontend/src/components/common/ErrorState.tsx` | P0 | Ошибки с request_id. |
| `frontend/src/components/common/Spinner.tsx` | P0 | Индикатор загрузки. |
| `frontend/src/components/common/Pagination.tsx` | P0 | Пагинация. |

---

## Участник 4 — Infrastructure / Queues / Security

**Зона владения:** `backend/app/workers`, `infrastructure/`, `.env.example`, CI; плюс `core/config.py`, `logging.py`, `middleware.py`, `services/storage.py`, `audit.py`, `retention.py`.

**Задачи:**

1. Поднять PostgreSQL/Redis через Docker Compose с volume и healthcheck.
2. Реализовать Redis/RQ worker и постановку задач, синхронизацию статусов с PostgreSQL.
3. Реализовать ограничение параллелизма, retry, таймауты, восстановление зависших заданий.
4. Настроить защищённое файловое хранилище, лимиты загрузки, очистку временных файлов.
5. Добавить логи без содержимого звонков, аудит, конфигурацию секретов, базовые security headers.
6. Подготовить инструкции локального и offline-запуска, CI-проверки, резервное копирование для пилота.

**План по дням:**

| День 1 | День 2 | День 3 | День 4 |
|---|---|---|---|
| Docker, Redis, worker scaffold | RQ, статусы, хранение | Retry, аудит, offline-тест | Восстановление, развёртывание |

**Готово, когда:** Несколько файлов становятся в очередь, worker их обрабатывает, ошибки не теряются, после перезапуска сервисы поднимаются без потери данных.

**Зависимости:** Участник 1 (модели и сессия БД), участник 2 (pipeline.process_call), участник 5 (офлайн-тест).

**Файлы для заполнения (34, из них P0: 25):**

| Файл | Прио | Что нужно сделать |
|---|---|---|
| `.env.example` | P0 | Пример настроек без секретов: БД, Redis, лимиты, модели, срок хранения. |
| `.gitignore` | P0 | Исключает секреты, аудио, модели, тома, node_modules. |
| `.dockerignore` | P0 | Исключения для сборки образов. |
| `.github/workflows/ci.yml` | P0 | CI: Ruff, ESLint, pytest, сборка фронтенда, проверка миграций. |
| `infrastructure/docker-compose.yml` | P0 | PostgreSQL, Redis, backend, worker, frontend, опционально Ollama; volume, healthcheck, внутренняя сеть. |
| `infrastructure/docker/backend.Dockerfile` | P0 | Образ backend с ffmpeg. |
| `infrastructure/docker/worker.Dockerfile` | P0 | Образ AI-worker с faster-whisper. |
| `infrastructure/docker/frontend.Dockerfile` | P0 | Сборка фронтенда и раздача через nginx. |
| `infrastructure/nginx/nginx.conf` | P1 | Прокси, security headers, подготовка к TLS, лимит тела запроса. |
| `infrastructure/scripts/download_models.ps1` | P0 | Предзагрузка моделей на Windows (дальше работа офлайн). |
| `infrastructure/scripts/download_models.sh` | P1 | То же для Linux-сервера. |
| `infrastructure/scripts/offline_check.sh` | P0 | Проверка работы при отключённом интернете. |
| `infrastructure/scripts/backup.sh` | P1 | Резервная копия БД и хранилища. |
| `infrastructure/scripts/restore.sh` | P1 | Восстановление из копии и проверка. |
| `backend/pyproject.toml` | P0 | Настройки Ruff и pytest. |
| `backend/app/core/config.py` | P0 | Настройки из .env (pydantic-settings), без секретов в коде. |
| `backend/app/core/logging.py` | P0 | Логи без содержимого звонков, с request_id. |
| `backend/app/core/middleware.py` | P0 | request_id и базовые security headers. |
| `backend/app/services/storage.py` | P0 | Защищённое хранилище вне статики: безопасные имена, лимиты, временные файлы, выдача по storage_key. |
| `backend/app/services/audit.py` | P1 | Запись audit_events без секретов. |
| `backend/app/services/retention.py` | P1 | Очистка аудио, транскриптов и отчётов по сроку хранения. |
| `backend/app/workers/__init__.py` | P0 | Пакет worker. |
| `backend/app/workers/queue.py` | P0 | Подключение Redis/RQ, постановка задач. |
| `backend/app/workers/tasks.py` | P0 | Задача обработки звонка: статусы в PostgreSQL, вызов pipeline, таймаут, ошибки. |
| `backend/app/workers/recovery.py` | P0 | Сверка зависших задач после перезапуска. |
| `backend/app/workers/worker.py` | P0 | Запуск worker, по умолчанию один процесс. |
| `backend/tests/test_storage.py` | P0 | Безопасные имена, лимиты, очистка временных файлов. |
| `backend/tests/test_queue.py` | P0 | Постановка, порядок, статусы, retry. |
| `backend/tests/test_recovery.py` | P0 | Восстановление после падения. |
| `backend/tests/test_audit.py` | P1 | Аудит без чувствительных данных. |
| `backend/tests/test_security_headers.py` | P1 | Заголовки безопасности и request_id. |
| `docs/security.md` | P0 | Модель безопасности, роли, хранение, логи. |
| `docs/deployment.md` | P0 | Запуск на Windows и Linux, офлайн-установка, восстановление. |
| `docs/pilot-readiness.md` | P2 | Чек-лист банковского пилота: ИБ, ПДн, TLS, ключи, SSO, резервирование. |

---

## Участник 5 — Product / KPI / QA / Integration

**Зона владения:** критерии качества, тестовые данные, `services/metrics.py`, `analytics_service.py`, `reports.py`, интеграционные и e2e тесты, документация.

**Задачи:**

1. Утвердить измеримые KPI, веса, формулы, обработку «недостаточно данных».
2. Реализовать агрегирование аналитики и CSV/JSON экспорт вместе с backend-разработчиком.
3. Подготовить синтетические тестовые звонки с ожидаемыми результатами и согласиями на использование.
4. Написать интеграционные тесты «загрузка → очередь → STT → оценка → экспорт».
5. Проверить права доступа, корректность расчётов, ошибки и offline-режим.
6. Собрать демонстрационный сценарий, презентацию, метрики скорости и список известных ограничений.

**План по дням:**

| День 1 | День 2 | День 3 | День 4 |
|---|---|---|---|
| KPI-спецификация, тестовые звонки | Аналитика, экспорт, API-тесты | E2E, проверка KPI, интеграция | Полный прогон, демо, документация |

**Готово, когда:** Есть воспроизводимая демонстрация, KPI проверяются тестами, отчёты открываются, ограничения честно задокументированы.

**Зависимости:** Участник 1 (эндпоинты аналитики и отчётов), участник 2 (формат оценки), участник 3 (селекторы для Playwright), участник 4 (окружение).

**Файлы для заполнения (28, из них P0: 24):**

| Файл | Прио | Что нужно сделать |
|---|---|---|
| `README.md` | P0 | Запуск по шагам, структура, ссылки на документацию. |
| `AGENTS.md` | P0 | Правила для Codex/агентов: приоритеты, запреты, порядок работы. |
| `PROJECT_PLAN_CallGuard_AI.md` | P0 | Исходное ТЗ и план. |
| `docs/kpi-spec.md` | P0 | Формулы, веса, критерии, обработка «недостаточно данных». |
| `docs/testing.md` | P0 | Стратегия тестов и запуск. |
| `docs/limitations.md` | P0 | Известные ограничения продукта. |
| `docs/demo-scenario.md` | P0 | Сценарий демонстрации и метрики скорости. |
| `backend/app/services/metrics.py` | P0 | Формулы KPI: итоговый балл, violation_rate, response_time_sec только при корректных метках, sentiment nullable. |
| `backend/app/services/analytics_service.py` | P0 | Агрегаты для дашборда с фильтрами и учётом прав. |
| `backend/app/services/reports.py` | P0 | Экспорт CSV/JSON с null вместо выдуманных значений; PDF позже. |
| `backend/tests/test_metrics.py` | P0 | Проверка формул и граничных случаев. |
| `backend/tests/test_analytics.py` | P0 | Агрегаты на тестовых данных. |
| `backend/tests/test_reports.py` | P0 | Поля CSV/JSON и null. |
| `backend/tests/integration/__init__.py` | P0 | Пакет интеграционных тестов. |
| `backend/tests/integration/conftest.py` | P0 | Окружение интеграционных тестов. |
| `backend/tests/integration/test_pipeline_e2e.py` | P0 | Загрузка, очередь, STT, оценка, экспорт. |
| `backend/tests/integration/test_access_control.py` | P0 | Сквозная проверка прав. |
| `backend/tests/integration/test_offline_mode.py` | P0 | Проверка отсутствия внешних вызовов. |
| `e2e/package.json` | P1 | Зависимости Playwright. |
| `e2e/playwright.config.ts` | P1 | Настройки Playwright. |
| `e2e/tests/full_scenario.spec.ts` | P1 | Вход, загрузка, очередь, транскрипт, оценка, дашборд, экспорт. |
| `e2e/tests/access.spec.ts` | P1 | Оператор не видит чужое. |
| `test_data/README.md` | P0 | Правила тестовых данных: синтетические записи, согласия, запрет реальных клиентов. |
| `test_data/manifest.json` | P0 | Список тестовых записей и ожидания. |
| `test_data/expected/call_ok.json` | P0 | Ожидаемый результат: корректный звонок. |
| `test_data/expected/call_rude.json` | P0 | Ожидаемый результат: нарушение вежливости. |
| `test_data/expected/call_unresolved.json` | P0 | Ожидаемый результат: вопрос не решён. |
| `test_data/audio/.gitkeep` | P0 | Каталог для синтетических WAV/MP3/OGG. |
