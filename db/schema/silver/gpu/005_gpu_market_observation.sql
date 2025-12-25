-- ============================================================
-- SILVER LAYER
-- Purpose: Immutable, append-only fact table of GPU market observations from retailers.
-- Data characteristics: Event log; rows are inserted once and preserved for history.
-- Row meaning: One retailer snapshot for a GPU variant at a specific observed_at timestamp.
-- ============================================================

-- Defines the observation grain and enforces controlled vocabularies
-- for retailer and stock status to keep downstream dimensions stable.
CREATE TABLE IF NOT EXISTS gpu_market_observation (
    observation_id TEXT PRIMARY KEY,   -- Synthetic UUID per observation
    
    variant_id TEXT NOT NULL,
    
    -- Constrain retailer domain to stabilize downstream dimensions.
    retailer TEXT NOT NULL,
    sku TEXT,                          -- External retailer SKU
    product_url TEXT NOT NULL,         -- External retailer product URL
    
    -- Observed market facts
    price_eur REAL NOT NULL CHECK (price_eur > 0),
    -- Constrain stock status to a stable, comparable vocabulary. NULL if unknown.
    stock_status TEXT CHECK (
        stock_status IS NULL OR 
        stock_status IN (
            'in_stock',
            'low_stock',
            'preorder',
            'out_of_stock',
            'discontinued'
        )
    ),
    
    -- Observation metadata
    observed_at TIMESTAMP NOT NULL,
    scrape_run_id TEXT NOT NULL,       -- ETL run identifier for lineage
    
    -- Maintain referential integrity to the normalized GPU variant.
    FOREIGN KEY (variant_id)
        REFERENCES gpu_variant(variant_id)
        ON DELETE CASCADE
);

-- ------------------------------------------------------------
-- Indexes
-- Designed to optimize Gold-layer queries for latest price and
-- historical time-series analysis.
-- ------------------------------------------------------------

-- Latest observation per variant and retailer
CREATE INDEX IF NOT EXISTS idx_latest_price 
    ON gpu_market_observation(variant_id, retailer, observed_at DESC);

-- Time-series analysis per variant
CREATE INDEX IF NOT EXISTS idx_price_history 
    ON gpu_market_observation(variant_id, observed_at);
