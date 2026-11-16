# CallGuard AI

Локальная веб-платформа контроля качества телефонных разговоров (кейс ПАО КБ «Центр-инвест»).

Подробности: `PROJECT_PLAN_CallGuard_AI.md`, `ARCHITECTURE.md`, `TEAM_PLAN.md`.

## Быстрый старт (заполняет участник 5 по мере готовности)
1. `cp .env.example .env` и задайте секреты.
2. Предзагрузите модели: `infrastructure/scripts/download_models.ps1`.
3. `docker compose -f infrastructure/docker-compose.yml up --build`.
4. Откройте http://localhost:8080.
