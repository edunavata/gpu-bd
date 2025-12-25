-- db/schema/gold/gpu/001_current_gpu_prices.sql

-- ============================================================================
-- GOLD LAYER: Current GPU Prices
-- Propósito: Obtener el último precio y estado de stock conocido por Variante y Retailer.
-- Lógica: Deduplicación basada en tiempo (Latest by Partition).
-- ============================================================================

CREATE VIEW IF NOT EXISTS current_gpu_prices AS
WITH ranked_observations AS (
    SELECT 
        observation_id,
        variant_id,
        retailer,
        sku,
        price_eur,
        stock_status,
        product_url,
        observed_at,
        scrape_run_id,
        -- Numeramos las observaciones por variante/retailer, de más reciente a más antigua
        ROW_NUMBER() OVER (
            PARTITION BY variant_id, retailer 
            ORDER BY observed_at DESC
        ) as rn
    FROM gpu_market_observation
)
SELECT 
    obs.variant_id,
    v.chip_id,
    obs.retailer,
    obs.price_eur,
    obs.stock_status,
    obs.product_url,
    obs.observed_at as last_seen_at,
    v.aib_manufacturer,
    v.model_suffix
FROM ranked_observations obs
JOIN gpu_variant v ON obs.variant_id = v.variant_id
WHERE obs.rn = 1;