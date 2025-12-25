-- db/schema/gold/gpu/004_gpu_price_performance.sql

-- ============================================================================
-- GOLD LAYER: GPU Price/Performance Ratios
-- Propósito: Calcular el valor del hardware por euro invertido.
-- Nota de Prudencia: Al no tener benchmarks (FPS), usamos "Ancho de Banda" y 
-- "Cómputo Bruto" (Cores * Clock) como proxies físicos de la potencia.
-- ============================================================================

-- db/schema/gold/004_gpu_price_performance.sql
CREATE VIEW IF NOT EXISTS gold_gpu_price_performance AS
SELECT 
    c.brand_series || ' ' || c.model_name AS model,
    v.vendor_id,
    p.price_eur,
    -- Proxy de potencia: (Núcleos * Frecuencia) / Precio
    ROUND((c.compute_units_count * c.boost_clock_mhz) / p.price_eur / 100.0, 2) AS performance_per_euro_score,
    -- Valor de ancho de banda: GB/s por euro
    ROUND(m.memory_bandwidth_gbs / p.price_eur, 3) AS bandwidth_per_euro,
    p.retailer
FROM gpu_chip c
JOIN gpu_vendor v ON c.vendor_id = v.vendor_id
JOIN gpu_memory m ON c.chip_id = m.chip_id
JOIN gpu_variant var ON c.chip_id = var.chip_id
JOIN current_gpu_prices p ON var.variant_id = p.variant_id;