from dataclasses import dataclass
from typing import Optional

@dataclass
class HardwareProfile:
    """Represents a hardware tier for CCUT local AI capabilities."""
    tier_name: str
    gpu_vram_gb: float
    system_ram_gb: int
    storage_type: str  # NVMe, SSD, HDD
    recommended_vlm_bits: int  # e.g., 4, 6, 8
    recommended_llm_bits: int
    context_window: int
    notes: str

# Developer Machine (Verification Benchmark)
DEVELOPER_PROFILE = HardwareProfile(
    tier_name="Developer Machine",
    gpu_vram_gb=8.0,  # Example: typical dev GPU
    system_ram_gb=32,
    storage_type="NVMe",
    recommended_vlm_bits=4,
    recommended_llm_bits=4,
    context_window=4096,
    notes="Used for functional verification and debugging only. Not a product performance benchmark."
)

# High-End Creator Laptop (Product Target)
HIGH_END_LAPTOP_PROFILE = HardwareProfile(
    tier_name="High-End Creator Laptop",
    gpu_vram_gb=16.0,  # RTX 4090 Laptop
    system_ram_gb=64,
    storage_type="NVMe",
    recommended_vlm_bits=8,
    recommended_llm_bits=6,
    context_window=16384,
    notes="The target for premium paid users. Benchmark for product viability."
)

# Ultra-High-End Laptop (Next-Gen Target)
ULTRA_HIGH_END_LAPTOP_PROFILE = HardwareProfile(
    tier_name="Ultra-High-End Laptop",
    gpu_vram_gb=24.0,  # RTX 5090 Laptop candidate
    system_ram_gb=128,
    storage_type="NVMe Gen5",
    recommended_vlm_bits=16,
    recommended_llm_bits=8,
    context_window=32768,
    notes="Future-proofing for next-gen portable AI workstations."
)

# Minimum Supported Laptop
MINIMUM_SUPPORT_PROFILE = HardwareProfile(
    tier_name="Minimum Supported Laptop",
    gpu_vram_gb=6.0,  # Mid-range consumer GPU
    system_ram_gb=16,
    storage_type="SSD",
    recommended_vlm_bits=2,  # Extreme quantization or off
    recommended_llm_bits=3,
    context_window=2048,
    notes="Limited functionality mode. Heavy reliance on rule-based fallbacks."
)
