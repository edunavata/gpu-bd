-- GPU Features: Tecnologías y capacidades binarias/enumeradas
-- NO es un scoring, es presencia/ausencia de tecnología hardware

CREATE TABLE IF NOT EXISTS gpu_features (
    chip_id TEXT PRIMARY KEY,
    
    -- Ray Tracing
    raytracing_hardware BOOLEAN NOT NULL DEFAULT 0,
    raytracing_api_support TEXT,  -- "DirectX Raytracing (DXR)", "Vulkan RT"
    
    -- NVIDIA-specific
    cuda_compute_capability TEXT,  -- "8.9", "9.0" (versión de arquitectura CUDA)
    dlss_version TEXT,             -- "3.5", "3.7" (NULL si no soporta)
    nvenc_generation TEXT,         -- "8th Gen", "9th Gen"
    nvidia_reflex BOOLEAN DEFAULT 0,
    
    -- AMD-specific
    fsr_support BOOLEAN DEFAULT 0,  -- FidelityFX Super Resolution
    amd_fmf BOOLEAN DEFAULT 0,      -- Fluid Motion Frames
    amd_hypr_rx BOOLEAN DEFAULT 0,
    
    -- Intel-specific
    xess_support BOOLEAN DEFAULT 0,  -- Xe Super Sampling
    
    -- Multi-vendor standards
    av1_encode BOOLEAN DEFAULT 0,
    av1_decode BOOLEAN DEFAULT 0,
    resizable_bar BOOLEAN DEFAULT 0,
    
    FOREIGN KEY (chip_id) REFERENCES gpu_chip(chip_id) ON DELETE CASCADE
);