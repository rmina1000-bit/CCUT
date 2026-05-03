"""Static AI provider inventory for the CCUT AI Boundary.

This module is intentionally not imported by runtime code.
It is a non-runtime skeleton for future provider management.
"""

from .provider_descriptor import ProviderCategory, ProviderDescriptor


AI_PROVIDER_INVENTORY = [
    ProviderDescriptor(
        name="Qwen3ASR",
        module_path="ccut_backend.ai.adapters.qwen3_asr_adapter.Qwen3ASRAdapter",
        category=ProviderCategory.ACTIVE_PROVIDER,
        notes="ASR provider currently active through config.yaml.",
    ),
    ProviderDescriptor(
        name="Whisper",
        module_path="ccut_backend.ai.adapters.whisper_adapter.WhisperAdapter",
        category=ProviderCategory.FALLBACK_PROVIDER,
        notes="Fallback ASR provider candidate.",
    ),
    ProviderDescriptor(
        name="NarrativeRuleBased",
        module_path="ccut_frontend.src.hooks.useProposalState.buildConsultationReply",
        category=ProviderCategory.RULE_BASED_FALLBACK,
        notes="Frontend rule-based narrative consultation fallback.",
    ),
    ProviderDescriptor(
        name="VisionPlaceholder",
        module_path="ccut_backend.engine.vision_engine.VisionEngine",
        category=ProviderCategory.PLACEHOLDER,
        notes="Simulation placeholder for future vision provider work.",
    ),
    ProviderDescriptor(
        name="VectorPlaceholder",
        module_path="ccut_backend.engine.vector_engine.VectorEngine",
        category=ProviderCategory.PLACEHOLDER,
        notes="Simulation placeholder for future embedding provider work.",
    ),
    ProviderDescriptor(
        name="NarrativeLLMFuture",
        module_path="ccut_backend.ai.adapters.qwen3_llm_adapter.Qwen3LLMAdapter",
        category=ProviderCategory.FUTURE_PROVIDER,
        notes="Future local narrative LLM provider for StoryIntentPatch generation.",
    ),
]
