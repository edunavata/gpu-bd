.PHONY: help init db setup migrate seed load clean reset

PYTHON := python3
VENV := .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

DB_PATH := db/pcbuilder.db

help:
	@echo ""
	@echo "Available commands:"
	@echo "  make init     -> full bootstrap (db + venv + migrate + seed + load)"
	@echo "  make db       -> create SQLite database if not exists"
	@echo "  make setup    -> create venv and install dependencies"
	@echo "  make migrate  -> run schema migrations"
	@echo "  make seed     -> seed reference tables"
	@echo "  make load     -> populate database from bronze mock data"
	@echo "  make clean    -> remove venv and database"
	@echo "  make reset    -> clean + init"
	@echo ""

# 1) Create SQLite database if it does not exist
db:
	mkdir -p db
	test -f $(DB_PATH) || sqlite3 $(DB_PATH) ""

# 2) Create virtual environment and install dependencies
setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

# 3) Run migrations
migrate:
	$(PY) -m src.common.migrate

# 4) Seed reference data
seed:
	$(PY) -m src.silver.gpu.seed

# 5) Load data from bronze (mocked in repo)
load:
	$(PY) -m src.pipelines.silver_gpu_pipeline --db-path $(DB_PATH)

# Full bootstrap
init: db setup migrate seed load

# Cleanup
clean:
	rm -rf $(VENV)
	rm -f $(DB_PATH)

reset: clean init
