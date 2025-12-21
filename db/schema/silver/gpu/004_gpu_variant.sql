-- ============================================================
-- SILVER LAYER
-- Purpose: Curated dimension of AIB (add-in board) GPU variants for each chip.
-- Data characteristics: Reference table; rows represent the latest known specs and can be updated in place.
-- Row meaning: One row per manufacturer-specific GPU variant tied to a chip.
-- ============================================================

-- Captures manufacturer variant attributes used for compatibility
-- checks and product-level enrichment.
CREATE TABLE IF NOT EXISTS gpu_variant (
    variant_id TEXT PRIMARY KEY,  -- Synthetic variant identifier
    chip_id TEXT NOT NULL,
    
    aib_manufacturer TEXT NOT NULL,
    model_suffix TEXT,
    
    factory_boost_mhz INTEGER,
    
    -- Constrain physical dimensions to realistic ranges for
    -- compatibility filtering.
    length_mm INTEGER CHECK (length_mm > 0),
    width_slots REAL CHECK (width_slots >= 2.0 AND width_slots <= 4.0),
    height_mm INTEGER,
    
    power_connectors TEXT,
    
    -- Normalize cooling categories for consistent filtering.
    cooling_type TEXT CHECK (
        cooling_type IN ('Air', 'Liquid', 'Hybrid')
    ),
    fan_count INTEGER CHECK (fan_count >= 0),
    
    displayport_count INTEGER DEFAULT 0,
    displayport_version TEXT,
    hdmi_count INTEGER DEFAULT 0,
    hdmi_version TEXT,
    
    warranty_years INTEGER,
    
    FOREIGN KEY (chip_id) REFERENCES gpu_chip(chip_id) ON DELETE CASCADE
);

-- Indexes for common joins and compatibility filters.
CREATE INDEX IF NOT EXISTS idx_gpu_variant_chip ON gpu_variant(chip_id);
CREATE INDEX IF NOT EXISTS idx_gpu_variant_aib ON gpu_variant(aib_manufacturer);
CREATE INDEX IF NOT EXISTS idx_gpu_variant_size ON gpu_variant(length_mm, width_slots);
