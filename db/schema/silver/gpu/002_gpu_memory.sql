-- ============================================================
-- SILVER LAYER
-- Purpose: Curated memory subsystem attributes per GPU chip.
-- Data characteristics: Reference table; rows represent the latest known memory specs and can be updated in place.
-- Row meaning: One row per chip with VRAM capacity, type, bus, and bandwidth.
-- ============================================================

-- Normalizes memory attributes to support sizing and performance analysis.
CREATE TABLE IF NOT EXISTS gpu_memory (
    chip_id TEXT PRIMARY KEY,
    
    -- Constrain memory attributes to known, comparable domains.
    vram_gb INTEGER NOT NULL CHECK (vram_gb > 0),
    memory_type TEXT NOT NULL CHECK (
        memory_type IN ('GDDR6', 'GDDR6X', 'GDDR7', 'HBM2', 'HBM3')
    ),
    
    memory_bus_bits INTEGER NOT NULL CHECK (
        memory_bus_bits IN (64, 128, 192, 256, 320, 384, 512)
    ),
    memory_speed_gbps REAL CHECK (memory_speed_gbps > 0),
    
    -- Store derived bandwidth for convenience in analytical queries.
    -- bandwidth_gbs = (memory_bus_bits / 8) * memory_speed_gbps
    memory_bandwidth_gbs REAL CHECK (memory_bandwidth_gbs > 0),
    
    FOREIGN KEY (chip_id) REFERENCES gpu_chip(chip_id) ON DELETE CASCADE
);

-- Index to accelerate VRAM capacity filters.
CREATE INDEX IF NOT EXISTS idx_gpu_memory_vram ON gpu_memory(vram_gb);
