up:
	docker compose up -d --build
down:
	docker compose down
models:
	bash scripts/download_models.sh
test:
	cd backend && pytest -q
seed:
	python scripts/seed_demo.py
