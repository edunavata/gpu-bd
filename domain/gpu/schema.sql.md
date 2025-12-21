# GPU SQL Schema

This document lists all SQL objects belonging to the GPU domain.

The schema is implemented in SQLite under `db/schema/`.

## Silver Layer

### Tables

| Table Name | Description |
|-----------|-------------|
| `gpu_chip` | Canonical GPU chip definitions |
| `gpu_memory` | GPU memory configurations |
| `gpu_features` | Feature flags per GPU |
| `gpu_variant` | Normalized GPU variants |
| `gpu_market_observation` | Immutable market observations |

## Gold Layer

### Views

| View Name | Description |
|----------|-------------|
| `current_gpu_prices` | Latest observed price per GPU variant and retailer |
