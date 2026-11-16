# Архитектура: CallQA — локальная платформа контроля качества звонков

Заказчик: ПАО КБ «Центр-инвест». Прототип по ТЗ «Система для автоматизации контроля качества и аналитики звонков для предпринимателей».

## 1. Принципы
- **Полностью локально:** аудио, расшифровки и оценки не покидают машину; LLM и STT работают офлайн.
- **Запуск на ноутбуке:** SQLite, очередь в БД (без Redis/Kafka), один `docker compose up`.
- **Простота внедрения:** веб-интерфейс, готовый скрипт и рубрика «из коробки».

## 2. Схема
```
Браузер (React) ──► nginx ──► FastAPI (API, auth, экспорт)
                                  │  SQLite: calls, transcripts, evaluations, jobs
                                  ▼
                          Очередь (таблица jobs)
                                  ▼
                    Worker ─► Pipeline:
        валидация → ffmpeg 16кГц → STT (faster-whisper) → диаризация
        → время ответа / тональность / скрипт / нарушения (+маскирование ПДн)
        → оценка по рубрике (локальная LLM, Ollama) → рекомендации → БД
```

## 3. Стек
| Слой | Технология | Почему |
|---|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy, Alembic | Быстрая разработка, async, экосистема ML |
| STT | faster-whisper (основной), Vosk (резерв) | Качество на русском, работа на CPU |
| Оценка | Ollama + локальная модель (Qwen2.5 7B и т.п.) | Офлайн, понимает русский, JSON-вывод |
| Очередь | Таблица `jobs` + процесс-воркер | Нет внешних зависимостей |
| БД | SQLite (PostgreSQL опционально) | Ноутбук/локальный сервер |
| Frontend | React + TypeScript + Vite + Recharts | Дашборды, SPA |
| Деплой | Docker Compose, systemd, nftables | Изоляция сети |

## 4. Соответствие ТЗ
| Требование ТЗ | Где реализуется |
|---|---|
| Расшифровка Whisper/Vosk | `pipeline/stt/*` |
| Оценка: вежливость, полнота, скрипт, решение проблемы | `pipeline/scoring/*`, `analysis/script_checker.py` |
| Рекомендации оператору | `scoring/recommendations.py` |
| Без передачи данных вовне | `security/offline_guard.py`, internal-сеть в compose, `deploy/firewall` |
| Локальное развёртывание | `docker-compose.yml`, `docs/deployment.md` |
| Форматы WAV/MP3/OGG | `pipeline/audio/validator.py`, `security/upload_guard.py` |
| Веб-интерфейс, дашборд, экспорт | `frontend/src/pages/*`, `api/routes/dashboard.py`, `exports.py` |
| KPI в CSV/JSON | `services/export_service.py`, `schemas/export.py` |
| 10 мин ≤ 3–5 мин | выбор модели, `resource_guard.py`, `scripts/benchmark.py` |
| Очередь | `queue/*`, `api/routes/queue.py` |

## 5. Описание файлов


### Корень проекта

| Файл | Назначение |
|---|---|
| `README.md` | Быстрый старт: установка, запуск одной командой, требования к железу, ссылки на docs/. |
| `ARCHITECTURE.md` | Этот документ: схема системы, стек, описание каждого файла. |
| `docker-compose.yml` | Локальный запуск всех сервисов (backend, worker, frontend, ollama) без выхода во внешнюю сеть. |
| `Makefile` | Короткие команды: make up, make down, make models, make test, make seed. |
| `.env.example` | Шаблон настроек (пути, модель Whisper, модель LLM, лимиты очереди, секреты). |
| `.gitignore` | Исключает аудио, веса моделей, БД, .env, node_modules. |

### docs/ — документация

| Файл | Назначение |
|---|---|
| `docs/tz.md` | Текст технического задания заказчика (Центр-инвест) и трассировка требований к модулям. |
| `docs/api.md` | Описание REST API: эндпоинты, примеры запросов/ответов. |
| `docs/metrics.md` | Определения метрик: вежливость, полнота ответа, соблюдение скрипта, решение проблемы, тональность, среднее время ответа, % нарушений; формулы расчёта и шкалы. |
| `docs/security.md` | Модель безопасности: локальная обработка, изоляция от интернета, хранение, маскирование ПДн, роли. |
| `docs/deployment.md` | Развёртывание на ноутбуке/локальном сервере, офлайн-установка моделей, требования CPU/GPU/RAM. |
| `docs/data-model.md` | ER-схема БД и описание таблиц. |
| `docs/benchmark.md` | Замеры скорости (цель: звонок 10 мин за ≤3–5 мин) и методика проверки. |

