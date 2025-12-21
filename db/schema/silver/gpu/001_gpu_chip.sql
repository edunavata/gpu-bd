-- GPU Chip: Identidad canónica del silicio físico
-- Representa el diseño base del fabricante (NVIDIA/AMD/Intel)
-- NO incluye variantes de fabricantes AIB ni precios

CREATE TABLE IF NOT EXISTS gpu_chip (
    chip_id TEXT PRIMARY KEY,  -- ej: "ad102-rtx5090", "navi48-rx9070xt"
    
    -- Identidad del producto
    vendor TEXT NOT NULL CHECK (vendor IN ('NVIDIA', 'AMD', 'Intel')),
    brand_series TEXT NOT NULL,  -- "GeForce RTX 50", "Radeon RX 9000", "Arc Battlemage"
    model_name TEXT NOT NULL,    -- "RTX 5090", "RX 9070 XT"
    code_name TEXT,              -- "Blackwell", "RDNA4", "Xe2-HPG"
    
    -- Arquitectura y fabricación
    architecture TEXT NOT NULL,  -- "Blackwell", "Ada Lovelace", "RDNA4"
    process_node_nm INTEGER,     -- 4, 5, 6 (nm)
    launch_date DATE,
    
    -- Unidades de cómputo (vendor-specific naming)
    compute_units_type TEXT NOT NULL CHECK (
        compute_units_type IN ('CUDA_CORES', 'STREAM_PROCESSORS', 'XE_CORES')
    ),
    compute_units_count INTEGER NOT NULL CHECK (compute_units_count > 0),
    
    -- Unidades especializadas
    rt_cores INTEGER DEFAULT 0,      -- Ray Tracing cores
    tensor_cores INTEGER DEFAULT 0,  -- NVIDIA Tensor / AMD AI Accelerators
    
    -- Frecuencias (MHz)
    base_clock_mhz INTEGER CHECK (base_clock_mhz > 0),
    boost_clock_mhz INTEGER CHECK (boost_clock_mhz >= base_clock_mhz),
    
    -- Potencia
    tdp_watts INTEGER NOT NULL CHECK (tdp_watts > 0),
    recommended_psu_watts INTEGER CHECK (recommended_psu_watts >= tdp_watts),
    
    -- Interface
    pcie_generation TEXT NOT NULL,  -- "Gen3", "Gen4", "Gen5"
    pcie_lanes INTEGER DEFAULT 16 CHECK (pcie_lanes IN (8, 16)),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices de búsqueda común
CREATE INDEX IF NOT EXISTS idx_gpu_chip_vendor ON gpu_chip(vendor);
CREATE INDEX IF NOT EXISTS idx_gpu_chip_series ON gpu_chip(vendor, brand_series);
CREATE INDEX IF NOT EXISTS idx_gpu_chip_launch ON gpu_chip(launch_date);