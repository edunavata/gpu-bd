-- GPU Variant: Implementaciones de fabricantes AIB (Add-In Board)
-- Diferencias físicas y de diseño sobre el mismo chip

CREATE TABLE IF NOT EXISTS gpu_variant (
    variant_id TEXT PRIMARY KEY,  -- ej: "ad102-rtx5090-asus-tuf-oc"
    chip_id TEXT NOT NULL,
    
    -- Fabricante AIB
    aib_manufacturer TEXT NOT NULL,  -- "ASUS", "MSI", "Gigabyte", "Founders Edition"
    model_suffix TEXT,               -- "TUF Gaming OC", "Gaming X Trio", "Eagle"
    
    -- Overclocking de fábrica (puede diferir del chip base)
    factory_boost_mhz INTEGER,
    
    -- Dimensiones físicas (crítico para compatibilidad de case)
    length_mm INTEGER CHECK (length_mm > 0),
    width_slots REAL CHECK (width_slots >= 2.0 AND width_slots <= 4.0),  -- 2.0, 2.5, 3.0, 4.0
    height_mm INTEGER,
    
    -- Conectores de alimentación
    power_connectors TEXT,  -- "1x 16-pin (12VHPWR)", "3x 8-pin PCIe"
    
    -- Refrigeración
    cooling_type TEXT CHECK (
        cooling_type IN ('Air', 'Liquid', 'Hybrid')
    ),
    fan_count INTEGER CHECK (fan_count >= 0),
    
    -- Conectores de salida
    displayport_count INTEGER DEFAULT 0,
    displayport_version TEXT,  -- "1.4a", "2.1"
    hdmi_count INTEGER DEFAULT 0,
    hdmi_version TEXT,  -- "2.1b"
    
    -- Garantía y soporte
    warranty_years INTEGER,
    
    FOREIGN KEY (chip_id) REFERENCES gpu_chip(chip_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_gpu_variant_chip ON gpu_variant(chip_id);
CREATE INDEX IF NOT EXISTS idx_gpu_variant_aib ON gpu_variant(aib_manufacturer);
CREATE INDEX IF NOT EXISTS idx_gpu_variant_size ON gpu_variant(length_mm, width_slots);