### backend/ — серверная часть (Python, FastAPI)

| Файл | Назначение |
|---|---|
| `backend/pyproject.toml` | Зависимости и настройки инструментов (fastapi, sqlalchemy, faster-whisper, pydub, httpx, pytest, ruff). |
| `backend/Dockerfile` | Образ backend/worker с ffmpeg и Python-зависимостями. |
| `backend/alembic.ini` | Конфигурация миграций БД. |
| `backend/migrations/env.py` | Окружение Alembic. |
| `backend/migrations/versions/0001_init.py` | Первая миграция: создание всех таблиц. |

### backend/app/ — ядро приложения

| Файл | Назначение |
|---|---|
| `backend/app/__init__.py` | Пакет приложения. |
| `backend/app/main.py` | Точка входа FastAPI: создание приложения, подключение роутеров, CORS, раздача статики фронтенда. |
| `backend/app/config.py` | Загрузка настроек из .env (pydantic-settings). |
| `backend/app/db.py` | Подключение к БД (SQLite по умолчанию, PostgreSQL опционально), фабрика сессий. |
| `backend/app/logging_config.py` | Настройка логов без записи содержимого разговоров. |

### backend/app/api/ — HTTP-слой

| Файл | Назначение |
|---|---|
| `backend/app/api/__init__.py` | Пакет API. |
| `backend/app/api/deps.py` | Зависимости FastAPI: сессия БД, текущий пользователь, проверка роли. |
| `backend/app/api/router.py` | Сборка всех роутеров под префикс /api/v1. |
| `backend/app/api/routes/__init__.py` | Пакет маршрутов. |
| `backend/app/api/routes/health.py` | GET /health — состояние сервиса, очереди, моделей (готовность Whisper/LLM). |
| `backend/app/api/routes/auth.py` | Вход/выход, выдача токена, текущий пользователь. |
| `backend/app/api/routes/calls.py` | Загрузка аудио (WAV/MP3/OGG, в том числе пакетная), список звонков, карточка звонка, расшифровка, оценка, удаление, повторная обработка. |
| `backend/app/api/routes/queue.py` | Состояние очереди: позиции, статусы, отмена, приоритет, прогресс. |
| `backend/app/api/routes/operators.py` | CRUD операторов, статистика по оператору. |
| `backend/app/api/routes/dashboard.py` | Агрегаты для дашборда: средние оценки, тренды по датам, распределение тональности, топ нарушений. |
| `backend/app/api/routes/exports.py` | Экспорт KPI в CSV/JSON и отчёта по звонку (PDF/HTML). |
| `backend/app/api/routes/scripts.py` | Управление скриптами разговора (чек-листы обязательных фраз/этапов) и критериями оценки. |
| `backend/app/api/routes/settings.py` | Настройки системы: модель STT, модель LLM, параллелизм, язык. |
| `backend/app/api/routes/events.py` | SSE/WebSocket: живое обновление статусов обработки в интерфейсе. |

### backend/app/models/ — ORM-модели (таблицы БД)

| Файл | Назначение |
|---|---|
| `backend/app/models/__init__.py` | Экспорт моделей. |
| `backend/app/models/base.py` | Базовый класс, общие поля (id, created_at). |
| `backend/app/models/user.py` | Пользователь системы (админ, руководитель, оператор-просмотр). |
| `backend/app/models/operator.py` | Оператор контакт-центра (идентификатор, ФИО/псевдоним, группа). |
| `backend/app/models/call.py` | Звонок: файл, формат, длительность, дата/время, оператор, статус обработки. |
| `backend/app/models/transcript.py` | Расшифровка: сегменты с таймкодами, спикер (оператор/клиент), текст, уверенность. |
| `backend/app/models/evaluation.py` | Оценка звонка: баллы по метрикам, тональность, нарушения, рекомендации, итоговый балл. |
| `backend/app/models/script.py` | Скрипт разговора и его пункты (обязательные фразы/этапы). |
| `backend/app/models/job.py` | Задача очереди: тип, статус, приоритет, попытки, ошибка, время начала/конца. |
| `backend/app/models/audit_log.py` | Журнал действий пользователей (кто смотрел/скачал/удалил). |

