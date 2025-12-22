# GPU SQL Schema

This document lists all SQL objects belonging to the GPU domain.

The schema is implemented in SQLite under `db/schema/`.

## Silver Layer

The Silver layer uses selective normalization:
- Reference tables are normalized where semantics are stable and reused (`gpu_vendor`, `gpu_architecture`, `gpu_memory_type`)
- Controlled text fields remain inline for unstable naming or simple enums (`brand_series`, `code_name`, `pcie_generation`, `stock_status`)

This avoids overengineering and keeps common queries direct.

### Tables

| Table Name | Description |
|-----------|-------------|
| `gpu_vendor` | GPU vendors (seed-initialized reference data) |
| `gpu_architecture` | GPU architecture families (seed-initialized reference data) |
| `gpu_memory_type` | GPU memory standards (seed-initialized reference data) |
| `gpu_chip` | Canonical GPU chip definitions with controlled text identity fields |
| `gpu_memory` | Memory configuration per chip (references `gpu_memory_type`) |
| `gpu_features` | Feature flags and capability metadata per chip |
| `gpu_variant` | Stable AIB variants derived from `gpu_chip`; created on-demand, not SKU/offer |
| `gpu_market_observation` | Append-only market observations referencing `gpu_variant` (no current state) |

## Gold Layer

### Views

| View Name | Description |
|----------|-------------|
| `current_gpu_prices` | Latest observed price per GPU variant and retailer |
