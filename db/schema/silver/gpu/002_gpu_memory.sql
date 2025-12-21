-- GPU Memory: Subsistema de memoria como entidad separada
-- Captura tipo, capacidad, bus y ancho de banda

CREATE TABLE IF NOT EXISTS gpu_memory (
    chip_id TEXT PRIMARY KEY,
    
    -- Capacidad y tipo
    vram_gb INTEGER NOT NULL CHECK (vram_gb > 0),
    memory_type TEXT NOT NULL CHECK (
        memory_type IN ('GDDR6', 'GDDR6X', 'GDDR7', 'HBM2', 'HBM3')
    ),
    
    -- Bus y velocidad
    memory_bus_bits INTEGER NOT NULL CHECK (
        memory_bus_bits IN (64, 128, 192, 256, 320, 384, 512)
    ),
    memory_speed_gbps REAL CHECK (memory_speed_gbps > 0),  -- Velocidad efectiva
    
    -- Ancho de banda calculado (GB/s)
    -- bandwidth_gbs = (memory_bus_bits / 8) * memory_speed_gbps
    memory_bandwidth_gbs REAL CHECK (memory_bandwidth_gbs > 0),
    
    FOREIGN KEY (chip_id) REFERENCES gpu_chip(chip_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_gpu_memory_vram ON gpu_memory(vram_gb);