### backend/app/schemas/ — Pydantic-схемы (контракты API)

| Файл | Назначение |
|---|---|
| `backend/app/schemas/__init__.py` | Экспорт схем. |
| `backend/app/schemas/call.py` | Схемы звонка (создание, список, детали). |
| `backend/app/schemas/transcript.py` | Схемы расшифровки и сегментов. |
| `backend/app/schemas/evaluation.py` | Схемы оценки и рекомендаций. |
| `backend/app/schemas/operator.py` | Схемы оператора и его статистики. |
| `backend/app/schemas/dashboard.py` | Схемы агрегатов дашборда. |
| `backend/app/schemas/export.py` | Схемы строки KPI-экспорта (operator_id, datetime, violation_pct, avg_response_time, sentiment). |
| `backend/app/schemas/queue.py` | Схемы очереди и событий прогресса. |
| `backend/app/schemas/script.py` | Схемы скриптов разговора. |
| `backend/app/schemas/auth.py` | Схемы логина и токена. |

### backend/app/services/ — бизнес-логика

| Файл | Назначение |
|---|---|
| `backend/app/services/__init__.py` | Пакет сервисов. |
| `backend/app/services/call_service.py` | Приём звонка, создание записи, постановка в очередь, удаление. |
| `backend/app/services/storage_service.py` | Локальное хранение аудио и артефактов на диске, TTL и очистка. |
| `backend/app/services/queue_service.py` | Постановка/отмена/приоритизация задач, чтение состояния очереди. |
| `backend/app/services/dashboard_service.py` | Расчёт агрегатов и трендов по периодам/операторам. |
| `backend/app/services/export_service.py` | Формирование CSV/JSON с KPI и отчётов по звонкам. |
| `backend/app/services/operator_service.py` | Операции над операторами и расчёт их рейтинга. |
| `backend/app/services/script_service.py` | Работа со скриптами разговора и критериями. |
| `backend/app/services/auth_service.py` | Проверка паролей, выдача токенов. |
| `backend/app/services/event_bus.py` | Внутренняя шина событий для SSE/WebSocket. |

### backend/app/pipeline/ — конвейер обработки звонка

| Файл | Назначение |
|---|---|
| `backend/app/pipeline/__init__.py` | Пакет конвейера. |
| `backend/app/pipeline/orchestrator.py` | Главный сценарий: валидация → предобработка → STT → диаризация → NLP → оценка → сохранение; обновляет прогресс. |
| `backend/app/pipeline/audio/validator.py` | Проверка формата (WAV/MP3/OGG по сигнатуре, не по расширению), размера, длительности. |
| `backend/app/pipeline/audio/preprocess.py` | Конвертация в 16 кГц mono WAV через ffmpeg, нормализация громкости, обрезка тишины. |
| `backend/app/pipeline/stt/base.py` | Интерфейс STT-движка (transcribe → сегменты с таймкодами). |
| `backend/app/pipeline/stt/whisper_engine.py` | Реализация на faster-whisper (CPU int8 / GPU), модели small/medium. |
| `backend/app/pipeline/stt/vosk_engine.py` | Резервный лёгкий движок Vosk для слабых машин. |
| `backend/app/pipeline/stt/factory.py` | Выбор движка по настройкам. |
| `backend/app/pipeline/diarization/speaker_split.py` | Разделение реплик на оператора и клиента (стерео-каналы или кластеризация эмбеддингов). |
| `backend/app/pipeline/analysis/response_time.py` | Расчёт времени ответа оператора по таймкодам реплик. |
| `backend/app/pipeline/analysis/sentiment.py` | Тональность клиента и оператора (локальная модель/LLM), динамика по ходу звонка. |
| `backend/app/pipeline/analysis/script_checker.py` | Проверка соблюдения скрипта: приветствие, идентификация, обязательные фразы, прощание (правила + семантическое сопоставление). |
| `backend/app/pipeline/analysis/violations.py` | Поиск нарушений (грубость, перебивание, запрещённые слова, пропуск обязательных этапов) и расчёт % нарушений. |
| `backend/app/pipeline/analysis/pii_masker.py` | Маскирование номеров карт, телефонов, паспортных данных в тексте расшифровки. |
| `backend/app/pipeline/scoring/rubric.py` | Рубрика оценки: вежливость, полнота ответа, соблюдение скрипта, решение проблемы; веса и шкалы 0–100. |
| `backend/app/pipeline/scoring/llm_client.py` | Клиент локальной LLM (Ollama, localhost); строгий JSON-ответ, таймауты, ретраи. |
| `backend/app/pipeline/scoring/prompts.py` | Промпты оценки качества и генерации рекомендаций (на русском). |
| `backend/app/pipeline/scoring/evaluator.py` | Запуск оценки по рубрике: LLM + эвристики, валидация ответа модели. |
| `backend/app/pipeline/scoring/aggregator.py` | Сведение частных метрик в итоговый балл звонка. |
| `backend/app/pipeline/scoring/recommendations.py` | Формирование рекомендаций оператору со ссылками на таймкоды в расшифровке. |

