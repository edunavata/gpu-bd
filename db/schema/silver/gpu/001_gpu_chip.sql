-- ============================================================
-- SILVER LAYER
-- Purpose: Canonical GPU chip dimension representing base silicon designs.
-- Data characteristics: Reference table; rows represent the latest known specs and can be updated in place.
-- Row meaning: One row per vendor chip model, independent of AIB variants or market data.
-- ============================================================

-- Defines the core chip attributes used by dependent Silver tables.
CREATE TABLE IF NOT EXISTS gpu_chip (
    chip_id TEXT PRIMARY KEY,  -- Synthetic chip identifier
    
    vendor TEXT NOT NULL CHECK (vendor IN ('NVIDIA', 'AMD', 'Intel')),
    brand_series TEXT NOT NULL,
    model_name TEXT NOT NULL,
    code_name TEXT,
    
    architecture TEXT NOT NULL,
    process_node_nm INTEGER,
    launch_date DATE,
    
    -- Normalize vendor-specific compute unit naming.
    compute_units_type TEXT NOT NULL CHECK (
        compute_units_type IN ('CUDA_CORES', 'STREAM_PROCESSORS', 'XE_CORES')
    ),
    compute_units_count INTEGER NOT NULL CHECK (compute_units_count > 0),
    
    rt_cores INTEGER DEFAULT 0,
    tensor_cores INTEGER DEFAULT 0,
    
    base_clock_mhz INTEGER CHECK (base_clock_mhz > 0),
    boost_clock_mhz INTEGER CHECK (boost_clock_mhz >= base_clock_mhz),
    
    tdp_watts INTEGER NOT NULL CHECK (tdp_watts > 0),
    recommended_psu_watts INTEGER CHECK (recommended_psu_watts >= tdp_watts),
    
    pcie_generation TEXT NOT NULL,
    -- Constrain lane counts to common configurations.
    pcie_lanes INTEGER DEFAULT 16 CHECK (pcie_lanes IN (8, 16)),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common filters and reporting slices.
CREATE INDEX IF NOT EXISTS idx_gpu_chip_vendor ON gpu_chip(vendor);
CREATE INDEX IF NOT EXISTS idx_gpu_chip_series ON gpu_chip(vendor, brand_series);
CREATE INDEX IF NOT EXISTS idx_gpu_chip_launch ON gpu_chip(launch_date);
