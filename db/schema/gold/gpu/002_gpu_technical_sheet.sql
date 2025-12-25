-- db/schema/gold/gpu/002_gpu_technical_sheet.sql

-- ============================================================================
-- GOLD LAYER: GPU Technical Sheet
-- Propósito: Vista desnormalizada de especificaciones técnicas para análisis y frontend.
-- Valor: Abstrae la complejidad de los JOINs de Silver y normaliza etiquetas de marketing.
-- ============================================================================

CREATE VIEW IF NOT EXISTS gpu_technical_sheet AS
SELECT 
    -- Identidad Principal
    c.chip_id,
    ven.full_name AS vendor_name,
    arch.generation AS architecture_gen,
    c.brand_series || ' ' || c.model_name AS full_model_name,
    
    -- Especificaciones de Cómputo (Normalización de Vendedor)
    c.compute_units_count,
    CASE 
        WHEN c.vendor_id = 'NVIDIA' THEN 'CUDA Cores'
        WHEN c.vendor_id = 'AMD' THEN 'Stream Processors'
        WHEN c.vendor_id = 'Intel' THEN 'Xe Cores'
        ELSE c.compute_units_type 
    END AS core_type_label,
    
    -- Semántica de Reloj (Game Clock vs Base Clock)
    c.typical_clock_mhz,
    CASE 
        WHEN c.vendor_id = 'AMD' THEN 'Game Clock'
        ELSE 'Base Clock'
    END AS typical_clock_label,
    c.boost_clock_mhz AS reference_boost_clock_mhz,
    
    -- Memoria (Join pre-calculado)
    m.vram_gb,
    mt.standard_name AS memory_type,
    m.memory_bus_bits,
    m.memory_bandwidth_gbs,
    
    -- Features Clave (Simplificación de booleans a texto legible donde aplica)
    f.raytracing_hardware AS supports_rt_hardware,
    CASE 
        WHEN c.vendor_id = 'NVIDIA' THEN f.dlss_version
        ELSE NULL 
    END AS dlss_version,
    f.fsr_support,
    f.av1_encode,
    
    -- Dimensiones Físicas y Energía
    c.tdp_watts,
    c.recommended_psu_watts,
    c.process_node_nm

FROM gpu_chip c
JOIN gpu_vendor ven ON c.vendor_id = ven.vendor_id
JOIN gpu_architecture arch ON c.architecture_id = arch.architecture_id
-- LEFT JOINs garantizan que no perdamos chips si falta metadata opcional,
-- aunque en Silver se espera consistencia (INNER JOIN sería aceptable también).
LEFT JOIN gpu_memory m ON c.chip_id = m.chip_id
LEFT JOIN gpu_memory_type mt ON m.memory_type_id = mt.memory_type_id
LEFT JOIN gpu_features f ON c.chip_id = f.chip_id;