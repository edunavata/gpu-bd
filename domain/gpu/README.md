# GPU Domain

This domain models the GPU (Graphics Processing Unit) market as observed from external retailers.
It supports a GPU recommendation system and does not attempt to model GPUs exhaustively or
replicate vendor datasheets.

Scope:
- GPU technical characteristics (chip, memory, features)
- Derived GPU variants as stable physical configurations
- Historical market observations (price and stock)
- Derived current prices for comparison purposes

Out of scope:
- User preferences
- Recommendations logic
- Forecasting or predictions

Data Sources:
- External e-commerce retailers (e.g. PcComponentes, Amazon)

All market data is ingested as immutable observations.

## Modeling Intent (Silver)

The Silver layer is designed for recommendation decisions, not exhaustive catalogs. It models:
- Comparable, stable hardware characteristics
- Vendor-neutral abstractions
- Capabilities that materially influence recommendations

## Normalization Strategy

The Silver layer uses selective, pragmatic normalization to balance stability and queryability:
- Normalized reference tables: `gpu_vendor`, `gpu_architecture`, `gpu_memory_type`
  (low cardinality, stable semantics, rich metadata, reused across the domain)
- Controlled text fields: `brand_series`, `code_name`, `pcie_generation`, `stock_status`
  (unstable naming, high cardinality, or simple enums without metadata)

This avoids overengineering while keeping common filters direct and consistent.

## Clock Semantics

`typical_clock_mhz` stores the typical sustained operating frequency under load in a vendor-neutral field.
For AMD this corresponds to Game Clock; for NVIDIA it corresponds to Base Clock.
It is not a minimum guaranteed clock and is not split into base/game/boost triplets.
Boost clocks remain modeled separately as peak capability via `gpu_variant.factory_boost_mhz`.

## Capability Semantics

- `tensor_cores` indicates presence of dedicated matrix/AI hardware only; it does not imply
  cross-vendor performance parity.
- `cuda_compute_capability` is NVIDIA-only by design. NULL values for AMD are semantically correct
  and are used for compatibility filtering, not scoring.

## GPU Variant Role

`gpu_variant` is a Silver entity that represents a stable physical/commercial configuration
derived from a `gpu_chip` (AIB, model suffix, factory boost/OC, cooling, dimensions).

It is:
- Not seed-initialized
- Not a retailer SKU
- Not a market offer

Variants are created on-demand when processing Bronze market observations, using
deterministic resolution logic.

## Market Observation Model

`gpu_market_observation` is append-only and immutable. It represents point-in-time facts,
never a current state, and always references an existing `gpu_variant`. Current prices and
availability are derived downstream in Gold.

## Seeding Policy

Seed-initialized entities:
- `gpu_vendor`
- `gpu_architecture`
- `gpu_memory_type`

Not seed-initialized:
- `gpu_variant`
- `gpu_market_observation`

Rationale: reference entities exist independently of the market, while variants and
observations only exist because the market materializes them.

## Data Flow

Bronze (raw offers) -> Silver (canonical chips, derived variants, observations) -> Gold (aggregates)
