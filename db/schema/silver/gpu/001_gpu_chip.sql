CREATE TABLE IF NOT EXISTS gpu_chip (
    chip_id TEXT PRIMARY KEY,
    
    -- Referencias normalizadas
    vendor_id TEXT NOT NULL,
    architecture_id TEXT NOT NULL,
    
    -- Identidad del producto (NO normalizado)
    brand_series TEXT NOT NULL,
    model_name TEXT NOT NULL,
    code_name TEXT,
    
    -- Arquitectura y fabricación
    process_node_nm INTEGER,  -- Puede diferir de architecture.process_node_nm
    launch_date DATE,
    
    -- Unidades de cómputo
    compute_units_type TEXT NOT NULL CHECK (
        compute_units_type IN ('CUDA_CORES', 'STREAM_PROCESSORS', 'XE_CORES')
    ),
    compute_units_count INTEGER NOT NULL CHECK (compute_units_count > 0),
    rt_cores INTEGER DEFAULT 0,
    tensor_cores INTEGER DEFAULT 0,
    
    -- Frecuencias (MHz)
    typical_clock_mhz INTEGER CHECK (typical_clock_mhz > 0),
    boost_clock_mhz INTEGER CHECK (boost_clock_mhz >= typical_clock_mhz),
    
    -- Potencia
    tdp_watts INTEGER NOT NULL CHECK (tdp_watts > 0),
    recommended_psu_watts INTEGER CHECK (recommended_psu_watts >= tdp_watts),
    
    -- Interface
    pcie_generation TEXT NOT NULL,
    pcie_lanes INTEGER DEFAULT 16 CHECK (pcie_lanes IN (8, 16)),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (vendor_id) REFERENCES gpu_vendor(vendor_id),
    FOREIGN KEY (architecture_id) REFERENCES gpu_architecture(architecture_id)
);

CREATE INDEX IF NOT EXISTS idx_gpu_chip_vendor ON gpu_chip(vendor_id);
CREATE INDEX IF NOT EXISTS idx_gpu_chip_architecture ON gpu_chip(architecture_id);
CREATE INDEX IF NOT EXISTS idx_gpu_chip_series ON gpu_chip(vendor_id, brand_series);
CREATE INDEX IF NOT EXISTS idx_gpu_chip_launch ON gpu_chip(launch_date);