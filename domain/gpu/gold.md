# GPU Gold Layer

The Gold layer provides derived, query-ready representations
built on top of immutable Silver data.

Gold objects can be dropped and rebuilt at any time.

## View: current_gpu_prices

Type: Derived view  
Source: `gpu_market_observation`

### Description

Provides the latest observed price and stock status
for each GPU variant and retailer.

### Logic

- Partitions by `(variant_id, retailer)`
- Orders observations by `observed_at DESC`
- Selects the most recent row per partition

### Guarantees

- One row per `(variant_id, retailer)`
- Always reflects the latest known observation
