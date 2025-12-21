# Documentación de Capa Silver: Dominio GPU

Este documento define el modelo de datos normalizado (3NF) para GPUs en la capa Silver del sistema PcBuilder.

La capa Silver representa la fuente de verdad estructural, desacoplada de retailers, precios y ruido de scraping.
Su objetivo es servir como base estable para:

- Capa Gold (configuraciones óptimas)
- Algoritmos deterministas de selección
- Razonamiento LLM con contexto fiable

## Principios de Diseño (Silver)

- Normalización estricta: una entidad = un concepto del dominio.
- Separación semántica:
  - Chip ≠ Variante ≠ Oferta
- Estabilidad temporal:
  - El chip y sus capacidades no dependen del mercado.
  - El precio y stock son efímeros.
- Trazabilidad:
  - Cada fila Silver debe ser rastreable a Bronze.
- SQL-first:
  - El esquema Silver es independiente de LLMs, UIs o scrapers.

## Diagrama de Entidad-Relación

Nota: el diagrama es representación visual, no contrato físico SQL.

```mermaid
%%{init: {
  "theme": "default",
  "themeVariables": {
    "primaryColor": "#141414ff",
    "primaryTextColor": "#000000",
    "primaryBorderColor": "#333333",
    "lineColor": "#333333",
    "secondaryColor": "#f5f5f5",
    "tertiaryColor": "#ffffff"
  }
}}%%
erDiagram
    gpu_chip ||--|| gpu_memory : has
    gpu_chip ||--|| gpu_features : has
    gpu_chip ||--o{ gpu_variant : is_basis_for
    gpu_variant ||--o{ gpu_offer : appears_in

    gpu_chip {
        string chip_id
        string vendor
        string brand_series
        string model_name
        string architecture
        string compute_units_type
        int compute_units_count
        int rt_cores
        int tensor_cores
        int tdp_watts
        string pcie_generation
    }

    gpu_memory {
        string chip_id
        int vram_gb
        string memory_type
        int memory_bus_bits
        float memory_speed_gbps
        float memory_bandwidth_gbs
    }

    gpu_features {
        string chip_id
        bool raytracing_hardware
        string dlss_version
        bool fsr_support
        bool av1_encode
        string cuda_compute_capability
    }

    gpu_variant {
        string variant_id
        string chip_id
        string aib_manufacturer
        string model_suffix
        int length_mm
        float width_slots
        string cooling_type
        string power_connectors
    }

    gpu_offer {
        string offer_id
        string variant_id
        string retailer
        float price_eur
        float original_price_eur
        string stock_status
        string last_seen_at
    }
```

## Definición Canónica de Entidades

### gpu_chip

Representa el silicio base diseñado por el fabricante (NVIDIA / AMD).

Clave primaria: chip_id

Inmutable en el tiempo

Ejemplo: AD104, GA102, NAVI31

Responsabilidades:

- Arquitectura
- Unidades de cómputo
- Capacidades base del chip

### gpu_memory

Describe el subsistema de memoria del chip.

Relación 1:1 con gpu_chip

No depende del ensamblador

Define límites físicos del chip

### gpu_features

Capacidades funcionales del chip.

Relación 1:1 con gpu_chip

Flags técnicos (ray tracing, AV1, DLSS/FSR)

Usado intensivamente por reglas Gold y razonamiento LLM

### gpu_variant

Representa una implementación comercial del chip por un AIB (ASUS, MSI, Gigabyte...).

Relación N:1 con gpu_chip

Afecta a:

- Dimensiones físicas
- Refrigeración
- Conectores de energía

Ejemplo:

- RTX 4070 Ti Gaming OC
- RTX 4070 Ti Ventus 2X

### gpu_offer

Instancia de mercado de una variante concreta.

Relación N:1 con gpu_variant

Entidad volátil

Puede desaparecer o cambiar de precio

Incluye:

- Precio actual
- Precio original
- Estado de stock
- Última detección

## Reglas de Integridad (no visibles en Mermaid)

Estas reglas DEBEN cumplirse en SQL:

- gpu_memory.chip_id → FK a gpu_chip.chip_id
- gpu_features.chip_id → FK a gpu_chip.chip_id
- gpu_variant.chip_id → FK a gpu_chip.chip_id
- gpu_offer.variant_id → FK a gpu_variant.variant_id

## Antipatrones Evitados (a propósito)

- ❌ Mezclar precios con especificaciones
- ❌ Duplicar información del chip en variantes
- ❌ Modelos "flat" dependientes del retailer
- ❌ Campos calculados en Silver

## Relación con Otras Capas

| Capa | Rol |
| --- | --- |
| Bronze | Datos crudos de scrapers |
| Silver | Dominio limpio y normalizado |
| Gold | Configuraciones óptimas, scoring, rankings |

Silver no decide, no optimiza, no recomienda.
Silver define la realidad del dominio.

## Estado del Modelo

- ✔ Normalizado (3NF)
- ✔ Escalable
- ✔ Compatible con SQLite / PostgreSQL
- ✔ Preparado para razonamiento LLM determinista
