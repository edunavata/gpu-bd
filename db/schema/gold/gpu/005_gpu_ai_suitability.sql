-- db/schema/gold/gpu/005_gpu_ai_suitability.sql

-- ============================================================================
-- GOLD LAYER: AI Workload Suitability
-- Propósito: Filtrar y rankear GPUs específicamente para cargas de trabajo de IA (LLMs, SD).
-- Lógica: En IA, VRAM > Ancho de Banda > Velocidad de Reloj.
-- ============================================================================

-- db/schema/gold/005_gpu_ai_suitability.sql
CREATE VIEW IF NOT EXISTS gold_gpu_ai_suitability AS
SELECT 
    c.brand_series || ' ' || c.model_name AS model,
    m.vram_gb,
    c.tensor_cores,
    f.cuda_compute_capability,
    -- Métrica clave para IA: ¿Cuánto me cuesta cada GB de VRAM?
    ROUND(p.price_eur / m.vram_gb, 2) AS eur_per_vram_gb,
    -- Métrica de velocidad de inferencia: Ancho de banda
    m.memory_bandwidth_gbs,
    p.price_eur
FROM gpu_chip c
JOIN gpu_memory m ON c.chip_id = m.chip_id
JOIN gpu_features f ON c.chip_id = f.chip_id
JOIN gpu_variant var ON c.chip_id = var.chip_id
JOIN current_gpu_prices p ON var.variant_id = p.variant_id
WHERE m.vram_gb >= 12 -- Filtro prudente para IA moderna
ORDER BY vram_gb DESC, eur_per_vram_gb ASC;