# Target Hardware Profile for Local AI

## 1. Overview
This document defines the hardware tiers targeted by CCUT 1.0.4. It separates the environment used for daily development from the high-end machines used to judge final product viability.

## 2. Hardware Tiers

| Tier | Target User | GPU (Recommended) | VRAM | RAM | Purpose |
|------|-------------|-------------------|------|-----|---------|
| **Developer Machine** | CCUT Development Team | Any CUDA-capable | 8GB+ | 32GB | Functional verification, logic debugging |
| **High-End Laptop** | Paid Creators / YouTubers | RTX 4090 Laptop | 16GB | 64GB | **Primary Product Benchmark** |
| **Ultra-High-End** | Next-Gen AI Workstation | RTX 5090 Laptop | 24GB | 128GB | Future-proofing & High-fidelity VLM |
| **Minimum Support** | Standard Consumer | RTX 4060/4070 | 6GB | 16GB | Lite mode / Rule-based fallbacks |

## 3. Benchmarking Policy
- **Speed measured on a Developer Machine is not a rejection criterion for a model.**
- Product feasibility is determined by whether the model runs at an acceptable speed on the **High-End Laptop Profile**.
- For users below the Minimum Support profile, the system will prioritize rule-based logic and static simulations over local LLM execution.

## 4. Local AI Requirements
- **Storage**: NVMe SSD is required for model loading speed.
- **Power**: High-performance AI mode is expected to run on AC power. Battery-only performance is a secondary optimization goal.
- **OS**: Windows 11 with latest NVIDIA drivers and CUDA support.
