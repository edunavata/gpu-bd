-- ============================================================================
-- Tablas de Referencia para GPU Domain (CORREGIDO)
-- ============================================================================

-- 1. VENDORS
CREATE TABLE IF NOT EXISTS gpu_vendor (
    vendor_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    founded_year INTEGER,
    headquarters TEXT,
    website_url TEXT,
    compute_unit_name TEXT NOT NULL,
    rt_core_name TEXT,
    tensor_core_name TEXT
);

-- Usamos OR IGNORE para evitar el error de llave duplicada
INSERT OR IGNORE INTO gpu_vendor VALUES 
('NVIDIA', 'NVIDIA Corporation', 1993, 'Santa Clara, CA', 'https://nvidia.com', 'CUDA Cores', 'RT Cores', 'Tensor Cores'),
('AMD', 'Advanced Micro Devices', 1969, 'Santa Clara, CA', 'https://amd.com', 'Stream Processors', 'Ray Accelerators', 'AI Accelerators'),
('Intel', 'Intel Corporation', 1968, 'Santa Clara, CA', 'https://intel.com', 'Xe Cores', NULL, 'XMX Engines');

-- 2. ARCHITECTURES
CREATE TABLE IF NOT EXISTS gpu_architecture (
    architecture_id TEXT PRIMARY KEY,
    vendor_id TEXT NOT NULL,
    generation TEXT,
    process_node_nm INTEGER,
    announcement_date DATE,
    first_product_launch DATE,
    supports_raytracing BOOLEAN DEFAULT 0,
    supports_mesh_shaders BOOLEAN DEFAULT 0,
    supports_direct_storage BOOLEAN DEFAULT 0,
    FOREIGN KEY (vendor_id) REFERENCES gpu_vendor(vendor_id)
);

INSERT OR IGNORE INTO gpu_architecture VALUES 
('Blackwell', 'NVIDIA', '5th Gen RTX', 5, '2024-03-18', '2025-01-30', 1, 1, 1),
('Ada Lovelace', 'NVIDIA', '4th Gen RTX', 5, '2022-09-20', '2022-10-12', 1, 1, 1),
('Ampere', 'NVIDIA', '3rd Gen RTX', 8, '2020-05-14', '2020-09-17', 1, 1, 0),
('RDNA4', 'AMD', 'RDNA 4', 4, '2024-01-08', '2025-01-23', 1, 1, 1),
('RDNA3', 'AMD', 'RDNA 3', 5, '2022-11-03', '2022-12-13', 1, 1, 1),
('Xe2-HPG', 'Intel', 'Xe2', 5, '2024-12-03', '2024-12-12', 1, 1, 1);

-- 3. MEMORY TYPES
CREATE TABLE IF NOT EXISTS gpu_memory_type (
    memory_type_id TEXT PRIMARY KEY,
    generation INTEGER NOT NULL,
    standard_name TEXT,
    max_speed_gbps REAL,
    typical_voltage REAL,
    release_year INTEGER,
    jedec_standard TEXT
);

INSERT OR IGNORE INTO gpu_memory_type VALUES 
('GDDR7', 7, 'GDDR7 SGRAM', 32.0, 1.1, 2024, 'JESD239A'),
('GDDR6X', 6, 'GDDR6X SGRAM', 24.0, 1.35, 2020, 'JESD239'),
('GDDR6', 6, 'GDDR6 SGRAM', 20.0, 1.35, 2018, 'JESD232'),
('HBM3', 3, 'High Bandwidth Memory 3', 8.0, 1.1, 2023, 'JESD238'),
('HBM2', 2, 'High Bandwidth Memory 2', 3.6, 1.2, 2016, 'JESD235');

-- Índices
CREATE INDEX IF NOT EXISTS idx_architecture_vendor ON gpu_architecture(vendor_id);