### backend/app/queue/ — очередь и воркеры

| Файл | Назначение |
|---|---|
| `backend/app/queue/__init__.py` | Пакет очереди. |
| `backend/app/queue/worker.py` | Процесс-воркер: берёт задачи из очереди БД по приоритету, запускает pipeline, пишет статус; число параллельных задач настраивается. |
| `backend/app/queue/claim.py` | Атомарный захват задачи (без двойной обработки), heartbeat, возврат «зависших» задач. |
| `backend/app/queue/retry.py` | Политика повторов и перевод в статус failed. |
| `backend/app/queue/resource_guard.py` | Ограничение параллелизма по CPU/RAM/GPU, чтобы не перегрузить ноутбук. |

### backend/app/security/ — безопасность

| Файл | Назначение |
|---|---|
| `backend/app/security/__init__.py` | Пакет безопасности. |
| `backend/app/security/passwords.py` | Хеширование паролей (argon2/bcrypt). |
| `backend/app/security/tokens.py` | JWT-токены, срок действия. |
| `backend/app/security/rbac.py` | Роли и права (admin / supervisor / viewer). |
| `backend/app/security/offline_guard.py` | Запрет исходящих соединений кроме localhost; проверка при старте и тест. |
| `backend/app/security/encryption.py` | Шифрование аудио и расшифровок на диске (опционально). |
| `backend/app/security/upload_guard.py` | Защита загрузки: лимит размера, проверка типа, безопасные имена файлов. |

### backend/tests/ — тесты

| Файл | Назначение |
|---|---|
| `backend/tests/conftest.py` | Фикстуры: тестовая БД, клиент API, примеры аудио. |
| `backend/tests/test_audio_validator.py` | Проверка форматов WAV/MP3/OGG и отказов. |
| `backend/tests/test_stt.py` | Тест расшифровки на коротком эталонном файле (WER-порог). |
| `backend/tests/test_response_time.py` | Тест расчёта времени ответа. |
| `backend/tests/test_script_checker.py` | Тесты соблюдения скрипта. |
| `backend/tests/test_scoring.py` | Тесты рубрики и агрегатора (с мок-LLM). |
| `backend/tests/test_queue.py` | Порядок, приоритеты, отсутствие двойной обработки, восстановление после падения. |
| `backend/tests/test_export.py` | Корректность полей CSV/JSON. |
| `backend/tests/test_offline.py` | Подтверждение отсутствия сетевых вызовов наружу. |
| `backend/tests/test_api.py` | Сквозной тест: загрузка → обработка → результат. |

### frontend/ — веб-интерфейс (React + TypeScript + Vite)

