-- db/schema/gold/gpu/003_gpu_value_analysis.sql

-- ============================================================================
-- GOLD LAYER: GPU Value Analysis
-- Propósito: Agregar precios de mercado a nivel de Chip para identificar "suelos" de precio
-- y calcular métricas de valor (Ej: Precio/VRAM).
-- Nota: Filtra stock agotado para evitar precios fantasma.
-- ============================================================================

CREATE VIEW IF NOT EXISTS gpu_value_analysis AS
SELECT 
    t.chip_id,
    t.full_model_name,
    t.vendor_name,
    t.vram_gb,
    
    -- Métricas de Mercado (Agregadas desde variantes)
    COUNT(DISTINCT p.variant_id) AS available_variants,
    MIN(p.price_eur) AS min_price_eur,
    AVG(p.price_eur) AS avg_price_eur,
    MAX(p.price_eur) AS max_price_eur,
    
    -- Métricas de Valor (Calculadas sobre el precio mínimo disponible)
    -- Útil para encontrar "Sweet Spots"
    ROUND(MIN(p.price_eur) / t.vram_gb, 2) AS price_per_vram_gb,
    
    -- Contexto técnico rápido
    t.memory_bandwidth_gbs,
    t.tdp_watts

FROM gpu_technical_sheet t
JOIN current_gpu_prices p ON t.chip_id = p.chip_id
GROUP BY 
    t.chip_id, 
    t.full_model_name, 
    t.vendor_name, 
    t.vram_gb,
    t.memory_bandwidth_gbs, 
    t.tdp_watts;