# GPU Gold Layer

The Gold layer provides derived, query-ready representations built on top of immutable Silver data. 

Gold objects are non-canonical, focus on decision-making metrics, and can be dropped and rebuilt at any time.

## View: current_gpu_prices

Type: Derived view  
Source: `gpu_market_observation`, `gpu_variant`

### Description
Provides the latest observed price and stock status for each specific GPU variant and retailer, filtering out historical noise.

### Logic
- Partitions observations by `(variant_id, retailer)`.
- Orders by `observed_at DESC`.
- Selects the most recent record per partition (`rn = 1`).

### Guarantees
- One row per `(variant_id, retailer)`.
- Always reflects the latest known state of the market.

---

## View: gpu_technical_sheet

Type: Denormalized view  
Source: `gpu_chip`, `gpu_vendor`, `gpu_memory`, `gpu_features`

### Description
A "one-stop shop" for technical specifications. It flattens the Silver normalization into a human-readable format, standardizing vendor terminology (e.g., "CUDA Cores" vs "Stream Processors").

### Logic
- Joins chip technical data with its corresponding memory and feature sets.
- Normalizes clock and core labels based on the `vendor_id`.

### Guarantees
- One row per `chip_id`.
- Vendor-neutral attribute naming for easier comparison.

---

## View: gpu_value_analysis

Type: Aggregated view  
Source: `gpu_technical_sheet`, `current_gpu_prices`

### Description
Aggregates market data at the chip level to identify the "price floor" (minimum price) and value metrics like Price per GB of VRAM.

### Logic
- Groups current prices by `chip_id`.
- Calculates `min_price_eur` and `avg_price_eur` across all retailers and variants.
- Derives the `price_per_vram_gb` ratio.

### Guarantees
- Only includes chips with at least one variant currently in stock.

---

## View: gold_gpu_price_performance

Type: Scoring view  
Source: `gpu_chip`, `gpu_memory`, `current_gpu_prices`

### Description
Calculates hardware value ratios based on physical performance proxies (compute power and memory bandwidth) per euro.

### Logic
- **Performance Score**: Calculated as `(compute_units * boost_clock) / price`.
- **Bandwidth Value**: Calculated as `memory_bandwidth_gbs / price`.
- Filters by `in_stock` and `low_stock` statuses only.

### Guarantees
- Provides a mathematical "bang-for-the-buck" ranking without relying on external benchmark variability.

---

## View: gold_gpu_ai_suitability

Type: Specialized ranking view  
Source: `gpu_chip`, `gpu_memory`, `gpu_features`, `current_gpu_prices`

### Description
Ranks GPUs specifically for AI/Machine Learning workloads (LLMs, Diffusion models), where VRAM capacity and specialized tensor hardware are the primary constraints.

### Logic
- Filters for GPUs with at least 12GB of VRAM.
- Calculates the `eur_per_vram_gb` (density cost).
- Exposes `tensor_cores` and `cuda_compute_capability` for compatibility checks.
- Sorts by VRAM capacity descending and price efficiency ascending.

### Guarantees
- Identifies the most cost-effective cards for loading large model weights.