| Файл | Назначение |
|---|---|
| `frontend/package.json` | Зависимости и скрипты фронтенда. |
| `frontend/tsconfig.json` | Настройки TypeScript. |
| `frontend/vite.config.ts` | Сборка и прокси /api на backend. |
| `frontend/index.html` | HTML-оболочка приложения. |
| `frontend/Dockerfile` | Сборка статики и раздача через nginx. |
| `frontend/nginx.conf` | Конфиг nginx: статика + проксирование API. |
| `frontend/src/main.tsx` | Точка входа React. |
| `frontend/src/App.tsx` | Каркас приложения и маршрутизация. |
| `frontend/src/api/client.ts` | HTTP-клиент к backend. |
| `frontend/src/api/types.ts` | Типы данных API. |
| `frontend/src/api/events.ts` | Подписка на события прогресса (SSE). |
| `frontend/src/pages/LoginPage.tsx` | Страница входа. |
| `frontend/src/pages/UploadPage.tsx` | Загрузка аудио (drag&drop, пакетная), выбор оператора и скрипта. |
| `frontend/src/pages/QueuePage.tsx` | Очередь обработки: статусы, прогресс, отмена. |
| `frontend/src/pages/CallsPage.tsx` | Список звонков с фильтрами (дата, оператор, оценка, нарушения). |
| `frontend/src/pages/CallDetailPage.tsx` | Карточка звонка: плеер, расшифровка с таймкодами, оценка по метрикам, рекомендации. |
| `frontend/src/pages/DashboardPage.tsx` | Дашборд: KPI, тренды, тональность, рейтинг операторов. |
| `frontend/src/pages/OperatorsPage.tsx` | Операторы и их динамика. |
| `frontend/src/pages/ScriptsPage.tsx` | Редактор скриптов и критериев оценки. |
| `frontend/src/pages/ExportPage.tsx` | Выбор периода/операторов и выгрузка CSV/JSON/отчёта. |
| `frontend/src/pages/SettingsPage.tsx` | Настройки моделей и параллелизма. |
| `frontend/src/components/AudioPlayer.tsx` | Плеер с переходом по клику на реплику. |
| `frontend/src/components/TranscriptView.tsx` | Расшифровка по репликам, подсветка нарушений. |
| `frontend/src/components/ScoreCard.tsx` | Карточка баллов по метрикам. |
| `frontend/src/components/SentimentChart.tsx` | График тональности по времени звонка. |
| `frontend/src/components/TrendChart.tsx` | График трендов на дашборде. |
| `frontend/src/components/QueueTable.tsx` | Таблица очереди. |
| `frontend/src/components/FileDropzone.tsx` | Зона загрузки файлов с проверкой формата. |
| `frontend/src/components/Layout.tsx` | Общий каркас: меню, шапка. |
| `frontend/src/hooks/useCalls.ts` | Загрузка и кэш списка звонков. |
| `frontend/src/hooks/useQueueEvents.ts` | Живые обновления очереди. |
| `frontend/src/styles/global.css` | Глобальные стили и тема. |

### scripts/ — служебные скрипты

| Файл | Назначение |
|---|---|
| `scripts/download_models.sh` | Загрузка весов Whisper и LLM один раз (дальше система работает офлайн). |
| `scripts/seed_demo.py` | Демо-данные: операторы, скрипт, примеры звонков для презентации. |
| `scripts/benchmark.py` | Замер времени обработки 10-минутного звонка. |
| `scripts/offline_check.sh` | Проверка, что при отключённой сети всё работает. |
| `scripts/create_admin.py` | Создание первого администратора. |

### deploy/ — развёртывание

| Файл | Назначение |
|---|---|
| `deploy/systemd/callqa-backend.service` | Юнит systemd для backend на локальном сервере. |
| `deploy/systemd/callqa-worker.service` | Юнит systemd для воркера. |
| `deploy/firewall/nftables.conf` | Правила: блок исходящего трафика, разрешён только LAN/localhost. |

### data/ и models/ — рабочие каталоги (не в git)

| Файл | Назначение |
|---|---|
| `data/audio/.gitkeep` | Хранилище загруженных записей. |
| `data/exports/.gitkeep` | Сформированные отчёты и выгрузки. |
| `data/db/.gitkeep` | Файл базы SQLite. |
| `models/.gitkeep` | Локальные веса Whisper/Vosk (и кэш Ollama). |
