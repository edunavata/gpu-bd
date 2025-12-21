-- GPU Offer: Estado de mercado dinámico
-- Precios, stock y disponibilidad por tienda y timestamp

CREATE TABLE IF NOT EXISTS gpu_offer (
    offer_id TEXT PRIMARY KEY,  -- UUID o composite key
    variant_id TEXT NOT NULL,
    
    -- Identificación de la oferta
    retailer TEXT NOT NULL,  -- "PcComponentes", "Amazon ES", "Coolmod"
    sku TEXT,                -- SKU interno de la tienda
    product_url TEXT NOT NULL UNIQUE,
    
    -- Precio
    price_eur REAL NOT NULL CHECK (price_eur > 0),
    original_price_eur REAL CHECK (original_price_eur >= price_eur),  -- Precio sin descuento
    
    -- Disponibilidad
    stock_status TEXT NOT NULL CHECK (
        stock_status IN ('in_stock', 'low_stock', 'preorder', 'out_of_stock', 'discontinued')
    ),
    stock_quantity INTEGER,  -- NULL si no especificado
    
    -- Timestamp
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (variant_id) REFERENCES gpu_variant(variant_id) ON DELETE CASCADE
);

-- Índices críticos para queries de precio/disponibilidad
CREATE INDEX IF NOT EXISTS idx_gpu_offer_variant ON gpu_offer(variant_id, price_eur);
CREATE INDEX IF NOT EXISTS idx_gpu_offer_retailer ON gpu_offer(retailer, stock_status);
CREATE INDEX IF NOT EXISTS idx_gpu_offer_price ON gpu_offer(price_eur, last_seen_at);