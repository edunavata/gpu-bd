-- ============================================================
-- SILVER LAYER
-- Purpose: Curated feature flags and capability metadata per GPU chip.
-- Data characteristics: Reference table; rows represent the latest known feature set and can be updated in place.
-- Row meaning: One row per chip, capturing support for hardware and API features.
-- ============================================================

-- Encodes binary/enumerated capabilities without deriving a score.
CREATE TABLE IF NOT EXISTS gpu_features (
    chip_id TEXT PRIMARY KEY,
    
    -- Ray tracing capabilities and API support.
    raytracing_hardware BOOLEAN NOT NULL DEFAULT 0,
    raytracing_api_support TEXT,
    
    -- Vendor-specific capabilities; values may be NULL/false for other vendors.
    cuda_compute_capability TEXT,
    dlss_version TEXT,
    nvenc_generation TEXT,
    nvidia_reflex BOOLEAN DEFAULT 0,
    
    fsr_support BOOLEAN DEFAULT 0,
    amd_fmf BOOLEAN DEFAULT 0,
    amd_hypr_rx BOOLEAN DEFAULT 0,
    
    xess_support BOOLEAN DEFAULT 0,
    
    -- Cross-vendor standards and features.
    av1_encode BOOLEAN DEFAULT 0,
    av1_decode BOOLEAN DEFAULT 0,
    resizable_bar BOOLEAN DEFAULT 0,
    
    FOREIGN KEY (chip_id) REFERENCES gpu_chip(chip_id) ON DELETE CASCADE
);
