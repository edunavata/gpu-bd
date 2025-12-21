-- ============================================================
-- GOLD LAYER
-- Purpose: Current price snapshot per GPU variant and retailer.
-- Data characteristics: Derived view over immutable observations; recalculates on query.
-- Row meaning: One row per variant and retailer representing the latest observation.
-- ============================================================

-- Selects the most recent observation for each variant/retailer pair.
CREATE VIEW IF NOT EXISTS current_gpu_prices AS
WITH ranked AS (
    -- Rank observations to keep the latest snapshot per retailer.
    SELECT
        observation_id,
        variant_id,
        retailer,
        sku,
        product_url,
        price_eur,
        stock_status,
        observed_at,
        ROW_NUMBER() OVER (
            PARTITION BY variant_id, retailer
            ORDER BY observed_at DESC
        ) AS rn
    FROM gpu_market_observation
)
SELECT
    observation_id,
    variant_id,
    retailer,
    sku,
    product_url,
    price_eur,
    stock_status,
    observed_at
FROM ranked
WHERE rn = 1;
