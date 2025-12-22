-- ============================================================
-- SILVER LAYER
-- Purpose: Curated memory subsystem attributes per GPU chip.
-- Data characteristics: Reference table; rows represent the latest known memory specs and can be updated in place.
-- Row meaning: One row per chip with VRAM capacity, type, bus, and bandwidth.
-- ============================================================

-- Normalizes memory attributes to support sizing and performance analysis.
CREATE TABLE IF NOT EXISTS gpu_memory (
    chip_id TEXT PRIMARY KEY,
    
    -- Capacidad
    vram_gb INTEGER NOT NULL CHECK (vram_gb > 0),
    
    -- Tipo normalizado
    memory_type_id TEXT NOT NULL,
    
    -- Bus y velocidad
    memory_bus_bits INTEGER NOT NULL CHECK (
        memory_bus_bits IN (64, 96, 128, 192, 256, 320, 384, 512, 1024, 2048, 4096)
    ),
    memory_speed_gbps REAL CHECK (memory_speed_gbps > 0),
    memory_bandwidth_gbs REAL CHECK (memory_bandwidth_gbs > 0),
    
    FOREIGN KEY (chip_id) REFERENCES gpu_chip(chip_id) ON DELETE CASCADE,
    FOREIGN KEY (memory_type_id) REFERENCES gpu_memory_type(memory_type_id)
);

CREATE INDEX IF NOT EXISTS idx_gpu_memory_vram ON gpu_memory(vram_gb);
CREATE INDEX IF NOT EXISTS idx_gpu_memory_type ON gpu_memory(memory_type_id);
