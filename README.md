# GPU BD PoC: LLM-Powered Data Structuring

PcBuilder is a Proof of Concept (PoC) designed to demonstrate how to transform chaotic, unstructured hardware data into a clean, enriched, and actionable data model using LLMs and a modern data architecture.

## 🎯 PoC Objectives
- Intelligent Structuring: Scraping unstructured sources and using LLMs (Perplexity/GPT) to normalize and enrich technical information (e.g., extracting GPU variants from complex text strings).
- Medallion Architecture: Implementing a three-layer data pipeline to ensure traceability and data quality.

## 🏗️ Data Architecture (Medallion)
The project implements a local-first flow on SQLite:

- Bronze Layer (Raw): Stores raw evidence (market observations) and LLM-generated hypotheses.
- Silver Layer (Canonical): Clean, deterministic model. Validated entities live here (chips, board partner variants).
- Gold Layer (Analytics): Derived views optimized for final consumption (e.g., current price comparisons).

## ⚠️ Important Notes and Ethics
- Use of AI: The included data has been partially generated/enriched with AI. LLM hypotheses are treated as evidence, not absolute canonical truth.
- Responsible Scraping:
  - This project is for personal and educational use, not commercial.
  - Scripts include intentional delays to minimize impact on Geizhals servers.
  - Do not run the scraper indiscriminately. Always respect the terms of service and robots.txt.

## 🚀 Quick Setup
Requirements: Python 3.10+, SQLite, and make.

```bash
# Initializes the environment, database, and loads sample data
make init
```

The `make init` command automates:
- Creating the venv and installing dependencies.
- Applying database migrations.
- Loading Seeds (pre-generated data) so you can try the project without scraping immediately.

## 🛠️ Pipeline Execution
If you want to run the processes manually or configure your own API:

1. LLM Enrichment
   Copy the example file and add your API Key to enable the inference engine:

```bash
cp .env.example .env
# Edit .env with your PERPLEXITY_API_KEY
```

2. Manual Flows

Bronze (Ingest + LLM):
> Note: Make sure you have created a virtual environment and installed dependencies before running the pipelines.

```bash
python -m src.pipelines.bronze_gpu_pipeline --pages 1 2
```

Silver (Processing):
```bash
python -m src.pipelines.silver_gpu_pipeline --db-path db/pcbuilder.db
```

> Important: The Bronze pipeline scraper will likely break over time. It works today, but there is no guarantee it will keep working as sites change.

## 📂 Project Structure
- `/domain/gpu/`: Business logic and hardware-specific data models.
- `/src/pipelines/`: Orchestration of the Bronze and Silver layers.
- `/db/`: SQL schemas and local database.
